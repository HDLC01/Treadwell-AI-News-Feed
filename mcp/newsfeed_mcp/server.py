"""Treadwell AI News Feed — custom connector (remote MCP server).

Exposes the News Feed (read-only) as MCP tools that work in Claude Desktop / web:
top picks, filtered project pulls, project detail, signals, a feed summary, and a
grounded outreach-draft composer (handed to the user's Gmail connector to draft).

Transport:
  * MCP_TRANSPORT=http  -> Streamable HTTP at /<MCP_PATH_SECRET>/mcp  (the connector)
  * MCP_TRANSPORT=stdio -> local stdio (handy for `claude mcp add` testing)

Run:  uv run newsfeed-mcp        (reads .env in this directory)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()  # read mcp/.env if present (Docker passes env directly; this is a no-op then)

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from newsfeed_mcp.feed_client import FeedClient
from newsfeed_mcp.outreach import compose_outreach, pick_contact

# ─── config ──────────────────────────────────────────────────────────────────
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8894"))
SECRET = os.environ.get("MCP_PATH_SECRET", "").strip().strip("/")
MCP_PATH = f"/{SECRET}/mcp" if SECRET else "/mcp"

feed = FeedClient()

INSTRUCTIONS = (
    "Read-only access to the Treadwell AI News Feed — a project-first construction-"
    "opportunity radar for commercial flooring leads around Kansas City. Use top_picks "
    "to surface the leads worth chasing, get_project for full detail (team + contacts + "
    "signals), summarize_feed for a what's-new briefing, and draft_outreach to compose an "
    "intro letter — then create the draft with the user's Gmail connector (never auto-send)."
)

mcp = FastMCP(
    "Treadwell AI News Feed",
    instructions=INSTRUCTIONS,
    host=HOST,
    port=PORT,
    streamable_http_path=MCP_PATH,
    stateless_http=True,
)


# ─── trimming helpers (keep tool payloads tight) ──────────────────────────────
_SUMMARY_FIELDS = (
    "id", "title", "project_type", "stage", "city", "state", "distance_mi",
    "within_70mi", "in_radius", "relevance_score", "relevance_tier",
    "team_confidence", "top_team_member", "signals_count", "est_megawatts",
    "est_value_usd", "est_sqft", "status", "last_signal_at", "first_seen_at",
)


def _trim_summary(p: Dict[str, Any]) -> Dict[str, Any]:
    return {k: p.get(k) for k in _SUMMARY_FIELDS}


def _redact_contacts(contacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Blank email/phone for do_not_contact records before they leave the
    system — the flag is surfaced, but never the address needed to violate it."""
    out: List[Dict[str, Any]] = []
    for c in contacts or []:
        if c.get("do_not_contact"):
            c = {**c, "email": None, "phone": None, "suppressed": "do_not_contact"}
        out.append(c)
    return out


def _passes(p: Dict[str, Any], project_types: Optional[List[str]], max_distance_mi: Optional[float]) -> bool:
    if project_types and (p.get("project_type") or "") not in project_types:
        return False
    if max_distance_mi is not None:
        d = p.get("distance_mi")
        if d is None or float(d) > max_distance_mi:
            return False
    return True


# ─── tools ─────────────────────────────────────────────────────────────────
@mcp.tool()
def feed_stats() -> Dict[str, Any]:
    """Top-of-feed counters: total / new / today / hot / in-radius / within-70mi / data-centers."""
    return feed.stats()


@mcp.tool()
def top_picks(
    limit: int = 10,
    tiers: str = "hot,warm",
    in_radius_only: bool = True,
    project_types: Optional[str] = None,
    max_distance_mi: Optional[float] = None,
) -> Dict[str, Any]:
    """The leads worth chasing, ranked by relevance. Returns {count, picks}.

    Args:
        limit: max projects to return.
        tiers: CSV of relevance tiers to include (hot, warm, cold).
        in_radius_only: only projects inside Treadwell's priority radius.
        project_types: optional CSV filter (e.g. "data_center,warehouse").
        max_distance_mi: optional hard cap on distance from Kansas City.
    """
    env = feed.list_projects(
        tier=tiers or None,
        in_radius=True if in_radius_only else None,
        sort="relevance",
        page=1,
        page_size=100,
    )
    types = [t.strip() for t in project_types.split(",")] if project_types else None
    items = [p for p in env.get("items", []) if _passes(p, types, max_distance_mi)]
    picks = [_trim_summary(p) for p in items[: max(1, limit)]]
    return {"count": len(picks), "picks": picks}


