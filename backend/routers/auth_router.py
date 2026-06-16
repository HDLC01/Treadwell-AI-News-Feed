"""
Auth router.
- GET  /auth/config    : public — tells the SPA how to reach the shared Supabase
                          auth project (Google sign-in).
- POST /auth/dev-login : DEV-ONLY — issues a preview-admin token (DEV_LOGIN gated).
- GET  /auth/me        : verified — the current principal's email + role.

Sign-in/out happens client-side via Supabase; the backend only verifies the
resulting Bearer token (see auth.py) on each API call.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

import auth
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
def config():
    return {
        "supabase_url": settings.AUTH_SUPABASE_URL,
        "supabase_anon_key": settings.AUTH_SUPABASE_ANON_KEY,
        "allowed_domain": settings.AUTH_ALLOWED_DOMAIN,
        "configured": settings.auth_configured,
        "dev_login": settings.DEV_LOGIN,
    }


@router.post("/dev-login")
def dev_login():
    """DEV-ONLY: issue a preview-admin token without Google. 404 unless DEV_LOGIN."""
    if not settings.DEV_LOGIN:
        raise auth.AuthError(404, "Not found")
    return {"access_token": auth.make_dev_token()}


@router.get("/me")
def me(request: Request):
    user = auth.require_user(request)
    return {"email": user["email"], "role": user["role"], "kind": user.get("kind", "user")}
