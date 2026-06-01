# Treadwell AI News Feed — CLAUDE.md

## What this is
A project-first **construction-opportunity radar**. The unit is a deduplicated PROJECT
(not a news article), enriched over time, showing location + distance from Kansas City,
stage, and a team hierarchy (General Contractor > Developer > Owner) with confidence.
Goal: get Treadwell in front of large-project teams — especially data centers — before
bid invites go out. News/permits/filings are *evidence* attached to a project, never the
top-level unit. (Contrast: the BioStar reference is an article-first RSS reader; we invert it.)

## SEPARATE SYSTEM — hard boundary
This is a STANDALONE project with its OWN git repo and its OWN subdomain
(newsfeed.wetreadwell.com). It is NOT part of, and MUST NOT import from or deploy with:
  - ../treadwell-proposal-tool  (proposals.wetreadwell.com)
  - ../Treadwell                (the main Expo + FastAPI app)
Proven patterns from those projects may be COPIED into this repo, never imported. It has
its own Supabase project, its own container, its own nginx server block and TLS cert. It
shares only the physical VPS host (50.6.110.215).

- **GitHub repo:** https://github.com/HDLC01/Treadwell-AI-News-Feed
- **Subdomain (target):** newsfeed.wetreadwell.com

## Golden rules
- **TEST LOCALLY FIRST.** Never push to GitHub or deploy to the VPS until the app runs and
  passes local smoke tests AND Hanz has given the go-ahead.
- **AI drafts, humans decide.** Especially Phase-2 outreach: one-at-a-time human approval
  only — there is NO batch-send endpoint.
- **Never scrape LinkedIn.** Respect robots.txt + ToS; descriptive User-Agent; rate-limit
  per host; store source_url on every contact; honor do_not_contact.

## Radius rules
  - project_type == data_center  -> in radius if distance_from_KC <= 350 miles
  - everything else              -> in radius if distance_from_KC <= 70 miles
KC origin = (39.0997, -94.5786). Distance is great-circle (Haversine) for the in/out gate.

## Stack
  - Backend: FastAPI (Python 3.11) — REST API + APScheduler daily job + serves the built SPA
  - Frontend: Vite + React + TypeScript + Tailwind + shadcn-style components (built to static,
    served by FastAPI StaticFiles)
  - DB: Supabase (Postgres) — server-side via supabase-py with the service-role key
  - AI: local `claude -p` CLI via subprocess (NO cloud Anthropic API) — extraction, dedup, scoring
  - Ingestion: httpx + feedparser (RSS) + BeautifulSoup/lxml (HTML scraping). Playwright is
    deferred to a later phase (JS-gated permit portals) — NOT in v1.
  - Email: Resend (transactional) from a dedicated sending subdomain w/ SPF/DKIM/DMARC
  - Deploy: single Docker container on the Bluehost VPS, nginx reverse proxy + certbot

## Design system (UI/UX Pro Max: "Data-Dense Dashboard")
  - Light + dark. Primary #1E40AF, secondary #3B82F6, accent/CTA #D97706, status: hot=red
    #DC2626 / warm=amber #D97706 / cold=slate #64748B. Destructive #DC2626.
  - Body: Fira Sans. Numerals / IDs / distances: Fira Code (tabular figures). Icons: lucide-react
    (SVG) — NO emoji as icons.
  - Mobile-first: 375 / 768 / 1024 / 1440. Touch targets >= 44px. Respect prefers-reduced-motion.
  - Lists paginate at 25/page. Destructive actions (dismiss/remove/merge) require a confirm dialog.

## Layout
  Treadwell AI News Feed/
    SPEC.md                        # the full build contract (schema, enums, interfaces, API, types)
    backend/
      main.py                      # FastAPI app + APScheduler lifespan + StaticFiles mount of ../frontend/dist
      config.py                    # pydantic-settings from .env
      requirements.txt
      .env.example
      routers/                     # health, projects, contacts, digests, subscribers, admin
      services/
        claude_cli.py              # ADAPTED pattern: `claude -p --output-format json`
        supabase_client.py         # ADAPTED pattern: HTTP/1.1 patch + retry wrapper
        ingest.py                  # source fetch + parser registry (rss/html)
        signal_extractor.py        # claude -p: article/filing -> structured project+team JSON
        clusterer.py               # dedup: deterministic blocking + claude -p adjudication
        team_enricher.py           # reconcile team assertions -> project_team rows + rollup
        geocode.py                 # US Census geocoder (+ Nominatim fallback) + Haversine + radius
        relevance_scorer.py        # claude -p: 0-100 score + hot/warm/cold + reasoning
        digest_builder.py          # select today's new/updated projects -> html/text
        mailer.py                  # Resend send w/ unsubscribe link (behind a flag)
      jobs/daily.py                # the scheduled pipeline entrypoint (Stages 0-9)
      models/schemas.py            # pydantic response models
    frontend/                      # Vite + React SPA (built to dist/, served by FastAPI)
    supabase/migrations/           # NNN_name.sql, idempotent (DO $$ ... IF NOT EXISTS)
    Dockerfile                     # multi-stage: Node builds SPA -> Python runtime w/ claude CLI baked
    docker-compose.yml
    deploy/                        # nginx server block + certbot + install notes for the subdomain

## Run locally
  - Backend:  cd backend && uvicorn main:app --reload --port 8890   (own port; avoid 8000/8888)
  - Frontend: cd frontend && npm run dev   (Vite dev server, proxy /api -> :8890)
  - Pipeline (manual): POST /api/admin/run-pipeline   (respects the DB run-lock)
  - Migrations: run supabase/migrations/*.sql in order against the (new, separate) Supabase project.

## Conventions
  - All DB access through services/supabase_client.py with with_supabase_retry().
  - All AI through services/claude_cli.py. Controlled-vocabulary enums; silently drop off-list values.
  - Every source is a row in `sources` (config-as-data); each parser is isolated so one dead
    source never kills a run.
  - The backend must START even without Supabase/Resend creds configured (health endpoint stays
    green); services raise clear errors only when actually invoked.

## Deploy (only after local tests pass + Hanz approves)
  - SSH: ssh -i ~/.ssh/treadwell_vps root@50.6.110.215  (key already on this machine; 50.6.110.215
    already in known_hosts). App dir on VPS: /opt/treadwell-newsfeed (separate from /opt/treadwell).
  - DNS: A-record `newsfeed` -> 50.6.110.215 in Bluehost DNS for wetreadwell.com.
  - Own nginx server block + Let's Encrypt cert for newsfeed.wetreadwell.com. Container binds
    127.0.0.1:8890; nginx reverse-proxies 80/443 -> 8890.
