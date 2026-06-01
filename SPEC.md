# BUILD SPEC — Treadwell AI News Feed (v1)

This is the **single source of truth** every build/audit agent must follow. Table names,
column names, enum values, API response keys, and TS type names below are CONTRACTS — do
not rename them. When in doubt, match this file exactly.

Read `CLAUDE.md` (same folder) for the project's purpose, hard boundaries, golden rules,
radius rules, and stack. This SPEC is the technical detail.

---

## 0. Already created — DO NOT recreate or overwrite
- `CLAUDE.md`
- `SPEC.md` (this file)
- `.gitignore`
- `backend/services/claude_cli.py`  — exposes `call_claude(prompt, system="", *, timeout=120) -> str`,
  `parse_loose_json(text) -> dict|list|None`, `call_claude_json(prompt, system="", *, timeout=120) -> dict|list|None`,
  exception `ClaudeCLIError`.
- `backend/services/supabase_client.py` — exposes `get_supabase()`, `is_configured() -> bool`,
  `with_supabase_retry(operation)`, `reset_supabase_clients()`. ALL Supabase access goes through these.

## Ports / URLs / env
- Backend dev port: **8890** (`uvicorn main:app --reload --port 8890`).
- Frontend dev: Vite on 5173, proxy `/api` -> `http://localhost:8890`.
- Production: FastAPI serves the built SPA from `../frontend/dist` via StaticFiles (SPA fallback to index.html), and the API under `/api`. nginx -> 127.0.0.1:8890.
- Env vars (pydantic-settings in `backend/config.py`, all optional with safe defaults so the app starts bare):
  - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` (default "")
  - `DEMO_MODE` (bool, default **auto**: true when Supabase not configured) — when true, the API serves sample fixtures instead of hitting the DB.
  - `RESEND_API_KEY` (default ""), `DIGEST_FROM_EMAIL` (default "radar@notify.wetreadwell.com"), `DIGEST_FROM_NAME` (default "Treadwell Radar")
  - `KC_LAT` (39.0997), `KC_LON` (-94.5786), `DATA_CENTER_RADIUS_MI` (350), `OTHER_RADIUS_MI` (70)
  - `PIPELINE_HOUR` (5), `PIPELINE_TZ` ("America/Chicago"), `RUN_SCHEDULER` (bool, default false in dev)
  - `CONTACTS_GATE_PASSWORD` (default "") — if set, `/api/projects/{id}/contacts` requires header `X-Contacts-Key` to match (the public-page carve-out). If empty, contacts are open.
  - `PUBLIC_BASE_URL` ("https://newsfeed.wetreadwell.com"), `CORS_ORIGINS` ("*" in dev)
  - `NOMINATIM_USER_AGENT` ("treadwell-newsfeed/1.0 (hanz@wetreadwell.com)")
  - `ENVIRONMENT` ("development")

---

## 1. Database schema (Supabase / Postgres)

Migrations in `supabase/migrations/`, idempotent (`create table if not exists`, `do $$ ... if not exists`
for constraints/indexes). Order matters (FKs). Use `gen_random_uuid()` (pgcrypto, on by default in Supabase)
and `timestamptz default now()`. CHECK constraints enforce the enums below.

### migration `001_extensions.sql`
`create extension if not exists pgcrypto;` `create extension if not exists cube;` `create extension if not exists earthdistance;`

### migration `002_core.sql` (order: sources, companies, projects, signals, project_team, contacts)

**sources**
- id uuid pk default gen_random_uuid()
- name text not null
- source_type text not null   -- one of: news, press_release, permit, utility_filing, econ_dev_minutes, planning_filing, other
- url text not null
- fetch_method text not null   -- one of: rss, html, pdf, api, playwright
- parser_key text not null     -- dispatch key into the parser registry (e.g. 'rss_generic', 'html_generic')
- region_scope text            -- free text, e.g. 'kc_metro', '350mi_ring'
- tier int not null default 1
- enabled boolean not null default true
- fetch_cadence text not null default 'daily'
- last_fetched_at timestamptz
- last_status text
- last_error text
- created_at timestamptz not null default now()

**companies**
- id uuid pk default gen_random_uuid()
- name text not null
- normalized_name text         -- lowercased, legal-suffix-stripped (set in code)
- company_type text not null default 'unknown'  -- general_contractor, developer, owner, end_user, architect, engineer, construction_manager, utility, subcontractor, unknown
- domain text
- website text
- hq_city text
- hq_state text
- is_hyperscaler boolean not null default false
- notes text
- created_at timestamptz not null default now()
- updated_at timestamptz not null default now()
- index on (normalized_name)

**projects** (the central deduplicated opportunity)
- id uuid pk default gen_random_uuid()
- title text not null
- summary text
- project_type text not null   -- data_center, industrial, healthcare, higher_ed, distribution, manufacturing, mission_critical, other_commercial
- stage text                   -- rumored, planning, design, permitting, procurement, pre_bid, under_construction, complete, dead
- address text
- city text
- state text
- county text
- latitude double precision
- longitude double precision
- distance_mi double precision
- in_radius boolean
- est_value_usd numeric
- est_sqft numeric
- est_megawatts numeric
- relevance_score int          -- 0..100
- relevance_tier text          -- hot, warm, cold
- relevance_reasoning jsonb
- team_confidence text not null default 'unknown'  -- gc_named, developer_named, owner_only, unknown
- status text not null default 'new'               -- new, active, watching, pursuing, archived, dismissed
- dedup_key text               -- normalized(title)|normalized(city)
- merged_into uuid references projects(id)
- scored_by_model text
- first_seen_at timestamptz not null default now()
- last_signal_at timestamptz not null default now()
- updated_at timestamptz not null default now()
- indexes: (in_radius, relevance_tier), (project_type), (stage), (dedup_key), (last_signal_at desc), (status)

**signals** (evidence — the demoted "article")
- id uuid pk default gen_random_uuid()
- project_id uuid references projects(id) on delete set null   -- null until clustered
- signal_type text not null    -- same vocab as sources.source_type
- source_id uuid references sources(id) on delete set null
- url text
- title text
- published_at timestamptz
- fetched_at timestamptz not null default now()
- raw_text text
- content_hash text not null unique   -- sha256(normalized url + '|' + title); idempotent ingest
- extracted jsonb
- extraction_confidence double precision
- created_at timestamptz not null default now()
- indexes: (project_id), (signal_type), (published_at desc)

**project_team** (team hierarchy as link rows — the "GC>Dev>Owner" engine)
- id uuid pk default gen_random_uuid()
- project_id uuid not null references projects(id) on delete cascade
- company_id uuid not null references companies(id) on delete cascade
- role text not null           -- general_contractor, developer, owner, end_user, architect, engineer, construction_manager, utility, other
- confidence double precision not null default 0.5  -- 0..1
- confidence_label text not null default 'rumored'  -- confirmed, likely, rumored
- source_signal_id uuid references signals(id) on delete set null
- first_asserted_at timestamptz not null default now()
- superseded boolean not null default false
- unique (project_id, company_id, role)

**contacts**
- id uuid pk default gen_random_uuid()
- company_id uuid references companies(id) on delete cascade
- project_id uuid references projects(id) on delete set null
- full_name text
- title text
- email text
- phone text
- contact_kind text not null default 'named_person'  -- named_person, general_inbox, main_line
- source text                  -- company_website, press_release, public_filing, enrichment_api, manual
- source_url text
- enrichment_provider text
- verified boolean not null default false
- do_not_contact boolean not null default false
- created_at timestamptz not null default now()
- updated_at timestamptz not null default now()
- indexes: (company_id), (project_id)

### migration `003_runs_digest_subscribers.sql` (order: pipeline_runs, email_subscribers, daily_digest)

**pipeline_runs** (observability + run mutex)
- id uuid pk default gen_random_uuid()
- started_at timestamptz not null default now()
- finished_at timestamptz
- status text not null default 'running'   -- running, success, partial, failed
- trigger text not null default 'scheduled'  -- scheduled, manual
- sources_fetched int not null default 0
- signals_ingested int not null default 0
- projects_created int not null default 0
- projects_updated int not null default 0
- errors jsonb not null default '[]'::jsonb

**email_subscribers**
- id uuid pk default gen_random_uuid()
- email text not null unique
- full_name text
- subscribed boolean not null default true
- unsubscribe_token uuid not null default gen_random_uuid()
- filters jsonb not null default '{}'::jsonb
- created_at timestamptz not null default now()
- unsubscribed_at timestamptz

**daily_digest**
- id uuid pk default gen_random_uuid()
- digest_date date not null unique
- project_ids uuid[] not null default '{}'
- new_count int not null default 0
- updated_count int not null default 0
- html_body text
- text_body text
- pipeline_run_id uuid references pipeline_runs(id)
- created_at timestamptz not null default now()

### migration `004_outreach_drafts.sql` (Phase 2 — create table, no API yet)
**outreach_drafts**
- id uuid pk default gen_random_uuid()
- project_id uuid references projects(id) on delete cascade
- contact_id uuid references contacts(id) on delete cascade
- subject text
- body text
- generated_by_model text
- status text not null default 'draft'   -- draft, approved, rejected, sent, bounced, replied
- approved_by text
- approved_at timestamptz
- sent_at timestamptz
- esp_message_id text
- created_at timestamptz not null default now()
- updated_at timestamptz not null default now()

### migration `005_seed_sources.sql`
Insert (idempotent on url) the v1 Tier-1 + light-scrape sources. Use `on conflict (url) do nothing`
(add a unique on sources.url in this migration). Seed at least these (parser_key in parens):
- Google News RSS queries (fetch_method=rss, parser_key=rss_generic, tier=1): build URLs of the form
  `https://news.google.com/rss/search?q=<ENCODED_QUERY>&hl=en-US&gl=US&ceid=US:en` for queries:
  "data center" "Kansas City"; "data center" Missouri; "data center" Kansas; "data center" Omaha;
  "data center" "Des Moines"; "data center" "St. Louis"; "data center" Nebraska; "data center" Iowa;
  "hyperscale" "data center" Midwest; "distribution center" "Kansas City"; "manufacturing plant" "Kansas City";
  "hospital" construction "Kansas City"; "warehouse" construction "Kansas City".
