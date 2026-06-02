"""
Contacts enrichment (Kyle's contacts ask).

Per project, in the daily pipeline:
  persist_article_contacts(...) -> store the contacts the extractor already pulled
        from the article (names / emails / phones) into the contacts table.
  enrich_company_websites(...)  -> for each team company, find its website (company
        row, a contact email domain, or a one-shot Claude lookup) and scrape the
        homepage + /contact + /about + /team for emails, LinkedIn URLs, and named
        people. Bounded + best-effort.

We never scrape LinkedIn (login wall / ToS). We DO capture LinkedIn URLs that appear
on a company's own pages; the UI offers a 'Find on LinkedIn' search link.

All functions are best-effort and never raise into the pipeline caller.
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from services.claude_cli import call_claude_json
from services.supabase_client import get_supabase, with_supabase_retry

log = logging.getLogger("newsfeed.contacts")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|company)/[A-Za-z0-9._%\-/]+", re.I)
_GENERIC_LOCAL = {
    "info", "contact", "sales", "hello", "admin", "office", "support", "inquiries",
    "general", "marketing", "media", "press", "careers", "hr", "help", "estimating",
}
_FREE_EMAIL = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com",
    "me.com", "proton.me", "protonmail.com", "gmx.com",
}
_PAGES = ["", "/contact", "/contact-us", "/about", "/about-us", "/team", "/leadership", "/our-team", "/people"]
_MAX_COMPANIES = 4
_MAX_PAGES = 6
_MAX_NAMED = 8
_FETCH_TIMEOUT = 15.0


def _ua() -> str:
    try:
        from config import settings

        return getattr(settings, "NOMINATIM_USER_AGENT", "") or "treadwell-newsfeed/1.0 (hanz@wetreadwell.com)"
    except Exception:  # noqa: BLE001
        return "treadwell-newsfeed/1.0 (hanz@wetreadwell.com)"


# ─── DB helpers ───────────────────────────────────────────────────────────
def _team_companies(project_id: str) -> list[dict]:
    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("project_team")
        .select("company_id, role, companies(id,name,domain,website)")
        .eq("project_id", project_id)
        .eq("superseded", False)
        .execute()
        .data
    ) or []
    out, seen = [], set()
    for r in rows:
        co = r.get("companies") or {}
        cid = co.get("id") or r.get("company_id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append({"id": cid, "name": co.get("name"), "domain": co.get("domain"), "website": co.get("website")})
    return out


def _primary_company_id(project_id: str) -> Optional[str]:
    cos = _team_companies(project_id)
    return cos[0]["id"] if cos else None


def _existing_contacts(project_id: str) -> list[dict]:
    return with_supabase_retry(
        lambda: get_supabase().table("contacts").select("id, full_name, email, source").eq("project_id", project_id).execute().data
    ) or []


def _contact_exists(existing: list[dict], email, full_name) -> bool:
    e = (email or "").lower().strip()
    fn = (full_name or "").lower().strip()
    for c in existing:
        if e and (c.get("email") or "").lower().strip() == e:
            return True
        if fn and not e and (c.get("full_name") or "").lower().strip() == fn:
            return True
    return False


def _has_website_contacts(existing: list[dict]) -> bool:
    return any((c.get("source") or "") == "company_website" for c in existing)


def _insert_contact(project_id, company_id, full_name, title, email, phone, kind, source, source_url, linkedin) -> None:
    row = {
        "project_id": project_id, "company_id": company_id, "full_name": full_name,
        "title": title, "email": email, "phone": phone, "contact_kind": kind,
        "source": source, "source_url": source_url, "linkedin_url": linkedin,
    }
    row = {k: v for k, v in row.items() if v is not None}
    with_supabase_retry(lambda: get_supabase().table("contacts").insert(row).execute())


def _kind(full_name, email) -> str:
    if full_name:
        return "named_person"
    local = (email or "").split("@")[0].lower() if email else ""
    if email:
        return "general_inbox"
    return "main_line" if not local else "general_inbox"


def _domain_from_email(email) -> Optional[str]:
    if not email or "@" not in email:
        return None
    dom = email.split("@")[1].lower().strip()
    return None if (not dom or dom in _FREE_EMAIL) else dom


# ─── public: article contacts ──────────────────────────────────────────────
def persist_article_contacts(project_id: str, signal_id: str, signal_type: str, extracted: dict) -> int:
    """Persist the extractor's contacts_mentioned for one signal. Returns # inserted."""
    cms = (extracted or {}).get("contacts_mentioned") or []
    if not cms:
        return 0
    existing = _existing_contacts(project_id)
    primary = _primary_company_id(project_id)
    src = (
        "press_release" if signal_type == "press_release"
        else "public_filing" if signal_type in ("permit", "utility_filing", "econ_dev_minutes", "planning_filing")
        else "news"
    )
    n = 0
    for c in cms:
        if not isinstance(c, dict):
            continue
        full_name = (c.get("full_name") or "").strip() or None
        email = (c.get("email") or "").strip() or None
        phone = (c.get("phone") or "").strip() or None
        title = (c.get("title") or "").strip() or None
        if not (full_name or email or phone):
            continue
        if _contact_exists(existing, email, full_name):
            continue
        _insert_contact(project_id, primary, full_name, title, email, phone, _kind(full_name, email), src, None, None)
        existing.append({"full_name": full_name, "email": email})
        n += 1
    return n


