"""
Projects router — the project-first feed, detail, signals, status, merge, stats.

In DEMO_MODE every endpoint reads from services/fixtures.py. When Supabase is
configured, the same shapes are assembled from the DB via supabase_client
(always through with_supabase_retry). All response keys match SPEC section 4.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from config import settings
from models.schemas import (
    MergeRequest,
    MergeResponse,
    ProjectDetail,
    ProjectListEnvelope,
    ProjectSummary,
    Signal,
    Stats,
    StatusUpdate,
)

router = APIRouter(tags=["projects"])

# Role priority for choosing the "top" team member on a summary card.
_ROLE_PRIORITY = {
    "general_contractor": 0,
    "developer": 1,
    "owner": 2,
    "end_user": 3,
    "construction_manager": 4,
    "architect": 5,
    "engineer": 6,
    "utility": 7,
    "other": 8,
}

_VALID_STATUSES = {"new", "active", "watching", "pursuing", "won", "passed", "archived", "dismissed"}


def _within_70(distance_mi) -> Optional[bool]:
    """True if within the 70-mile priority radius of the office; None if distance unknown."""
    if distance_mi is None:
        return None
    try:
        return float(distance_mi) <= settings.OTHER_RADIUS_MI
    except (TypeError, ValueError):
        return None


# ─── DB helpers (only used when Supabase configured) ─────────────────────
def _sb():
    from services.supabase_client import get_supabase

    return get_supabase()


def _retry(op):
    from services.supabase_client import with_supabase_retry

    return with_supabase_retry(op)


def _top_team_member(team: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    active = [m for m in team if not m.get("superseded")]
    if not active:
        return None
    best = sorted(
        active,
        key=lambda m: (_ROLE_PRIORITY.get(m.get("role", ""), 99), -(m.get("confidence") or 0)),
    )[0]
    return {
        "company_name": best.get("company_name"),
        "role": best.get("role"),
        "confidence_label": best.get("confidence_label"),
    }


def _team_rows_for(project_id: str) -> List[Dict[str, Any]]:
    """Fetch project_team rows joined to companies for a project (live mode)."""
    rows = _retry(
        lambda: _sb()
        .table("project_team")
        .select("*, companies(id,name,company_type,is_hyperscaler)")
        .eq("project_id", project_id)
        .eq("superseded", False)
        .execute()
        .data
    ) or []
    out = []
    for r in rows:
        co = r.get("companies") or {}
        out.append(
            {
                "company_id": r.get("company_id"),
                "company_name": co.get("name"),
                "company_type": co.get("company_type", "unknown"),
                "role": r.get("role"),
                "confidence": r.get("confidence", 0.5),
                "confidence_label": r.get("confidence_label", "rumored"),
                "is_hyperscaler": bool(co.get("is_hyperscaler")),
                "superseded": r.get("superseded", False),
            }
        )
    return out


def _signals_count(project_id: str) -> int:
    res = _retry(
        lambda: _sb()
        .table("signals")
        .select("id", count="exact")
        .eq("project_id", project_id)
        .execute()
    )
    return getattr(res, "count", None) or len(getattr(res, "data", []) or [])


def _contacts_count(project_id: str) -> int:
    res = _retry(
        lambda: _sb()
        .table("contacts")
        .select("id", count="exact")
        .eq("project_id", project_id)
        .execute()
    )
    return getattr(res, "count", None) or len(getattr(res, "data", []) or [])


def _row_to_summary(p: Dict[str, Any]) -> Dict[str, Any]:
    team = _team_rows_for(p["id"])
    return {
        "id": p["id"],
        "title": p.get("title"),
        "project_type": p.get("project_type"),
        "stage": p.get("stage"),
        "city": p.get("city"),
        "state": p.get("state"),
        "county": p.get("county"),
        "distance_mi": p.get("distance_mi"),
        "in_radius": p.get("in_radius"),
        "within_70mi": _within_70(p.get("distance_mi")),
        "relevance_score": p.get("relevance_score"),
        "relevance_tier": p.get("relevance_tier"),
        "team_confidence": p.get("team_confidence", "unknown"),
        "top_team_member": _top_team_member(team),
        "signals_count": _signals_count(p["id"]),
        "est_megawatts": p.get("est_megawatts"),
        "est_value_usd": p.get("est_value_usd"),
        "est_sqft": p.get("est_sqft"),
        "status": p.get("status", "new"),
        "notes": p.get("notes"),
        "last_signal_at": p.get("last_signal_at"),
        "first_seen_at": p.get("first_seen_at"),
    }


def _row_to_detail(p: Dict[str, Any]) -> Dict[str, Any]:
    summary = _row_to_summary(p)
    team = _team_rows_for(p["id"])
    summary.update(
        {
            "summary": p.get("summary"),
            "address": p.get("address"),
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "relevance_reasoning": p.get("relevance_reasoning"),
            "team": [{k: v for k, v in m.items() if k != "superseded"} for m in team],
            "contacts_count": _contacts_count(p["id"]),
        }
    )
    return summary


# ─── Endpoints ───────────────────────────────────────────────────────────
@router.get("/projects", response_model=ProjectListEnvelope)
def list_projects(
    q: Optional[str] = Query(None),
    project_type: Optional[str] = Query(None, description="csv"),
    stage: Optional[str] = Query(None, description="csv"),
    in_radius: Optional[bool] = Query(None),
    tier: Optional[str] = Query(None, description="csv of hot/warm/cold"),
    team_confidence: Optional[str] = Query(None, description="csv"),
    status: Optional[str] = Query(None, description="csv; default excludes archived,dismissed"),
    sort: str = Query("relevance", pattern="^(relevance|distance|recent)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> ProjectListEnvelope:
    """Paginated, filterable project feed (25/page by default)."""
    filters = {
        "q": q,
        "project_type": project_type,
        "stage": stage,
        "in_radius": in_radius,
        "tier": tier,
        "team_confidence": team_confidence,
        "status": status,
        "sort": sort,
        "page": page,
        "page_size": page_size,
    }

    if settings.demo_mode:
        from services import fixtures

        return ProjectListEnvelope(**fixtures.list_projects(filters))

    # ── Live Supabase path ──
    def _csv(v: Optional[str]) -> Optional[List[str]]:
        if not v:
            return None
        return [x.strip() for x in v.split(",") if x.strip()] or None

    def _query():
        qb = _sb().table("projects").select("*")
        types = _csv(project_type)
        if types:
            qb = qb.in_("project_type", types)
        stages = _csv(stage)
        if stages:
            qb = qb.in_("stage", stages)
        tiers = _csv(tier)
        if tiers:
            qb = qb.in_("relevance_tier", tiers)
        tcs = _csv(team_confidence)
        if tcs:
            qb = qb.in_("team_confidence", tcs)
        statuses = _csv(status)
        if statuses:
            qb = qb.in_("status", statuses)
        else:
            qb = qb.not_.in_("status", ["archived", "dismissed"])
        if in_radius is not None:
            qb = qb.eq("in_radius", in_radius)
        if q:
            qb = qb.or_(f"title.ilike.%{q}%,summary.ilike.%{q}%,city.ilike.%{q}%")
        return qb.execute().data

    try:
        rows = _retry(_query) or []
    except Exception:  # noqa: BLE001 — degrade gracefully, never 500 the feed
        rows = []

    # Sort in-memory for parity with DEMO_MODE semantics.
    if sort == "distance":
        rows.sort(key=lambda r: (r.get("distance_mi") is None, r.get("distance_mi") or 0.0))
    elif sort == "recent":
        rows.sort(key=lambda r: (r.get("last_signal_at") or ""), reverse=True)
    else:
        rows.sort(key=lambda r: (r.get("relevance_score") or 0), reverse=True)
    # 70-mile projects are the priority: stable-sort them to the top, preserving
    # whatever secondary order was chosen above (Python sort is stable).
    rows.sort(key=lambda r: _within_70(r.get("distance_mi")) is not True)

    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    total_pages = (total + page_size - 1) // page_size if page_size else 0

    return ProjectListEnvelope(
        items=[ProjectSummary(**_row_to_summary(r)) for r in page_rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str) -> ProjectDetail:
    """Full detail for a single project."""
    if settings.demo_mode:
        from services import fixtures

        data = fixtures.get_project(project_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return ProjectDetail(**data)

    rows = _retry(
        lambda: _sb().table("projects").select("*").eq("id", project_id).limit(1).execute().data
    ) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetail(**_row_to_detail(rows[0]))


@router.get("/projects/{project_id}/signals", response_model=List[Signal])
def get_project_signals(project_id: str):
    """Evidence (signals) attached to a project, newest first."""
    if settings.demo_mode:
        from services import fixtures

        if not fixtures.project_exists(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return fixtures.get_signals(project_id)

    rows = _retry(
        lambda: _sb()
        .table("signals")
        .select("*, sources(name)")
        .eq("project_id", project_id)
        .order("published_at", desc=True)
        .execute()
        .data
    ) or []
    out = []
    for r in rows:
        src = r.get("sources") or {}
        raw = r.get("raw_text") or ""
        out.append(
            {
                "id": r.get("id"),
                "signal_type": r.get("signal_type"),
                "source_name": src.get("name"),
                "url": r.get("url"),
                "title": r.get("title"),
                "published_at": r.get("published_at"),
                "snippet": (raw[:280] + "…") if len(raw) > 280 else (raw or None),
                "extraction_confidence": r.get("extraction_confidence"),
            }
        )
    return out


@router.patch("/projects/{project_id}", response_model=ProjectSummary)
def update_project_status(project_id: str, body: StatusUpdate) -> ProjectSummary:
    """Update a project's pipeline status and/or notes (either or both)."""
    patch: Dict[str, Any] = {}
    if body.status is not None:
        if body.status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{body.status}'. Allowed: {sorted(_VALID_STATUSES)}",
            )
        patch["status"] = body.status
    if body.notes is not None:
        patch["notes"] = body.notes
    if not patch:
        raise HTTPException(status_code=422, detail="Provide 'status' and/or 'notes'.")

    if settings.demo_mode:
        from services import fixtures

        data = fixtures.get_project(project_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Project not found")
        # DEMO_MODE is read-only; echo the patch back so the UI updates.
        data.update(patch)
        return ProjectSummary(**{k: data.get(k) for k in ProjectSummary.model_fields})

    updated = _retry(
        lambda: _sb().table("projects").update(patch).eq("id", project_id).execute().data
    ) or []
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectSummary(**_row_to_summary(updated[0]))


@router.post("/projects/{project_id}/merge", response_model=MergeResponse)
def merge_project(project_id: str, body: MergeRequest) -> MergeResponse:
    """Mark a project as merged into a target (sets merged_into + status=archived)."""
    if body.target_id == project_id:
        raise HTTPException(status_code=422, detail="Cannot merge a project into itself")

    if settings.demo_mode:
        from services import fixtures

        if not fixtures.project_exists(project_id) or not fixtures.project_exists(body.target_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return MergeResponse(ok=True, merged_into=body.target_id)

    target = _retry(
        lambda: _sb().table("projects").select("id").eq("id", body.target_id).limit(1).execute().data
    ) or []
    if not target:
        raise HTTPException(status_code=404, detail="Target project not found")

    updated = _retry(
        lambda: _sb()
        .table("projects")
        .update({"merged_into": body.target_id, "status": "archived"})
        .eq("id", project_id)
        .execute()
        .data
    ) or []
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return MergeResponse(ok=True, merged_into=body.target_id)


@router.get("/map-points")
def map_points() -> List[Dict[str, Any]]:
    """Geo points for the Radar map: non-merged, not archived/dismissed, with coordinates."""
    def _pt(r: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": r.get("id"),
            "title": r.get("title"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "relevance_tier": r.get("relevance_tier"),
            "project_type": r.get("project_type"),
            "within_70mi": _within_70(r.get("distance_mi")),
            "distance_mi": r.get("distance_mi"),
            "city": r.get("city"),
            "state": r.get("state"),
            "status": r.get("status", "new"),
        }

    if settings.demo_mode:
        from services import fixtures

        filt = {
            "q": None, "project_type": None, "stage": None, "in_radius": None,
            "tier": None, "team_confidence": None, "status": None,
            "sort": "relevance", "page": 1, "page_size": 1000,
        }
        out = []
        for item in fixtures.list_projects(filt).get("items", []):
            d = fixtures.get_project(item["id"]) or {}
            if d.get("latitude") is not None and d.get("longitude") is not None:
                out.append(_pt(d))
        return out

    try:
        rows = _retry(
            lambda: _sb()
            .table("projects")
            .select("id,title,latitude,longitude,relevance_tier,project_type,distance_mi,city,state,status")
            .is_("merged_into", "null")
            .not_.in_("status", ["archived", "dismissed"])
            .not_.is_("latitude", "null")
            .limit(2000)
            .execute()
            .data
        ) or []
    except Exception:  # noqa: BLE001
        rows = []
    return [_pt(r) for r in rows if r.get("latitude") is not None and r.get("longitude") is not None]


@router.get("/stats", response_model=Stats)
def get_stats() -> Stats:
    """Top-of-feed summary counters."""
    if settings.demo_mode:
        from services import fixtures

        return Stats(**fixtures.get_stats())

    try:
        rows = _retry(
            lambda: _sb()
            .table("projects")
            .select("status,relevance_tier,in_radius,distance_mi,project_type,first_seen_at,last_signal_at")
            .execute()
            .data
        ) or []
    except Exception:  # noqa: BLE001
        rows = []

    from datetime import date as _date

    today = _date.today().isoformat()
    visible = [r for r in rows if (r.get("status") or "") not in ("archived", "dismissed")]
    return Stats(
        total=len(visible),
        new=sum(1 for r in visible if (r.get("status") or "") == "new"),
        today=sum(
            1
            for r in visible
            if (r.get("first_seen_at") or "").startswith(today)
            or (r.get("last_signal_at") or "").startswith(today)
        ),
        hot=sum(1 for r in visible if (r.get("relevance_tier") or "") == "hot"),
        in_radius=sum(1 for r in visible if r.get("in_radius")),
        within_70mi=sum(1 for r in visible if _within_70(r.get("distance_mi")) is True),
        data_centers=sum(1 for r in visible if (r.get("project_type") or "") == "data_center"),
    )
