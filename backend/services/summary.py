"""
Daily "top hottest opportunities" summary email (Kyle's 6 AM ask).

Selects the top N hottest in-range projects (within-70 first, then relevance score),
renders a branded HTML/text email with each project's 1-2 sentence summary + its
source article link(s), and sends via Resend to SUMMARY_TO_EMAILS.

No-op (returns {"skipped": True, ...}) without DB or RESEND_API_KEY. Never raises
into the caller. httpx is imported lazily.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.supabase_client import get_supabase, is_configured, with_supabase_retry

log = logging.getLogger("newsfeed.summary")

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_SITE = "https://newsfeed.wetreadwell.com"

_PRIMARY, _ACCENT, _FG, _MUTED, _BORDER = "#1E40AF", "#D97706", "#0F172A", "#475569", "#DBEAFE"
_TIER = {"hot": "#DC2626", "warm": "#D97706", "cold": "#64748B"}
_TYPE = {
    "data_center": "Data Center", "industrial": "Industrial", "healthcare": "Healthcare",
    "higher_ed": "Higher Ed", "distribution": "Distribution", "manufacturing": "Manufacturing",
    "mission_critical": "Mission Critical", "other_commercial": "Commercial",
}


def _settings():
    from config import settings

    return settings


def _esc(s) -> str:
    return ("" if s is None else str(s)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_and_send_hot_summary() -> dict:
    """Build + send the top-hottest summary. Returns a result dict; never raises."""
    if not is_configured():
        return {"skipped": True, "reason": "no DB configured"}
    s = _settings()
    api_key = getattr(s, "RESEND_API_KEY", "") or ""
    recipients = s.summary_to_list
    if not api_key:
        return {"skipped": True, "reason": "RESEND_API_KEY empty"}
    if not recipients:
        return {"skipped": True, "reason": "no recipients"}

    count = int(getattr(s, "SUMMARY_COUNT", 5) or 5)
    threshold = float(getattr(s, "OTHER_RADIUS_MI", 70) or 70)

    try:
        rows = with_supabase_retry(
            lambda: get_supabase()
            .table("projects")
            .select(
                "id, title, summary, relevance_reasoning, project_type, stage, city, state, "
                "distance_mi, relevance_score, relevance_tier"
            )
            .is_("merged_into", "null")
            .in_("relevance_tier", ["hot", "warm"])
            .not_.in_("status", ["archived", "dismissed"])
            .order("relevance_score", desc=True)
            .limit(60)
            .execute()
            .data
        ) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("hot summary query failed: %s", exc)
        return {"error": str(exc)}

    def w70(r: dict) -> bool:
        d = r.get("distance_mi")
        return d is not None and d <= threshold

    rows.sort(key=lambda r: (not w70(r), -(r.get("relevance_score") or 0)))
    top = rows[:count]
    if not top:
        return {"skipped": True, "reason": "no hot/warm projects"}

    for p in top:
        pid = p["id"]
        try:
            sigs = with_supabase_retry(
                lambda: get_supabase()
                .table("signals")
                .select("title, url, published_at, sources(name)")
                .eq("project_id", pid)
                .order("published_at", desc=True)
                .limit(3)
                .execute()
                .data
            ) or []
        except Exception:  # noqa: BLE001
            sigs = []
        p["_articles"] = [x for x in sigs if x.get("url")][:2]

    html, text, subject = _render(top, w70)

    payload = {
        "from": f"{s.SUMMARY_FROM_NAME} <{s.SUMMARY_FROM_EMAIL}>",
        "to": recipients,
        "reply_to": s.SUMMARY_REPLY_TO,
        "subject": subject,
        "html": html,
        "text": text,
    }
    try:
        import httpx  # lazy

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                _RESEND_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
        log.info("hot summary sent to %s (id=%s)", recipients, data.get("id"))
        return {"sent": True, "id": data.get("id"), "count": len(top), "recipients": recipients}
    except Exception as exc:  # noqa: BLE001
        log.warning("hot summary send failed: %s", exc)
        return {"error": str(exc), "recipients": recipients}


def _today() -> str:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(getattr(_settings(), "PIPELINE_TZ", "America/Chicago"))
        return datetime.now(tz).strftime("%b %d, %Y")
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc).strftime("%b %d, %Y")


def _render(top: list[dict], w70) -> tuple[str, str, str]:
    today = _today()
    cards = []
    for p in top:
        tier = (p.get("relevance_tier") or "cold").lower()
        tc = _TIER.get(tier, _MUTED)
        desc = (p.get("summary") or (p.get("relevance_reasoning") or {}).get("summary") or "").strip()
        loc = ", ".join([x for x in [p.get("city"), p.get("state")] if x]) or "Location TBD"
        d = p.get("distance_mi")
        dist = f"{d:.0f} mi from KC" if isinstance(d, (int, float)) else ""
        within = w70(p)
        badge = (
            f'<span style="background:{"#DCFCE7" if within else "#F1F5F9"};color:{"#166534" if within else _MUTED};'
            f'font-size:11px;font-weight:700;padding:2px 7px;border-radius:10px;">'
            f'{"WITHIN 70 MI" if within else "OUTSIDE 70 MI"}</span>'
        )
        arts = "".join(
            f'<div style="font-size:13px;margin-top:3px;">&#128240; '
            f'<a href="{_esc(a.get("url"))}" style="color:{_PRIMARY};">'
            f'{_esc((a.get("title") or a.get("url") or "")[:90])}</a>'
            + (f' &middot; {_esc((a.get("sources") or {}).get("name"))}' if (a.get("sources") or {}).get("name") else "")
            + "</div>"
            for a in p.get("_articles", [])
        ) or f'<div style="font-size:12px;color:{_MUTED};margin-top:3px;">(no source link yet)</div>'
        score = p.get("relevance_score")
        cards.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {_BORDER};border-radius:8px;margin:12px 0;">'
            f'<tr><td style="padding:14px 16px;font-family:Arial,Helvetica,sans-serif;">'
            f'<div style="font-size:12px;color:{_MUTED};">'
            f'<span style="color:{tc};font-weight:700;text-transform:uppercase;">{tier}</span>'
            + (f' &middot; <b style="color:{_FG};">{score}</b>/100' if score is not None else "")
            + f' &middot; {_esc(_TYPE.get(p.get("project_type"), p.get("project_type")))} &nbsp; {badge}</div>'
            f'<a href="{_SITE}/project/{p["id"]}" style="font-size:17px;font-weight:700;color:{_PRIMARY};text-decoration:none;display:block;margin:6px 0 2px;">{_esc(p.get("title") or "Untitled")}</a>'
            f'<div style="font-size:13px;color:{_FG};">{_esc(loc)}'
            + (f' &middot; <span style="color:{_MUTED};">{dist}</span>' if dist else "")
            + "</div>"
            + (f'<div style="font-size:13px;color:{_FG};margin-top:8px;">{_esc(desc[:280])}</div>' if desc else "")
            + f'<div style="margin-top:8px;">{arts}</div>'
            + "</td></tr></table>"
        )

    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>'
        '<body style="margin:0;background:#F8FAFC;"><div style="max-width:640px;margin:0 auto;background:#FFFFFF;">'
        f'<div style="background:{_PRIMARY};padding:20px 24px;font-family:Arial,Helvetica,sans-serif;">'
        '<span style="color:#FFFFFF;font-size:20px;font-weight:700;">Treadwell Radar</span><br/>'
        f'<span style="color:#DBEAFE;font-size:13px;">Top {len(top)} hottest opportunities &middot; {today}</span></div>'
        f'<div style="padding:8px 24px 24px;">{"".join(cards)}'
        f'<div style="margin-top:18px;font-family:Arial,Helvetica,sans-serif;font-size:13px;"><a href="{_SITE}" style="color:{_ACCENT};font-weight:700;">View the full radar &rarr;</a></div></div>'
        f'<div style="padding:16px 24px;border-top:1px solid {_BORDER};font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{_MUTED};">Daily summary from the Treadwell construction-opportunity radar.</div>'
        "</div></body></html>"
    )

    lines = [f"TREADWELL RADAR — Top {len(top)} hottest opportunities — {today}", ""]
    for p in top:
        loc = ", ".join([x for x in [p.get("city"), p.get("state")] if x]) or "Location TBD"
        d = p.get("distance_mi")
        dist = f" ({d:.0f} mi)" if isinstance(d, (int, float)) else ""
        desc = (p.get("summary") or (p.get("relevance_reasoning") or {}).get("summary") or "").strip()
        lines.append(f"[{(p.get('relevance_tier') or '').upper()} {p.get('relevance_score')}] {p.get('title')}{dist} {'<=70mi' if w70(p) else ''}")
        lines.append(f"  {loc} — {_SITE}/project/{p['id']}")
        if desc:
            lines.append(f"  {desc[:240]}")
        for a in p.get("_articles", []):
            lines.append(f"  - {a.get('url')}")
        lines.append("")
    lines.append(f"Full radar: {_SITE}")

    subject = f"Treadwell Radar — Top {len(top)} hottest opportunities — {today}"
    return html, "\n".join(lines), subject
