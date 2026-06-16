"""
Treadwell AI News Feed — FastAPI application entrypoint.

Run locally:
    cd backend && uvicorn main:app --reload --port 8890

Design guarantees:
  * Starts with NO environment configured (DEMO_MODE auto-on, fixtures served).
  * The APScheduler daily job starts ONLY when RUN_SCHEDULER is true AND Supabase
    is configured; APScheduler is imported lazily inside the lifespan and wrapped
    in try/except so a missing dep or a scheduler error never blocks startup.
  * The built SPA (../frontend/dist) is mounted with an SPA fallback to index.html
    IF that directory exists; otherwise the mount is skipped silently.
  * No service crashes on import — every heavy/optional dep is imported lazily.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import auth
from config import settings
from routers import admin, auth_router, contacts, digests, health, projects, subscribers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("newsfeed.app")

# Holds the live scheduler so we can shut it down cleanly on app stop.
_scheduler = None


def _maybe_start_scheduler() -> None:
    """Start the APScheduler daily cron iff RUN_SCHEDULER and Supabase configured."""
    global _scheduler

    if not settings.RUN_SCHEDULER:
        log.info("Scheduler disabled (RUN_SCHEDULER is false).")
        return
    if not settings.supabase_configured:
        log.info("Scheduler not started: Supabase is not configured.")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        from jobs.daily import run_pipeline

        scheduler = BackgroundScheduler(timezone=settings.PIPELINE_TZ)
        scheduler.add_job(
            lambda: run_pipeline("scheduled"),
            trigger=CronTrigger(hour=settings.PIPELINE_HOUR, timezone=settings.PIPELINE_TZ),
            id="daily_pipeline",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        scheduler.start()
        _scheduler = scheduler
        log.info(
            "APScheduler started: daily pipeline at hour=%s tz=%s.",
            settings.PIPELINE_HOUR,
            settings.PIPELINE_TZ,
        )
    except Exception as exc:  # noqa: BLE001 — never block startup on the scheduler
        log.warning("Could not start APScheduler (continuing without it): %s", exc)


def _stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            log.info("APScheduler stopped.")
        except Exception as exc:  # noqa: BLE001
            log.warning("Error shutting down scheduler: %s", exc)
        finally:
            _scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "Starting Treadwell AI News Feed — env=%s demo_mode=%s supabase_configured=%s",
        settings.ENVIRONMENT,
        settings.demo_mode,
        settings.supabase_configured,
    )
    _maybe_start_scheduler()
    try:
        yield
    finally:
        _stop_scheduler()


# Interactive API docs (/docs, /redoc, /openapi.json) only in development —
# in production they'd hand out the full route map of an internal tool.
_docs_enabled = settings.ENVIRONMENT == "development"
app = FastAPI(
    title="Treadwell AI News Feed",
    description="Project-first construction-opportunity radar (API).",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# ─── CORS ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Auth gate ───────────────────────────────────────────────────────────
@app.exception_handler(auth.AuthError)
async def _auth_error_handler(request: Request, exc: auth.AuthError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """Gate every /api/* request (except the public sign-in paths). Accepts a
    Supabase/Google Bearer token (humans) OR a read-only X-Api-Key (the MCP
    connector, GET-only). Non-/api paths fall through to the SPA. Bearer/api-key
    headers aren't sent automatically by browsers, so there's no CSRF surface."""
    path = request.url.path
    if path.startswith("/api/") and not auth.is_public_api_path(path):
        if request.method == "OPTIONS":
            return await call_next(request)
        header = request.headers.get("authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if token:
            try:
                request.state.user = auth.resolve_user(token)
            except auth.AuthError as exc:
                return JSONResponse(status_code=exc.status, content={"detail": exc.detail})
            except Exception as exc:  # noqa: BLE001
                log.warning("auth verify failed: %s", exc)
                return JSONResponse(status_code=401, content={"detail": "Could not verify session"})
        else:
            api_key = request.headers.get("x-api-key", "")
            svc = auth.resolve_service(api_key) if api_key else None
            if svc is None:
                return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
            if request.method != "GET":
                return JSONResponse(status_code=403, content={"detail": "Read-only API key"})
            request.state.user = svc
    return await call_next(request)

# ─── API routers (all under /api) ────────────────────────────────────────
app.include_router(health.router, prefix="/api")
app.include_router(auth_router.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")
app.include_router(digests.router, prefix="/api")
app.include_router(subscribers.router, prefix="/api")
# Admin endpoints (run-pipeline, send-hot-summary, runs) require an admin user.
app.include_router(admin.router, prefix="/api", dependencies=[Depends(auth.require_admin)])


# ─── SPA static mount (only if the built frontend exists) ────────────────
def _mount_spa() -> None:
    """Serve ../frontend/dist with an SPA fallback to index.html, if present."""
    here = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.normpath(os.path.join(here, "..", "frontend", "dist"))
    index_file = os.path.join(dist_dir, "index.html")

    if not (os.path.isdir(dist_dir) and os.path.isfile(index_file)):
        log.info("No built SPA at %s — skipping StaticFiles mount (API-only).", dist_dir)
        return

    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    # Vite emits hashed bundles under dist/assets — serve them with correct
    # content types via StaticFiles. (Skipped cleanly if the dir is absent.)
    assets_dir = os.path.join(dist_dir, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # SPA history-mode fallback: any non-/api path resolves to a real file in
    # dist (favicon, manifest, etc.) or falls through to index.html.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):  # noqa: ANN001
        if full_path == "" or full_path.startswith("api"):
            # Root -> index.html; anything under /api is handled by the routers
            # (this branch only fires for /api paths with no matching route).
            if full_path.startswith("api"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            return FileResponse(index_file)
        candidate = os.path.normpath(os.path.join(dist_dir, full_path))
        # Prevent path traversal outside dist_dir; serve real files directly.
        if candidate.startswith(dist_dir) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index_file)

    log.info("Mounted SPA from %s.", dist_dir)


_mount_spa()


@app.get("/", include_in_schema=False)
def _root_when_no_spa():
    """Fallback root when no SPA is built — point callers at the API/docs."""
    return JSONResponse(
        {
            "name": "Treadwell AI News Feed",
            "status": "ok",
            "demo_mode": settings.demo_mode,
            "api_health": "/api/health",
        }
    )
