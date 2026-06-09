# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.27",
#   "openpyxl>=3.1",
#   "python-docx>=1.1",
#   "pypdf>=4.2",
#   "python-dotenv>=1.0",
# ]
# ///
"""
Dropbox -> News Feed dedup matcher (LOCAL, read-only on Dropbox).

Finds feed projects that Treadwell already has (a bid in `$$ Potential Bids`, or a
won/active job in `Projects`) and — with --apply — tags them status='existing' on the
feed so they drop out of the feed/top_picks and the connector won't pitch them.

Safety:
  * DRY-RUN by default — prints a match report, writes nothing.
  * Dropbox is NEVER modified. Folder names are listed; for close calls a candidate
    file is COPIED to WORK_DIR, parsed, then DELETED. Files are never opened in place.
  * --apply only tags STRONG matches; REVIEW matches are listed for you to decide.

Run:  uv run match.py            (dry run)
      uv run match.py --apply    (tag STRONG matches as 'existing')
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

FEED_BASE_URL = (os.environ.get("FEED_BASE_URL", "https://newsfeed.wetreadwell.com")).rstrip("/")
DROPBOX_POTENTIAL_BIDS = os.environ.get("DROPBOX_POTENTIAL_BIDS", "")
DROPBOX_PROJECTS = os.environ.get("DROPBOX_PROJECTS", "")
WORK_DIR = Path(os.environ.get("WORK_DIR", r"C:\tmp\dropbox_dedup_work"))

# Outreach-eligible statuses we check (i.e. things we might still pitch).
ELIGIBLE_STATUSES = "new,active,watching,pursuing"

# ─── matching vocabulary (vendored from backend/services/clusterer.py) ──────────
_LEGAL_SUFFIXES = {
    "inc", "inc.", "incorporated", "llc", "l.l.c.", "llp", "lp", "ltd", "ltd.",
    "limited", "co", "co.", "company", "corp", "corp.", "corporation", "plc",
    "pllc", "pc", "group", "holdings", "partners", "development", "developments",
    "properties", "realty", "construction", "builders", "constructors", "the",
}
_NOISE = {
    "project", "facility", "campus", "expansion", "phase", "new", "proposed",
    "planned", "site", "center", "centre", "data", "building", "addition",
    "renovation", "reno", "remodel", "improvements", "upgrade", "upgrades",
    "repairs", "repair", "tenant", "ti", "set", "permit", "store", "phase",
}
# US state abbreviations / names we may see appended to folder names.
_STATES = {"ks", "mo", "kansas", "missouri", "ne", "nebraska", "ia", "iowa", "ok", "oklahoma"}


def normalize(s: str) -> str:
    s = (s or "").lower().strip().replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(t for t in s.split() if t and t not in _LEGAL_SUFFIXES)


def tokens(s: str) -> Set[str]:
    return {t for t in normalize(s).split() if t not in _NOISE and t not in _STATES and len(t) > 1}


def dedup_key(title: str, city: Optional[str]) -> str:
    return f"{' '.join(sorted(tokens(title)))}|{normalize(city or '')}"


def containment(a: Set[str], b: Set[str]) -> float:
    """Overlap coefficient — forgiving across different naming conventions."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# ─── Dropbox index (folder NAMES only — no file opens here) ─────────────────────
_DATE_BID = re.compile(r"^\d{2}\.\d{2}\.\d{2}\s+")        # "26.06.12 "
_DATE_PROJ = re.compile(r"^\d{2}\.\d{3}\s+")               # "24.117 "
_TRAILING = re.compile(r"[\s!#$*]+$")
_PARENS = re.compile(r"\([^)]*\)")


def _clean_folder_name(name: str) -> str:
    n = _DATE_BID.sub("", name)
    n = _DATE_PROJ.sub("", n)
    n = _PARENS.sub(" ", n)
    n = _TRAILING.sub("", n)
    return n.strip()


def _is_real_project(name: str) -> bool:
    low = name.strip().lower()
    if not name or name[0] in "$_.":
        return False
    if low.startswith("z ") or "new estimate" in low or "new project" in low or "new t&m" in low:
        return False
    if low in ("z declined", "training projects"):
        return False
    return True


