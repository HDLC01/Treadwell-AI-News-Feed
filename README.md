# Treadwell AI News Feed

A **project-first construction-opportunity radar**. The unit is a deduplicated *project*
(not a news article): a real building/facility being planned, designed, permitted, or
built, enriched over time with location + distance from Kansas City, stage, and a team
hierarchy (General Contractor → Developer → Owner) with confidence.

**Goal:** get Treadwell (commercial flooring) in front of large-project teams —
especially **data centers** — before bid invites go out. News, permits, and filings are
*evidence* attached to a project, never the top-level unit.

> Standalone system — its own repo, Supabase project, container, and subdomain
> (`newsfeed.wetreadwell.com`). It does **not** import from or deploy with the
> proposal tool or the main Treadwell app. See `CLAUDE.md` for the hard boundaries and
> `SPEC.md` for the full build contract.

---

## Stack
- **Backend:** FastAPI (Python 3.11) — REST API + APScheduler daily job + serves the built SPA.
- **Frontend:** Vite + React + TypeScript + Tailwind (built to static, served by FastAPI).
- **DB:** Supabase (Postgres) via `supabase-py` (service-role, server-side).
- **AI:** local `claude -p` CLI (no cloud Anthropic API) — extraction, dedup, scoring.
- **Ingestion:** httpx + feedparser (RSS) + BeautifulSoup (HTML). Playwright deferred.
- **Email:** Resend (transactional), one message per subscriber.
- **Deploy:** single Docker container on the Bluehost VPS behind nginx + certbot.

## Radius rules
- `project_type == data_center` → in-radius if distance from KC ≤ **350 mi**.
- everything else → in-radius if distance ≤ **70 mi**.
- KC origin = `(39.0997, -94.5786)`; great-circle (Haversine) distance.

---

## Run locally

### DEMO_MODE (zero external services)
The backend **starts with no environment variables set**: `DEMO_MODE` turns on
automatically when Supabase isn't configured, and the API serves sample fixtures so the
UI looks fully populated with no DB, no Resend, and no `claude` CLI required.

```bash
# Backend (port 8890 — avoids 8000/8888)
cd backend
python -m venv .venv && . .venv/Scripts/activate    # Windows; use bin/activate on macOS/Linux
pip install -r requirements.txt
uvicorn main:app --reload --port 8890

# health check
curl http://localhost:8890/api/health
#   -> {"status":"ok","env":"development","demo_mode":true,"supabase_configured":false,...}
```

```bash
# Frontend (Vite dev server on 5173, proxies /api -> :8890)
cd frontend
npm install
npm run dev
```

### With a real database
1. Create a **new, separate** Supabase project for the news feed.
2. Run the migrations in order (idempotent):
   ```
   supabase/migrations/001_extensions.sql
   supabase/migrations/002_core.sql
   supabase/migrations/003_runs_digest_subscribers.sql
   supabase/migrations/004_outreach_drafts.sql
   supabase/migrations/005_seed_sources.sql
   ```
   (paste into the Supabase SQL editor, or `psql -f`).
3. Copy `backend/.env.example` → `backend/.env` and fill in `SUPABASE_URL` +
   `SUPABASE_SERVICE_ROLE_KEY` (and optionally `RESEND_API_KEY`). With Supabase
   configured, `DEMO_MODE` defaults to **false**.
4. Restart the backend. `/api/health` now reports `supabase_configured: true`.

### Run the pipeline manually
```bash
curl -X POST http://localhost:8890/api/admin/run-pipeline
```
- Respects a DB run-lock (one run at a time).
- In DEMO_MODE returns `{ok:true, started:false, note:"DEMO_MODE — no DB"}` (no-op).
- Stages: fetch sources → extract signals (claude) → cluster/dedup → enrich team →
  geocode + radius → score → persist → build digest → email subscribers.

The scheduled run fires daily at `PIPELINE_HOUR` (default 5) in `PIPELINE_TZ`
(`America/Chicago`) when `RUN_SCHEDULER=true` **and** Supabase is configured.

---

## Key environment variables
All optional with safe defaults so the app starts bare (full list in `backend/.env.example`):

| Var | Default | Notes |
|-----|---------|-------|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | `""` | DB access; empty → DEMO_MODE |
| `DEMO_MODE` | auto | `true` when Supabase unconfigured; serves fixtures |
| `RESEND_API_KEY` | `""` | empty → email sending is a no-op |
| `DATA_CENTER_RADIUS_MI` / `OTHER_RADIUS_MI` | `350` / `70` | in/out-radius gate |
| `PIPELINE_HOUR` / `PIPELINE_TZ` | `5` / `America/Chicago` | daily job time |
| `RUN_SCHEDULER` | `false` | enable the APScheduler cron |
| `CONTACTS_GATE_PASSWORD` | `""` | if set, `/api/projects/{id}/contacts` needs `X-Contacts-Key` |
| `PUBLIC_BASE_URL` | `https://newsfeed.wetreadwell.com` | used in digest links |

---

## Layout
```
backend/        FastAPI app, services, daily job, models, migrations-aware config
frontend/       Vite + React SPA (built to dist/, served by FastAPI)
supabase/migrations/   NNN_name.sql, idempotent
Dockerfile      multi-stage: Node builds SPA -> Python runtime w/ claude CLI baked
docker-compose.yml
deploy/         nginx server block + certbot runbook for the subdomain
CLAUDE.md       purpose, boundaries, golden rules, stack
SPEC.md         the full build contract (schema, enums, interfaces, API, types)
```

## Deploy
See [`deploy/README.md`](deploy/README.md). **Test locally first — do not deploy until
local smoke tests pass and Hanz approves.**

## Guardrails
- All DB access via `backend/services/supabase_client.py` (`with_supabase_retry`).
- All AI via `backend/services/claude_cli.py`; controlled-vocab enums (off-list values dropped).
- Self-contained — no imports from the proposal tool or the main Treadwell app.
- **Never scrape LinkedIn.** Respect `robots.txt`/ToS, descriptive User-Agent, per-host
  rate limit; every contact carries `source`/`source_url`; honor `do_not_contact`.
- AI drafts, humans decide — outreach (Phase 2) is one-at-a-time human approval, no batch send.
