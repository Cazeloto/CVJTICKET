"""Serviço de acesso ao banco de dados PostgreSQL (psycopg3).

Responsabilidades:
- Gerenciar a conexão com o banco via PgConfig (lida de variáveis de ambiente).
- Garantir na inicialização que tabelas e índices de performance existam.
- Fornecer todas as operações de leitura/escrita de tickets, workdays e consulentes.

Sequências de senha são geradas com pg_advisory_xact_lock para segurança
multi-terminal, sem depender de sequences do Postgres.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

load_dotenv()

LOG = logging.getLogger("CVJFILAS")

# ---------------------------------------------------------------------------
# Helpers de módulo
# ---------------------------------------------------------------------------

def _env(name: str, default: str = "") -> str:
    """Lê variável de ambiente; retorna *default* se ausente ou vazia."""
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _pad3(n: int) -> str:
    """Formata inteiro com zero-padding de 3 dígitos (ex.: 7 → '007')."""
    return str(n).zfill(3)


def _fila_prefix(fila: str) -> str:
    """Valida e normaliza o código de fila para maiúscula.

    Raises:
        ValueError: se o código não for N, P, E ou A.
    """
    fila = (fila or "").upper().strip()
    if fila not in ("N", "P", "E", "A"):
        raise ValueError("fila inválida, use 'N', 'P', 'E' ou 'A'")
    return fila


def _senha_texto(fila: str, seq: int) -> str:
    """Gera o texto da senha (ex.: fila='N', seq=7 → 'N-007')."""
    return f"{fila}-{_pad3(seq)}"


# ---------------------------------------------------------------------------
# Configuração de conexão
# ---------------------------------------------------------------------------

@dataclass
class PgConfig:
    """Parâmetros de conexão PostgreSQL, lidos de variáveis de ambiente."""
    host: str
    port: int
    dbname: str
    user: str
    password: str


# ---------------------------------------------------------------------------
# Serviço principal
# ---------------------------------------------------------------------------

class DatabaseService:
    """Camada de acesso a dados para o sistema de filas CVJTICKET.

    Todas as operações de escrita são transacionais: fazem commit em caso de
    sucesso e rollback em caso de erro, relançando a exceção original.
    """

    def __init__(self, config: Optional[PgConfig] = None) -> None:
        self.config = config or PgConfig(
            host=_env("PG_HOST", "127.0.0.1"),
            port=int(_env("PG_PORT", "5432")),
            dbname=_env("PG_DB", "cvj_filas"),
            user=_env("PG_USER", "postgres"),
            password=_env("PG_PASS", ""),
        )
        self._ensure_runtime_performance_objects()

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------

    def _connect(self) -> psycopg.Connection:
        """Abre e retorna uma nova conexão com autocommit desabilitado."""
        conn = psycopg.connect(
            host=self.config.host,
            port=self.config.port,
            dbname=self.config.dbname,
            user=self.config.user,
            password=self.config.password,
            row_factory=dict_row,
        )
        conn.autocommit = False
        return conn

    # ------------------------------------------------------------------
    # Bootstrap de performance
    # ------------------------------------------------------------------

    def _ensure_runtime_performance_objects(self) -> None:
        """Cria/atualiza tabelas e índices auxiliares na primeira execução.

        Roda silenciosamente: falhas são logadas mas não impedem a inicialização,
        pois o banco pode ainda não ter sido provisionado completamente.
        """
        statements = [
            # Tabela de contadores por (workday, fila, categoria)
            """
            create table if not exists ticket_counter (
              workday_id  bigint not null references workday(id) on delete cascade,
              fila        char(1) not null check (fila in ('N','P','E','A')),
              categoria   char(1) not null check (categoria in ('N','R')),
              last_seq    integer not null default 0,
              primary key (workday_id, fila, categoria)
            )
            """,
            # Garante que o check de ticket_counter inclua 'A'
            """
            do $$
            begin
              if exists (
                select 1 from pg_constraint
                where conrelid = 'ticket_counter'::regclass
                  and conname = 'ticket_counter_fila_check'
                  and position(quote_literal('A') in pg_get_constraintdef(oid)) = 0
              ) then
                alter table ticket_counter drop constraint ticket_counter_fila_check;
                alter table ticket_counter
                  add constraint ticket_counter_fila_check
                  check (fila in ('N','P','E','A'));
              end if;
            end $$
            """,
            # Garante que o check de ticket inclua 'A'
            """
            do $$
            begin
              if exists (
                select 1 from pg_constraint
                where conrelid = 'ticket'::regclass
                  and conname = 'ticket_fila_check'
                  and position(quote_literal('A') in pg_get_constraintdef(oid)) = 0
              ) then
                alter table ticket drop constraint ticket_fila_check;
                alter table ticket
                  add constraint ticket_fila_check
                  check (fila in ('N','P','E','A'));
              end if;
            end $$
            """,
            "create index if not exists idx_ticket_day_fila_seq on ticket(workday_id, fila, seq)",
            "create extension if not exists pg_trgm",
            "create index if not exists idx_consulente_nome_trgm on consulente using gin (lower(nome) gin_trgm_ops)",
        ]
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    for stmt in statements:
                        cur.execute(stmt)
                conn.commit()
        except Exception:
            LOG.exception("Não foi possível garantir otimizações do banco")

    # ------------------------------------------------------------------
    # Workday
    # ------------------------------------------------------------------

    def get_or_create_workday(
        self,
        work_date: date,
        title: str | None = None,
        created_by: str | None = None,
    ) -> Dict[str, Any]:
        """Retorna o workday do dia, criando-o caso não exista."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into workday (work_date, title, created_by)
                    values (%s, %s, %s)
                    on conflict (work_date) do update set
                      title = coalesce(excluded.title, workday.title)
                    returning id, work_date, title, opened_at, closed_at, is_closed, created_by
                    """,
                    (work_date, title, created_by),
                )
                row = cur.fetchone()
                conn.commit()
                return row

    def get_workday_by_date(self, work_date: date) -> Optional[Dict[str, Any]]:
        """Retorna o workday de uma data específica, ou None se não existir."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, work_date, title, opened_at, closed_at, is_closed, created_by
                    from workday where work_date = %s
                    """,
                    (work_date,),
                )
                return cur.fetchone()

    # ------------------------------------------------------------------
    # Sequência por fila (segura para multi-terminal)
    # ------------------------------------------------------------------

    def _fila_lock_key(self, workday_id: int, fila: str) -> int:
        """Gera chave inteira para pg_advisory_xact_lock por (workday, fila)."""
        return workday_id * 10 + {"N": 1, "P": 2, "E": 3, "A": 4}.get(fila, 9)

    def _next_seq_by_fila(
        self,
        cur: psycopg.Cursor,
        workday_id: int,
        fila: str,
        categoria: str = "N",
    ) -> int:
        """Obtém o próximo número de sequência para a fila, usando lock por transação."""
        categoria = (categoria or "N").upper().strip()
        if categoria not in ("N", "R"):
            categoria = "N"
        cur.execute("select pg_advisory_xact_lock(%s)", (self._fila_lock_key(workday_id, fila),))
        cur.execute(
            """
            insert into ticket_counter (workday_id, fila, categoria, last_seq)
            select %s, %s, %s, coalesce(max(seq), 0) + 1
            from ticket
            where workday_id=%s and fila=%s and categoria=%s
            on conflict (workday_id, fila, categoria) do update set
              last_seq = ticket_counter.last_seq + 1
            returning last_seq
            """,
            (workday_id, fila, categoria, workday_id, fila, categoria),
        )
        return int(cur.fetchone()["last_seq"])

    # ------------------------------------------------------------------
    # Helpers internos de ticket
    # ------------------------------------------------------------------

    def _parse_notes_dict(self, notes: Any) -> Dict[str, Any]:
        """Converte o campo notes (JSON ou string) para dict Python."""
        if notes is None:
            return {}
        if isinstance(notes, dict):
            return dict(notes)
        if isinstance(notes, str):
            s = notes.strip()
            if not s:
                return {}
            try:
                obj = json.loads(s)
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
        return {}

    def _ticket_with_acompanhantes(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Adiciona o campo 'acompanhantes' (int) ao dict do ticket, lido do JSON de notes."""
        ticket = dict(ticket)
        notes_dict = self._parse_notes_dict(ticket.get("notes"))
        try:
            acompanhantes = int(notes_dict.get("acompanhantes", 0) or 0)
        except Exception:
            acompanhantes = 0
        ticket["acompanhantes"] = acompanhantes if acompanhantes in (0, 1, 2) else 0
        return ticket

    def _fetch_ticket_by_id(
        self, cur: psycopg.Cursor, ticket_id: int
    ) -> Dict[str, Any] | None:
        """Busca um ticket pelo ID dentro de uma transação aberta."""
        cur.execute(
            """
            select
              id, workday_id, consulente_id, nome_livre, fila, categoria,
              seq, senha, status, called_at, confirmed_at, finished_at,
              notes, origin_device, offline_id, created_at, updated_at
            from ticket where id = %s
            """,
            (ticket_id,),
        )
        row = cur.fetchone()
        return self._ticket_with_acompanhantes(row) if row else None

    def _log_event(
        self,
        cur: psycopg.Cursor,
        workday_id: int,
        ticket_id: int | None,
        event_type: str,
        payload: dict,
        origin_device: str,
    ) -> None:
        """Insere um evento de auditoria em ticket_event.

        Falhas são silenciadas para não bloquear a operação principal caso
        a tabela ticket_event não exista no schema.
        """
        try:
            cur.execute(
                """
                insert into ticket_event
                    (workday_id, ticket_id, event_type, payload, origin_device)
                values (%s, %s, %s, %s, %s)
                """,
                (workday_id, ticket_id, event_type, Jsonb(payload), origin_device),
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Consulentes
    # ------------------------------------------------------------------

    def search_consulentes(self, termo: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Busca consulentes por nome (LIKE), ordenando por prefixo exato primeiro."""
        termo = (termo or "").strip()
        if len(termo) < 2:
            return []
        limit = max(1, min(int(limit or 8), 20))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, nome, documento, telefone, created_at
                    from consulente
                    where lower(nome) like lower(%s)
                    order by
                      case when lower(nome) like lower(%s) then 0 else 1 end,
                      nome asc
                    limit %s
                    """,
                    (f"%{termo}%", f"{termo}%", limit),
                )
                return cur.fetchall()

    def _get_or_create_consulente(
        self, cur: psycopg.Cursor, nome: str
    ) -> Dict[str, Any]:
        """Busca um consulente pelo nome normalizado, criando-o se não existir."""
        nome_key = " ".join(nome.split()).lower()
        cur.execute("select pg_advisory_xact_lock(hashtext(%s))", (nome_key,))
        cur.execute(
            """
            select id, nome, documento, telefone, created_at
            from consulente
            where lower(regexp_replace(trim(nome), '\\s+', ' ', 'g')) = %s
            order by id asc limit 1
            """,
            (nome_key,),
        )
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            "insert into consulente (nome) values (%s) returning id, nome, documento, telefone, created_at",
            (nome,),
        )
        return cur.fetchone()

    # ------------------------------------------------------------------
    # Tickets — CRUD
    # ------------------------------------------------------------------

    def create_ticket(
        self,
        work_date: date,
        nome: str,
        fila: str,
        categoria: str = "N",
        origin_device: str = "",
        offline_id: str = "",
        notes: Any = "",
        acompanhantes: int = 0,
    ) -> Dict[str, Any]:
        """Cria um novo ticket na fila indicada para a data de trabalho.

        Args:
            work_date: Data da gira (cria workday se necessário).
            nome: Nome do consulente (obrigatório, será salvo em nome_livre).
            fila: Código da fila — N, P, E ou A.
            categoria: N (normal) ou R (prioritário); não altera a senha.
            origin_device: Identificador do terminal que criou o ticket.
            offline_id: ID local para reconciliação offline (opcional).
            notes: Dados extras em JSON/dict (acompanhantes é lido daqui).
            acompanhantes: Número de acompanhantes (0, 1 ou 2).

        Returns:
            Dict com todos os campos do ticket, incluindo 'acompanhantes'.

        Raises:
            ValueError: se nome estiver vazio ou fila inválida.
        """
        fila = _fila_prefix(fila)
        nome = (nome or "").strip()
        if not nome:
            raise ValueError("Nome do consulente é obrigatório.")

        categoria = (categoria or "N").upper().strip()
        if categoria not in ("N", "R"):
            categoria = "N"

        try:
            acompanhantes = int(acompanhantes or 0)
        except Exception:
            acompanhantes = 0
        if acompanhantes not in (0, 1, 2):
            acompanhantes = 0

        notes_dict = self._parse_notes_dict(notes)
        notes_dict["acompanhantes"] = acompanhantes

        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    wd = self.get_or_create_workday(work_date)
                    workday_id = int(wd["id"])
                    consulente = self._get_or_create_consulente(cur, nome)
                    seq = self._next_seq_by_fila(cur, workday_id, fila, categoria)
                    senha = _senha_texto(fila, seq)

                    cur.execute(
                        """
                        insert into ticket (
                          workday_id, consulente_id, nome_livre, fila, categoria,
                          seq, senha, status, origin_device, offline_id, notes
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, 'W', %s, %s, %s)
                        returning
                          id, workday_id, consulente_id, nome_livre, fila, categoria,
                          seq, senha, status, called_at, confirmed_at, finished_at,
                          notes, origin_device, offline_id, created_at, updated_at
                        """,
                        (
                            workday_id, consulente["id"], nome, fila, categoria,
                            seq, senha, origin_device, offline_id, Jsonb(notes_dict),
                        ),
                    )
                    ticket = cur.fetchone()
                    self._log_event(cur, workday_id, ticket["id"], "CREATED",
                                    {"fila": fila, "senha": senha, "nome": nome},
                                    origin_device)
                conn.commit()
                return self._ticket_with_acompanhantes(ticket)
            except Exception:
                conn.rollback()
                raise

    def list_tickets(self, work_date: date) -> List[Dict[str, Any]]:
        """Retorna todos os tickets do dia, ordenados por fila (P→N→E→A) e sequência."""
        wd = self.get_workday_by_date(work_date)
        if not wd:
            return []
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                      id, workday_id, consulente_id, nome_livre, fila, categoria,
                      seq, senha, status, called_at, confirmed_at, finished_at,
                      notes, origin_device, offline_id, created_at, updated_at
                    from ticket
                    where workday_id = %s
                    order by
                      case fila when 'P' then 1 when 'N' then 2 when 'E' then 3 when 'A' then 4 else 9 end,
                      seq asc
                    """,
                    (int(wd["id"]),),
                )
                return [self._ticket_with_acompanhantes(r) for r in cur.fetchall()]

    def call_ticket(self, ticket_id: int, origin_device: str = "") -> Dict[str, Any]:
        """Marca o ticket como 'Chamado' (status C) e registra called_at."""
        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("select workday_id from ticket where id=%s", (ticket_id,))
                    row = cur.fetchone()
                    if not row:
                        raise ValueError("Ticket não encontrado.")
                    workday_id = int(row["workday_id"])

                    cur.execute(
                        "update ticket set status='C', called_at=now(), updated_at=now() where id=%s",
                        (ticket_id,),
                    )
                    ticket = self._fetch_ticket_by_id(cur, ticket_id)
                    self._log_event(cur, workday_id, ticket_id, "CALLED", {}, origin_device)
                conn.commit()
                return ticket
            except Exception:
                conn.rollback()
                raise

    def confirm_ticket(self, ticket_id: int, origin_device: str = "") -> Dict[str, Any]:
        """Marca o ticket como 'Concluído' (status F) e registra confirmed_at."""
        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("select workday_id from ticket where id=%s", (ticket_id,))
                    row = cur.fetchone()
                    if not row:
                        raise ValueError("Ticket não encontrado.")
                    workday_id = int(row["workday_id"])

                    cur.execute(
                        """
                        update ticket
                        set status='F',
                            confirmed_at=coalesce(confirmed_at, now()),
                            updated_at=now()
                        where id=%s
                        """,
                        (ticket_id,),
                    )
                    ticket = self._fetch_ticket_by_id(cur, ticket_id)
                    self._log_event(cur, workday_id, ticket_id, "CONFIRMED", {}, origin_device)
                conn.commit()
                return ticket
            except Exception:
                conn.rollback()
                raise

    def cancel_ticket(
        self, ticket_id: int, origin_device: str = ""
    ) -> Dict[str, Any] | None:
        """Marca o ticket como 'Cancelado' (status X). Retorna None se não encontrado."""
        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("select workday_id from ticket where id=%s", (ticket_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    workday_id = int(row["workday_id"])

                    cur.execute(
                        "update ticket set status='X', updated_at=now() where id=%s",
                        (ticket_id,),
                    )
                    ticket = self._fetch_ticket_by_id(cur, ticket_id)
                    self._log_event(cur, workday_id, ticket_id, "CANCELED", {}, origin_device)
                conn.commit()
                return ticket
            except Exception:
                conn.rollback()
                raise

    def delete_ticket(self, ticket_id: int, origin_device: str = "") -> None:
        """Remove fisicamente o ticket do banco (usado para fila A e zerar dia)."""
        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select workday_id, fila, senha from ticket where id=%s",
                        (ticket_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return
                    workday_id = int(row["workday_id"])
                    self._log_event(cur, workday_id, ticket_id, "DELETED",
                                    {"fila": row["fila"], "senha": row["senha"]},
                                    origin_device)
                    cur.execute("delete from ticket where id=%s", (ticket_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def move_ticket(
        self, ticket_id: int, nova_fila: str, origin_device: str = ""
    ) -> Dict[str, Any] | None:
        """Move um ticket para outra fila, gerando nova sequência e nova senha.

        Se o ticket já estiver na fila destino, retorna-o sem alteração.
        """
        nova_fila = _fila_prefix(nova_fila)
        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select id, workday_id, fila, categoria, seq, senha from ticket where id=%s for update",
                        (ticket_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ValueError("Ticket não encontrado.")

                    workday_id = int(row["workday_id"])
                    fila_antiga = row["fila"]

                    if fila_antiga == nova_fila:
                        return self._fetch_ticket_by_id(cur, ticket_id)

                    novo_seq = self._next_seq_by_fila(
                        cur, workday_id, nova_fila, row.get("categoria") or "N"
                    )
                    nova_senha = _senha_texto(nova_fila, novo_seq)

                    cur.execute(
                        "update ticket set fila=%s, seq=%s, senha=%s, updated_at=now() where id=%s",
                        (nova_fila, novo_seq, nova_senha, ticket_id),
                    )
                    ticket = self._fetch_ticket_by_id(cur, ticket_id)
                    self._log_event(cur, workday_id, ticket_id, "MOVED",
                                    {"fila_antiga": fila_antiga, "nova_fila": nova_fila,
                                     "senha_antiga": row["senha"], "nova_senha": nova_senha},
                                    origin_device)
                conn.commit()
                return ticket
            except Exception:
                conn.rollback()
                raise

    def reset_workday(
        self, work_date: date, hard_delete: bool = False, origin_device: str = ""
    ) -> int:
        """Zera todos os tickets do dia.

        Args:
            work_date: Data cujos tickets serão zerados.
            hard_delete: Se True, apaga fisicamente os tickets e contadores.
                         Se False, apenas marca todos como cancelados (X).
            origin_device: Terminal que solicitou o reset.

        Returns:
            Número de tickets afetados.
        """
        wd = self.get_workday_by_date(work_date)
        if not wd:
            return 0
        workday_id = int(wd["id"])

        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    if hard_delete:
                        cur.execute("delete from ticket where workday_id=%s", (workday_id,))
                        affected = cur.rowcount
                        cur.execute("delete from ticket_counter where workday_id=%s", (workday_id,))
                    else:
                        cur.execute(
                            "update ticket set status='X' where workday_id=%s and status <> 'X'",
                            (workday_id,),
                        )
                        affected = cur.rowcount

                    event_type = "RESET_DAY_HARD" if hard_delete else "RESET_DAY"
                    self._log_event(cur, workday_id, None, event_type,
                                    {"affected": affected}, origin_device)
                conn.commit()
                return affected
            except Exception:
                conn.rollback()
                raise
