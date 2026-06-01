"""
Clustering / dedup: map an extracted record onto an existing project, or create one.

Strategy:
  1. Deterministic blocking by `dedup_key` = normalize(title) | normalize(city).
  2. If exactly one candidate blocks, reuse it.
  3. If multiple candidates block (ambiguous), ask `claude -p` to adjudicate
     ("same project? -> {decision, target_project_id, confidence}").
  4. Otherwise create a new project.

normalize_name strips legal suffixes + punctuation; dedup_key composes title+city.
All writes go through services.supabase_client. Imports cleanly with no DB configured.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from services.claude_cli import call_claude_json
from services.supabase_client import get_supabase, with_supabase_retry

log = logging.getLogger("newsfeed.cluster")

# Legal / corporate suffixes stripped during normalization.
_LEGAL_SUFFIXES = {
    "inc",
    "inc.",
    "incorporated",
    "llc",
    "l.l.c.",
    "llp",
    "lp",
    "ltd",
    "ltd.",
    "limited",
    "co",
    "co.",
    "company",
    "corp",
    "corp.",
    "corporation",
    "plc",
    "pllc",
    "pc",
    "group",
    "holdings",
    "partners",
    "development",
    "developments",
    "properties",
    "realty",
    "construction",
    "builders",
    "constructors",
    "the",
}

# Generic project-noise words removed when building a dedup key from a title.
_TITLE_NOISE = {
    "project",
    "facility",
    "campus",
    "development",
    "expansion",
    "phase",
    "new",
    "proposed",
    "planned",
    "site",
    "center",
    "centre",
}

_ADJUDICATION_SYSTEM = """You decide whether a newly-extracted construction project refers \
to the SAME real-world project as one of several existing candidates. Consider name, \
aka names, city/county/state, type, and scale. Two records are the SAME project only if \
they describe the same physical facility at the same location.