# ─── public: company website scrape ────────────────────────────────────────
def enrich_company_websites(project_id: str) -> int:
    """Find + scrape the project's team companies' websites for contacts. Returns # inserted."""
    companies = _team_companies(project_id)
    if not companies:
        return 0
    existing = _existing_contacts(project_id)
    inserted, seen_domains = 0, set()
    for co in companies[:_MAX_COMPANIES]:
        site = _company_website(co, existing)
        if not site:
            continue
        dom = urlparse(site).netloc.lower().replace("www.", "")
        if not dom or dom in seen_domains:
            continue
        seen_domains.add(dom)
        try:
            inserted += _scrape_company(project_id, co, site, existing)
        except Exception as exc:  # noqa: BLE001
            log.warning("contacts: scrape %s failed: %s", site, exc)
    return inserted


def _company_website(co: dict, existing: list[dict]) -> Optional[str]:
    w = (co.get("website") or "").strip()
    if w:
        return w if w.startswith("http") else f"https://{w}"
    d = (co.get("domain") or "").strip()
    if d:
        return f"https://{d}"
    for c in existing:
        dom = _domain_from_email(c.get("email"))
        if dom:
            return f"https://{dom}"
    name = (co.get("name") or "").strip()
    if not name:
        return None
    res = call_claude_json(
        f'What is the official company website for "{name}" (a US construction-industry company)? '
        f'Return ONLY {{"website": "https://..."}} or {{"website": null}} if you are not confident.',
        timeout=40,
    )
    if isinstance(res, dict):
        w = (res.get("website") or "").strip()
        if w.startswith("http") and "." in urlparse(w).netloc:
            cid = co.get("id")
            try:
                with_supabase_retry(
                    lambda: get_supabase().table("companies").update(
                        {"website": w, "domain": urlparse(w).netloc.replace("www.", "")}
                    ).eq("id", cid).execute()
                )
            except Exception:  # noqa: BLE001
                pass
            return w
    return None


