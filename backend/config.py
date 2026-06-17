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
    DIGEST_FROM_EMAIL: str = "newsfeed@notify.wetreadwell.com"
    DIGEST_FROM_NAME: str = "Treadwell Radar"

    # ─── Daily "top hottest" summary (Kyle's 6 AM email) ─────────────────
    SUMMARY_FROM_EMAIL: str = "newsfeed@notify.wetreadwell.com"
    SUMMARY_FROM_NAME: str = "Treadwell Radar"
    SUMMARY_REPLY_TO: str = "hanz@wetreadwell.com"
    SUMMARY_TO_EMAILS: str = "hanz@wetreadwell.com,kyle@wetreadwell.com"
    SUMMARY_COUNT: int = 5

    # ─── Geography / radius gate ─────────────────────────────────────────
    KC_LAT: float = 39.0997
    KC_LON: float = -94.5786
    DATA_CENTER_RADIUS_MI: float = 350.0
    OTHER_RADIUS_MI: float = 70.0

    # ─── Recency (keep the radar to current opportunities) ───────────────
    # A project whose most-recent article/signal is older than STALE_MONTHS is
    # treated as stale: forced cold and auto-archived out of the feed. New signals
    # older than this are skipped at ingest. The 6 AM summary only includes leads
    # whose latest signal is within SUMMARY_RECENCY_DAYS.
    STALE_MONTHS: int = 18
    SUMMARY_RECENCY_DAYS: int = 365

    # ─── Scheduler / pipeline ────────────────────────────────────────────
    PIPELINE_HOUR: int = 5
    PIPELINE_TZ: str = "America/Chicago"
    RUN_SCHEDULER: bool = False

    # ─── Contacts gate (legacy; superseded by SSO + the service API key) ──
    CONTACTS_GATE_PASSWORD: str = ""

    # ─── Auth: Google SSO via the SHARED Treadwell auth Supabase project ──
    # Sign-in uses the shared Treadwell auth project (NOT this feed's data
    # project above). The SPA signs in with Google there; the backend verifies
    # the resulting JWT and gates to @wetreadwell.com. Feed data still flows
    # only through this API — no Supabase client ever reaches the browser.
    AUTH_SUPABASE_URL: str = ""          # https://<ref>.supabase.co (JWKS + frontend)
    AUTH_SUPABASE_ANON_KEY: str = ""     # public anon key, sent to the SPA
    AUTH_SUPABASE_JWT_SECRET: str = ""   # legacy HS256 secret (fallback verify)
    AUTH_ALLOWED_DOMAIN: str = "wetreadwell.com"
    ADMIN_EMAILS: str = "hanz@wetreadwell.com"
    # DEV-ONLY "Preview as admin" bypass; MUST stay false in production.
    DEV_LOGIN: bool = False
    # Read-only service principal for the MCP connector (sent as X-Api-Key).
    NEWSFEED_API_KEY: str = ""

    # ─── Search API (resolve real LinkedIn profile URLs — NOT scraping LinkedIn) ─
    # provider: "brave" (api.search.brave.com, generous free tier) or "serpapi".
    # Leave SEARCH_API_KEY blank to disable LinkedIn resolution (a search link still shows).
    SEARCH_API_PROVIDER: str = "brave"
    SEARCH_API_KEY: str = ""

    # ─── URLs / CORS ─────────────────────────────────────────────────────
    PUBLIC_BASE_URL: str = "https://newsfeed.wetreadwell.com"
    CORS_ORIGINS: Union[str, List[str]] = "*"

    # ─── Geocoder politeness ─────────────────────────────────────────────
    NOMINATIM_USER_AGENT: str = "treadwell-newsfeed/1.0 (hanz@wetreadwell.com)"

    # ─── Environment label ───────────────────────────────────────────────
    ENVIRONMENT: str = "production"

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
    def summary_to_list(self) -> List[str]:
        """Recipient list for the daily hot-summary email (comma-separated env)."""
        raw = self.SUMMARY_TO_EMAILS or ""
        return [e.strip() for e in raw.split(",") if e.strip()]

    @property
    def auth_configured(self) -> bool:
        """True once the shared auth project's URL + anon key are present."""
        return bool(self.AUTH_SUPABASE_URL and self.AUTH_SUPABASE_ANON_KEY)

    @property
    def admin_email_set(self) -> set:
        """Lower-cased admin emails (comma-separated env)."""
        return {e.strip().lower() for e in (self.ADMIN_EMAILS or "").split(",") if e.strip()}

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
