-- 003_runs_digest_subscribers.sql
-- Observability + delivery tables, created in order:
--   pipeline_runs -> email_subscribers -> daily_digest
-- (daily_digest FKs pipeline_runs). Idempotent.

-- ─── pipeline_runs (observability + run mutex) ───────────────────────────
create table if not exists pipeline_runs (
    id                uuid primary key default gen_random_uuid(),
    started_at        timestamptz not null default now(),
    finished_at       timestamptz,
    status            text not null default 'running',     -- running, success, partial, failed
    trigger           text not null default 'scheduled',   -- scheduled, manual
    sources_fetched   int not null default 0,
    signals_ingested  int not null default 0,
    projects_created  int not null default 0,
    projects_updated  int not null default 0,
    errors            jsonb not null default '[]'::jsonb
);

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'pipeline_runs_status_check') then
        alter table pipeline_runs add constraint pipeline_runs_status_check
            check (status in ('running','success','partial','failed'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'pipeline_runs_trigger_check') then
        alter table pipeline_runs add constraint pipeline_runs_trigger_check
            check (trigger in ('scheduled','manual'));
    end if;
end $$;

create index if not exists pipeline_runs_started_at_idx on pipeline_runs (started_at desc);
-- Partial unique index enforces the single-running-run mutex.
create unique index if not exists pipeline_runs_one_running_idx
    on pipeline_runs ((status)) where status = 'running';

-- ─── email_subscribers ───────────────────────────────────────────────────
create table if not exists email_subscribers (
    id                uuid primary key default gen_random_uuid(),
    email             text not null unique,
    full_name         text,
    subscribed        boolean not null default true,
    unsubscribe_token uuid not null default gen_random_uuid(),
    filters           jsonb not null default '{}'::jsonb,
    created_at        timestamptz not null default now(),
    unsubscribed_at   timestamptz
);

create index if not exists email_subscribers_token_idx on email_subscribers (unsubscribe_token);

-- ─── daily_digest ─────────────────────────────────────────────────────────
create table if not exists daily_digest (
    id              uuid primary key default gen_random_uuid(),
    digest_date     date not null unique,
    project_ids     uuid[] not null default '{}',
    new_count       int not null default 0,
    updated_count   int not null default 0,
    html_body       text,
    text_body       text,
    pipeline_run_id uuid references pipeline_runs(id),
    created_at      timestamptz not null default now()
);

create index if not exists daily_digest_date_idx on daily_digest (digest_date desc);
