-- ============================================================================
-- Treadwell AI News Feed — FULL SCHEMA (generated: migrations 001-005 concatenated)
-- Paste this whole file into the Supabase SQL Editor of a NEW project, then Run.
-- Idempotent + safe to re-run. Source of truth = supabase/migrations/*.sql
-- ============================================================================

-- ===================== 001_extensions.sql =====================

-- 001_extensions.sql
-- Postgres extensions for the Treadwell AI News Feed.
-- pgcrypto -> gen_random_uuid(); cube + earthdistance -> great-circle math in SQL.
-- All idempotent.

create extension if not exists pgcrypto;
create extension if not exists cube;
create extension if not exists earthdistance;

-- ===================== 002_core.sql =====================

-- 002_core.sql
-- Core domain tables, created in FK order:
--   sources -> companies -> projects -> signals -> project_team -> contacts
-- Idempotent: `create table if not exists`, constraints/indexes guarded with
-- `do $$ ... if not exists` or `create index if not exists`.

-- ─── sources ─────────────────────────────────────────────────────────────
create table if not exists sources (
    id              uuid primary key default gen_random_uuid(),
    name            text not null,
    source_type     text not null,                         -- news, press_release, permit, utility_filing, econ_dev_minutes, planning_filing, other
    url             text not null,
    fetch_method    text not null,                         -- rss, html, pdf, api, playwright
    parser_key      text not null,                         -- dispatch key into the parser registry
    region_scope    text,
    tier            int not null default 1,
    enabled         boolean not null default true,
    fetch_cadence   text not null default 'daily',
    last_fetched_at timestamptz,
    last_status     text,
    last_error      text,
    created_at      timestamptz not null default now()
);

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'sources_source_type_check') then
        alter table sources add constraint sources_source_type_check
            check (source_type in ('news','press_release','permit','utility_filing','econ_dev_minutes','planning_filing','other'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'sources_fetch_method_check') then
        alter table sources add constraint sources_fetch_method_check
            check (fetch_method in ('rss','html','pdf','api','playwright'));
    end if;
end $$;

-- ─── companies ───────────────────────────────────────────────────────────
create table if not exists companies (
    id              uuid primary key default gen_random_uuid(),
    name            text not null,
    normalized_name text,                                  -- lowercased, legal-suffix-stripped (set in code)
    company_type    text not null default 'unknown',       -- general_contractor, developer, owner, end_user, architect, engineer, construction_manager, utility, subcontractor, unknown
    domain          text,
    website         text,
    hq_city         text,
    hq_state        text,
    is_hyperscaler  boolean not null default false,
    notes           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'companies_company_type_check') then
        alter table companies add constraint companies_company_type_check
            check (company_type in ('general_contractor','developer','owner','end_user','architect','engineer','construction_manager','utility','subcontractor','unknown'));
    end if;
end $$;

create index if not exists companies_normalized_name_idx on companies (normalized_name);

-- ─── projects (the central deduplicated opportunity) ─────────────────────
create table if not exists projects (
    id                  uuid primary key default gen_random_uuid(),
    title               text not null,
    summary             text,
    project_type        text not null,                     -- data_center, industrial, healthcare, higher_ed, distribution, manufacturing, mission_critical, other_commercial
    stage               text,                              -- rumored, planning, design, permitting, procurement, pre_bid, under_construction, complete, dead
    address             text,
    city                text,
    state               text,
    county              text,
    latitude            double precision,
    longitude           double precision,
    distance_mi         double precision,
    in_radius           boolean,
    est_value_usd       numeric,
    est_sqft            numeric,
    est_megawatts       numeric,
    relevance_score     int,                               -- 0..100
    relevance_tier      text,                              -- hot, warm, cold
    relevance_reasoning jsonb,
    team_confidence     text not null default 'unknown',   -- gc_named, developer_named, owner_only, unknown
    status              text not null default 'new',       -- new, active, watching, pursuing, archived, dismissed
    dedup_key           text,                              -- normalized(title)|normalized(city)
    merged_into         uuid references projects(id),
    scored_by_model     text,
    first_seen_at       timestamptz not null default now(),
    last_signal_at      timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'projects_project_type_check') then
        alter table projects add constraint projects_project_type_check
            check (project_type in ('data_center','industrial','healthcare','higher_ed','distribution','manufacturing','mission_critical','other_commercial'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'projects_stage_check') then
        alter table projects add constraint projects_stage_check
            check (stage is null or stage in ('rumored','planning','design','permitting','procurement','pre_bid','under_construction','complete','dead'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'projects_relevance_tier_check') then
        alter table projects add constraint projects_relevance_tier_check
            check (relevance_tier is null or relevance_tier in ('hot','warm','cold'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'projects_relevance_score_check') then
        alter table projects add constraint projects_relevance_score_check
            check (relevance_score is null or (relevance_score >= 0 and relevance_score <= 100));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'projects_team_confidence_check') then
        alter table projects add constraint projects_team_confidence_check
            check (team_confidence in ('gc_named','developer_named','owner_only','unknown'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'projects_status_check') then
        alter table projects add constraint projects_status_check
            check (status in ('new','active','watching','pursuing','archived','dismissed'));
    end if;
end $$;

create index if not exists projects_radius_tier_idx   on projects (in_radius, relevance_tier);
create index if not exists projects_project_type_idx  on projects (project_type);
create index if not exists projects_stage_idx         on projects (stage);
create index if not exists projects_dedup_key_idx     on projects (dedup_key);
create index if not exists projects_last_signal_idx   on projects (last_signal_at desc);
create index if not exists projects_status_idx        on projects (status);

-- ─── signals (evidence — the demoted "article") ──────────────────────────
create table if not exists signals (
    id                    uuid primary key default gen_random_uuid(),
    project_id            uuid references projects(id) on delete set null,   -- null until clustered
    signal_type           text not null,                                     -- same vocab as sources.source_type
    source_id             uuid references sources(id) on delete set null,
    url                   text,
    title                 text,
    published_at          timestamptz,
    fetched_at            timestamptz not null default now(),
    raw_text              text,
    content_hash          text not null unique,                              -- sha256(normalized url + '|' + title)
    extracted             jsonb,
    extraction_confidence double precision,
    created_at            timestamptz not null default now()
);

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'signals_signal_type_check') then
        alter table signals add constraint signals_signal_type_check
            check (signal_type in ('news','press_release','permit','utility_filing','econ_dev_minutes','planning_filing','other'));
    end if;
end $$;

create index if not exists signals_project_id_idx    on signals (project_id);
create index if not exists signals_signal_type_idx   on signals (signal_type);
create index if not exists signals_published_at_idx  on signals (published_at desc);

-- ─── project_team (GC > Dev > Owner hierarchy as link rows) ──────────────
create table if not exists project_team (
    id                uuid primary key default gen_random_uuid(),
    project_id        uuid not null references projects(id) on delete cascade,
    company_id        uuid not null references companies(id) on delete cascade,
    role              text not null,                       -- general_contractor, developer, owner, end_user, architect, engineer, construction_manager, utility, other
    confidence        double precision not null default 0.5,  -- 0..1
    confidence_label  text not null default 'rumored',     -- confirmed, likely, rumored
    source_signal_id  uuid references signals(id) on delete set null,
    first_asserted_at timestamptz not null default now(),
    superseded        boolean not null default false,
    unique (project_id, company_id, role)
);

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'project_team_role_check') then
        alter table project_team add constraint project_team_role_check
            check (role in ('general_contractor','developer','owner','end_user','architect','engineer','construction_manager','utility','other'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'project_team_confidence_label_check') then
        alter table project_team add constraint project_team_confidence_label_check
            check (confidence_label in ('confirmed','likely','rumored'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'project_team_confidence_range_check') then
        alter table project_team add constraint project_team_confidence_range_check
            check (confidence >= 0 and confidence <= 1);
    end if;
end $$;

create index if not exists project_team_project_id_idx on project_team (project_id);
create index if not exists project_team_company_id_idx on project_team (company_id);

-- ─── contacts ────────────────────────────────────────────────────────────
create table if not exists contacts (
    id                  uuid primary key default gen_random_uuid(),
    company_id          uuid references companies(id) on delete cascade,
    project_id          uuid references projects(id) on delete set null,
    full_name           text,
    title               text,
    email               text,
    phone               text,
    contact_kind        text not null default 'named_person',  -- named_person, general_inbox, main_line
    source              text,                                  -- company_website, press_release, public_filing, enrichment_api, manual
    source_url          text,
    enrichment_provider text,
    verified            boolean not null default false,
    do_not_contact      boolean not null default false,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'contacts_contact_kind_check') then
        alter table contacts add constraint contacts_contact_kind_check
            check (contact_kind in ('named_person','general_inbox','main_line'));
    end if;
    if not exists (select 1 from pg_constraint where conname = 'contacts_source_check') then
        alter table contacts add constraint contacts_source_check
            check (source is null or source in ('company_website','press_release','public_filing','enrichment_api','manual'));
    end if;
end $$;

create index if not exists contacts_company_id_idx on contacts (company_id);
create index if not exists contacts_project_id_idx on contacts (project_id);

-- ===================== 003_runs_digest_subscribers.sql =====================

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

-- ===================== 004_outreach_drafts.sql =====================

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

-- ===================== 005_seed_sources.sql =====================

-- 005_seed_sources.sql
-- Seed the v1 Tier-1 + light-scrape sources (config-as-data). Idempotent on url.
-- First add a unique constraint on sources.url so re-running this file is a no-op.

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'sources_url_key') then
        alter table sources add constraint sources_url_key unique (url);
    end if;
end $$;

-- ─── Google News RSS queries (tier 1, rss_generic) ───────────────────────
insert into sources (name, source_type, url, fetch_method, parser_key, region_scope, tier, enabled)
values
  ('Google News - data center Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - data center Missouri', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Missouri&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Kansas', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Kansas&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Omaha', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Omaha&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Des Moines', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20%22Des%20Moines%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center St. Louis', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20%22St.%20Louis%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Nebraska', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Nebraska&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - data center Iowa', 'news',
   'https://news.google.com/rss/search?q=%22data%20center%22%20Iowa&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - hyperscale data center Midwest', 'news',
   'https://news.google.com/rss/search?q=%22hyperscale%22%20%22data%20center%22%20Midwest&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Google News - distribution center Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22distribution%20center%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - manufacturing plant Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22manufacturing%20plant%22%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - hospital construction Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22hospital%22%20construction%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true),
  ('Google News - warehouse construction Kansas City', 'news',
   'https://news.google.com/rss/search?q=%22warehouse%22%20construction%20%22Kansas%20City%22&hl=en-US&gl=US&ceid=US:en',
   'rss', 'rss_generic', 'kc_metro', 1, true)
on conflict (url) do nothing;

-- ─── Industry / trade RSS (tier 1, rss_generic) ──────────────────────────
insert into sources (name, source_type, url, fetch_method, parser_key, region_scope, tier, enabled)
values
  ('Data Center Dynamics', 'news',
   'https://www.datacenterdynamics.com/en/rss/',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Data Center Frontier', 'news',
   'https://www.datacenterfrontier.com/rss',
   'rss', 'rss_generic', '350mi_ring', 1, true),
  ('Kansas City Business Journal', 'news',
   'https://www.bizjournals.com/kansascity/news/rss.xml',
   'rss', 'rss_generic', 'kc_metro', 1, true)
on conflict (url) do nothing;

-- ─── Light HTML scrape targets (tier 2, html_generic, best-effort) ───────
-- KC-metro economic-development news/press index pages. The html_generic parser
-- pulls article links + visible text; if a page changes layout it simply yields
-- nothing for that run (one dead source never kills the pipeline). No fabricated
-- permit-portal URLs are seeded here.
insert into sources (name, source_type, url, fetch_method, parser_key, region_scope, tier, enabled)
values
  ('KCADC News (Kansas City Area Development Council)', 'press_release',
   'https://www.thinkkc.com/news/',
   'html', 'html_generic', 'kc_metro', 2, true),
  ('Olathe Economic Development News', 'press_release',
   'https://www.olatheks.org/business/economic-development',
   'html', 'html_generic', 'kc_metro', 2, true)
on conflict (url) do nothing;