def index_dropbox() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for root, label in ((DROPBOX_POTENTIAL_BIDS, "bidding"), (DROPBOX_PROJECTS, "won/active")):
        if not root or not os.path.isdir(root):
            print(f"  ! skipping (not found): {root or '(unset)'}")
            continue
        for entry in os.scandir(root):
            if not entry.is_dir() or not _is_real_project(entry.name):
                continue
            clean = _clean_folder_name(entry.name)
            out.append({
                "folder": entry.name,
                "path": entry.path,
                "label": label,
                "clean": clean,
                "tokens": tokens(clean),
            })
    return out


# ─── feed client (read + tag) ───────────────────────────────────────────────────
def fetch_eligible_projects() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page = 1
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        while True:
            r = c.get(f"{FEED_BASE_URL}/api/projects",
                      params={"status": ELIGIBLE_STATUSES, "page": page, "page_size": 100, "sort": "relevance"})
            r.raise_for_status()
            env = r.json()
            items.extend(env.get("items", []))
            if page >= (env.get("total_pages") or 1):
                break
            page += 1
    return items


def tag_existing(project_id: str, note: str) -> bool:
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        r = c.patch(f"{FEED_BASE_URL}/api/projects/{project_id}",
                    json={"status": "existing", "notes": note})
        if r.status_code >= 400:
            print(f"    ! PATCH failed ({r.status_code}): {r.text[:160]}")
            return False
    return True


# ─── deep confirm (close calls only — copy -> parse -> delete) ──────────────────
_SKIP_EXT = {".jpg", ".jpeg", ".png", ".dwg", ".xml", ".zip", ".gif"}
_PARSE_PRIORITY = (".pdf", ".docx", ".xlsx", ".xls")


def _candidate_files(folder_path: str, limit: int = 2) -> List[Path]:
    files = [Path(e.path) for e in os.scandir(folder_path) if e.is_file()]
    files = [f for f in files if f.suffix.lower() not in _SKIP_EXT]
    def rank(f: Path) -> Tuple[int, int]:
        ext = f.suffix.lower()
        name = f.name.lower()
        hint = 0 if any(k in name for k in ("permit", "bid", "spec", "comcheck", "scope", "plan")) else 1
        try:
            extrank = _PARSE_PRIORITY.index(ext)
        except ValueError:
            extrank = 9
        return (extrank, hint)
    return sorted(files, key=rank)[:limit]


