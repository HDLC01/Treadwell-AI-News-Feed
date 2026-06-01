"""
Geocoding + distance + radius gate.

  - geocode(): US Census onelineaddress geocoder first (free, no key), then
    Nominatim (OpenStreetMap) as a fallback (1 req/s, descriptive UA from settings).
  - haversine_mi(): great-circle distance in miles (the in/out-radius gate, per CLAUDE.md).
  - compute_radius(): data_center <= DATA_CENTER_RADIUS_MI, else <= OTHER_RADIUS_MI.

httpx is imported lazily so this module imports cleanly in DEMO_MODE.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Optional

log = logging.getLogger("newsfeed.geocode")

_CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

_HTTP_TIMEOUT_S = 20.0

# Nominatim usage policy: max 1 request/second from one source.
_NOMINATIM_MIN_INTERVAL_S = 1.0
_last_nominatim_at = 0.0

# Defaults mirror settings (used if config is not importable yet).
_DEFAULT_KC_LAT = 39.0997
_DEFAULT_KC_LON = -94.5786
_DEFAULT_DC_RADIUS_MI = 350.0
_DEFAULT_OTHER_RADIUS_MI = 70.0

_EARTH_RADIUS_MI = 3958.7613


def _settings():
    try:
        from config import settings

        return settings
    except Exception:  # noqa: BLE001
        return None


def _user_agent() -> str:
    s = _settings()
    ua = getattr(s, "NOMINATIM_USER_AGENT", "") if s else ""
    return ua or "treadwell-newsfeed/1.0 (hanz@wetreadwell.com)"


def _compose_oneline(address: Optional[str], city: Optional[str], state: Optional[str]) -> str:
    parts = [p.strip() for p in (address, city, state) if p and str(p).strip()]
    return ", ".join(parts)


def geocode(
    address: Optional[str],
    city: Optional[str],
    state: Optional[str],
) -> Optional[tuple[float, float]]:
    """Return (lat, lon) for the best available location, or None.

    Tries the US Census geocoder first (no API key), then falls back to Nominatim.
    Caller decides when to call (no internal caching) so the daily job can throttle.
    """
    oneline = _compose_oneline(address, city, state)
    if not oneline:
        return None

    coords = _geocode_census(oneline)
    if coords is not None:
        return coords

    coords = _geocode_nominatim(oneline)
    if coords is not None:
        return coords

    log.info("geocode: no match for %r", oneline)
    return None


def _geocode_census(oneline: str) -> Optional[tuple[float, float]]:
    """US Census onelineaddress geocoder. Returns (lat, lon) or None."""
    try:
        import httpx  # lazy

        params = {
            "address": oneline,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
        headers = {"User-Agent": _user_agent()}
        with httpx.Client(timeout=_HTTP_TIMEOUT_S, follow_redirects=True, headers=headers) as client:
            resp = client.get(_CENSUS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        matches = (data.get("result") or {}).get("addressMatches") or []
        if not matches:
            return None
        coords = matches[0].get("coordinates") or {}
        lat = coords.get("y")
        lon = coords.get("x")
        if lat is None or lon is None:
            return None
        return (float(lat), float(lon))
    except Exception as exc:  # noqa: BLE001 — fall through to Nominatim
        log.info("Census geocode failed for %r: %s", oneline, exc)
        return None


def _geocode_nominatim(oneline: str) -> Optional[tuple[float, float]]:
    """Nominatim fallback (1 req/s, descriptive UA). Returns (lat, lon) or None."""
    global _last_nominatim_at
    try:
        import httpx  # lazy

        # Enforce the 1 req/s courtesy limit.
        now = time.monotonic()
        wait = _NOMINATIM_MIN_INTERVAL_S - (now - _last_nominatim_at)
        if wait > 0:
            time.sleep(wait)

        params = {"q": oneline, "format": "json", "limit": 1, "countrycodes": "us"}
        headers = {"User-Agent": _user_agent()}
        with httpx.Client(timeout=_HTTP_TIMEOUT_S, follow_redirects=True, headers=headers) as client:
            resp = client.get(_NOMINATIM_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        _last_nominatim_at = time.monotonic()

        if not data:
            return None
        first = data[0]
        return (float(first["lat"]), float(first["lon"]))
    except Exception as exc:  # noqa: BLE001
        log.info("Nominatim geocode failed for %r: %s", oneline, exc)
        return None


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles between two lat/lon points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return _EARTH_RADIUS_MI * c


def distance_from_kc(lat: float, lon: float) -> float:
    """Convenience: great-circle miles from the Kansas City origin to (lat, lon)."""
    s = _settings()
    kc_lat = float(getattr(s, "KC_LAT", _DEFAULT_KC_LAT)) if s else _DEFAULT_KC_LAT
    kc_lon = float(getattr(s, "KC_LON", _DEFAULT_KC_LON)) if s else _DEFAULT_KC_LON
    return haversine_mi(kc_lat, kc_lon, lat, lon)


def compute_radius(project_type: str, distance_mi: float) -> bool:
    """True if a project of `project_type` at `distance_mi` from KC is in-radius.

    data_center -> within DATA_CENTER_RADIUS_MI (default 350)
    everything else -> within OTHER_RADIUS_MI (default 70)
    """
    if distance_mi is None:
        return False
    s = _settings()
    dc_radius = float(getattr(s, "DATA_CENTER_RADIUS_MI", _DEFAULT_DC_RADIUS_MI)) if s else _DEFAULT_DC_RADIUS_MI
    other_radius = float(getattr(s, "OTHER_RADIUS_MI", _DEFAULT_OTHER_RADIUS_MI)) if s else _DEFAULT_OTHER_RADIUS_MI
    limit = dc_radius if (project_type or "").strip().lower() == "data_center" else other_radius
    return float(distance_mi) <= limit
