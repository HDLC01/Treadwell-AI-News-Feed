"""
Subscribers router — email signup + one-click unsubscribe.

POST /api/subscribers upserts an email_subscribers row (idempotent on email).
GET /api/unsubscribe?token=... flips subscribed=false and returns a small HTML
confirmation page. In DEMO_MODE both are accepted as no-ops with friendly output.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from config import settings
from models.schemas import OkResponse, SubscribeRequest

router = APIRouter(tags=["subscribers"])

# Linear (no overlapping quantifiers): domain labels exclude '.', so there's no
# ambiguous backtracking between the label classes and the literal dots — avoids
# the polynomial-ReDoS of `[^@\s]+\.[^@\s]+`.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")


def _unsub_page(message: str, ok: bool = True) -> HTMLResponse:
    color = "#1E40AF" if ok else "#DC2626"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Treadwell Radar — Subscription</title>
  <style>
    body {{ font-family: 'Fira Sans', Arial, sans-serif; background: #F8FAFC; color: #0F172A;
            display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
    .card {{ background: #FFFFFF; border: 1px solid #DBEAFE; border-radius: 12px;
             padding: 32px; max-width: 420px; text-align: center;
             box-shadow: 0 1px 3px rgba(15,23,42,.08); }}
    h1 {{ color: {color}; font-size: 20px; margin: 0 0 12px; }}
    p {{ color: #475569; line-height: 1.5; margin: 0; }}
    a {{ color: #1E40AF; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Treadwell Radar</h1>
    <p>{message}</p>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


@router.post("/subscribers", response_model=OkResponse)
def subscribe(body: SubscribeRequest) -> OkResponse:
    """Add (or reactivate) a digest subscriber by email."""
    email = (body.email or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):  # 254 = RFC 5321 max
        raise HTTPException(status_code=422, detail="A valid email address is required.")

    if settings.demo_mode:
        # No DB in demo; accept the signup so the UI can confirm success.
        return OkResponse(ok=True)

    from services.supabase_client import get_supabase, with_supabase_retry

    payload = {
        "email": email,
        "full_name": (body.full_name or None),
        "subscribed": True,
    }
    with_supabase_retry(
        lambda: get_supabase()
        .table("email_subscribers")
        .upsert(payload, on_conflict="email")
        .execute()
    )
    return OkResponse(ok=True)


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(token: str = Query(..., description="unsubscribe_token")) -> HTMLResponse:
    """Flip a subscriber to unsubscribed via their token; returns a confirmation page."""
    if not (token or "").strip():
        return _unsub_page("Missing unsubscribe token.", ok=False)

    if settings.demo_mode:
        return _unsub_page(
            "You're unsubscribed (demo mode — no email was actually on file). "
            "You will no longer receive the daily radar digest."
        )

    from services.supabase_client import get_supabase, with_supabase_retry
    from datetime import datetime, timezone

    try:
        updated = with_supabase_retry(
            lambda: get_supabase()
            .table("email_subscribers")
            .update(
                {
                    "subscribed": False,
                    "unsubscribed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("unsubscribe_token", token)
            .execute()
            .data
        ) or []
    except Exception:  # noqa: BLE001 — always render a friendly page
        updated = []

    if not updated:
        return _unsub_page(
            "We couldn't find that subscription. It may already be removed.", ok=False
        )
    return _unsub_page(
        "You've been unsubscribed. You will no longer receive the daily radar digest."
    )