@mcp.tool()
def list_projects(
    q: Optional[str] = None,
    project_type: Optional[str] = None,
    stage: Optional[str] = None,
    tier: Optional[str] = None,
    status: Optional[str] = None,
    in_radius: Optional[bool] = None,
    sort: str = "relevance",
    page: int = 1,
    page_size: int = 25,
) -> Dict[str, Any]:
    """Filterable, paginated project feed (25/page). CSV allowed for project_type,
    stage, tier, status. sort ∈ relevance|distance|recent. Returns items + paging."""
    env = feed.list_projects(
        q=q, project_type=project_type, stage=stage, tier=tier, status=status,
        in_radius=in_radius, sort=sort, page=page, page_size=page_size,
    )
    env["items"] = [_trim_summary(p) for p in env.get("items", [])]
    return env


@mcp.tool()
def get_project(
    project_id: str,
    include_signals: bool = True,
    include_contacts: bool = True,
) -> Dict[str, Any]:
    """Full detail for one project: summary, location, team, and (optionally) the
    evidence signals and known contacts."""
    detail = feed.get_project(project_id)
    if include_signals:
        try:
            detail["signals"] = feed.get_signals(project_id)
        except Exception as exc:  # noqa: BLE001
            detail["signals_error"] = str(exc)
    if include_contacts:
        try:
            detail["contacts"] = _redact_contacts(feed.get_contacts(project_id))
        except Exception as exc:  # noqa: BLE001
            detail["contacts_error"] = str(exc)
    return detail


@mcp.tool()
def project_signals(project_id: str) -> Dict[str, Any]:
    """Evidence (news / permits / filings) attached to a project, newest first.
    Returns {project_id, count, signals}."""
    sigs = feed.get_signals(project_id)
    return {"project_id": project_id, "count": len(sigs), "signals": sigs}


@mcp.tool()
def summarize_feed(recent_limit: int = 12) -> Dict[str, Any]:
    """A what's-new briefing: feed counters, the latest daily digest summary, and the
    most recently active projects — for the model to narrate into a short summary."""
    out: Dict[str, Any] = {}
    try:
        out["stats"] = feed.stats()
    except Exception as exc:  # noqa: BLE001
        out["stats_error"] = str(exc)
    try:
        digests = feed.list_digests()
        out["latest_digest"] = digests[0] if digests else None
    except Exception as exc:  # noqa: BLE001
        out["digests_error"] = str(exc)
    try:
        env = feed.list_projects(sort="recent", page=1, page_size=max(1, recent_limit))
        out["recent_projects"] = [_trim_summary(p) for p in env.get("items", [])]
    except Exception as exc:  # noqa: BLE001
        out["recent_error"] = str(exc)
    return out


@mcp.tool()
def draft_outreach(
    project_id: str,
    contact_id: Optional[str] = None,
    signer_name: Optional[str] = None,
    signer_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose a grounded intro/outreach letter for a project.

    Returns {to, subject, body, rationale, warnings}. It does NOT send — hand the
    result to your Gmail connector's create_draft and review before sending. If a
    contact is flagged do_not_contact or has no email, that's surfaced in warnings.

    Args:
        project_id: the feed project to write about.
        contact_id: optional specific contact id; otherwise the best contact is chosen.
        signer_name / signer_email: who the letter is from (defaults from config).
    """
    detail = feed.get_project(project_id)
    # Never pitch a project Treadwell already has (matched to the Dropbox pipeline).
    if (detail.get("status") or "") == "existing":
        return {
            "skipped": True,
            "reason": "This project is already in Treadwell's pipeline (existing bid or owned) - not pitching.",
            "project": {"id": detail.get("id"), "title": detail.get("title"), "status": "existing"},
        }
    team = detail.get("team") or []
    try:
        contacts = feed.get_contacts(project_id)
    except Exception:  # noqa: BLE001
        contacts = []
    contact = pick_contact(contacts, team, contact_id)
    draft = compose_outreach(detail, contact, signer_name, signer_email)
    draft["project"] = {
        "id": detail.get("id"),
        "title": detail.get("title"),
        "project_type": detail.get("project_type"),
        "stage": detail.get("stage"),
        "city": detail.get("city"),
        "state": detail.get("state"),
    }
    draft["next_step"] = (
        "Review, then create a draft with your Gmail connector "
        "(create_draft: to/subject/body above). Do not auto-send."
    )
    return draft


# ─── health route (for nginx / uptime checks) ────────────────────────────────
@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    # Public endpoint — never echo the secret path or the internal feed URL.
    return JSONResponse(
        {"status": "ok", "service": "treadwell-newsfeed-mcp", "configured": bool(SECRET)}
    )


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "http").lower()
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
