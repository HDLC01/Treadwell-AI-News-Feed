"""
Daily digest builder.

Selects in-radius projects first-seen or materially updated on `for_date` with a
hot/warm tier (data centers first, then by score), and renders an email-ready
digest as project CARDS (NOT a flat article list) plus a plain-text alternative.

Returns a dict matching the daily_digest insert shape:
    {digest_date, project_ids, new_count, updated_count, html_body, text_body}

HTML is inline-styled for email clients and ends with an unsubscribe link using the
`{PUBLIC_BASE_URL}/api/unsubscribe?token={UNSUBSCRIBE_TOKEN}` placeholder (mailer.py
substitutes the per-subscriber token at send time).

Reads via supabase_client; imports cleanly with no DB configured.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from services.supabase_client import get_supabase, with_supabase_retry

log = logging.getLogger("newsfeed.digest")

# Placeholder the mailer replaces per subscriber.
UNSUBSCRIBE_TOKEN_PLACEHOLDER = "{UNSUBSCRIBE_TOKEN}"

# ── Design tokens (email-safe subset of SPEC §5) ──
_C_BG = "#F8FAFC"
_C_SURFACE = "#FFFFFF"
_C_FG = "#0F172A"
_C_MUTED = "#475569"
_C_BORDER = "#DBEAFE"
_C_PRIMARY = "#1E40AF"
_C_ACCENT = "#D97706"
_TIER_COLOR = {"hot": "#DC2626", "warm": "#D97706", "cold": "#64748B"}

_HUMAN_TYPE = {
    "data_center": "Data Center",
    "industrial": "Industrial",
    "healthcare": "Healthcare",
    "higher_ed": "Higher Ed",
    "distribution": "Distribution",
    "manufacturing": "Manufacturing",
    "mission_critical": "Mission Critical",
    "other_commercial": "Commercial",
}
_HUMAN_STAGE = {
    "rumored": "Rumored",
    "planning": "Planning",
    "design": "Design",
    "permitting": "Permitting",
    "procurement": "Procurement",
    "pre_bid": "Pre-Bid",
    "under_construction": "Under Construction",
    "complete": "Complete",
    "dead": "Dead",
}
_HUMAN_TEAM = {
    "gc_named": "GC named",
    "developer_named": "Developer named",
    "owner_only": "Owner only",
    "unknown": "Team unknown",
}


def _public_base_url() -> str:
    try:
        from config import settings

        return getattr(settings, "PUBLIC_BASE_URL", "") or "https://newsfeed.wetreadwell.com"
    except Exception:  # noqa: BLE001
        return "https://newsfeed.wetreadwell.com"


def build_digest(for_date: date) -> dict:
    """Build the digest dict for `for_date`. Reads projects from Supabase.

    `for_date` MUST be the LOCAL (Central) calendar date — the selection window
    and the new/updated split are both computed in that timezone.

    Selection: in_radius, tier in (hot, warm), and last_signal_at falls within
    the Central day. Ordering: data centers first, then by relevance_score desc.
    Splits new vs updated by whether first_seen_at is on for_date (Central).
    """
    if isinstance(for_date, datetime):
        for_date = for_date.date()
    next_day = _add_one_day(for_date)
    # for_date is the LOCAL (Central) calendar day. Build the selection window as
    # Central midnight .. next Central midnight, converted to UTC, so it matches
    # the UTC-stored last_signal_at against Kyle's day — not the UTC host day.
    from datetime import time as _time

    _tz = _local_tz()
    lo = datetime.combine(for_date, _time(), _tz).astimezone(timezone.utc).isoformat()
    hi = datetime.combine(next_day, _time(), _tz).astimezone(timezone.utc).isoformat()

    # Pull candidate in-radius hot/warm projects active in the window.
    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .select(
            "id, title, summary, project_type, stage, city, state, county, distance_mi, "
            "in_radius, relevance_score, relevance_tier, team_confidence, est_value_usd, "
            "est_sqft, est_megawatts, first_seen_at, last_signal_at"
        )
        .eq("in_radius", True)
        .in_("relevance_tier", ["hot", "warm"])
        .gte("last_signal_at", lo)
        .lt("last_signal_at", hi)
        .order("relevance_score", desc=True)
        .execute()
        .data
    )
    rows = rows or []

    # Data centers first, then by score desc (stable within score by sort key).
    rows.sort(key=lambda p: (0 if p.get("project_type") == "data_center" else 1, -(p.get("relevance_score") or 0)))

    new_rows, updated_rows = [], []
    for p in rows:
        if _on_date(p.get("first_seen_at"), for_date):
            new_rows.append(p)
        else:
            updated_rows.append(p)

    project_ids = [p["id"] for p in rows]
    html_body = _render_html(for_date, new_rows, updated_rows)
    text_body = _render_text(for_date, new_rows, updated_rows)

    return {
        "digest_date": for_date.isoformat(),
        "project_ids": project_ids,
        "new_count": len(new_rows),
        "updated_count": len(updated_rows),
        "html_body": html_body,
        "text_body": text_body,
    }


# ─── Rendering ───────────────────────────────────────────────────────────
def _render_html(for_date: date, new_rows: list[dict], updated_rows: list[dict]) -> str:
    base = _public_base_url()
    unsub = f"{base}/api/unsubscribe?token={UNSUBSCRIBE_TOKEN_PLACEHOLDER}"

    sections = []
    if new_rows:
        sections.append(_html_section("New opportunities", new_rows, base))
    if updated_rows:
        sections.append(_html_section("Updated opportunities", updated_rows, base))
    if not sections:
        sections.append(
            f'<p style="color:{_C_MUTED};font-family:Arial,Helvetica,sans-serif;">'
            "No new in-radius opportunities today.</p>"
        )

    header = (
        f'<div style="background:{_C_PRIMARY};padding:20px 24px;">'
        f'<span style="color:#FFFFFF;font-family:Arial,Helvetica,sans-serif;font-size:20px;'
        f'font-weight:700;">Treadwell Radar</span><br/>'
        f'<span style="color:#DBEAFE;font-family:Arial,Helvetica,sans-serif;font-size:13px;">'
        f'Project digest &middot; {for_date.isoformat()} &middot; '
        f'{len(new_rows)} new, {len(updated_rows)} updated</span></div>'
    )

    footer = (
        f'<div style="padding:18px 24px;border-top:1px solid {_C_BORDER};'
        f'font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{_C_MUTED};">'
        f'You are receiving the Treadwell construction-opportunity radar. '
        f'<a href="{unsub}" style="color:{_C_PRIMARY};">Unsubscribe</a>.'
        f'</div>'
    )

    body = "".join(sections)
    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1.0"></head>'
        f'<body style="margin:0;padding:0;background:{_C_BG};">'
        f'<div style="max-width:640px;margin:0 auto;background:{_C_SURFACE};">'
        f'{header}'
        f'<div style="padding:8px 24px 24px 24px;">{body}</div>'
        f'{footer}'
        f'</div></body></html>'
    )


def _html_section(heading: str, rows: list[dict], base: str) -> str:
    cards = "".join(_html_card(p, base) for p in rows)
    return (
        f'<h2 style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
        f'text-transform:uppercase;letter-spacing:0.04em;color:{_C_MUTED};'
        f'margin:24px 0 8px 0;">{_esc(heading)}</h2>{cards}'
    )


def _html_card(p: dict, base: str) -> str:
    tier = (p.get("relevance_tier") or "cold").lower()
    tier_color = _TIER_COLOR.get(tier, _C_MUTED)
    ptype = _HUMAN_TYPE.get(p.get("project_type"), p.get("project_type") or "Project")
    stage = _HUMAN_STAGE.get(p.get("stage"), p.get("stage") or "—")
    team = _HUMAN_TEAM.get(p.get("team_confidence"), "Team unknown")
    loc = ", ".join([x for x in [p.get("city"), p.get("state")] if x]) or "Location TBD"
    dist = p.get("distance_mi")
    dist_str = f"{dist:.0f} mi from KC" if isinstance(dist, (int, float)) else ""
    score = p.get("relevance_score")
    url = f"{base}/project/{p.get('id')}"

    facts = []
    if p.get("est_megawatts"):
        facts.append(f"{_fmt_num(p['est_megawatts'])} MW")
    if p.get("est_value_usd"):
        facts.append(_fmt_money(p["est_value_usd"]))
    if p.get("est_sqft"):
        facts.append(f"{_fmt_num(p['est_sqft'])} sqft")
    facts_str = " &middot; ".join(facts)

    summary = _esc((p.get("summary") or "")[:240])

    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid {_C_BORDER};border-radius:8px;margin:10px 0;">'
        f'<tr><td style="padding:14px 16px;">'
        # tier dot + type + score
        f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{_C_MUTED};">'
        f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
        f'background:{tier_color};margin-right:6px;"></span>'
        f'<span style="color:{tier_color};font-weight:700;text-transform:uppercase;">{tier}</span>'
        f' &middot; {_esc(ptype)} &middot; {_esc(stage)}'
        + (f' &middot; <b style="color:{_C_FG};">{score}</b>/100' if score is not None else "")
        + "</div>"
        # title
        f'<a href="{url}" style="font-family:Arial,Helvetica,sans-serif;font-size:17px;'
        f'font-weight:700;color:{_C_PRIMARY};text-decoration:none;display:block;margin:6px 0 2px 0;">'
        f'{_esc(p.get("title") or "Untitled project")}</a>'
        # location + distance
        f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{_C_FG};">'
        f'{_esc(loc)}'
        + (f' &middot; <span style="color:{_C_MUTED};">{dist_str}</span>' if dist_str else "")
        + "</div>"
        # team confidence
        f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{_C_MUTED};'
        f'margin-top:4px;">{_esc(team)}</div>'
        + (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{_C_FG};margin-top:8px;">{summary}</div>' if summary else "")
        + (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{_C_ACCENT};margin-top:8px;font-weight:600;">{facts_str}</div>' if facts_str else "")
        + f'</td></tr></table>'
    )


def _render_text(for_date: date, new_rows: list[dict], updated_rows: list[dict]) -> str:
    base = _public_base_url()
    lines = [
        "TREADWELL RADAR — Project digest",
        for_date.isoformat(),
        f"{len(new_rows)} new, {len(updated_rows)} updated",
        "",
    ]
    if new_rows:
        lines.append("== NEW OPPORTUNITIES ==")
        lines.extend(_text_card(p, base) for p in new_rows)
        lines.append("")
    if updated_rows:
        lines.append("== UPDATED OPPORTUNITIES ==")
        lines.extend(_text_card(p, base) for p in updated_rows)
        lines.append("")
    if not new_rows and not updated_rows:
        lines.append("No new in-radius opportunities today.")
        lines.append("")
    lines.append(f"Unsubscribe: {base}/api/unsubscribe?token={UNSUBSCRIBE_TOKEN_PLACEHOLDER}")
    return "\n".join(lines)


def _text_card(p: dict, base: str) -> str:
    tier = (p.get("relevance_tier") or "cold").upper()
    ptype = _HUMAN_TYPE.get(p.get("project_type"), p.get("project_type") or "Project")
    stage = _HUMAN_STAGE.get(p.get("stage"), p.get("stage") or "-")
    loc = ", ".join([x for x in [p.get("city"), p.get("state")] if x]) or "Location TBD"
    dist = p.get("distance_mi")
    dist_str = f" ({dist:.0f} mi)" if isinstance(dist, (int, float)) else ""
    score = p.get("relevance_score")
    score_str = f" [{score}/100]" if score is not None else ""
    url = f"{base}/project/{p.get('id')}"
    return (
        f"- [{tier}] {p.get('title') or 'Untitled project'}{score_str}\n"
        f"    {ptype} / {stage} / {_HUMAN_TEAM.get(p.get('team_confidence'), 'Team unknown')}\n"
        f"    {loc}{dist_str}\n"
        f"    {url}"
    )


# ─── small helpers ─────────────────────────────────────────────────────────
def _add_one_day(d: date) -> date:
    from datetime import timedelta

    return d + timedelta(days=1)


def _local_tz():
    """Pipeline's local timezone (America/Chicago by default); UTC if unresolved."""
    try:
        from zoneinfo import ZoneInfo
        from config import settings

        return ZoneInfo(getattr(settings, "PIPELINE_TZ", "America/Chicago"))
    except Exception:  # noqa: BLE001
        return timezone.utc


def _on_date(iso: Optional[str], target: date) -> bool:
    """True if UTC-stored timestamp `iso` falls on `target` in LOCAL (Central)
    time. `target` is a Central calendar date, so compare in Central, not UTC."""
    if not iso:
        return False
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_local_tz()).date() == target
    except (ValueError, TypeError):
        return False


def _fmt_money(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if n >= 1_000_000_000:
        return f"${n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"${n / 1_000_000:.0f}M"
    if n >= 1_000:
        return f"${n / 1_000:.0f}K"
    return f"${n:.0f}"


def _fmt_num(v) -> str:
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def _esc(s) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
