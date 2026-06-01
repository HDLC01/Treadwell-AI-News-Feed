"""
Application configuration via pydantic-settings.

ALL settings are optional with safe defaults so the backend can START with no
environment configured at all (DEMO_MODE auto-on). Real services raise clear
errors only when actually invoked without their credentials.

Import convention (matches services/supabase_client.py): the working directory
is `backend/`, so this module is imported as top-level `config`:
    from config import settings
"""

from __future__ import annotations

from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings. See backend/.env.example for every var."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Supabase ────────────────────────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""

    # ─── Demo mode (None = auto) ─────────────────────────────────────────
    # Stored as an explicit override; the public `demo_mode` property resolves it.
    DEMO_MODE: Optional[bool] = None

    # ─── Email (Resend) ──────────────────────────────────────────────────
    RESEND_API_KEY: str = ""
    DIGEST_FROM_EMAIL: str = "radar@notify.wetreadwell.com"
    DIGEST_FROM_NAME: str = "Treadwell Radar"

    # ─── Geography / radius gate ─────────────────────────────────────────
    KC_LAT: float = 39.0997
    KC_LON: float = -94.5786
    DATA_CENTER_RADIUS_MI: float = 350.0
    OTHER_RADIUS_MI: float = 70.0

    # ─── Scheduler / pipeline ────────────────────────────────────────────
    PIPELINE_HOUR: int = 5
    PIPELINE_TZ: str = "America/Chicago"
    RUN_SCHEDULER: bool = False

    # ─── Contacts gate ───────────────────────────────────────────────────
    CONTACTS_GATE_PASSWORD: str = ""

    # ─── URLs / CORS ─────────────────────────────────────────────────────
    PUBLIC_BASE_URL: str = "https://newsfeed.wetreadwell.com"
    CORS_ORIGINS: Union[str, List[str]] = "*"

    # ─── Geocoder politeness ─────────────────────────────────────────────
    NOMINATIM_USER_AGENT: str = "treadwell-newsfeed/1.0 (hanz@wetreadwell.com)"

    # ─── Environment label ───────────────────────────────────────────────
    ENVIRONMENT: str = "development"

    # ─── Derived helpers ─────────────────────────────────────────────────
    @property
    def supabase_configured(self) -> bool:
        """True when both the Supabase URL and the service-role key are present."""
        return bool(self.SUPABASE_URL and self.SUPABASE_SERVICE_ROLE_KEY)

    @property
    def demo_mode(self) -> bool:
        """Resolve DEMO_MODE: explicit override wins; otherwise auto-on when
        Supabase is not configured."""
        if self.DEMO_MODE is not None:
            return self.DEMO_MODE
        return not self.supabase_configured

    @property
    def cors_origins_list(self) -> List[str]:
        """CORS_ORIGINS as a list. '*' stays a single-element wildcard list;
        a comma-separated string is split and trimmed."""
        value = self.CORS_ORIGINS
        if isinstance(value, list):
            return value
        value = (value or "").strip()
        if not value or value == "*":
            return ["*"]
        return [origin.strip() for origin in value.split(",") if origin.strip()]

    @field_validator("DEMO_MODE", mode="before")
    @classmethod
    def _empty_demo_mode_is_none(cls, v):
        """Treat an empty-string DEMO_MODE env var as 'auto' (None)."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


settings = Settings()