Return ONLY this JSON object (no prose, no fences):
{
  "decision": "same" | "different",
  "target_project_id": string | null,   // the matching candidate id when decision="same", else null
  "confidence": number                   // 0.0 - 1.0
}"""


def normalize_name(s: str) -> str:
    """Lowercase, strip punctuation + legal suffixes, collapse whitespace.

    Used for companies.normalized_name and as a building block for dedup_key.
    """
    if not s:
        return ""
    s = s.lower().strip()
    # Replace ampersand, drop other punctuation.
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = [t for t in s.split() if t and t not in _LEGAL_SUFFIXES]
    return " ".join(tokens).strip()


def dedup_key(title: str, city: Optional[str]) -> str:
    """Build the deterministic blocking key: normalized(title) | normalized(city).

    Title normalization additionally drops generic project-noise words so that
    "New Acme Data Center Project" and "Acme Data Center" block together.
    """
    norm_title_tokens = [t for t in normalize_name(title).split() if t not in _TITLE_NOISE]
    norm_title = " ".join(norm_title_tokens).strip()
    norm_city = normalize_name(city or "")
    return f"{norm_title}|{norm_city}"


def find_or_create_project(extracted: dict, existing_candidates: list[dict]) -> tuple[str, bool]:
    """Map `extracted` onto an existing project or create a new one.

    Args:
        extracted: cleaned dict from signal_extractor.extract_signal (project_name,
            project_type, stage, location{city,...}, est_*, dedup_hints{aka_names}, ...).
        existing_candidates: project rows to consider (at minimum id, title, city,
            dedup_key, project_type). The caller may prefilter; this function also
            blocks internally by dedup_key.

    Returns:
        (project_id, created) — created=True if a new projects row was inserted.

    Writes via supabase_client. Raises only on hard DB failure.
    """
    title = (extracted.get("project_name") or "").strip()
    location = extracted.get("location") or {}
    city = location.get("city")
    key = dedup_key(title, city)

    # ── 1. Deterministic blocking by dedup_key ──
    blocked = [c for c in (existing_candidates or []) if (c.get("dedup_key") or "") == key and key.strip("|")]

    # Also block on aka_names: if an aka matches a candidate title, include it.
    aka = [a for a in (extracted.get("dedup_hints") or {}).get("aka_names", []) if isinstance(a, str)]
    if aka:
        aka_keys = {dedup_key(a, city) for a in aka}
        for c in existing_candidates or []:
            if (c.get("dedup_key") or "") in aka_keys and c not in blocked:
                blocked.append(c)

    if len(blocked) == 1:
        return blocked[0]["id"], False

    if len(blocked) > 1:
        target = _adjudicate(extracted, blocked)
        if target:
            return target, False
        # Adjudication said "different" / unsure -> create fresh.
        return _create_project(extracted, key), True

    # ── No deterministic block: create a new project ──
    return _create_project(extracted, key), True


def _adjudicate(extracted: dict, candidates: list[dict]) -> Optional[str]:
    """Ask claude -p whether `extracted` matches one of the candidates. Returns id or None."""
    loc = extracted.get("location") or {}
    new_blob = {
        "name": extracted.get("project_name"),
        "aka_names": (extracted.get("dedup_hints") or {}).get("aka_names", []),
        "project_type": extracted.get("project_type"),
        "city": loc.get("city"),
        "county": loc.get("county"),
        "state": loc.get("state"),
        "est_megawatts": extracted.get("est_megawatts"),
        "est_sqft": extracted.get("est_sqft"),
    }
    cand_blobs = [
        {
            "id": c.get("id"),
            "title": c.get("title"),
            "project_type": c.get("project_type"),
            "city": c.get("city"),
            "county": c.get("county"),
            "state": c.get("state"),
        }
        for c in candidates
    ]

    import json

    prompt = (
        "NEW PROJECT:\n"
        + json.dumps(new_blob, ensure_ascii=False)
        + "\n\nEXISTING CANDIDATES:\n"
        + json.dumps(cand_blobs, ensure_ascii=False)
        + "\n\nIs the NEW project the same as one of the candidates?"
    )

    result = call_claude_json(prompt, _ADJUDICATION_SYSTEM, timeout=90)
    if not isinstance(result, dict):
        return None
    if result.get("decision") != "same":
        return None

    target_id = result.get("target_project_id")
    valid_ids = {c.get("id") for c in candidates}
    if target_id in valid_ids:
        return target_id
    return None


def _create_project(extracted: dict, key: str) -> str:
    """Insert a new projects row from an extracted record; return its id."""
    loc = extracted.get("location") or {}
    row = {
        "title": (extracted.get("project_name") or "Untitled project").strip(),
        "project_type": extracted.get("project_type") or "other_commercial",
        "stage": extracted.get("stage"),
        "address": loc.get("address"),
        "city": loc.get("city"),
        "state": loc.get("state"),
        "county": loc.get("county"),
        "est_value_usd": extracted.get("est_value_usd"),
        "est_sqft": extracted.get("est_sqft"),
        "est_megawatts": extracted.get("est_megawatts"),
        "dedup_key": key,
        "status": "new",
        "team_confidence": "unknown",
    }
    # Drop None values so DB defaults / nullable columns behave predictably.
    row = {k: v for k, v in row.items() if v is not None}

    inserted = with_supabase_retry(
        lambda: get_supabase().table("projects").insert(row).execute().data
    )
    if not inserted:
        raise RuntimeError("find_or_create_project: insert returned no row")
    return inserted[0]["id"]


def load_candidate_projects(extracted: dict, limit: int = 200) -> list[dict]:
    """Fetch a reasonable set of existing projects to block against.

    Convenience for the daily job: pulls recent, non-merged projects of the same
    project_type (data centers can match across the whole 350mi ring, so type
    matters more than city for blocking). Read-only.
    """
    project_type = extracted.get("project_type") or "other_commercial"
    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .select("id, title, project_type, city, county, state, dedup_key")
        .is_("merged_into", "null")
        .eq("project_type", project_type)
        .order("last_signal_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    return rows or []
