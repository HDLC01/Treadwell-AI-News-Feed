"""
Pydantic response models — the API contract (SPEC section 4).

Key names here are CONTRACTS and must mirror the SPEC exactly; the frontend's
TS interfaces (frontend/src/lib/types.ts) mirror these one-for-one.

These models are intentionally permissive (Optional fields, no strict enums) so
that DEMO_MODE fixtures and live Supabase rows both validate cleanly. The
controlled-vocabulary enforcement lives in the pipeline services, not here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Nested pieces ───────────────────────────────────────────────────────
class TopTeamMember(BaseModel):
    """The single highest-authority team member surfaced on a summary card."""

    company_name: str
    role: str
    confidence_label: str


class TeamMember(BaseModel):
    """A full project_team link row, joined to its company."""

    company_id: str
    company_name: str
    company_type: str
    role: str
    confidence: float
    confidence_label: str
    is_hyperscaler: bool = False


# ─── Projects ────────────────────────────────────────────────────────────
class ProjectSummary(BaseModel):
    """Card-level view of a project (feed/list endpoints)."""

    id: str
    title: str
    project_type: str
    stage: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    county: Optional[str] = None
    distance_mi: Optional[float] = None
    in_radius: Optional[bool] = None
    within_70mi: Optional[bool] = None
    relevance_score: Optional[int] = None
    relevance_tier: Optional[str] = None
    team_confidence: str = "unknown"
    top_team_member: Optional[TopTeamMember] = None
    signals_count: int = 0
    est_megawatts: Optional[float] = None
    est_value_usd: Optional[float] = None
    est_sqft: Optional[float] = None
    status: str = "new"
    last_signal_at: Optional[str] = None
    first_seen_at: Optional[str] = None


class ProjectDetail(ProjectSummary):
    """Full project view (detail endpoint) — ProjectSummary plus deep fields."""

    summary: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    relevance_reasoning: Optional[Dict[str, Any]] = None
    team: List[TeamMember] = Field(default_factory=list)
    contacts_count: int = 0


# ─── Signals (evidence) ──────────────────────────────────────────────────
class Signal(BaseModel):
    """A piece of evidence attached to a project."""

    id: str
    signal_type: str
    source_name: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    published_at: Optional[str] = None
    snippet: Optional[str] = None
    extraction_confidence: Optional[float] = None


# ─── Contacts ────────────────────────────────────────────────────────────
class Contact(BaseModel):
    """A person or inbox associated with a company on a project."""

    id: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    contact_kind: str = "named_person"
    source: Optional[str] = None
    source_url: Optional[str] = None
    verified: bool = False
    do_not_contact: bool = False


# ─── Digests ─────────────────────────────────────────────────────────────
class DigestSummary(BaseModel):
    """List-row view of a daily digest."""

    digest_date: str
    new_count: int = 0
    updated_count: int = 0
    project_count: int = 0


class DigestDetail(BaseModel):
    """Full digest view (rendered HTML + the project ids it covered)."""

    digest_date: str
    html_body: Optional[str] = None
    project_ids: List[str] = Field(default_factory=list)
    new_count: int = 0
    updated_count: int = 0


# ─── Pipeline runs ───────────────────────────────────────────────────────
class PipelineRun(BaseModel):
    """Observability row for one pipeline execution."""

    id: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: str = "running"
    trigger: str = "scheduled"
    sources_fetched: int = 0
    signals_ingested: int = 0
    projects_created: int = 0
    projects_updated: int = 0
    errors: List[Any] = Field(default_factory=list)


# ─── Stats ───────────────────────────────────────────────────────────────
class Stats(BaseModel):
    """Top-of-feed summary counters."""

    total: int = 0
    new: int = 0
    today: int = 0
    hot: int = 0
    in_radius: int = 0
    within_70mi: int = 0
    data_centers: int = 0


# ─── Envelopes / misc ────────────────────────────────────────────────────
class ProjectListEnvelope(BaseModel):
    """Paginated list response for GET /api/projects."""

    items: List[ProjectSummary] = Field(default_factory=list)
    page: int = 1
    page_size: int = 25
    total: int = 0
    total_pages: int = 0


class HealthResponse(BaseModel):
    status: str = "ok"
    env: str = "development"
    demo_mode: bool = True
    supabase_configured: bool = False
    time: str = ""


class StatusUpdate(BaseModel):
    """PATCH /api/projects/{id} request body."""

    status: str


class MergeRequest(BaseModel):
    """POST /api/projects/{id}/merge request body."""

    target_id: str


class MergeResponse(BaseModel):
    ok: bool = True
    merged_into: str


class SubscribeRequest(BaseModel):
    """POST /api/subscribers request body."""

    email: str
    full_name: Optional[str] = None


class OkResponse(BaseModel):
    ok: bool = True


class RunPipelineResponse(BaseModel):
    """POST /api/admin/run-pipeline response."""

    ok: bool = True
    started: bool = False
    note: str = ""
