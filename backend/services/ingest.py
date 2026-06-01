"""
Source ingestion + parser registry.

Fetches each enabled `sources` row, dispatches by `parser_key` into the PARSERS
registry, and returns candidate *signal* dicts ready for extraction/clustering.

Two parsers ship in v1:
  - `rss_generic`  : feedparser over an RSS/Atom feed (Google News, trade RSS, biz journals)
  - `html_generic` : httpx + BeautifulSoup best-effort scrape of an index page
                     (pull article links + the page's visible text)

Design rules (SPEC §2, CLAUDE.md):
  - Heavy deps (httpx, feedparser, bs4) are imported LAZILY inside the parsers so this
    module imports cleanly in DEMO_MODE with only fastapi/uvicorn/pydantic installed.
  - Descriptive User-Agent (from settings.NOMINATIM_USER_AGENT family).
  - Per-source try/except: one dead source can never abort the batch.
  - Simple per-host politeness delay between network calls.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Callable, Optional
from urllib.parse import urlparse

log = logging.getLogger("newsfeed.ingest")

# Per-host politeness: minimum seconds between hits to the same host.
_HOST_DELAY_S = 1.0
_last_hit_at: dict[str, float] = {}

# Network timeout for any single fetch.
_FETCH_TIMEOUT_S = 25.0

# Cap on the number of items pulled from any single source per run (sanity guard).
_MAX_ITEMS_PER_SOURCE = 40

# Cap on raw_text length stored per signal (keep extraction prompts bounded).
_MAX_RAW_TEXT_CHARS = 8000


def _user_agent() -> str:
    """Descriptive UA string; falls back to a sane default if settings absent."""
    try:
        from config import settings

        ua = getattr(settings, "NOMINATIM_USER_AGENT", "") or ""
        if ua:
            return ua
    except Exception:  # noqa: BLE001 — settings may not be importable yet
        pass
    return "treadwell-newsfeed/1.0 (hanz@wetreadwell.com)"


def _polite_wait(url: str) -> None:
    """Sleep just enough to keep at least _HOST_DELAY_S between hits to one host."""
    try:
        host = urlparse(url).netloc or url
    except Exception:  # noqa: BLE001
        host = url
    now = time.monotonic()
    last = _last_hit_at.get(host)
    if last is not None:
        elapsed = now - last
        if elapsed < _HOST_DELAY_S:
            time.sleep(_HOST_DELAY_S - elapsed)
    _last_hit_at[host] = time.monotonic()


def content_hash(url: str, title: str) -> str:
    """sha256 of normalized(url) + '|' + (title) — the idempotency key for signals.

    URL is normalized by stripping scheme, lowercasing the host, and trimming a
    trailing slash so trivially-different URLs for the same article still collide.
    """
    norm_url = _normalize_url(url)
    norm_title = (title or "").strip()
    digest = hashlib.sha256(f"{norm_url}|{norm_title}".encode("utf-8")).hexdigest()
    return digest


def _normalize_url(url: str) -> str:
    """Lowercase host, drop scheme + fragment, trim trailing slash. Best-effort."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        if path.endswith("/") and len(path) > 1:
            path = path.rstrip("/")
        query = f"?{parsed.query}" if parsed.query else ""
        if host:
            return f"{host}{path}{query}"
        # Relative / scheme-less — return as-is, lowercased path only.
        return f"{path}{query}".lower()
    except Exception:  # noqa: BLE001
        return url.lower()


def _clip_text(text: str) -> str:
    text = (text or "").strip()
    if len(text) > _MAX_RAW_TEXT_CHARS:
        return text[:_MAX_RAW_TEXT_CHARS]
    return text


# ─── Parsers ──────────────────────────────────────────────────────────────
def rss_generic(source: dict) -> list[dict]:
    """Parse an RSS/Atom feed into candidate signal dicts via feedparser.

    Returns a list of dicts: {source_id, signal_type, url, title, published_at, raw_text}.
    Lazy-imports feedparser; raises on import so the per-source try/except in
    fetch_all_sources records the failure without killing the batch.
    """
    import feedparser  # lazy

    url = source.get("url") or ""
    if not url:
        return []

    _polite_wait(url)

    # feedparser can fetch the URL itself, but we pass a UA via request_headers.
    parsed = feedparser.parse(url, request_headers={"User-Agent": _user_agent()})

    signal_type = _signal_type_for(source)
    source_id = source.get("id")

    items: list[dict] = []
    for entry in (parsed.entries or [])[:_MAX_ITEMS_PER_SOURCE]:
        link = (getattr(entry, "link", "") or "").strip()
        title = (getattr(entry, "title", "") or "").strip()
        if not link and not title:
            continue

        published_at = _entry_published_iso(entry)
        raw_parts: list[str] = []
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        if summary:
            raw_parts.append(_strip_html(summary))
        # Some feeds carry fuller content under content[].value
        content = getattr(entry, "content", None)
        if content:
            for c in content:
                val = getattr(c, "value", "") or (c.get("value") if isinstance(c, dict) else "")
                if val:
                    raw_parts.append(_strip_html(val))
        raw_text = _clip_text("\n\n".join(p for p in raw_parts if p))

        items.append(
            {
                "source_id": source_id,
                "signal_type": signal_type,
                "url": link,
                "title": title,
                "published_at": published_at,
                "raw_text": raw_text,
            }
        )
    return items


