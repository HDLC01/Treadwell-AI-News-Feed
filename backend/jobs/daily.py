"""
Daily pipeline entrypoint — Stages 0-9 (SPEC §2, CLAUDE.md).

  Stage 0  run-lock: insert a pipeline_runs row (status=running); abort if one is
           already running so two triggers can't stomp each other.
  Stage 1  fetch: ingest.fetch_all_sources(enabled sources) -> candidate signals.
  Stage 2  extract: per NEW signal (dedup by content_hash), signal_extractor.extract_signal.
  Stage 3  cluster: clusterer.find_or_create_project -> attach signal to a project.
  Stage 4  team: team_enricher.resolve_company + upsert_team_member + recompute rollup.
  Stage 5  geocode + radius: geocode missing-coord projects, compute distance + in_radius.
  Stage 6  score: relevance_scorer.score_project (claude w/ rule-based fallback).
  Stage 7  persist: project fields written through stages 3-6 (mutates as it goes).
  Stage 8  digest: digest_builder.build_digest(today) -> upsert daily_digest.
  Stage 9  send: mailer.send_digest per active subscriber (one call each).
  Finalize: update pipeline_runs counters + status (success/partial/failed).

Resilience: every stage and every per-item loop is wrapped so a single bad source /
signal / extraction never aborts the run. When Supabase is unconfigured (DEMO_MODE),
this is a safe no-op that returns a clear dict and never raises.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from services.supabase_client import get_supabase, is_configured, with_supabase_retry

log = logging.getLogger("newsfeed.pipeline")


def run_pipeline(trigger: str = "scheduled") -> dict:
    """Run the full daily pipeline. `trigger` is 'scheduled' or 'manual'.

    Returns a summary dict. Safe to call with no DB configured: logs and returns
    {"ok": True, "skipped": True, "reason": "no DB configured"} without raising.
    """
    if not is_configured():
        log.info("run_pipeline(%s): skipped — no DB configured (DEMO_MODE).", trigger)
        return {"ok": True, "skipped": True, "reason": "no DB configured", "trigger": trigger}

    # ── Stage 0: run-lock ──
    run_id = _acquire_run_lock(trigger)
    if run_id is None:
        log.info("run_pipeline(%s): another run is already in progress — aborting.", trigger)
        return {"ok": False, "skipped": True, "reason": "run already in progress", "trigger": trigger}

    errors: list[dict] = []
    counters = {
        "sources_fetched": 0,
        "signals_ingested": 0,
        "projects_created": 0,
        "projects_updated": 0,
    }
    touched_project_ids: set[str] = set()

    try:
        # ── Stage 1: fetch ──
        from services import ingest

        sources = _load_enabled_sources()
        counters["sources_fetched"] = len(sources)
        candidates = []
        try:
            candidates = ingest.fetch_all_sources(sources)
        except Exception as exc:  # noqa: BLE001
            errors.append({"stage": "fetch", "error": str(exc)})
            log.warning("Stage 1 fetch failed wholesale: %s", exc)

        # ── Stages 2-7: per-signal extract -> cluster -> team -> geocode -> score ──
        from services import clusterer, relevance_scorer, signal_extractor

        for cand in candidates:
            try:
                signal_id, is_new_signal = _ingest_signal(cand, ingest)
                if not is_new_signal:
                    continue  # duplicate content_hash — already processed
                counters["signals_ingested"] += 1

                extracted = signal_extractor.extract_signal(
                    cand.get("title", ""), cand.get("raw_text", "")
                )
                if not extracted or not extracted.get("is_construction_opportunity"):
                    _set_signal_extraction(signal_id, extracted)
                    continue

                _set_signal_extraction(signal_id, extracted)

                # Stage 3: cluster
                candidates_for_block = clusterer.load_candidate_projects(extracted)
                project_id, created = clusterer.find_or_create_project(extracted, candidates_for_block)
                if created:
                    counters["projects_created"] += 1
                else:
                    counters["projects_updated"] += 1
                touched_project_ids.add(project_id)

                # link the signal to its project + bump last_signal_at
                _attach_signal_to_project(signal_id, project_id)
                _bump_last_signal_at(project_id, cand.get("published_at"))

                # Stage 4: team
                _enrich_team(project_id, signal_id, extracted)

                # Stage 5: geocode + radius
                _geocode_and_radius(project_id, extracted)

                # Stage 6/7: score + persist
                _score_and_persist(project_id, relevance_scorer)

            except Exception as exc:  # noqa: BLE001 — one bad signal never aborts the run
                errors.append({"stage": "signal", "url": cand.get("url"), "error": str(exc)})
                log.warning("Signal failed (%s): %s", cand.get("url"), exc)
                continue

        # ── Stage 8: digest ──
        digest_id = None
        try:
            digest_id = _build_and_store_digest(run_id)
        except Exception as exc:  # noqa: BLE001
            errors.append({"stage": "digest", "error": str(exc)})
            log.warning("Stage 8 digest failed: %s", exc)

        # ── Stage 9: send ──
        try:
            _send_digest_to_subscribers(digest_id)
        except Exception as exc:  # noqa: BLE001
            errors.append({"stage": "send", "error": str(exc)})
            log.warning("Stage 9 send failed: %s", exc)

        status = "success" if not errors else "partial"
        _finalize_run(run_id, status, counters, errors)
        return {
            "ok": True,
            "trigger": trigger,
            "run_id": run_id,
            "status": status,
            **counters,
            "errors": errors,
        }

    except Exception as exc:  # noqa: BLE001 — catastrophic; mark the run failed
        errors.append({"stage": "pipeline", "error": str(exc)})
        log.exception("run_pipeline failed catastrophically.")
        _finalize_run(run_id, "failed", counters, errors)
        return {"ok": False, "trigger": trigger, "run_id": run_id, "status": "failed", "errors": errors}


# ─── Stage 0 helpers ───────────────────────────────────────────────────────
def _acquire_run_lock(trigger: str) -> Optional[str]:
    """Insert a running pipeline_runs row unless one is already running. Returns id or None."""
    running = with_supabase_retry(
        lambda: get_supabase()
        .table("pipeline_runs")
        .select("id")
        .eq("status", "running")
        .limit(1)
        .execute()
        .data
    )
    if running:
        return None
    inserted = with_supabase_retry(
        lambda: get_supabase()
        .table("pipeline_runs")
        .insert({"status": "running", "trigger": trigger})
        .execute()
        .data
    )
    if not inserted:
        return None
    return inserted[0]["id"]


def _finalize_run(run_id: str, status: str, counters: dict, errors: list[dict]) -> None:
    patch = {
        "status": status,
        "finished_at": _now_iso(),
        "errors": errors,
        **counters,
    }
    try:
        with_supabase_retry(
            lambda: get_supabase().table("pipeline_runs").update(patch).eq("id", run_id).execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to finalize pipeline_run %s: %s", run_id, exc)


# ─── Stage 1/2 helpers ─────────────────────────────────────────────────────
def _load_enabled_sources() -> list[dict]:
    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("sources")
        .select("*")
        .eq("enabled", True)
        .order("tier")
        .execute()
        .data
    )
    return rows or []


def _ingest_signal(cand: dict, ingest_mod) -> tuple[str, bool]:
    """Insert the signal if its content_hash is new. Returns (signal_id, is_new)."""
    chash = ingest_mod.content_hash(cand.get("url", ""), cand.get("title", ""))

    existing = with_supabase_retry(
        lambda: get_supabase()
        .table("signals")
        .select("id")
        .eq("content_hash", chash)
        .limit(1)
        .execute()
        .data
    )
    if existing:
        return existing[0]["id"], False

    row = {
        "signal_type": cand.get("signal_type") or "news",
        "source_id": cand.get("source_id"),
        "url": cand.get("url"),
        "title": cand.get("title"),
        "published_at": cand.get("published_at"),
        "raw_text": cand.get("raw_text"),
        "content_hash": chash,
    }
    row = {k: v for k, v in row.items() if v is not None}
    inserted = with_supabase_retry(
        lambda: get_supabase().table("signals").insert(row).execute().data
    )
    if not inserted:
        # Race on unique content_hash — re-fetch.
        again = with_supabase_retry(
            lambda: get_supabase().table("signals").select("id").eq("content_hash", chash).limit(1).execute().data
        )
        if again:
            return again[0]["id"], False
        raise RuntimeError("failed to insert signal")
    return inserted[0]["id"], True


def _set_signal_extraction(signal_id: str, extracted: Optional[dict]) -> None:
    patch = {
        "extracted": extracted,
        "extraction_confidence": (extracted or {}).get("extraction_confidence") if extracted else None,
    }
    with_supabase_retry(
        lambda: get_supabase().table("signals").update(patch).eq("id", signal_id).execute()
    )


def _attach_signal_to_project(signal_id: str, project_id: str) -> None:
    with_supabase_retry(
        lambda: get_supabase().table("signals").update({"project_id": project_id}).eq("id", signal_id).execute()
    )


def _bump_last_signal_at(project_id: str, published_at: Optional[str]) -> None:
    stamp = published_at or _now_iso()
    with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .update({"last_signal_at": stamp, "updated_at": _now_iso()})
        .eq("id", project_id)
        .execute()
    )


# ─── Stage 4 helper ────────────────────────────────────────────────────────
def _enrich_team(project_id: str, signal_id: str, extracted: dict) -> None:
    from services import team_enricher

    _CONF_NUM = {"confirmed": 0.9, "likely": 0.65, "rumored": 0.35}
    for member in extracted.get("team") or []:
        try:
            company = member.get("company")
            role = member.get("role") or "other"
            label = member.get("confidence_label") or "rumored"
            conf = _CONF_NUM.get(label, 0.35)
            company_id = team_enricher.resolve_company(company, role)
            team_enricher.upsert_team_member(project_id, company_id, role, conf, label, signal_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("team enrich failed for %r on %s: %s", member.get("company"), project_id, exc)
            continue
    try:
        team_enricher.recompute_team_confidence(project_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("recompute_team_confidence failed on %s: %s", project_id, exc)


# ─── Stage 5 helper ────────────────────────────────────────────────────────
def _geocode_and_radius(project_id: str, extracted: dict) -> None:
    from services import geocode as geo

    proj = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .select("id, project_type, latitude, longitude, address, city, state")
        .eq("id", project_id)
        .limit(1)
        .execute()
        .data
    )
    if not proj:
        return
    p = proj[0]

    lat, lon = p.get("latitude"), p.get("longitude")
    if lat is None or lon is None:
        coords = geo.geocode(p.get("address"), p.get("city"), p.get("state"))
        if coords is None:
            return  # leave distance/radius null
        lat, lon = coords

    distance = geo.distance_from_kc(float(lat), float(lon))
    in_radius = geo.compute_radius(p.get("project_type") or "other_commercial", distance)
    with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .update(
            {
                "latitude": float(lat),
                "longitude": float(lon),
                "distance_mi": distance,
                "in_radius": in_radius,
            }
        )
        .eq("id", project_id)
        .execute()
    )


# ─── Stage 6/7 helper ──────────────────────────────────────────────────────
def _score_and_persist(project_id: str, scorer_mod) -> None:
    proj = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .select(
            "id, title, project_type, stage, city, state, in_radius, distance_mi, "
            "team_confidence, est_value_usd, est_sqft, est_megawatts"
        )
        .eq("id", project_id)
        .limit(1)
        .execute()
        .data
    )
    if not proj:
        return
    scored = scorer_mod.score_project(proj[0])
    with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .update(
            {
                "relevance_score": scored["relevance_score"],
                "relevance_tier": scored["relevance_tier"],
                "relevance_reasoning": scored["relevance_reasoning"],
                "scored_by_model": "claude-cli/rule-based",
                "updated_at": _now_iso(),
            }
        )
        .eq("id", project_id)
        .execute()
    )


# ─── Stage 8/9 helpers ─────────────────────────────────────────────────────
def _build_and_store_digest(run_id: str) -> Optional[str]:
    from services import digest_builder

    today = _today_local()
    digest = digest_builder.build_digest(today)

    row = {
        "digest_date": digest["digest_date"],
        "project_ids": digest["project_ids"],
        "new_count": digest["new_count"],
        "updated_count": digest["updated_count"],
        "html_body": digest["html_body"],
        "text_body": digest["text_body"],
        "pipeline_run_id": run_id,
    }

    # Upsert on the unique digest_date so a re-run replaces today's digest.
    existing = with_supabase_retry(
        lambda: get_supabase()
        .table("daily_digest")
        .select("id")
        .eq("digest_date", digest["digest_date"])
        .limit(1)
        .execute()
        .data
    )
    if existing:
        digest_id = existing[0]["id"]
        with_supabase_retry(
            lambda: get_supabase().table("daily_digest").update(row).eq("id", digest_id).execute()
        )
        return digest_id

    inserted = with_supabase_retry(
        lambda: get_supabase().table("daily_digest").insert(row).execute().data
    )
    return inserted[0]["id"] if inserted else None


def _send_digest_to_subscribers(digest_id: Optional[str]) -> None:
    if not digest_id:
        return
    from services import mailer

    digest = with_supabase_retry(
        lambda: get_supabase()
        .table("daily_digest")
        .select("digest_date, html_body, text_body, new_count, updated_count")
        .eq("id", digest_id)
        .limit(1)
        .execute()
        .data
    )
    if not digest:
        return
    digest = digest[0]

    # Nothing to send if the digest is empty.
    if not (digest.get("new_count") or digest.get("updated_count")):
        log.info("Digest empty — no subscriber emails sent.")
        return

    subscribers = with_supabase_retry(
        lambda: get_supabase()
        .table("email_subscribers")
        .select("email, full_name, unsubscribe_token")
        .eq("subscribed", True)
        .execute()
        .data
    )
    for sub in subscribers or []:
        try:
            mailer.send_digest(sub, digest)  # one call per subscriber; never batches
        except Exception as exc:  # noqa: BLE001
            log.warning("send_digest failed for %s: %s", sub.get("email"), exc)
            continue


# ─── time helpers ──────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_local() -> date:
    """Today's date in the pipeline timezone (falls back to UTC)."""
    try:
        from config import settings
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(getattr(settings, "PIPELINE_TZ", "America/Chicago"))
        return datetime.now(tz).date()
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc).date()
