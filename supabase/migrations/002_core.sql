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
