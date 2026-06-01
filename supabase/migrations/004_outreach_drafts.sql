-- 004_outreach_drafts.sql
-- Phase 2 table only — created now so the schema is complete; there is NO API
-- for it in v1 (AI drafts, humans decide; one-at-a-time approval, no batch send).
-- Idempotent.

create table if not exists outreach_drafts (
    id                 uuid primary key default gen_random_uuid(),
    project_id         uuid references projects(id) on delete cascade,
    contact_id         uuid references contacts(id) on delete cascade,
    subject            text,
    body               text,
    generated_by_model text,
    status             text not null default 'draft',   -- draft, approved, rejected, sent, bounced, replied
    approved_by        text,
    approved_at        timestamptz,
    sent_at            timestamptz,
    esp_message_id     text,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'outreach_drafts_status_check') then
        alter table outreach_drafts add constraint outreach_drafts_status_check
            check (status in ('draft','approved','rejected','sent','bounced','replied'));
    end if;
end $$;

create index if not exists outreach_drafts_project_id_idx on outreach_drafts (project_id);
create index if not exists outreach_drafts_contact_id_idx on outreach_drafts (contact_id);
create index if not exists outreach_drafts_status_idx     on outreach_drafts (status);
