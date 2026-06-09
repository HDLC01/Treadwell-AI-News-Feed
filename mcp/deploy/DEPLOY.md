# Deploy — connector.wetreadwell.com (News Feed custom connector)

> Golden rule: test locally first, deploy only after Hanz approves. This stack is
> **fully separate** from the News Feed: its own dir, container, nginx block, and
> TLS cert. Bringing it up/down never touches the running feed (`/opt/treadwell-newsfeed`).
> It has **no database** — it reads the live feed over HTTPS (read-only).

Port map on the VPS: 8888 proposal · 8890 newsfeed · 8892 roadmap · **8894 connector**.

## 1. DNS (Bluehost, wetreadwell.com zone)
A-record: Type `A`, Host `connector`, Points to `50.6.110.215`, TTL 4h.
Verify: `dig +short connector.wetreadwell.com`.

## 2. Ship the code to the VPS
The repo is private; ship the `mcp/` tree as a tarball (same pattern as the roadmap):
```bash
# from the local mcp/ dir
git archive --format=tar.gz -o /tmp/connector.tgz HEAD .    # or: tar czf with the working tree
scp -i ~/.ssh/treadwell_vps /tmp/connector.tgz root@50.6.110.215:/tmp/
ssh -i ~/.ssh/treadwell_vps root@50.6.110.215
mkdir -p /opt/treadwell-newsfeed-connector && cd /opt/treadwell-newsfeed-connector
tar xzf /tmp/connector.tgz
```

## 3. Configure `.env`
```bash
cp .env.example .env && nano .env
#   NEWSFEED_BASE_URL=https://newsfeed.wetreadwell.com
#   NEWSFEED_CONTACTS_KEY=<the feed's CONTACTS_GATE_PASSWORD, if set>   # else blank
#   MCP_PORT=8894
#   MCP_TRANSPORT=http
#   MCP_PATH_SECRET=<openssl rand -hex 16 | tr -d '\n'>   # the random bit in the URL
#   TREADWELL_SIGNER_NAME / TREADWELL_SIGNER_EMAIL / TREADWELL_PHONE
```
The full connector URL is then:
`https://connector.wetreadwell.com/<MCP_PATH_SECRET>/mcp`

## 4. Build + run
```bash
docker compose up -d --build
docker compose logs -f connector          # "Application startup complete"
curl -fsS http://127.0.0.1:8894/healthz   # {"status":"ok",...,"mcp_path":"/<secret>/mcp"}
```

## 5. nginx + TLS
```bash
cp deploy/nginx-connector.conf /etc/nginx/sites-available/connector.wetreadwell.com
ln -sf /etc/nginx/sites-available/connector.wetreadwell.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d connector.wetreadwell.com --redirect --non-interactive --agree-tos -m hanz@wetreadwell.com
curl -fsS https://connector.wetreadwell.com/healthz
```

## 6. Update flow
```bash
cd /opt/treadwell-newsfeed-connector
# re-ship the tarball (step 2), then:
docker compose up -d --build
```

## Notes
- The container binds `127.0.0.1:8894`; nginx is the only public surface.
- To rotate access: change `MCP_PATH_SECRET` in `.env`, `docker compose up -d`, and
  re-share the new URL. The old URL stops working immediately.
- To make it fully open (no secret in the URL): set `MCP_PATH_SECRET=` (blank). The
  endpoint becomes `https://connector.wetreadwell.com/mcp`.
