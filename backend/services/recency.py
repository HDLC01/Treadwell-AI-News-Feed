"""Recency helpers — keep the radar to current opportunities.

A project's freshness is judged by its most-recent article/signal date
(projects.last_signal_at, which the pipeline stamps from the article's published_at).
Unknown dates are treated as current (never penalized for missing data).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def _parse(iso) -> Optional[datetime]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_older_than_months(iso, months: int) -> bool:
    """True if the timestamp is older than `months`. Unknown/unparseable -> False."""
    dt = _parse(iso)
    if dt is None:
        return False
    return dt < datetime.now(timezone.utc) - timedelta(days=months * 30)


def is_older_than_days(iso, days: int) -> bool:
    dt = _parse(iso)
    if dt is None:
        return False
    return dt < datetime.now(timezone.utc) - timedelta(days=days)


def cutoff_iso_days(days: int) -> str:
    """ISO timestamp `days` ago (UTC) — for `>= cutoff` DB filters."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def cutoff_iso_months(months: int) -> str:
    return cutoff_iso_days(months * 30)
