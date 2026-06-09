# Dropbox → News Feed dedup matcher

A **local** tool that stops the News Feed (and the connector) from re-pitching projects
Treadwell already has. It matches feed leads against your Dropbox estimating folders and
tags the matches `existing` on the feed — which hides them from the feed, `top_picks`, and
`draft_outreach`.

**Runs on your machine only — never deployed.** It reads the feed over HTTPS and reads your
Dropbox **read-only**: folder names are listed, and for close calls a candidate file is
copied to `WORK_DIR`, parsed, and **deleted**. Nothing in Dropbox is ever modified.

## Setup
```bash
cd "Treadwell AI News Feed/tools/dropbox_dedup"
cp .env.example .env        # paths are pre-filled; edit if your Dropbox lives elsewhere
```

## Use (review-first)
```bash
# 1) DRY RUN — prints a match report, writes nothing
uv run match.py

# 2) Eyeball the STRONG list (and the REVIEW list). When happy:
uv run match.py --apply     # tags only the STRONG matches as 'existing'
```
- **STRONG** = high-confidence (name + city match, or file-confirmed) → tagged on `--apply`.
- **REVIEW** = plausible but uncertain → **never auto-tagged**; mark those by hand in the
  feed UI (project page → status → **Existing**) if they're real.

Tuning: `--strong 0.7 --review 0.45` (score thresholds), `--no-deep` (skip opening files).

## Undo
A false positive is reversible: open the project in the feed and set its status back to
**Active** (or `PATCH /api/projects/{id}` `{"status":"new"}`).

## How matching works
Reuses the feed's clustering vocabulary (normalize → token sets → overlap coefficient) plus a
city-token boost; `--apply` calls the feed's open `PATCH /api/projects/{id}` to set
`status='existing'`. Requires migration `010_existing_status.sql` applied to the feed's
Supabase project first (so the status is valid).
