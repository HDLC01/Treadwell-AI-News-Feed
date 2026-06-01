"""
Transactional email via Resend.

`send_digest(subscriber, digest)` POSTs one email to the Resend API per subscriber
(never batched — golden rule). It substitutes the per-subscriber unsubscribe token
into the digest's html/text bodies, then sends.

No-op (returns {"skipped": True, ...}) when RESEND_API_KEY is empty so the daily
pipeline runs end-to-end in dev / DEMO_MODE without sending anything. httpx is
imported lazily so this module imports cleanly with no deps installed.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.digest_builder import UNSUBSCRIBE_TOKEN_PLACEHOLDER

log = logging.getLogger("newsfeed.mailer")

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_HTTP_TIMEOUT_S = 30.0


def _settings():
    try:
        from config import settings

        return settings
    except Exception:  # noqa: BLE001
        return None


def _from_header() -> str:
    s = _settings()
    name = getattr(s, "DIGEST_FROM_NAME", "") if s else ""
    email = getattr(s, "DIGEST_FROM_EMAIL", "") if s else ""
    name = name or "Treadwell Radar"
    email = email or "radar@notify.wetreadwell.com"
    return f"{name} <{email}>"


def send_digest(subscriber: dict, digest: dict) -> dict:
    """Send one digest email to one subscriber via Resend.

    Args:
        subscriber: dict with at least {email, unsubscribe_token}. full_name optional.
        digest: dict from digest_builder.build_digest (html_body, text_body, digest_date).

    Returns:
        {"sent": True, "id": <resend_id>, "email": ...} on success,
        {"skipped": True, "reason": ...} when RESEND_API_KEY is empty or no recipient,
        {"error": <str>, "email": ...} on a send failure (never raises — the pipeline
        must keep going for the next subscriber).
    """
    s = _settings()
    api_key = getattr(s, "RESEND_API_KEY", "") if s else ""

    to_email = (subscriber or {}).get("email")
    if not to_email:
        return {"skipped": True, "reason": "no recipient email"}

    if not api_key:
        log.warning("RESEND_API_KEY empty — skipping send to %s (no-op).", to_email)
        return {"skipped": True, "reason": "RESEND_API_KEY empty", "email": to_email}

    token = str((subscriber or {}).get("unsubscribe_token") or "")
    html_body = _inject_token(digest.get("html_body") or "", token)
    text_body = _inject_token(digest.get("text_body") or "", token)

    digest_date = digest.get("digest_date") or ""
    subject = f"Treadwell Radar — {_subject_counts(digest)}{(' · ' + str(digest_date)) if digest_date else ''}"

    payload = {
        "from": _from_header(),
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }

    try:
        import httpx  # lazy

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=_HTTP_TIMEOUT_S) as client:
            resp = client.post(_RESEND_ENDPOINT, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
        msg_id = data.get("id")
        log.info("Resend: digest sent to %s (id=%s).", to_email, msg_id)
        return {"sent": True, "id": msg_id, "email": to_email}
    except Exception as exc:  # noqa: BLE001 — never abort the per-subscriber loop
        log.warning("Resend send failed for %s: %s", to_email, exc)
        return {"error": str(exc), "email": to_email}


def _inject_token(body: str, token: str) -> str:
    """Replace the unsubscribe-token placeholder with the subscriber's real token."""
    if not body:
        return body
    return body.replace(UNSUBSCRIBE_TOKEN_PLACEHOLDER, token)


def _subject_counts(digest: dict) -> str:
    new = digest.get("new_count") or 0
    updated = digest.get("updated_count") or 0
    return f"{new} new, {updated} updated"
