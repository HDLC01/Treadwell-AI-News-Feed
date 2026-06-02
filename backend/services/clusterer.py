"""
Clustering / dedup: map an extracted record onto an existing project, or create one.

Strategy (hardened — Phase 2):
  1. Deterministic blocking by `dedup_key` = sorted(noise-stripped title tokens) | normalize(city).
     Tokens are SORTED so word-order variants collide:
     "Google KC Northland Data Center" == "Google Data Center - KC Northland".
  2. Exact-key (or aka) block: 1 candidate -> reuse; >1 -> `claude -p` adjudicates.
  3. If NO exact block, gather FUZZY candidates (high title-token overlap, same type)
     and let `claude -p` adjudicate before creating a brand-new project.
  4. On reuse, ENRICH the existing project with better/missing fields (don't discard).

normalize_name strips legal suffixes + punctuation. All writes go through
services.supabase_client. Imports cleanly with no DB configured.
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
    "inc", "inc.", "incorporated", "llc", "l.l.c.", "llp", "lp", "ltd", "ltd.",
    "limited", "co", "co.", "company", "corp", "corp.", "corporation", "plc",
    "pllc", "pc", "group", "holdings", "partners", "development", "developments",
    "properties", "realty", "construction", "builders", "constructors", "the",
}

# Generic project-noise words removed when building a dedup key from a title.
# "data" is included so "... Data Center" fully collapses to the proper-noun tokens.
_TITLE_NOISE = {
    "project", "facility", "campus", "development", "expansion", "phase", "new",
    "proposed", "planned", "site", "center", "centre", "data", "building",
}

# Lifecycle order — used to ADVANCE a project's stage on enrichment (never regress).
_STAGE_ORDER = {
    "rumored": 0, "planning": 1, "design": 2, "permitting": 3, "procurement": 4,
    "pre_bid": 5, "under_construction": 6, "complete": 7, "dead": 8,
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
    """Lowercase, strip punctuation + legal suffixes, collapse whitespace."""
    if not s:
        return ""
    s = s.lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = [t for t in s.split() if t and t not in _LEGAL_SUFFIXES]
    return " ".join(tokens).strip()


def _key_tokens(title: str) -> list[str]:
    """Sorted, noise-stripped tokens of a title — the basis of an order-insensitive key."""
    return sorted(t for t in normalize_name(title).split() if t not in _TITLE_NOISE)


def dedup_key(title: str, city: Optional[str]) -> str:
    """Order-insensitive blocking key: sorted(noise-stripped title tokens) | normalized(city)."""
    norm_title = " ".join(_key_tokens(title)).strip()
    norm_city = normalize_name(city or "")
    return f"{norm_title}|{norm_city}"


def _token_set(title: str) -> set[str]:
    return set(_key_tokens(title))


def _overlap(a: set[str], b: set[str]) -> float:
    """Jaccard overlap of two token sets (0..1)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_or_create_project(extracted: dict, existing_candidates: list[dict]) -> tuple[str, bool]:
    """Map `extracted` onto an existing project or create a new one.

    Returns (project_id, created). created=True if a new row was inserted.
    """
    title = (extracted.get("project_name") or "").strip()
    location = extracted.get("location") or {}
    city = location.get("city")
    key = dedup_key(title, city)
    new_tokens = _token_set(title)

    # ── 1. Deterministic blocking by dedup_key (+ aka names) ──
    blocked = [c for c in (existing_candidates or []) if (c.get("dedup_key") or "") == key and key.strip("|")]
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
        return (target, False) if target else (_create_project(extracted, key), True)

    # ── 2. No exact block → fuzzy candidates, then AI adjudication ──
    fuzzy = _fuzzy_candidates(new_tokens, city, existing_candidates)
    if fuzzy:
        target = _adjudicate(extracted, fuzzy)
        if target:
            return target, False

    # ── 3. Genuinely new ──
    return _create_project(extracted, key), True


def _fuzzy_candidates(new_tokens: set[str], city: Optional[str], candidates: list[dict], limit: int = 5) -> list[dict]:
    """Candidates with high title-token overlap (or moderate overlap in the same city)."""
    if not new_tokens:
        return []
    norm_city = normalize_name(city or "")
    scored: list[tuple[float, dict]] = []
    for c in candidates or []:
        ct = _token_set(c.get("title") or "")
        ov = _overlap(new_tokens, ct)
        same_city = bool(norm_city) and normalize_name(c.get("city") or "") == norm_city
        if ov >= 0.6 or (same_city and ov >= 0.34):
            scored.append((ov, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:limit]]


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
    return target_id if target_id in valid_ids else None


def _create_project(extracted: dict, key: str) -> str:
    """Insert a new projects row from an extracted record; return its id."""
    loc = extracted.get("location") or {}
    row = {
        "title": (extracted.get("project_name") or "Untitled project").strip(),
        "summary": extracted.get("summary"),
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
    row = {k: v for k, v in row.items() if v is not None}

    inserted = with_supabase_retry(
        lambda: get_supabase().table("projects").insert(row).execute().data
    )
    if not inserted:
        raise RuntimeError("find_or_create_project: insert returned no row")
    return inserted[0]["id"]


def enrich_existing_project(project_id: str, extracted: dict) -> None:
    """Fill missing fields + advance stage on an existing project from a new signal.

    Fill-if-empty for summary/address/city/state/county/est_*; advance-only for stage.
    Never overwrites existing non-null values (except a forward stage move). Best-effort.
    """
    loc = extracted.get("location") or {}
    cur = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .select("id, summary, address, city, state, county, stage, est_value_usd, est_sqft, est_megawatts")
        .eq("id", project_id)
        .limit(1)
        .execute()
        .data
    )
    if not cur:
        return
    p = cur[0]
    patch: dict = {}

    fill_fields = [
        ("summary", extracted.get("summary")),
        ("address", loc.get("address")),
        ("city", loc.get("city")),
        ("state", loc.get("state")),
        ("county", loc.get("county")),
        ("est_value_usd", extracted.get("est_value_usd")),
        ("est_sqft", extracted.get("est_sqft")),
        ("est_megawatts", extracted.get("est_megawatts")),
    ]
    for field, val in fill_fields:
        if val is not None and p.get(field) in (None, ""):
            patch[field] = val

    new_stage = extracted.get("stage")
    if new_stage in _STAGE_ORDER:
        cur_stage = p.get("stage")
        if cur_stage not in _STAGE_ORDER or _STAGE_ORDER[new_stage] > _STAGE_ORDER[cur_stage]:
            patch["stage"] = new_stage

    if patch:
        with_supabase_retry(
            lambda: get_supabase().table("projects").update(patch).eq("id", project_id).execute()
        )


def load_candidate_projects(extracted: dict, limit: int = 200) -> list[dict]:
    """Fetch recent non-merged projects of the same project_type to block/fuzzy-match against."""
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
