"""
Team enrichment: turn extracted team assertions into companies + project_team rows,
then roll the project's team hierarchy up into a single `team_confidence` label.

  - resolve_company(): normalize a name, find-or-create the companies row, set the
    is_hyperscaler flag via heuristic. Returns company_id.
  - upsert_team_member(): insert/update one project_team link row (unique on
    project_id+company_id+role).
  - recompute_team_confidence(): roll up to gc_named / developer_named / owner_only /
    unknown and write it onto the project.

All DB access goes through services.supabase_client.with_supabase_retry(); this module
imports cleanly with no DB configured (functions raise only when actually invoked).
"""

from __future__ import annotations

import logging
from typing import Optional

from services.clusterer import normalize_name
from services.supabase_client import get_supabase, with_supabase_retry

log = logging.getLogger("newsfeed.team")

# Hyperscaler / large end-user heuristic. normalized_name substrings.
_HYPERSCALER_HINTS = {
    "google",
    "alphabet",
    "meta",
    "facebook",
    "microsoft",
    "amazon",
    "aws",
    "amazon web services",
    "apple",
    "oracle",
    "qts",
    "vantage",
    "edgeconnex",
    "aligned",
    "cloudhq",
    "cyrusone",
    "switch",
    "digital realty",
    "equinix",
    "stack infrastructure",
    "compass datacenters",
    "nvidia",
    "openai",
    "x ai",
    "xai",
}

# companies.company_type vocab (SPEC §1).
_COMPANY_TYPES = {
    "general_contractor",
    "developer",
    "owner",
    "end_user",
    "architect",
    "engineer",
    "construction_manager",
    "utility",
    "subcontractor",
    "unknown",
}


def is_hyperscaler(normalized: str) -> bool:
    """Heuristic: does this normalized company name look like a hyperscaler / major end-user?"""
    n = (normalized or "").strip().lower()
    if not n:
        return False
    return any(hint in n for hint in _HYPERSCALER_HINTS)


def _company_type_for_role(role: str) -> str:
    """Map a project_team role to a default companies.company_type."""
    r = (role or "").strip().lower()
    if r in _COMPANY_TYPES:
        return r
    return "unknown"


def resolve_company(name: str, role: str) -> str:
    """Find-or-create a companies row for `name`; return its id.

    Normalizes the name, matches on normalized_name, creates if absent, and sets
    is_hyperscaler via heuristic. If the existing row is type 'unknown' and we now
    have a more specific role, the company_type is upgraded.
    """
    raw = (name or "").strip()
    if not raw:
        raise ValueError("resolve_company: empty company name")

    normalized = normalize_name(raw)
    hyper = is_hyperscaler(normalized)
    desired_type = _company_type_for_role(role)

    existing = with_supabase_retry(
        lambda: get_supabase()
        .table("companies")
        .select("id, company_type, is_hyperscaler")
        .eq("normalized_name", normalized)
        .limit(1)
        .execute()
        .data
    )

    if existing:
        row = existing[0]
        company_id = row["id"]
        patch: dict = {}
        if row.get("company_type") in (None, "unknown") and desired_type != "unknown":
            patch["company_type"] = desired_type
        if hyper and not row.get("is_hyperscaler"):
            patch["is_hyperscaler"] = True
        if patch:
            with_supabase_retry(
                lambda: get_supabase().table("companies").update(patch).eq("id", company_id).execute()
            )
        return company_id

    inserted = with_supabase_retry(
        lambda: get_supabase()
        .table("companies")
        .insert(
            {
                "name": raw,
                "normalized_name": normalized,
                "company_type": desired_type,
                "is_hyperscaler": hyper,
            }
        )
        .execute()
        .data
    )
    if not inserted:
        # Race: another writer created it; re-fetch.
        again = with_supabase_retry(
            lambda: get_supabase()
            .table("companies")
            .select("id")
            .eq("normalized_name", normalized)
            .limit(1)
            .execute()
            .data
        )
        if again:
            return again[0]["id"]
        raise RuntimeError(f"resolve_company: failed to create company {raw!r}")
    return inserted[0]["id"]


def upsert_team_member(
    project_id: str,
    company_id: str,
    role: str,
    confidence: float,
    confidence_label: str,
    source_signal_id: Optional[str],
) -> str:
    """Insert or update one project_team link row; return its id.

    Unique on (project_id, company_id, role). On conflict, keep the HIGHER
    numeric confidence (and its label) and refresh source_signal_id.
    """
    existing = with_supabase_retry(
        lambda: get_supabase()
        .table("project_team")
        .select("id, confidence, confidence_label")
        .eq("project_id", project_id)
        .eq("company_id", company_id)
        .eq("role", role)
        .limit(1)
        .execute()
        .data
    )

    conf = max(0.0, min(1.0, float(confidence)))

    if existing:
        row = existing[0]
        team_id = row["id"]
        if conf >= float(row.get("confidence") or 0.0):
            patch = {
                "confidence": conf,
                "confidence_label": confidence_label,
                "source_signal_id": source_signal_id,
                "superseded": False,
            }
            with_supabase_retry(
                lambda: get_supabase().table("project_team").update(patch).eq("id", team_id).execute()
            )
        return team_id

    inserted = with_supabase_retry(
        lambda: get_supabase()
        .table("project_team")
        .insert(
            {
                "project_id": project_id,
                "company_id": company_id,
                "role": role,
                "confidence": conf,
                "confidence_label": confidence_label,
                "source_signal_id": source_signal_id,
                "superseded": False,
            }
        )
        .execute()
        .data
    )
    if not inserted:
        raise RuntimeError("upsert_team_member: insert returned no row")
    return inserted[0]["id"]


def recompute_team_confidence(project_id: str) -> str:
    """Roll the project's team rows up into a single team_confidence label and persist it.

    Precedence (SPEC §1 team_confidence enum):
        gc_named        — a general_contractor is on the team
        developer_named — a developer (but no GC) is on the team
        owner_only      — only owner / end_user roles are present
        unknown         — no usable team rows
    Only non-superseded rows count.
    """
    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("project_team")
        .select("role, superseded")
        .eq("project_id", project_id)
        .execute()
        .data
    )

    roles = {r["role"] for r in (rows or []) if not r.get("superseded")}

    if "general_contractor" in roles:
        label = "gc_named"
    elif "developer" in roles:
        label = "developer_named"
    elif roles & {"owner", "end_user"}:
        label = "owner_only"
    else:
        label = "unknown"

    with_supabase_retry(
        lambda: get_supabase().table("projects").update({"team_confidence": label}).eq("id", project_id).execute()
    )
    return label
