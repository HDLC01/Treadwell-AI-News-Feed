# Treadwell AI News Feed — Custom Connector

A **custom Claude connector** (remote MCP server) over the [Treadwell AI News
Feed](https://newsfeed.wetreadwell.com). Add it to **Claude Desktop / claude.ai** and
ask Claude to pull the leads worth chasing, summarize what's new, and draft outreach —
then create the email with your own Gmail connector.

- **Read-only.** It never writes to the feed. (Dedup / "Existing Project" tagging is a
  separate, local job — see the News Feed repo.)
- **Hosted, shareable.** One URL works for you, Kyle, and anyone you share it with.
- **No login to type.** There's a random string *in the URL* so it isn't publicly
  discoverable; there's nothing else to enter.

## Tools
| Tool | What it does |
|---|---|
| `feed_stats` | Top-of-feed counters (total / new / hot / in-radius / data centers). |
| `top_picks` | The leads worth chasing, ranked by relevance. Filters: tiers, radius, type, max distance. |
| `list_projects` | Filterable, paginated feed (q, type, stage, tier, status, sort). |
| `get_project` | Full detail for one project: team, contacts, signals. |
| `project_signals` | The evidence (news / permits / filings) behind a project. |
| `summarize_feed` | A what's-new briefing: counters + latest digest + recent projects. |
| `draft_outreach` | A grounded intro letter `{to, subject, body}` for your Gmail connector to draft. |

## Add it to Claude Desktop (you + Kyle)
1. **Settings → Connectors → Add custom connector**
2. **Name:** `Treadwell News Feed`
3. **URL:** `https://connector.wetreadwell.com/<SECRET>/mcp`
   *(the full URL with the secret — Hanz shares this; nothing else to enter)*
4. **Add.** Done — no sign-in, no token field.

Then just ask Claude things like:
> *"Show me the top 10 hot data-center leads within 70 miles, then draft an intro email
> for the closest one and put it in my Gmail drafts."*

Claude calls `top_picks` → `get_project`/`draft_outreach` here, then `create_draft` on
**your** Gmail connector. You review and send. (Nothing is ever auto-sent.)

> Works in **Claude Desktop** and **claude.ai** (paid plans). Claude Code (cowork) doesn't
> support remote connectors yet — for that, run it locally (below).

## Run locally
```bash
cd "Treadwell AI News Feed/mcp"
cp .env.example .env          # defaults point at the live feed; edit if needed

# Hosted-style (Streamable HTTP) on http://127.0.0.1:8894/<secret>/mcp
MCP_TRANSPORT=http MCP_PATH_SECRET=dev123 uv run newsfeed-mcp

# Or stdio, to register in Claude Code:
#   claude mcp add --transport stdio treadwell-newsfeed -- \
#     uv run --directory "<abs path>/Treadwell AI News Feed/mcp" newsfeed-mcp
#   (set MCP_TRANSPORT=stdio)
```
Point at a local dev feed instead of prod by setting `NEWSFEED_BASE_URL=http://127.0.0.1:8890`.

## Layout
```
mcp/
  newsfeed_mcp/
    feed_client.py   # read-only httpx client for the feed API
    outreach.py      # composes the grounded outreach letter
    server.py        # FastMCP server + the 7 tools + /healthz
  Dockerfile         # tiny single service, no DB
  docker-compose.yml # standalone stack (separate from the feed)
  deploy/            # nginx server block + DEPLOY.md (connector.wetreadwell.com)
```

## Deploy
See [`deploy/DEPLOY.md`](deploy/DEPLOY.md). Separate dir, container, nginx block, and TLS
cert from the News Feed — deploying it never touches the running feed.
