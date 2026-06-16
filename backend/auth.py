"""
Authentication — Google SSO via the SHARED Treadwell auth Supabase project
(the same sign-in the roadmap + proposal tools use). The SPA signs in with
Google and sends the access token as `Authorization: Bearer <jwt>`. We verify it
(RS256 via the project JWKS, falling back to the legacy HS256 secret), gate to
@wetreadwell.com, and derive the role from ADMIN_EMAILS. No user table — this is
a small internal tool, so role is config-driven, not stored.

Two principal kinds reach the API:
  * user    — a verified Google JWT. role = admin if email in ADMIN_EMAILS else viewer.
  * service — the read-only MCP connector, presenting X-Api-Key (GET requests only;
              the middleware rejects writes from a service principal).
"""

from __future__ import annotations

import datetime
import hmac
import logging
from typing import Optional

import jwt
from fastapi import Request
from jwt import PyJWKClient

from config import settings

log = logging.getLogger("newsfeed.auth")

# Public API paths (no token required) — just what the sign-in flow needs.
PUBLIC_API_PATHS = {"/api/health", "/api/auth/config", "/api/auth/dev-login"}

# DEV-ONLY signing secret for the "Preview as admin" bypass. Tokens signed with
# it are ONLY accepted when settings.DEV_LOGIN is true (never in production).
_DEV_SECRET = "treadwell-newsfeed-dev-login-only"

_jwks_client: Optional[PyJWKClient] = None


class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def _allowed_domain(email: str) -> bool:
    return email.lower().endswith("@" + settings.AUTH_ALLOWED_DOMAIN.lower())


def _get_jwks() -> Optional[PyJWKClient]:
    global _jwks_client
    if _jwks_client is None and settings.AUTH_SUPABASE_URL:
        url = settings.AUTH_SUPABASE_URL.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        try:
            _jwks_client = PyJWKClient(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not init JWKS client: %s", exc)
    return _jwks_client


def verify_supabase_jwt(token: str) -> dict:
    """Verify a Supabase access token. Tries asymmetric (JWKS) first, then the
    legacy HS256 project secret, then the DEV preview token. Raises AuthError."""
    # 1) Asymmetric (RS256/ES256) via the project JWKS.
    client = _get_jwks()
    if client is not None:
        try:
            key = client.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=["RS256", "ES256"], audience="authenticated")
        except Exception:  # noqa: BLE001 — fall through to HS256
            pass
    # 2) Legacy symmetric HS256 secret.
    if settings.AUTH_SUPABASE_JWT_SECRET:
        try:
            return jwt.decode(token, settings.AUTH_SUPABASE_JWT_SECRET,
                              algorithms=["HS256"], audience="authenticated")
        except jwt.ExpiredSignatureError:
            raise AuthError(401, "Session expired — sign in again")
        except jwt.InvalidTokenError:
            pass
    # 3) DEV-ONLY preview token (gated by DEV_LOGIN; never accepted in prod).
    if settings.DEV_LOGIN:
        try:
            return jwt.decode(token, _DEV_SECRET, algorithms=["HS256"], audience="authenticated")
        except jwt.ExpiredSignatureError:
            raise AuthError(401, "Session expired — sign in again")
        except jwt.InvalidTokenError:
            pass
    raise AuthError(401, "Sign-in is not configured on the server yet")


def make_dev_token() -> str:
    """Mint a 12h DEV preview token for the first admin email. DEV_LOGIN only."""
    email = next(iter(settings.admin_email_set), None) or ("admin@" + settings.AUTH_ALLOWED_DOMAIN)
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {"sub": "dev-preview", "email": email, "aud": "authenticated",
         "iat": now, "exp": now + datetime.timedelta(hours=12)},
        _DEV_SECRET, algorithm="HS256",
    )


def resolve_user(token: str) -> dict:
    """Verify a Google JWT, enforce the domain, derive the role. {email, role, kind}."""
    claims = verify_supabase_jwt(token)
    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise AuthError(403, "No email on this account")
    if not _allowed_domain(email):
        raise AuthError(403, f"Use your @{settings.AUTH_ALLOWED_DOMAIN} account")
    role = "admin" if email in settings.admin_email_set else "viewer"
    return {"email": email, "role": role, "kind": "user"}


def resolve_service(api_key: str) -> Optional[dict]:
    """Match the read-only service key (the MCP connector). Constant-time."""
    expected = settings.NEWSFEED_API_KEY or ""
    if expected and hmac.compare_digest(api_key, expected):
        return {"email": "connector@service", "role": "service", "kind": "service"}
    return None


# ─── request helpers (read the principal the middleware attached) ───────────
def current_user(request: Request) -> Optional[dict]:
    return getattr(request.state, "user", None)


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise AuthError(401, "Not authenticated")
    return user


def require_admin(request: Request) -> dict:
    user = require_user(request)
    if user.get("role") != "admin":
        raise AuthError(403, "Admin only")
    return user


def is_public_api_path(path: str) -> bool:
    return path in PUBLIC_API_PATHS
