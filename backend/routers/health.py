"""Health / readiness endpoint. Must stay green even with NO env configured."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from config import settings
from models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness + configuration snapshot. Never touches external services."""
    supabase_configured = False
    try:
        # Lazy import so a missing supabase dep can't break the health check.
        from services.supabase_client import is_configured

        supabase_configured = is_configured()
    except Exception:  # noqa: BLE001 — health must never crash
        supabase_configured = settings.supabase_configured

    return HealthResponse(
        status="ok",
        env=settings.ENVIRONMENT,
        demo_mode=settings.demo_mode,
        supabase_configured=supabase_configured,
        time=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


@router.get("/config")
def config() -> dict:
    """Office anchor + radii for the Radar map (no secrets)."""
    return {
        "kc_lat": settings.KC_LAT,
        "kc_lon": settings.KC_LON,
        "data_center_radius_mi": settings.DATA_CENTER_RADIUS_MI,
        "other_radius_mi": settings.OTHER_RADIUS_MI,
    }
