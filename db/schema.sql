-- 1) Sessão do dia (a "gira")
create table if not exists workday (
  id              bigserial primary key,
  work_date       date not null unique,
  title           text,
  opened_at       timestamptz not null default now(),
  closed_at       timestamptz,
  is_closed       boolean not null default false,
  created_by      text
);

-- 2) Consulente (cadastro básico; opcional)
create table if not exists consulente (
  id              bigserial primary key,
  nome            text not null,
  documento       text,          -- cpf/rg etc (opcional)
  telefone        text,          -- opcional
  created_at      timestamptz not null default now()
);

-- enums "simulados" via check (compatível com PG 10)
-- fila: N=Normal, P=Preferencial, E=Espera, A=Não apareceu
-- categoria: N=Normal, R=Prioritário
-- status: W=Waiting, C=Called, F=Confirmed, X=Canceled, D=Done
create table if not exists ticket (
  id                bigserial primary key,
  workday_id        bigint not null references workday(id) on delete cascade,

  consulente_id     bigint references consulente(id),
  nome_livre        text,  -- se quiser cadastrar sem criar consulente

  fila              char(1) not null check (fila in ('N','P','E','A')),
  categoria         char(1) not null check (categoria in ('N','R')),

  seq               integer not null,               -- número sequencial do dia (por fila/categoria)
  senha             text not null,                  -- ex: N-023, P-004, E-015, R-010 etc

  status            char(1) not null check (status in ('W','C','F','X','D')) default 'W',
  called_at         timestamptz,
  confirmed_at      timestamptz,
  finished_at       timestamptz,

  notes             text,

  -- contingência / rastreio de origem
  origin_device     text,     -- hostname/uuid do terminal
  offline_id        text,     -- id local quando criado offline (uuid/seq)
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  -- impede duplicar seq por fila/categoria no mesmo dia:
  unique (workday_id, fila, categoria, seq),
  -- impede duplicar "senha" no mesmo dia:
  unique (workday_id, senha)
);

create index if not exists idx_ticket_day_queue_status on ticket(workday_id, fila, status);
create index if not exists idx_ticket_day_created_at on ticket(workday_id, created_at);

-- 3) Eventos (auditoria / sincronização / diagnóstico)
create table if not exists ticket_event (
  id            bigserial primary key,
  workday_id    bigint not null references workday(id) on delete cascade,
  ticket_id     bigint references ticket(id) on delete set null,

  event_type    text not null,  -- CREATED, MOVED, CALLED, CONFIRMED, DELETED, RESET_DAY, etc.
  payload       jsonb not null default '{}'::jsonb,

  origin_device text,
  created_at    timestamptz not null default now()
);

create index if not exists idx_event_day_created on ticket_event(workday_id, created_at);

-- 4) Controle de sequência por dia/fila/categoria (gera senha sem conflito)
create table if not exists ticket_counter (
  workday_id  bigint not null references workday(id) on delete cascade,
  fila        char(1) not null check (fila in ('N','P','E','A')),
  categoria   char(1) not null check (categoria in ('N','R')),
  last_seq    integer not null default 0,
  primary key (workday_id, fila, categoria)
);

-- trigger simples pra updated_at
create or replace function trg_set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_ticket_updated on ticket;
create trigger trg_ticket_updated
before update on ticket
for each row execute procedure trg_set_updated_at();