def _scrape_company(project_id: str, co: dict, site: str, existing: list[dict]) -> int:
    import httpx  # lazy
    from bs4 import BeautifulSoup  # lazy

    base = site.rstrip("/")
    company_id = co.get("id")
    headers = {"User-Agent": _ua(), "Accept": "text/html,application/xhtml+xml"}
    emails: dict[str, str] = {}
    linkedin: set[str] = set()
    page_texts: list[tuple[str, str]] = []
    pages_done = 0

    with httpx.Client(timeout=_FETCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
        for path in _PAGES:
            if pages_done >= _MAX_PAGES:
                break
            url = base + path
            try:
                r = client.get(url)
            except Exception:  # noqa: BLE001
                continue
            if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
                continue
            pages_done += 1
            html = r.text
            for m in _EMAIL_RE.findall(html):
                e = m.lower()
                if e.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
                    continue
                emails.setdefault(e, url)
            for m in _LINKEDIN_RE.findall(html):
                linkedin.add(m.rstrip("/"))
            soup = BeautifulSoup(html, "html.parser")
            for t in soup(["script", "style", "noscript"]):
                t.decompose()
            page_texts.append((url, soup.get_text(" ", strip=True)[:6000]))

    inserted = 0
    company_li = next(iter(linkedin), None)  # attach a found company LinkedIn to the first inbox
    for e, src_url in emails.items():
        if _contact_exists(existing, e, None):
            continue
        local = e.split("@")[0].lower()
        kind = "general_inbox" if local in _GENERIC_LOCAL else "named_person"
        _insert_contact(project_id, company_id, None, None, e, None, kind, "company_website", src_url, company_li)
        existing.append({"email": e})
        inserted += 1
        company_li = None

    # Named people via one Claude pass over the richest page.
    if page_texts:
        best = max(page_texts, key=lambda x: len(x[1]))
        people = call_claude_json(
            "From this company web page, extract real PEOPLE (employees/leadership) who are NAMED. "
            'Return ONLY JSON: {"people":[{"full_name":str,"title":str|null,"email":str|null,"linkedin":str|null}]}. '
            "Only include people actually named on the page; return an empty list if none.\n\nPAGE:\n" + best[1],
            timeout=60,
        )
        if isinstance(people, dict):
            for p in (people.get("people") or [])[:_MAX_NAMED]:
                if not isinstance(p, dict):
                    continue
                fn = (p.get("full_name") or "").strip() or None
                if not fn:
                    continue
                em = (p.get("email") or "").strip() or None
                if _contact_exists(existing, em, fn):
                    continue
                li = (p.get("linkedin") or "").strip() or None
                _insert_contact(
                    project_id, company_id, fn, (p.get("title") or "").strip() or None, em, None,
                    "named_person", "company_website", best[0], li,
                )
                existing.append({"full_name": fn, "email": em})
                inserted += 1
    return inserted


def backfill_article_contacts_all() -> dict:
    """One-off: persist article contacts for every non-merged project from its stored
    signal extractions (cheap — DB only, no scraping/Claude)."""
    projects = with_supabase_retry(
        lambda: get_supabase().table("projects").select("id").is_("merged_into", "null").execute().data
    ) or []
    total = 0
    for pr in projects:
        pid = pr["id"]
        sigs = with_supabase_retry(
            lambda: get_supabase().table("signals").select("id, signal_type, extracted").eq("project_id", pid).execute().data
        ) or []
        for s in sigs:
            ex = s.get("extracted")
            if isinstance(ex, dict) and ex.get("contacts_mentioned"):
                try:
                    total += persist_article_contacts(pid, s.get("id"), s.get("signal_type") or "news", ex)
                except Exception as exc:  # noqa: BLE001
                    log.warning("article backfill failed on %s: %s", pid, exc)
    return {"projects": len(projects), "contacts_inserted": total}


def backfill_web_top(n: int = 12) -> dict:
    """One-off: scrape company websites for the top-N in-radius hot/warm projects."""
    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .select("id")
        .is_("merged_into", "null")
        .eq("in_radius", True)
        .in_("relevance_tier", ["hot", "warm"])
        .not_.in_("status", ["archived", "dismissed"])
        .order("relevance_score", desc=True)
        .limit(n)
        .execute()
        .data
    ) or []
    total = 0
    for r in rows:
        try:
            existing = _existing_contacts(r["id"])
            if not _has_website_contacts(existing):
                total += enrich_company_websites(r["id"])
        except Exception as exc:  # noqa: BLE001
            log.warning("web backfill failed on %s: %s", r["id"], exc)
    return {"projects": len(rows), "web_contacts_inserted": total}


def enrich_project_contacts(project_id: str, signal_id: str, signal_type: str, extracted: dict, web: bool) -> dict:
    """Pipeline entrypoint: always persist article contacts; optionally scrape company sites."""
    out = {"article": 0, "web": 0}
    try:
        out["article"] = persist_article_contacts(project_id, signal_id, signal_type, extracted)
    except Exception as exc:  # noqa: BLE001
        log.warning("persist_article_contacts failed on %s: %s", project_id, exc)
    if web:
        try:
            existing = _existing_contacts(project_id)
            if not _has_website_contacts(existing):
                out["web"] = enrich_company_websites(project_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("enrich_company_websites failed on %s: %s", project_id, exc)
    return out
