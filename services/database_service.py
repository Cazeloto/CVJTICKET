from __future__ import annotations

import os
import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _pad3(n: int) -> str:
    return str(n).zfill(3)


def _fila_prefix(fila: str) -> str:
    fila = (fila or "").upper().strip()
    if fila not in ("N", "P", "E", "A"):
        raise ValueError("fila inválida, use 'N', 'P', 'E' ou 'A'")
    return fila


def _senha_texto(fila: str, seq: int) -> str:
    # Sem categoria -> senha por fila
    return f"{fila}-{_pad3(seq)}"


@dataclass
class PgConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str


class DatabaseService:
    """
    PostgreSQL (psycopg3)

    Ajustes:
    - Sequência por (workday_id + fila) ignorando categoria
    - move_ticket(ticket_id, new_fila, origin_device) garantido
    """

    def __init__(self, config: Optional[PgConfig] = None):
        self.config = config or PgConfig(
            host=_env("PG_HOST", "127.0.0.1"),
            port=int(_env("PG_PORT", "5432")),
            dbname=_env("PG_DB", "cvj_filas"),
            user=_env("PG_USER", "postgres"),
            password=_env("PG_PASS", ""),
        )

    def _connect(self) -> psycopg.Connection:
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

    # -------------------------
    # Workday
    # -------------------------
    def get_or_create_workday(
        self,
        work_date: date,
        title: str | None = None,
        created_by: str | None = None,
    ) -> Dict[str, Any]:
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
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, work_date, title, opened_at, closed_at, is_closed, created_by
                    from workday
                    where work_date=%s
                    """,
                    (work_date,),
                )
                return cur.fetchone()

    # -------------------------
    # Sequência por fila (segura)
    # -------------------------
    def _fila_lock_key(self, workday_id: int, fila: str) -> int:
        map_f = {"N": 1, "P": 2, "E": 3, "A": 4}
        return workday_id * 10 + map_f.get(fila, 9)

    def _next_seq_by_fila(self, cur: psycopg.Cursor, workday_id: int, fila: str) -> int:
        lock_key = self._fila_lock_key(workday_id, fila)
        # trava por transação -> multi-terminal seguro
        cur.execute("select pg_advisory_xact_lock(%s)", (lock_key,))
        cur.execute(
            """
            select coalesce(max(seq), 0) + 1 as next_seq
            from ticket
            where workday_id=%s and fila=%s
            """,
            (workday_id, fila),
        )
        row = cur.fetchone()
        return int(row["next_seq"])

    # -------------------------
    # Ticket CRUD
    # -------------------------

    def _parse_notes_dict(self, notes: Any) -> Dict[str, Any]:
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
        ticket = dict(ticket)
        notes_dict = self._parse_notes_dict(ticket.get("notes"))
        try:
            acompanhantes = int(notes_dict.get("acompanhantes", 0) or 0)
        except Exception:
            acompanhantes = 0
        if acompanhantes not in (0, 1, 2):
            acompanhantes = 0
        ticket["acompanhantes"] = acompanhantes
        return ticket

    def create_ticket(
        self,
        work_date: date,
        nome: str,
        fila: str,
        categoria: str = "N",  # ainda existe no banco, mas não influencia a senha
        origin_device: str = "",
        offline_id: str = "",
        notes: Any = "",
        acompanhantes: int = 0,
    ) -> Dict[str, Any]:
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
        notes_json = Jsonb(notes_dict)

        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    wd = self.get_or_create_workday(work_date)
                    workday_id = int(wd["id"])

                    seq = self._next_seq_by_fila(cur, workday_id, fila)
                    senha = _senha_texto(fila, seq)

                    cur.execute(
                        """
                        insert into ticket (
                          workday_id, nome_livre, fila, categoria, seq, senha,
                          status, origin_device, offline_id, notes
                        )
                        values (%s, %s, %s, %s, %s, %s, 'W', %s, %s, %s)
                        returning
                          id, workday_id, nome_livre, fila, categoria, seq, senha, status,
                          called_at, confirmed_at, finished_at, notes,
                          origin_device, offline_id, created_at, updated_at
                        """,
                        (
                            workday_id,
                            nome,
                            fila,
                            categoria,
                            seq,
                            senha,
                            origin_device,
                            offline_id,
                            notes_json,
                        ),
                    )
                    ticket = cur.fetchone()

                    # evento (se a tabela existir no seu schema)
                    try:
                        cur.execute(
                            """
                            insert into ticket_event (workday_id, ticket_id, event_type, payload, origin_device)
                            values (%s, %s, 'CREATED', %s, %s)
                            """,
                            (
                                workday_id,
                                ticket["id"],
                                Jsonb({"fila": fila, "senha": senha, "nome": nome}),
                                origin_device,
                            ),
                        )
                    except Exception:
                        # se não existir ticket_event, não quebra o sistema
                        pass

                conn.commit()
                return self._ticket_with_acompanhantes(ticket)
            except Exception:
                conn.rollback()
                raise

    def list_tickets(self, work_date: date) -> List[Dict[str, Any]]:
        wd = self.get_workday_by_date(work_date)
        if not wd:
            return []
        workday_id = int(wd["id"])

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                      id, workday_id, nome_livre, fila, categoria, seq, senha, status,
                      called_at, confirmed_at, finished_at, notes,
                      origin_device, offline_id, created_at, updated_at
                    from ticket
                    where workday_id = %s
                    order by
                      case fila when 'P' then 1 when 'N' then 2 when 'E' then 3 when 'A' then 4 else 9 end,
                      seq asc
                    """,
                    (workday_id,),
                )
                rows = cur.fetchall()
                return [self._ticket_with_acompanhantes(r) for r in rows]

    def call_ticket(self, ticket_id: int, origin_device: str = "") -> None:
        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select workday_id from ticket where id=%s", (ticket_id,)
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ValueError("ticket não encontrado")
                    workday_id = int(row["workday_id"])

                    cur.execute(
                        "update ticket set status='C', called_at=coalesce(called_at, now()) where id=%s",
                        (ticket_id,),
                    )

                    try:
                        cur.execute(
                            """
                            insert into ticket_event (workday_id, ticket_id, event_type, payload, origin_device)
                            values (%s, %s, 'CALLED', '{}'::jsonb, %s)
                            """,
                            (workday_id, ticket_id, origin_device),
                        )
                    except Exception:
                        pass

                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def confirm_ticket(self, ticket_id: int, origin_device: str = "") -> None:
        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select workday_id from ticket where id=%s", (ticket_id,)
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ValueError("ticket não encontrado")
                    workday_id = int(row["workday_id"])

                    cur.execute(
                        "update ticket set status='F', confirmed_at=coalesce(confirmed_at, now()) where id=%s",
                        (ticket_id,),
                    )

                    try:
                        cur.execute(
                            """
                            insert into ticket_event (workday_id, ticket_id, event_type, payload, origin_device)
                            values (%s, %s, 'CONFIRMED', '{}'::jsonb, %s)
                            """,
                            (workday_id, ticket_id, origin_device),
                        )
                    except Exception:
                        pass

                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def cancel_ticket(self, ticket_id: int, origin_device: str = "") -> None:
        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select workday_id from ticket where id=%s", (ticket_id,)
                    )
                    row = cur.fetchone()
                    if not row:
                        return
                    workday_id = int(row["workday_id"])

                    cur.execute(
                        "update ticket set status='X' where id=%s", (ticket_id,)
                    )

                    try:
                        cur.execute(
                            """
                            insert into ticket_event (workday_id, ticket_id, event_type, payload, origin_device)
                            values (%s, %s, 'CANCELED', '{}'::jsonb, %s)
                            """,
                            (workday_id, ticket_id, origin_device),
                        )
                    except Exception:
                        pass

                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ✅ ESTE É O PONTO QUE ESTAVA TE TRAVANDO:
    # assinatura + update garantidos
    def delete_ticket(self, ticket_id: int, origin_device: str = "") -> None:
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

                    try:
                        cur.execute(
                            """
                            insert into ticket_event (workday_id, ticket_id, event_type, payload, origin_device)
                            values (%s, %s, 'DELETED', %s, %s)
                            """,
                            (
                                workday_id,
                                ticket_id,
                                Jsonb(
                                    {
                                        "fila": row.get("fila"),
                                        "senha": row.get("senha"),
                                    }
                                ),
                                origin_device,
                            ),
                        )
                    except Exception:
                        pass

                    cur.execute("delete from ticket where id=%s", (ticket_id,))

                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def move_ticket(self, ticket_id: int, nova_fila: str, origin_device: str = ""):
        nova_fila = _fila_prefix(nova_fila)

        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    # trava o ticket
                    cur.execute(
                        """
                        SELECT id, workday_id, fila, categoria, seq, senha
                        FROM ticket
                        WHERE id = %s
                        FOR UPDATE
                        """,
                        (ticket_id,),
                    )

                    row = cur.fetchone()

                    if not row:
                        raise ValueError("Ticket não encontrado.")

                    workday_id = int(row["workday_id"])
                    fila_antiga = row["fila"]
                    senha_antiga = row["senha"]

                    # evita mover para mesma fila
                    if fila_antiga == nova_fila:
                        return

                    # calcula nova sequência segura
                    novo_seq = self._next_seq_by_fila(
                        cur,
                        workday_id,
                        nova_fila,
                    )

                    # gera nova senha
                    nova_senha = _senha_texto(nova_fila, novo_seq)

                    # atualiza ticket
                    cur.execute(
                        """
                        UPDATE ticket
                        SET fila = %s,
                            seq = %s,
                            senha = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            nova_fila,
                            novo_seq,
                            nova_senha,
                            ticket_id,
                        ),
                    )

                    # registra evento (se existir tabela)
                    try:
                        cur.execute(
                            """
                            INSERT INTO ticket_event
                                (
                                    workday_id,
                                    ticket_id,
                                    event_type,
                                    payload,
                                    origin_device
                                )
                            VALUES
                                (
                                    %s,
                                    %s,
                                    'MOVED',
                                    %s,
                                    %s
                                )
                            """,
                            (
                                workday_id,
                                ticket_id,
                                Jsonb(
                                    {
                                        "fila_antiga": fila_antiga,
                                        "nova_fila": nova_fila,
                                        "senha_antiga": senha_antiga,
                                        "nova_senha": nova_senha,
                                    }
                                ),
                                origin_device or "",
                            ),
                        )
                    except Exception:
                        pass

                conn.commit()

            except Exception:
                conn.rollback()
                raise

    def reset_workday(
        self, work_date: date, hard_delete: bool = False, origin_device: str = ""
    ) -> int:
        wd = self.get_workday_by_date(work_date)
        if not wd:
            return 0
        workday_id = int(wd["id"])

        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    if hard_delete:
                        cur.execute(
                            "delete from ticket where workday_id=%s", (workday_id,)
                        )
                        affected = cur.rowcount
                    else:
                        cur.execute(
                            "update ticket set status='X' where workday_id=%s and status <> 'X'",
                            (workday_id,),
                        )
                        affected = cur.rowcount

                    try:
                        cur.execute(
                            """
                            insert into ticket_event (workday_id, ticket_id, event_type, payload, origin_device)
                            values (%s, null, %s, %s, %s)
                            """,
                            (
                                workday_id,
                                "RESET_DAY_HARD" if hard_delete else "RESET_DAY",
                                Jsonb({"affected": affected}),
                                origin_device,
                            ),
                        )
                    except Exception:
                        pass

                conn.commit()
                return affected
            except Exception:
                conn.rollback()
                raise
