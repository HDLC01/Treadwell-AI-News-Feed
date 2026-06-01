# Deploy — Treadwell AI News Feed (newsfeed.wetreadwell.com)

> ⚠️ **TEST LOCALLY FIRST. DO NOT DEPLOY UNTIL APPROVED.**
> Per `CLAUDE.md` golden rules: never push to GitHub or deploy to the VPS until the app
> runs and passes local smoke tests **and** Hanz has given the go-ahead. This file is the
> runbook for *when that approval lands* — not a signal to deploy now.

This is a **standalone system** with its own subdomain, container, nginx server block, and
TLS cert. It shares only the physical VPS host (`50.6.110.215`) with the proposal tool and
the main Treadwell app. It must never be merged into `/opt/treadwell` or `proposals.wetreadwell.com`.

---

## 1. DNS (Bluehost — wetreadwell.com zone)
Add an **A record**:

    Host:   newsfeed
    Type:   A
    Value:  50.6.110.215
    TTL:    default

Confirm it resolves before requesting a cert:

    dig +short newsfeed.wetreadwell.com      # -> 50.6.110.215

---

## 2. SSH to the VPS
The key is already on this machine and `50.6.110.215` is already in `known_hosts`:

    ssh -i ~/.ssh/treadwell_vps root@50.6.110.215

App directory on the VPS (kept **separate** from `/opt/treadwell`):

    /opt/treadwell-newsfeed

---

## 3. First-time setup on the VPS
```bash
# as root@50.6.110.215
mkdir -p /opt/treadwell-newsfeed
cd /opt/treadwell-newsfeed

# Clone (or copy) this repo here.
git clone https://github.com/HDLC01/Treadwell-AI-News-Feed.git .

# Create the runtime env file from the example and fill in real values.
cp backend/.env.example .env
nano .env
#   SUPABASE_URL=...                  (the NEW, separate newsfeed Supabase project)
#   SUPABASE_SERVICE_ROLE_KEY=...
#   RESEND_API_KEY=...                (leave blank to disable sending)
#   DEMO_MODE=false                   (real DB in production)
#   RUN_SCHEDULER=true                (enable the 5am daily job)
#   PUBLIC_BASE_URL=https://newsfeed.wetreadwell.com
#   CORS_ORIGINS=https://newsfeed.wetreadwell.com
```

### Run the Supabase migrations (separate project)
Run `supabase/migrations/*.sql` **in numeric order** against the new newsfeed Supabase
project (SQL editor or `psql`). They are idempotent, so re-running is safe.

### Log the `claude` CLI in (one time)
The container bakes the `claude` CLI and persists its login on the `claude_credentials`
volume (`/root/.claude`). Authenticate once so the AI stages work:

```bash
docker compose run --rm treadwell-newsfeed claude login
# follow the prompts; the token persists on the named volume across rebuilds
```

---

## 4. Build + run the container
```bash
cd /opt/treadwell-newsfeed
docker compose up -d --build

# verify (binds to loopback only)
curl -fsS http://127.0.0.1:8890/api/health
```

---

## 5. nginx + TLS
```bash
# Install the server block.
cp deploy/nginx-newsfeed.conf /etc/nginx/sites-available/newsfeed.wetreadwell.com
ln -sf /etc/nginx/sites-available/newsfeed.wetreadwell.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Provision the Let's Encrypt cert (certbot rewrites the block to add 443 + redirect).
certbot --nginx -d newsfeed.wetreadwell.com --redirect \
  --non-interactive --agree-tos -m hanz@wetreadwell.com

nginx -t && systemctl reload nginx
```

Verify end-to-end:

    curl -fsS https://newsfeed.wetreadwell.com/api/health

---

## 6. Updating (after approval)
```bash
cd /opt/treadwell-newsfeed
git pull
docker compose up -d --build
docker compose logs -f --tail=100 treadwell-newsfeed   # watch startup
```

## 7. Operations
- **Manual pipeline run:** `POST https://newsfeed.wetreadwell.com/api/admin/run-pipeline`
  (respects the DB run-lock). The scheduled run fires daily at `PIPELINE_HOUR` (default 5)
  in `PIPELINE_TZ` (`America/Chicago`) when `RUN_SCHEDULER=true`.
- **Logs:** `docker compose logs -f treadwell-newsfeed`
- **Restart:** `docker compose restart treadwell-newsfeed`
- **Health:** `curl https://newsfeed.wetreadwell.com/api/health`

## 8. Rollback
```bash
cd /opt/treadwell-newsfeed
git checkout <previous-good-sha>
docker compose up -d --build
```

---

### Boundaries (do not cross)
- Separate Supabase project, separate container, separate nginx block + cert.
- No imports from `/opt/treadwell` or the proposal tool. Shares only the host box.
- Never scrape LinkedIn; honor `robots.txt`/ToS; rate-limit per host.
