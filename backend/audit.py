"""
Audit trail — one JSON object per line recording authenticated state-changing
actions and sensitive-data access, so a later "who deleted this / who viewed
these contacts" question is answerable.

Sinks:
  * ALWAYS stdout via a dedicated logger (prefixed "AUDIT " so `docker logs` is
    greppable). Never propagates to the root logger (no double-logging).
  * ADDITIONALLY a RotatingFileHandler at <AUDIT_LOG_DIR>/audit.log — but only
    when AUDIT_LOG_DIR points at a writable, persistent directory. This repo's
    only Docker volume is /root/.claude (CLI creds), so by default there is no
    file sink and audit lines flow to stdout only. Point AUDIT_LOG_DIR at a
    mounted volume to also persist to disk.

Everything is best-effort: import and emission are wrapped so audit logging can
never break a request or block startup.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("newsfeed.audit")

# Dedicated audit logger -> stdout only, no propagation to the app's root logger.
_audit = logging.getLogger("newsfeed.audit.trail")
_audit.setLevel(logging.INFO)
_audit.propagate = False

if not _audit.handlers:
    _stdout = logging.StreamHandler()  # stdout/stderr -> captured by `docker logs`
    _stdout.setFormatter(logging.Formatter("AUDIT %(message)s"))
    _audit.addHandler(_stdout)

    # Optional persistent file sink — only if a writable dir is configured.
    _dir = (os.environ.get("AUDIT_LOG_DIR") or "").strip()
    if _dir:
        try:
            os.makedirs(_dir, exist_ok=True)
            if os.access(_dir, os.W_OK):
                from logging.handlers import RotatingFileHandler

                _file = RotatingFileHandler(
                    os.path.join(_dir, "audit.log"),
                    maxBytes=5_000_000,
                    backupCount=5,
                    encoding="utf-8",
                )
                _file.setFormatter(logging.Formatter("%(message)s"))
                _audit.addHandler(_file)
                log.info("Audit file sink enabled at %s/audit.log", _dir)
        except Exception as exc:  # noqa: BLE001 — never block startup on the file sink
            log.warning("Audit file sink disabled (%s): %s", _dir, exc)


def audit_log(record: dict) -> None:
    """Emit one compact JSON line. Best-effort; never raises."""
    try:
        _audit.info(json.dumps(record, separators=(",", ":"), default=str))
    except Exception as exc:  # noqa: BLE001 — auditing must never break the caller
        log.warning("audit_log failed: %s", exc)
