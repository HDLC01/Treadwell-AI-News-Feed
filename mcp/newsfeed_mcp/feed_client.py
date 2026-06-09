"""Read-only HTTP client for the Treadwell AI News Feed REST API.

All access is GET-only. The connector never writes to the feed. Endpoints used
(all under `{base}/api`): /stats, /projects, /projects/{id}, /projects/{id}/signals,
/projects/{id}/contacts (gated by X-Contacts-Key), /digests, /digests/{date}.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_BASE = "https://newsfeed.wetreadwell.com"


class FeedClient:
    """Thin, read-only wrapper over the News Feed API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        contacts_key: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        raw = base_url if base_url is not None else os.environ.get("NEWSFEED_BASE_URL", DEFAULT_BASE)
        self.base_url = (raw or DEFAULT_BASE).rstrip("/")
        self.contacts_key = (
            contacts_key if contacts_key is not None else os.environ.get("NEWSFEED_CONTACTS_KEY", "")
        )
        self.timeout = timeout

    # ─── transport ───────────────────────────────────────────────────────
    def _get(self, path: str, params: Optional[Dict[str, Any]] = None,
             headers: Optional[Dict[str, str]] = None) -> Any:
        url = f"{self.base_url}/api{path}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.get(url, params=clean, headers=headers)
            resp.raise_for_status()
            return resp.json()

    # ─── endpoints ───────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        return self._get("/stats")

    def list_projects(
        self,
        q: Optional[str] = None,
        project_type: Optional[str] = None,
        stage: Optional[str] = None,
        in_radius: Optional[bool] = None,
        tier: Optional[str] = None,
        team_confidence: Optional[str] = None,
        status: Optional[str] = None,
        sort: str = "relevance",
        page: int = 1,
        page_size: int = 25,
    ) -> Dict[str, Any]:
        """Paginated, filterable project feed. CSV strings allowed for the
        comma-separated filters (project_type, stage, tier, team_confidence, status)."""
        return self._get(
            "/projects",
            {
                "q": q,
                "project_type": project_type,
                "stage": stage,
                "in_radius": in_radius,
                "tier": tier,
                "team_confidence": team_confidence,
                "status": status,
                "sort": sort,
                "page": page,
                "page_size": page_size,
            },
        )

    def get_project(self, project_id: str) -> Dict[str, Any]:
        return self._get(f"/projects/{project_id}")

    def get_signals(self, project_id: str) -> List[Dict[str, Any]]:
        return self._get(f"/projects/{project_id}/signals")

    def get_contacts(self, project_id: str) -> List[Dict[str, Any]]:
        headers = {"X-Contacts-Key": self.contacts_key} if self.contacts_key else None
        try:
            return self._get(f"/projects/{project_id}/contacts", headers=headers)
        except httpx.HTTPStatusError as exc:
            # 401 => contacts are gated and we lack the key; degrade to empty.
            if exc.response is not None and exc.response.status_code == 401:
                return []
            raise

    def list_digests(self) -> List[Dict[str, Any]]:
        return self._get("/digests")

    def get_digest(self, digest_date: str) -> Dict[str, Any]:
        return self._get(f"/digests/{digest_date}")

    def health(self) -> Dict[str, Any]:
        return self._get("/health")
