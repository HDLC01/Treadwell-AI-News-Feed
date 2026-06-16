"""
SSRF guard for outbound fetches.

The pipeline fetches URLs that ultimately derive from untrusted content — source
pages, and (worst case) a company website the model picked from article text. A
poisoned input could point a fetch at an internal/metadata address
(169.254.169.254, localhost, 10.x, etc.). `assert_public_url` resolves the host
and refuses anything that lands on a private/loopback/link-local/reserved range;
`safe_get` validates, fetches WITHOUT auto-following redirects, then re-validates
and follows each redirect itself (so a 302 → http://169.254.169.254 can't slip
through).
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urljoin

import httpx


class UnsafeURLError(ValueError):
    """Raised when a URL is not an allowed public http(s) destination."""


def _ip_is_blocked(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # un-parseable → treat as unsafe
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local      # 169.254.0.0/16 — cloud metadata lives here
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_public_url(url: str) -> None:
    """Raise UnsafeURLError unless `url` is http(s) and every resolved IP is public."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("no host in URL")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURLError(f"could not resolve host {host!r}: {exc}") from exc
    for info in infos:
        ip = info[4][0]
        if _ip_is_blocked(ip):
            raise UnsafeURLError(f"host {host!r} resolves to a blocked address {ip}")


def safe_get(
    url: str,
    *,
    timeout: float = 15.0,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    max_redirects: int = 3,
) -> httpx.Response:
    """GET `url` with SSRF protection: every hop (initial + each redirect) is
    validated against the private-range blocklist before the request is made."""
    current = url
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(max_redirects + 1):
            assert_public_url(current)
            resp = client.get(current, params=params)
            if resp.is_redirect and resp.headers.get("location"):
                current = urljoin(current, resp.headers["location"])
                params = None  # don't re-append query params to the redirect target
                continue
            return resp
    raise UnsafeURLError(f"too many redirects starting from {url!r}")
