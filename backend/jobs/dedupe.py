"""
Post-hoc deduplication.

Recomputes the (now order-insensitive) `dedup_key` for every live project, then
merges projects that collapse to the SAME (project_type, dedup_key): the survivor
(most signals, tie-break earliest first_seen) keeps the cluster; the losers' signals
+ contacts are reassigned to it and the losers are marked `merged_into` + `archived`
(so they drop out of the default feed).

Runs at the end of the daily pipeline AND as a one-off backfill after the
normalization change. Safe no-op without DB; idempotent; never raises (best-effort).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from services import clusterer
from services.supabase_client import get_supabase, is_configured, with_supabase_retry

log = logging.getLogger("newsfeed.dedupe")


def recompute_dedup_keys() -> int:
    """Recompute dedup_key for every non-merged project under current normalization."""
    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .select("id, title, city, dedup_key")
        .is_("merged_into", "null")
        .execute()
        .data
    ) or []
    changed = 0
    for p in rows:
        new_key = clusterer.dedup_key(p.get("title") or "", p.get("city"))
        if new_key != (p.get("dedup_key") or ""):
            pid = p["id"]
            with_supabase_retry(
                lambda: get_supabase().table("projects").update({"dedup_key": new_key}).eq("id", pid).execute()
            )
            changed += 1
    return changed


def _signal_counts(project_ids: list[str]) -> dict[str, int]:
    rows = with_supabase_retry(
        lambda: get_supabase().table("signals").select("project_id").in_("project_id", project_ids).execute().data
    ) or []
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        pid = r.get("project_id")
        if pid:
            counts[pid] += 1
    return counts


def _merge_into(src: str, target: str) -> None:
    """Reassign the source project's evidence + contacts to target, then archive it."""
    with_supabase_retry(
        lambda: get_supabase().table("signals").update({"project_id": target}).eq("project_id", src).execute()
    )
    with_supabase_retry(
        lambda: get_supabase().table("contacts").update({"project_id": target}).eq("project_id", src).execute()
    )
    with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .update({"merged_into": target, "status": "archived"})
        .eq("id", src)
        .execute()
    )


def merge_exact_duplicates() -> dict:
    """Merge non-merged projects that share (project_type, dedup_key). Returns counts."""
    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .select("id, project_type, dedup_key, first_seen_at")
        .is_("merged_into", "null")
        .execute()
        .data
    ) or []

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in rows:
        key = p.get("dedup_key") or ""
        title_part = key.split("|", 1)[0].strip()
        if not title_part:  # never merge on an empty title key
            continue
        groups[(p.get("project_type"), key)].append(p)

    clusters = 0
    merged = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        clusters += 1
        ids = [m["id"] for m in members]
        counts = _signal_counts(ids)
        members_sorted = sorted(members, key=lambda m: (-counts.get(m["id"], 0), m.get("first_seen_at") or ""))
        target = members_sorted[0]["id"]
        for m in members_sorted[1:]:
            _merge_into(m["id"], target)
            merged += 1
    return {"clusters": clusters, "merged": merged}


def archive_stale_projects() -> int:
    """Archive new/active projects whose latest signal is older than STALE_MONTHS.

    Only touches status in (new, active) — never archives something Kyle is tracking
    (watching/pursuing/won/passed) or already archived/dismissed. Returns count archived.
    """
    from config import settings
    from services import recency

    months = int(getattr(settings, "STALE_MONTHS", 18) or 18)
    cutoff = recency.cutoff_iso_months(months)
    res = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .update({"status": "archived"})
        .is_("merged_into", "null")
        .in_("status", ["new", "active"])
        .lt("last_signal_at", cutoff)
        .execute()
        .data
    ) or []
    return len(res)


def dedupe_existing() -> dict:
    """Recompute keys + merge exact duplicates + archive stale projects. Best-effort."""
    if not is_configured():
        return {"skipped": True, "reason": "no DB configured"}
    try:
        keys_recomputed = recompute_dedup_keys()
        res = merge_exact_duplicates()
        res["keys_recomputed"] = keys_recomputed
        res["archived_stale"] = archive_stale_projects()
        log.info("dedupe_existing: %s", res)
        return res
    except Exception as exc:  # noqa: BLE001
        log.warning("dedupe_existing failed: %s", exc)
        return {"error": str(exc)}
