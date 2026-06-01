"""
Digests router — list past daily digests and fetch one by date.

DEMO_MODE reads from fixtures. Live mode reads the daily_digest table. Response
shapes match SPEC §4 (DigestSummary[] and the digest detail object).
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from config import settings
from models.schemas import DigestDetail, DigestSummary

router = APIRouter(tags=["digests"])


@router.get("/digests", response_model=List[DigestSummary])
def list_digests() -> List[DigestSummary]:
    """All daily digests as summaries, date descending."""
    if settings.demo_mode:
        from services import fixtures

        return [DigestSummary(**d) for d in fixtures.get_digests()]

    from services.supabase_client import get_supabase, with_supabase_retry

    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("daily_digest")
        .select("digest_date,new_count,updated_count,project_ids")
        .order("digest_date", desc=True)
        .execute()
        .data
    ) or []

    out: List[DigestSummary] = []
    for r in rows:
        out.append(
            DigestSummary(
                digest_date=_date_str(r.get("digest_date")),
                new_count=r.get("new_count", 0),
                updated_count=r.get("updated_count", 0),
                project_count=len(r.get("project_ids") or []),
            )
        )
    return out


@router.get("/digests/{digest_date}", response_model=DigestDetail)
def get_digest(digest_date: str) -> DigestDetail:
    """A single digest by date (YYYY-MM-DD), including its rendered html_body."""
    if settings.demo_mode:
        from services import fixtures

        data = fixtures.get_digest(digest_date)
        if data is None:
            raise HTTPException(status_code=404, detail="Digest not found")
        return DigestDetail(**data)

    from services.supabase_client import get_supabase, with_supabase_retry

    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("daily_digest")
        .select("digest_date,html_body,project_ids,new_count,updated_count")
        .eq("digest_date", digest_date)
        .limit(1)
        .execute()
        .data
    ) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Digest not found")
    r: Dict[str, Any] = rows[0]
    return DigestDetail(
        digest_date=_date_str(r.get("digest_date")),
        html_body=r.get("html_body"),
        project_ids=[str(x) for x in (r.get("project_ids") or [])],
        new_count=r.get("new_count", 0),
        updated_count=r.get("updated_count", 0),
    )


def _date_str(value: Any) -> str:
    """Normalize a date/datetime/str to an ISO date string."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
