"""
Supabase client factory (server-side, service-role).

`get_supabase()` returns a memoised service-role client (bypasses RLS, full access).
This tool is server-side only — there is no anon/RLS path in v1.

Architectural note (copied pattern from the Treadwell stack, 2026-05):
    FastAPI sync route handlers run in a thread pool. supabase-py creates a single
    `httpx.Client(http2=True)` per client, and HTTP/2 stream multiplexing across
    threads is not reliably safe in httpx — concurrent requests can corrupt the
    HTTP/2 frame buffer and surface as `LocalProtocolError("Received pseudo-header
    in trailer ...")` then 400-from-Cloudflare on poisoned connections.

    Two-layer fix:
      1. `_disable_postgrest_http2()` monkey-patches postgrest's create_session to
         use HTTP/1.1 (pools per host, thread-safe for our request shape).
      2. `with_supabase_retry()` retries once on the known stale-pool error markers
         with a fresh client.

Configuration is read lazily so the app can START without Supabase creds (DEMO_MODE):
get_supabase() raises a clear error only when actually invoked without config.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, TypeVar

from config import settings

log = logging.getLogger("newsfeed.supabase")
T = TypeVar("T")


# ─── HTTP/2 → HTTP/1.1 patch ─────────────────────────────────────────────
def _disable_postgrest_http2() -> None:
    """Patch postgrest's SyncPostgrestClient to build HTTP/1.1 sessions. Idempotent."""
    try:
        from postgrest._sync.client import SyncPostgrestClient
        from postgrest.utils import SyncClient
    except ImportError:
        log.warning("postgrest internals not importable — HTTP/2 patch skipped.")
        return

    if getattr(SyncPostgrestClient.create_session, "_newsfeed_patched", False):
        return

    def _http1_session(self, base_url, headers, timeout, verify: bool = True, proxy=None) -> "SyncClient":
        return SyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            verify=verify,
            proxy=proxy,
            follow_redirects=True,
            http2=False,  # <-- the whole point
        )

    _http1_session._newsfeed_patched = True  # type: ignore[attr-defined]
    SyncPostgrestClient.create_session = _http1_session  # type: ignore[assignment]
    log.info("postgrest SyncPostgrestClient.create_session patched: HTTP/2 disabled.")


_disable_postgrest_http2()


# ─── Singleton with thread-safe reset ────────────────────────────────────
_cache_lock = threading.Lock()
_service_client = None  # type: Optional[object]


def is_configured() -> bool:
    """True if Supabase URL + service-role key are present in settings."""
    return bool(getattr(settings, "SUPABASE_URL", "") and getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", ""))


def _build_service_client():
    from supabase import create_client

    if not is_configured():
        raise RuntimeError(
            "Supabase is not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing). "
            "Set them in .env, or run with DEMO_MODE=true for sample data."
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def get_supabase():
    """Return the memoised service-role Supabase client. Raises if unconfigured."""
    global _service_client
    if _service_client is None:
        with _cache_lock:
            if _service_client is None:
                _service_client = _build_service_client()
    return _service_client


def reset_supabase_clients() -> None:
    """Discard the cached client so the next call builds a fresh one."""
    global _service_client
    with _cache_lock:
        _service_client = None


# ─── Retry helper for stale-connection protocol errors ──────────────────
def _is_stale_connection_error(exc: BaseException) -> bool:
    msg = str(exc)
    return (
        "pseudo-header in trailer" in msg
        or "Trailers must have END_STREAM" in msg
        or "Server disconnected" in msg
        or ("400 Bad Request" in msg and "cloudflare" in msg.lower())
        or "JSON could not be generated" in msg
    )


def with_supabase_retry(operation: Callable[[], T]) -> T:
    """Run a Supabase operation, retrying once if the HTTP/2 pool is stale.

    Usage:
        rows = with_supabase_retry(
            lambda: get_supabase().table("projects").select("*").execute().data
        )
    """
    try:
        return operation()
    except Exception as exc:  # noqa: BLE001 — narrowed via _is_stale_connection_error
        if not _is_stale_connection_error(exc):
            raise
        log.warning(
            "Supabase HTTP/2 pool went stale (%s) — resetting client and retrying once.",
            type(exc).__name__,
        )
        reset_supabase_clients()
        return operation()