- Industry/trade RSS (rss, rss_generic, tier=1): Data Center Dynamics (https://www.datacenterdynamics.com/en/rss/),
  Data Center Frontier (https://www.datacenterfrontier.com/rss), Kansas City Business Journal
  (https://www.bizjournals.com/kansascity/news/rss.xml).
- Light HTML scrape targets (fetch_method=html, parser_key=html_generic, tier=2, enabled=true): one or two
  economic-development "news"/"press" index pages for the KC metro (leave as best-effort; parser extracts
  article links + text). Mark clearly with region_scope.
Keep the list reasonable (~15-20 rows). Each agent: do NOT invent fake permit-portal URLs.

---

## 2. Backend module interfaces (services) — agents must match these signatures

All services live in `backend/services/`. They use `claude_cli` and `supabase_client` (already written).
Every public function has type hints + a docstring. Services must NOT crash the app on import.

`ingest.py`
- `fetch_all_sources(sources: list[dict]) -> list[dict]` — for each enabled source, dispatch by parser_key;
  return candidate signal dicts `{source_id, signal_type, url, title, published_at(iso|None), raw_text}`.
- parser registry: `PARSERS: dict[str, Callable]` with at least `rss_generic` (feedparser) and `html_generic`
  (httpx + BeautifulSoup: pull article links + visible text from an index page, best-effort).
- `content_hash(url: str, title: str) -> str` — sha256 of normalized url + '|' + title.
- All network calls: httpx with a descriptive User-Agent (from settings.NOMINATIM_USER_AGENT family),
  timeout, try/except per source so one failure never aborts the batch. Respect a simple per-host politeness delay.

`signal_extractor.py`
- `extract_signal(title: str, raw_text: str) -> dict | None` — calls `call_claude_json` with a strict-JSON
  system prompt; returns `{project_name, project_type, stage, location:{address,city,state,county},
  est_value_usd, est_sqft, est_megawatts, team:[{company,role,confidence_label,evidence_quote}],
  contacts_mentioned:[{full_name,title,email,phone}], is_construction_opportunity:bool,
  dedup_hints:{aka_names:[...]}, extraction_confidence:0..1}`. Enforce controlled-vocab (drop off-list
  project_type/stage/role values). Return None if not parseable.
- Provide the SYSTEM_PROMPT as a module constant.

`clusterer.py`
- `normalize_name(s: str) -> str`, `dedup_key(title: str, city: str|None) -> str`.
- `find_or_create_project(extracted: dict, existing_candidates: list[dict]) -> tuple[str, bool]` —
  deterministic blocking by dedup_key first; if ambiguous, `call_claude_json` adjudication
  ("same project? -> {decision:'same'|'different', target_project_id, confidence}"). Returns
  (project_id, created_bool). Writes via supabase_client.

`team_enricher.py`
- `resolve_company(name: str, role: str) -> str` — normalize, find-or-create companies row, set is_hyperscaler
  (Google/Meta/Microsoft/Amazon/AWS/QTS/Vantage/EdgeConneX/Aligned/CloudHQ/Meta...) heuristic. Returns company_id.
- `upsert_team_member(project_id, company_id, role, confidence, confidence_label, source_signal_id)`.
- `recompute_team_confidence(project_id) -> str` — rollup to gc_named/developer_named/owner_only/unknown; writes project.

`geocode.py`
- `geocode(address: str|None, city: str|None, state: str|None) -> tuple[float,float]|None` — US Census
  geocoder first (https://geocoding.geo.census.gov/geocoder/locations/onelineaddress, free, no key),
  Nominatim fallback (1 req/s, UA from settings). Cache-friendly (caller decides when to call).
- `haversine_mi(lat1, lon1, lat2, lon2) -> float`.
- `compute_radius(project_type: str, distance_mi: float) -> bool` — data_center<=DATA_CENTER_RADIUS_MI else <=OTHER_RADIUS_MI.

`relevance_scorer.py`
- `score_project(project: dict) -> dict` — `call_claude_json`; returns `{relevance_score:0..100,
  relevance_tier:'hot'|'warm'|'cold', relevance_reasoning:{...}}`. Falls back to a deterministic
  rule-based score if Claude unavailable (earlier stage + in_radius + gc_named + bigger size => higher).

`digest_builder.py`
- `build_digest(for_date: date) -> dict` — select in-radius projects first_seen or materially updated on
  for_date with tier in (hot,warm), data-centers first then by score; render `{digest_date, project_ids,
  new_count, updated_count, html_body, text_body}`. HTML = project CARDS (not an article list), inline-styled
  for email clients, with the unsubscribe link `{PUBLIC_BASE_URL}/api/unsubscribe?token=...` placeholder.

`mailer.py`
- `send_digest(subscriber: dict, digest: dict) -> dict` — POST to Resend via httpx using RESEND_API_KEY.
  No-op + log warning (return {skipped:true}) if RESEND_API_KEY empty. Never batch — one call per subscriber.

`backend/jobs/daily.py`
- `run_pipeline(trigger: str = 'scheduled') -> dict` — Stages 0-9 (see CLAUDE.md / plan):
  0 run-lock (insert pipeline_runs status=running; abort if one already running),
  1 fetch_all_sources, 2 extract per new signal (skip dup content_hash), 3 cluster, 4 enrich team,
  5 geocode + radius, 6 score, 7 persist, 8 build_digest, 9 send to subscribers; finalize pipeline_runs.
  Must be safe to call when DEMO_MODE/no Supabase: log "skipped — no DB" and return a clear dict (do not crash).
- `fixtures` for DEMO mode are owned by the API agent (see §4), not here.

---

## 3. APScheduler wiring (in `backend/main.py`)
- On FastAPI `lifespan` startup: if `settings.RUN_SCHEDULER` is true AND Supabase configured, start a
  `BackgroundScheduler` with one `CronTrigger(hour=PIPELINE_HOUR, timezone=PIPELINE_TZ)`,
  `max_instances=1`, `coalesce=True`, calling `jobs.daily.run_pipeline('scheduled')`. Shut it down on app stop.
- Never block startup on the scheduler; wrap in try/except and log.

---

## 4. API (FastAPI routers under `/api`) — exact response shapes

All list endpoints paginate at **25/page** by default. All responses are JSON. Dates ISO-8601 strings.
When `DEMO_MODE` (or Supabase unconfigured), endpoints return data from a `fixtures.py` module
(API agent owns `backend/services/fixtures.py` with ~10 realistic sample projects incl. >=4 data centers
across the 350mi ring, varied stages, varied team_confidence, sample signals/contacts/digests/runs).
The frontend must look fully populated in DEMO_MODE with zero external services.

`routers/health.py`
- `GET /api/health` -> `{status:"ok", env:str, demo_mode:bool, supabase_configured:bool, time:iso}`

`routers/projects.py`
- `GET /api/projects` query params: `q`(str), `project_type`(csv), `stage`(csv), `in_radius`(bool),
  `tier`(csv of hot/warm/cold), `team_confidence`(csv), `status`(csv; default excludes archived,dismissed),
  `sort`(relevance|distance|recent; default relevance), `page`(int=1), `page_size`(int=25).
  -> `{items: ProjectSummary[], page, page_size, total, total_pages}`
- `GET /api/projects/{id}` -> `ProjectDetail`
- `GET /api/projects/{id}/signals` -> `Signal[]`
- `PATCH /api/projects/{id}` body `{status: str}` -> updated `ProjectSummary`
- `POST /api/projects/{id}/merge` body `{target_id: str}` -> `{ok:true, merged_into:str}`
- `GET /api/stats` -> `{total:int, new:int, today:int, hot:int, in_radius:int, data_centers:int}`

`routers/contacts.py`
- `GET /api/projects/{id}/contacts` (honors CONTACTS_GATE_PASSWORD via `X-Contacts-Key` header if set;
  401 if required and missing/wrong) -> `Contact[]`

`routers/digests.py`
- `GET /api/digests` -> `DigestSummary[]` (date desc)
- `GET /api/digests/{date}` -> `{digest_date, html_body, project_ids, new_count, updated_count}`

`routers/subscribers.py`
- `POST /api/subscribers` body `{email, full_name?}` -> `{ok:true}`
- `GET /api/unsubscribe?token=...` -> small HTML page confirming unsubscribe (sets subscribed=false)

`routers/admin.py`
- `GET /api/admin/runs` -> `PipelineRun[]` (started_at desc, limit 25)
- `POST /api/admin/run-pipeline` -> triggers `run_pipeline('manual')` via FastAPI BackgroundTasks
  (respects run-lock); returns `{ok:true, started:bool, note:str}`. In DEMO_MODE return `{ok:true, started:false, note:"DEMO_MODE — no DB"}`.

### JSON shapes (these key names are the contract; mirror exactly in TS types)
**ProjectSummary**: `{id, title, project_type, stage, city, state, county, distance_mi, in_radius,
relevance_score, relevance_tier, team_confidence, top_team_member: {company_name, role, confidence_label}|null,
signals_count, est_megawatts, est_value_usd, est_sqft, status, last_signal_at, first_seen_at}`
**ProjectDetail**: ProjectSummary + `{summary, address, latitude, longitude, relevance_reasoning,
team: TeamMember[], signals_count, contacts_count}`
**TeamMember**: `{company_id, company_name, company_type, role, confidence, confidence_label, is_hyperscaler}`
**Signal**: `{id, signal_type, source_name, url, title, published_at, snippet, extraction_confidence}`
**Contact**: `{id, company_id, company_name, full_name, title, email, phone, contact_kind, source, source_url, verified, do_not_contact}`
**DigestSummary**: `{digest_date, new_count, updated_count, project_count}`
**PipelineRun**: `{id, started_at, finished_at, status, trigger, sources_fetched, signals_ingested, projects_created, projects_updated, errors}`

`backend/models/schemas.py`: define pydantic models for the above (used for response_model + validation).

---

## 5. Frontend (Vite + React + TypeScript + Tailwind)

Mobile-first. Single-page app, client-side routing (react-router-dom). Icons: **lucide-react** (no emoji).
Use Tailwind utility classes + a small set of shadcn-style components written by hand (no need to run the
shadcn CLI). Theme: light + dark via a `dark` class on <html> + CSS variables; persist choice in localStorage.

### Files (Frontend Agent 1 = scaffold + feed; Frontend Agent 2 = detail + drawers + secondary pages)
- `frontend/package.json` (Agent 1) — deps: react, react-dom, react-router-dom, lucide-react;
  devDeps: vite, @vitejs/plugin-react, typescript, tailwindcss, postcss, autoprefixer, @types/react, @types/react-dom.
  scripts: `dev`, `build` (tsc -b? keep simple: `vite build`), `preview`.
- `frontend/vite.config.ts` (Agent 1) — react plugin; server.proxy `/api` -> http://localhost:8890; build.outDir 'dist'.
- `frontend/tsconfig.json` + `tsconfig.node.json` (Agent 1).
- `frontend/index.html` (Agent 1) — title "Treadwell Radar"; Google Fonts preconnect + Fira Sans/Fira Code.
- `frontend/tailwind.config.js` + `frontend/postcss.config.js` (Agent 1) — theme.extend.colors mapped to CSS vars
  (primary, secondary, accent, bg, surface, fg, muted, border, destructive, hot, warm, cold); darkMode 'class';
  fontFamily sans -> 'Fira Sans', mono -> 'Fira Code'.
- `frontend/src/main.tsx`, `frontend/src/App.tsx` (Agent 1) — router with routes: `/` (FeedPage),
  `/project/:id` (ProjectDetailPage), `/digests` (DigestsPage), `/admin` (AdminPage). App shell: top bar
  (brand "Treadwell Radar", theme toggle, nav links), responsive.
- `frontend/src/index.css` (Agent 1) — @import Fira fonts; Tailwind directives; :root + .dark CSS variables
  (see tokens below); base styles; tabular-nums utility for `.num`.
- `frontend/src/lib/types.ts` (Agent 1) — TS interfaces mirroring §4 JSON shapes EXACTLY.
- `frontend/src/lib/api.ts` (Agent 1) — typed fetch wrappers: `getProjects(params)`, `getProject(id)`,
  `getProjectSignals(id)`, `getProjectContacts(id, key?)`, `patchProjectStatus(id, status)`,
  `mergeProject(id, targetId)`, `getStats()`, `getDigests()`, `getDigest(date)`, `getRuns()`, `runPipeline()`,
  `subscribe(email, name)`. Base URL '' (same origin / proxied).
- `frontend/src/lib/format.ts` (Agent 1) — `miles(n)`, `money(n)`, `megawatts(n)`, `sqft(n)`, `relativeDate(iso)`,
  label maps for project_type/stage/role/team_confidence/tier (human-readable).
- `frontend/src/components/` shared (Agent 1): `TopBar`, `ThemeToggle`, `StatCard`, `FilterBar` (the data-center
  vs other toggle, type/stage/tier/team chips, search, sort), `ProjectCard`, `StageBadge`, `TeamConfidenceBadge`,
  `RelevanceIndicator` (hot/warm/cold dot+label), `DistancePill`, `Pagination` (25/page), `EmptyState`,
  `Skeleton`, `ConfirmDialog`.
- `frontend/src/pages/FeedPage.tsx` (Agent 1) — THE project-first feed: stats row (from /api/stats),
  FilterBar, responsive grid of ProjectCards (1 col mobile / 2 col tablet / 3 col desktop), Pagination,
  loading skeletons, empty state. Sort + filters update query params + refetch.
- `frontend/src/pages/ProjectDetailPage.tsx` (Agent 2) — header (title, type, stage, distance, in/out-radius,
  relevance), TeamHierarchy (GC>Dev>Owner with confidence), key facts (MW/$/sqft), tabs: **Overview** +
  **Evidence** (signals list). A prominent **Contacts** button that opens ContactsDrawer. Status control
  (active/watching/pursuing/dismiss) with ConfirmDialog on dismiss.
- `frontend/src/components/TeamHierarchy.tsx` (Agent 2) — renders project.team ordered GC, developer, owner,
  others; shows confidence_label + hyperscaler flag; empty -> "Team not yet identified".
- `frontend/src/components/EvidenceList.tsx` (Agent 2) — signals as compact rows: source_name, title (links out),
  published date, snippet, signal_type badge.
- `frontend/src/components/ContactsDrawer.tsx` (Agent 2) — slide-over; lists contacts grouped by company;
  named_person vs general_inbox/main_line; mailto:/tel: links; shows source provenance; if API returns 401
  (gated), shows a small password field that re-requests with X-Contacts-Key.
- `frontend/src/pages/DigestsPage.tsx` (Agent 2) — list past digests (date, new/updated counts); click -> render
  the digest html_body (dangerouslySetInnerHTML in a sandboxed container) or a project list.
- `frontend/src/pages/AdminPage.tsx` (Agent 2) — pipeline runs table + "Run pipeline now" button (ConfirmDialog;
  calls /api/admin/run-pipeline; shows the returned note, handles DEMO_MODE gracefully).

### Design tokens (CSS variables; Agent 1 sets both light + dark)
Light: `--bg:#F8FAFC; --surface:#FFFFFF; --fg:#0F172A; --muted:#E9EEF6; --border:#DBEAFE;
--primary:#1E40AF; --primary-fg:#FFFFFF; --secondary:#3B82F6; --accent:#D97706;
--destructive:#DC2626; --hot:#DC2626; --warm:#D97706; --cold:#64748B; --ring:#1E40AF`
Dark: `--bg:#0B1220; --surface:#131C2E; --fg:#E5EDF7; --muted:#1C2740; --border:#24324F;
--primary:#3B82F6; --primary-fg:#0B1220; --secondary:#60A5FA; --accent:#F59E0B;
--destructive:#F87171; --hot:#F87171; --warm:#F59E0B; --cold:#94A3B8; --ring:#3B82F6`
Body text must hit >=4.5:1 in both themes. Numerals/distances/MW/$ use the mono (Fira Code) + tabular-nums.

### UX rules (non-negotiable)
- Mobile-first; verify at 375px: no horizontal scroll, >=44px touch targets, readable contrast.
- Lists paginate at 25/page. Destructive actions (dismiss/merge) require ConfirmDialog.
- lucide-react icons only (no emoji as icons). cursor-pointer on clickables. Hover/transition 150-300ms.
- Respect prefers-reduced-motion. Loading uses Skeletons, not blank screens. Show EmptyState with guidance.
- The feed must read as PROJECTS (opportunity cards), never as a flat article list.

---

## 6. Infra (owned by Backend Agent 1 unless noted)
- `Dockerfile` (multi-stage): Stage 1 `node:20-slim` builds the SPA (`frontend/` -> `dist/`). Stage 2
  `python:3.11-slim`: install backend requirements, install Node + `@anthropic-ai/claude-code` (claude CLI),
  copy backend + the built `frontend/dist`, expose 8890, CMD `uvicorn main:app --host 0.0.0.0 --port 8890`.
  Use tini as entrypoint. Persist `/root/.claude` via a volume (compose).
- `docker-compose.yml`: one service `treadwell-newsfeed`, build ., ports `127.0.0.1:8890:8890`, env_file .env,
  volumes: `claude_credentials:/root/.claude`. healthcheck curl /api/health.
- `.dockerignore`: node_modules, .venv, .git, frontend/dist (rebuilt), __pycache__, .env.
- `deploy/nginx-newsfeed.conf`: server block for newsfeed.wetreadwell.com -> 127.0.0.1:8890 (proxy headers).
- `deploy/README.md`: DNS A-record `newsfeed`->50.6.110.215; certbot; `ssh -i ~/.ssh/treadwell_vps root@50.6.110.215`;
  app dir `/opt/treadwell-newsfeed`; `git pull && docker compose up -d --build`. NOTE: local test first; do not deploy until approved.
- root `README.md`: what it is, local run steps (backend + frontend), migrations, DEMO_MODE, deploy pointer.

---

## 7. Guardrails (audit agents enforce)
- All Supabase access via `with_supabase_retry(lambda: get_supabase()...)`. No direct create_client elsewhere.
- All AI via `claude_cli`. Controlled-vocab enums; drop off-list values silently.
- Backend imports cleanly with NO env set (DEMO_MODE on). `GET /api/health` works bare. No service crashes on import.
- No imports from ../treadwell-proposal-tool or ../Treadwell. Fully self-contained.
- Never scrape LinkedIn. Contacts always carry source/source_url. Honor do_not_contact (exclude from any future outreach).
- Pipeline resilient: one bad source/signal/extraction must not abort the run.
