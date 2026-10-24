# Treadwell AI News Feed — CLAUDE.md

## What this is

A project-first construction-opportunity radar. The primary record is a deduplicated
**project**, never an article. News, permits, and filings are evidence attached to that
project as it is enriched with location, Kansas City distance, delivery stage, project
team hierarchy, contacts, and relevance.

The purpose is to put Treadwell in front of major projects — particularly data centers —
before bid invitations. It is a standalone application with its own repository, data
Supabase project, container, subdomain target, and nginx configuration. Do not import from
the proposal tool, main Treadwell system, or roadmap. Copy/adapt a proven idea locally.

## Current architecture — verified from source on 2026-07-22

- Backend: FastAPI (Python 3.11), APScheduler pipeline, server-served Vite/React SPA.
- Frontend: React 18, TypeScript, Vite, Tailwind, React Router, and Leaflet map views.
- Data: this app's own Supabase Postgres, accessed server-side only via
  `services/supabase_client.py` with retry handling. Browsers do not receive data-project
  credentials.
- Authentication: shared Treadwell Supabase **auth** project signs in `@wetreadwell.com`
  users; it is distinct from the News Feed data project. Admins are configuration-derived.
- AI: local `claude -p` CLI for structured extraction, dedup adjudication, and relevance
  scoring. All model output is constrained to controlled vocabulary before persistence.
- Email: Resend sends subscription digests and the opt-in daily hot-project summary.
- Deployment: a single Docker container on loopback port `8890`; build off-box and ship
  prebuilt images with `deploy/ship.sh`. Do not build on the shared 1 vCPU/2 GB VPS.

## Access models

- Internal users are Google SSO principals: `admin` or read-only `viewer`.
- The custom connector in `mcp/` is a separate, read-only service principal using
  `X-Api-Key`. It can never write to the feed. Its own container/domain/deploy flow is
  independent from the feed application.
- `DEV_LOGIN` is a local preview mechanism only; it must remain false in production.
- With no data Supabase credentials, the backend enters safe `DEMO_MODE` automatically
  and uses fixtures. It must still start and keep `/api/health` useful.

## Domain and pipeline invariants

- A project is the unit of deduplication. Sources/signals are evidence rows; never turn
  the UI back into an article-first reader.
- Kansas City is `(39.0997, -94.5786)`. Data centers are in range at 350 miles or less;
  every other type at 70 miles or less, using Haversine distance.
- Pipeline stages are fetch → extract → cluster/dedup → team/contact enrichment →
  geocode/radius → relevance → persistence → digest/summary. The run lock permits only
  one active pipeline at a time.
- Stale-project policy is configuration-driven (`STALE_MONTHS`); do not resurrect stale
  evidence without a new, relevant signal.
- Every contact needs provenance (`source`/`source_url`) and must respect
  `do_not_contact`.
- Never scrape LinkedIn. Respect robots.txt and site terms, use a descriptive User-Agent,
  per-host rate limits, and a search API only for permitted public URL resolution.
- Outreach is human-approved, one item at a time. There is no batch-send endpoint.

## Code map

| Location | Responsibility |
|---|---|
| `SPEC.md` | Full build contract: schema, enums, interfaces, endpoints, and types. |
| `backend/main.py`, `config.py`, `auth.py` | App boot, environment modes, SSO/service-principal enforcement. |
| `backend/jobs/daily.py`, `dedupe.py` | Scheduled pipeline orchestration and dedup task handling. |
| `backend/services/` | Ingestion, guardrails, extraction, clustering, team/contact enrichment, geocoding, relevance, recency, digest, and mail. |
| `backend/routers/` | Projects/map/stats, contacts, digests, subscribers, admin pipeline/summary, and auth config. |
| `supabase/migrations/` | Ordered, idempotent data-schema and source/pipeline migrations. |
| `frontend/src/pages/` | Feed, map, pipeline, project detail, digests, and admin UI. |
| `mcp/` | Standalone FastMCP read-only connector and grounded outreach draft helper. |

## Local run and verification

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8890

cd ..\frontend
npm install
npm run dev
npm run typecheck
npm run build
```

With no environment variables, use the fixture-backed UI and verify `/api/health`. With a
real data project, apply `supabase/migrations/` in numeric order, configure the private
environment, then run the pipeline manually through `/api/admin/run-pipeline` before
enabling the schedule.

## Deploy and safety rules

- Test locally first and get Hanz's approval before pushing, running migrations, enabling
  scheduler/email, or deploying.
- `deploy/ship.sh` is the current delivery path: build the Linux image locally, ship/load
  it, restart Compose without `--build`, then wait for the health endpoint.
- Runtime configuration/secrets (Supabase service role, Resend, shared-auth settings,
  API key, Claude credentials) never belong in git, source output, or public docs.
- The connector is read-only by design. Any change that could mutate feed data or send
  email requires a separate explicit authorization and audit.