def html_generic(source: dict) -> list[dict]:
    """Best-effort scrape of an HTML index page via httpx + BeautifulSoup.

    Pulls article-ish links and the page's visible text. Each discovered link
    becomes one candidate signal; the page text is shared as raw_text context
    (real per-article fetching is deferred — v1 keeps this light + polite).
    Lazy-imports httpx and bs4.
    """
    import httpx  # lazy
    from bs4 import BeautifulSoup  # lazy

    url = source.get("url") or ""
    if not url:
        return []

    _polite_wait(url)

    headers = {"User-Agent": _user_agent(), "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(timeout=_FETCH_TIMEOUT_S, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    page_text = _clip_text(soup.get_text(separator=" ", strip=True))
    base = urlparse(url)
    base_origin = f"{base.scheme}://{base.netloc}"

    signal_type = _signal_type_for(source)
    source_id = source.get("id")

    seen: set[str] = set()
    items: list[dict] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        text = a.get_text(strip=True)
        if not href or not text:
            continue
        # Skip nav/footer/anchor noise; keep only plausibly-article links.
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        if href.startswith("javascript:"):
            continue
        if len(text) < 25:  # headlines are usually longer than nav labels
            continue

        full = _absolutize(href, base_origin)
        if full in seen:
            continue
        seen.add(full)

        items.append(
            {
                "source_id": source_id,
                "signal_type": signal_type,
                "url": full,
                "title": text,
                "published_at": None,
                "raw_text": page_text,
            }
        )
        if len(items) >= _MAX_ITEMS_PER_SOURCE:
            break

    # If no plausible links surfaced, emit the page itself as one signal so the
    # source is not silently invisible.
    if not items and page_text:
        items.append(
            {
                "source_id": source_id,
                "signal_type": signal_type,
                "url": url,
                "title": (soup.title.get_text(strip=True) if soup.title else url),
                "published_at": None,
                "raw_text": page_text,
            }
        )
    return items


# Registry: parser_key -> callable(source dict) -> list[signal dict]
PARSERS: dict[str, Callable[[dict], list[dict]]] = {
    "rss_generic": rss_generic,
    "html_generic": html_generic,
}


# ─── Orchestration ──────────────────────────────────────────────────────────
def fetch_all_sources(sources: list[dict]) -> list[dict]:
    """Fetch every enabled source and return a flat list of candidate signal dicts.

    Each source is dispatched by its `parser_key` into PARSERS. A failure in any
    single source is logged and skipped — never aborts the batch. Returns a list
    of dicts shaped: {source_id, signal_type, url, title, published_at, raw_text}.
    """
    out: list[dict] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        if not source.get("enabled", True):
            continue

        parser_key = source.get("parser_key") or ""
        parser = PARSERS.get(parser_key)
        name = source.get("name") or source.get("url") or parser_key or "?"

        if parser is None:
            log.warning("No parser registered for parser_key=%r (source=%s) — skipping.", parser_key, name)
            continue

        try:
            items = parser(source) or []
            log.info("Source %s (%s): %d candidate signals.", name, parser_key, len(items))
            out.extend(items)
        except Exception as exc:  # noqa: BLE001 — isolation per source is the whole point
            log.warning("Source %s (%s) failed: %s", name, parser_key, exc)
            continue

    return out


# ─── Helpers ─────────────────────────────────────────────────────────────
# Same controlled vocab as sources.source_type / signals.signal_type (SPEC §1).
_SIGNAL_TYPES = {
    "news",
    "press_release",
    "permit",
    "utility_filing",
    "econ_dev_minutes",
    "planning_filing",
    "other",
}


def _signal_type_for(source: dict) -> str:
    """Map a source row to a controlled signal_type, defaulting to 'news'."""
    st = (source.get("source_type") or "").strip().lower()
    return st if st in _SIGNAL_TYPES else "news"


def _entry_published_iso(entry) -> Optional[str]:
    """Return an ISO-8601 string for a feedparser entry's publish time, or None."""
    import datetime as _dt

    for attr in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, attr, None)
        if struct:
            try:
                return _dt.datetime(*struct[:6], tzinfo=_dt.timezone.utc).isoformat()
            except Exception:  # noqa: BLE001
                continue
    # Fall back to the raw string fields if present.
    for attr in ("published", "updated"):
        val = getattr(entry, attr, None)
        if val:
            return str(val)
    return None


def _strip_html(fragment: str) -> str:
    """Strip tags from a small HTML fragment (feed summaries) without bs4 if possible."""
    fragment = fragment or ""
    if "<" not in fragment:
        return fragment.strip()
    try:
        from bs4 import BeautifulSoup  # lazy

        return BeautifulSoup(fragment, "html.parser").get_text(separator=" ", strip=True)
    except Exception:  # noqa: BLE001
        # Crude fallback: drop angle-bracket spans.
        import re

        return re.sub(r"<[^>]+>", " ", fragment).strip()


def _absolutize(href: str, base_origin: str) -> str:
    """Resolve a possibly-relative href against the page origin."""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"{base_origin}{href}"
    return f"{base_origin}/{href}"