def _extract_text(src: Path, cap: int = 20000) -> str:
    """Copy src to WORK_DIR, parse, delete the copy. Returns lowercased text."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    tmp = WORK_DIR / f"_{os.getpid()}_{src.name}"
    text = ""
    try:
        shutil.copy2(src, tmp)
        ext = src.suffix.lower()
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(tmp))
            text = "\n".join((reader.pages[i].extract_text() or "") for i in range(min(3, len(reader.pages))))
        elif ext == ".docx":
            import docx
            text = "\n".join(p.text for p in docx.Document(str(tmp)).paragraphs)
        elif ext in (".xlsx",):
            import openpyxl
            wb = openpyxl.load_workbook(str(tmp), read_only=True, data_only=True)
            ws = wb.active
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= 60:
                    break
                rows.append(" ".join(str(v) for v in row if v is not None))
            text = "\n".join(rows)
            wb.close()
    except Exception as e:  # noqa: BLE001 — never let one bad file break a run
        text = ""
        print(f"      (parse skip {src.name}: {type(e).__name__})")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    return text.lower()[:cap]


def deep_confirm(project: Dict[str, Any], folder: Dict[str, Any]) -> Optional[str]:
    """Open candidate files in the folder; return evidence string if the project's
    city/state or distinctive title tokens appear, else None."""
    city = (project.get("city") or "").lower().strip()
    state = (project.get("state") or "").lower().strip()
    proper = [t for t in tokens(project.get("title") or "") if len(t) >= 4]
    for f in _candidate_files(folder["path"]):
        text = _extract_text(f)
        if not text:
            continue
        hits = []
        if city and city in text:
            hits.append(f"city '{city}'")
        if state and re.search(rf"\b{re.escape(state)}\b", text):
            hits.append(f"state '{state}'")
        tok_hits = [t for t in proper if t in text]
        if len(tok_hits) >= 2:
            hits.append("tokens " + "/".join(tok_hits[:4]))
        if hits and (city in text or len(tok_hits) >= 2):
            return f"{f.name}: " + ", ".join(hits)
    return None


# ─── scoring ────────────────────────────────────────────────────────────────────
def best_match(project: Dict[str, Any], index: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    p_tokens = tokens(project.get("title") or "")
    p_city = normalize(project.get("city") or "")
    p_key = dedup_key(project.get("title") or "", project.get("city"))
    if not p_tokens:
        return None
    scored = []
    for f in index:
        shared = p_tokens & f["tokens"]
        if len(shared) < 2:
            continue
        score = containment(p_tokens, f["tokens"])
        city_match = bool(p_city) and p_city in f["tokens"]
        if city_match:
            score = min(1.0, score + 0.12)
        exact = dedup_key(f["clean"], None).split("|")[0] == p_key.split("|")[0]
        scored.append({**f, "score": round(score, 3), "shared": sorted(shared),
                       "city_match": city_match, "exact": exact})
    if not scored:
        return None
    scored.sort(key=lambda x: (x["exact"], x["score"]), reverse=True)
    return scored[0]


def classify(m: Dict[str, Any], strong: float, review: float) -> str:
    if m["exact"] or m["score"] >= strong or (m["city_match"] and m["score"] >= strong - 0.1):
        return "STRONG"
    if m["score"] >= review:
        return "REVIEW"
    return "NONE"


# ─── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Dropbox -> News Feed dedup matcher")
    ap.add_argument("--apply", action="store_true", help="tag STRONG matches as 'existing' on the feed")
    ap.add_argument("--strong", type=float, default=0.7, help="STRONG score threshold")
    ap.add_argument("--review", type=float, default=0.45, help="REVIEW score threshold")
    ap.add_argument("--no-deep", action="store_true", help="skip opening files on close calls")
    args = ap.parse_args()

    print(f"Feed: {FEED_BASE_URL}   (mode: {'APPLY' if args.apply else 'DRY RUN'})")
    print("Indexing Dropbox folders (names only)...")
    index = index_dropbox()
    print(f"  {len(index)} project folders indexed.")
    print("Fetching outreach-eligible feed projects...")
    projects = fetch_eligible_projects()
    print(f"  {len(projects)} feed projects to check.\n")

    strong_hits: List[Tuple[Dict, Dict]] = []
    review_hits: List[Tuple[Dict, Dict, Optional[str]]] = []

    for p in projects:
        m = best_match(p, index)
        if not m:
            continue
        cls = classify(m, args.strong, args.review)
        if cls == "NONE":
            continue
        if cls == "REVIEW" and not args.no_deep:
            ev = deep_confirm(p, m)
            if ev:
                cls = "STRONG"  # file contents confirm it
                m["evidence"] = ev
            else:
                review_hits.append((p, m, None))
                continue
        if cls == "STRONG":
            strong_hits.append((p, m))
        else:
            review_hits.append((p, m, None))

    # ── report ──
    print("=" * 78)
    print(f"STRONG matches ({len(strong_hits)}) - already in Treadwell's pipeline:")
    for p, m in strong_hits:
        loc = ", ".join(x for x in [p.get("city"), p.get("state")] if x)
        print(f"  • {p.get('title')}  [{loc}]")
        print(f"      -> {m['label']}: {m['folder']}   (score {m['score']}"
              f"{', exact' if m['exact'] else ''}{', city' if m['city_match'] else ''})")
        if m.get("evidence"):
            print(f"      file-confirmed: {m['evidence']}")
    print(f"\nREVIEW matches ({len(review_hits)}) - likely, but eyeball before tagging:")
    for p, m, _ in review_hits:
        loc = ", ".join(x for x in [p.get("city"), p.get("state")] if x)
        print(f"  ? {p.get('title')}  [{loc}]")
        print(f"      ~ {m['label']}: {m['folder']}   (score {m['score']}; shared {'/'.join(m['shared'][:5])})")
    print("=" * 78)

    if args.apply:
        print(f"\nApplying status='existing' to {len(strong_hits)} STRONG matches...")
        done = 0
        for p, m in strong_hits:
            if tag_existing(p["id"], f"Matched Treadwell pipeline ({m['label']}): {m['folder']}"):
                done += 1
                print(f"  tagged: {p.get('title')}")
        print(f"\nDone. {done}/{len(strong_hits)} tagged 'existing'. "
              f"(REVIEW matches were left untouched.)")
    else:
        print("\nDRY RUN - nothing written. Re-run with --apply to tag the STRONG matches.")
        print("Review the REVIEW list; to tag one manually, set it to 'Existing' in the feed UI.")


if __name__ == "__main__":
    main()
