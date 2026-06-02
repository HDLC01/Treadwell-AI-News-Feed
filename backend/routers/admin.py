"""
Admin router — pipeline run history + manual trigger.

GET  /api/admin/runs          -> recent PipelineRun[] (started_at desc, limit 25)
POST /api/admin/run-pipeline  -> kicks run_pipeline('manual') via BackgroundTasks.

The pipeline import is LAZY (inside the handler) so missing pipeline deps never
break app import. In DEMO_MODE the trigger returns the documented skip response.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks

from config import settings
from models.schemas import PipelineRun, RunPipelineResponse

log = logging.getLogger("newsfeed.admin")

router = APIRouter(tags=["admin"])


@router.get("/admin/runs", response_model=List[PipelineRun])
def list_runs() -> List[PipelineRun]:
    """Most recent pipeline runs (newest first, up to 25)."""
    if settings.demo_mode:
        from services import fixtures

        return [PipelineRun(**r) for r in fixtures.get_runs(limit=25)]

    from services.supabase_client import get_supabase, with_supabase_retry

    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("pipeline_runs")
        .select("*")
        .order("started_at", desc=True)
        .limit(25)
        .execute()
        .data
    ) or []

    out: List[PipelineRun] = []
    for r in rows:
        out.append(
            PipelineRun(
                id=str(r.get("id")),
                started_at=_iso(r.get("started_at")),
                finished_at=_iso(r.get("finished_at")),
                status=r.get("status", "running"),
                trigger=r.get("trigger", "scheduled"),
                sources_fetched=r.get("sources_fetched", 0),
                signals_ingested=r.get("signals_ingested", 0),
                projects_created=r.get("projects_created", 0),
                projects_updated=r.get("projects_updated", 0),
                errors=r.get("errors") or [],
            )
        )
    return out


def _run_pipeline_bg() -> None:
    """Background entrypoint: import the pipeline lazily and run it once."""
    try:
        from jobs.daily import run_pipeline

        result = run_pipeline("manual")
        log.info("manual pipeline finished: %s", result)
    except Exception as exc:  # noqa: BLE001 — background task must not propagate
        log.exception("manual pipeline failed: %s", exc)


@router.post("/admin/run-pipeline", response_model=RunPipelineResponse)
def run_pipeline_now(background_tasks: BackgroundTasks) -> RunPipelineResponse:
    """Trigger a manual pipeline run (respects the DB run-lock). No-op in DEMO_MODE."""
    if settings.demo_mode:
        return RunPipelineResponse(ok=True, started=False, note="DEMO_MODE — no DB")

    background_tasks.add_task(_run_pipeline_bg)
    return RunPipelineResponse(
        ok=True,
        started=True,
        note="Pipeline started in the background (trigger=manual). Watch /api/admin/runs for status.",
    )


@router.post("/admin/send-hot-summary")
def send_hot_summary_now() -> dict:
    """Build + send the daily 'top hottest opportunities' email now (the 6 AM cron hits this).

    Runs synchronously (no Claude calls — reads existing summaries/scores), sends via
    Resend to SUMMARY_TO_EMAILS. No-op in DEMO_MODE.
    """
    if settings.demo_mode:
        return {"ok": True, "skipped": True, "note": "DEMO_MODE — no DB"}

    from services import summary

    result = summary.build_and_send_hot_summary()
    return {"ok": "error" not in result, **result}


def _iso(value):
    """Normalize a timestamp value (datetime|str|None) to an ISO string or None."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
