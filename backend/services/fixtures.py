"""
DEMO_MODE sample data + helper accessors.

When DEMO_MODE is on (no Supabase configured), every API router reads from this
module instead of the database, so the frontend looks fully populated with zero
external services.

The shapes here mirror SPEC section 4 EXACTLY (ProjectSummary / ProjectDetail /
Signal / Contact / DigestSummary / PipelineRun). Distances are real great-circle
miles from Kansas City (39.0997, -94.5786); the in_radius flag follows the radius
rule (data_center <= 350 mi, everything else <= 70 mi).

Ten internally-consistent projects: five data centers spread across the 350-mile
ring (Council Bluffs IA, Altoona/Des Moines IA, St. Louis MO, Topeka KS, Cedar
Rapids IA) plus distribution / healthcare / manufacturing / higher-ed / industrial
work inside (and one just outside) the 70-mile metro gate. Stages and
team_confidence are varied on purpose.

All accessors return plain dicts/lists of dicts (JSON-ready); routers wrap them in
the pydantic response models. None of the data is mutated by reads.
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# ─── Time anchors (relative to "now" so the demo always looks fresh) ──────
_NOW = datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _days_ago(n: float) -> str:
    return _iso(_NOW - timedelta(days=n))


_TODAY = _NOW.date()


def _date_str(d: date) -> str:
    return d.isoformat()


# ─── Companies (referenced by team + contacts) ───────────────────────────
# Kept as a small registry so contacts and team members agree on company_id/name.
COMPANIES: Dict[str, Dict[str, Any]] = {
    "co-meta": {
        "id": "co-meta", "name": "Meta Platforms, Inc.",
        "company_type": "end_user", "is_hyperscaler": True,
        "hq_city": "Menlo Park", "hq_state": "CA",
    },
    "co-turner": {
        "id": "co-turner", "name": "Turner Construction Company",
        "company_type": "general_contractor", "is_hyperscaler": False,
        "hq_city": "New York", "hq_state": "NY",
    },
    "co-qts": {
        "id": "co-qts", "name": "QTS Data Centers",
        "company_type": "developer", "is_hyperscaler": True,
        "hq_city": "Overland Park", "hq_state": "KS",
    },
    "co-mortenson": {
        "id": "co-mortenson", "name": "Mortenson Construction",
        "company_type": "general_contractor", "is_hyperscaler": False,
        "hq_city": "Minneapolis", "hq_state": "MN",
    },
    "co-aligned": {
        "id": "co-aligned", "name": "Aligned Data Centers",
        "company_type": "developer", "is_hyperscaler": True,
        "hq_city": "Dallas", "hq_state": "TX",
    },
    "co-evergy": {
        "id": "co-evergy", "name": "Evergy, Inc.",
        "company_type": "utility", "is_hyperscaler": False,
        "hq_city": "Topeka", "hq_state": "KS",
    },
    "co-microsoft": {
        "id": "co-microsoft", "name": "Microsoft Corporation",
        "company_type": "end_user", "is_hyperscaler": True,
        "hq_city": "Redmond", "hq_state": "WA",
    },
    "co-holder": {
        "id": "co-holder", "name": "Holder Construction Group",
        "company_type": "general_contractor", "is_hyperscaler": False,
        "hq_city": "Atlanta", "hq_state": "GA",
    },
    "co-edgeconnex": {
        "id": "co-edgeconnex", "name": "EdgeConneX",
        "company_type": "developer", "is_hyperscaler": True,
        "hq_city": "Herndon", "hq_state": "VA",
    },
    "co-jecompany": {
        "id": "co-jecompany", "name": "J.E. Dunn Construction",
        "company_type": "general_contractor", "is_hyperscaler": False,
        "hq_city": "Kansas City", "hq_state": "MO",
    },
    "co-northpoint": {
        "id": "co-northpoint", "name": "NorthPoint Development",
        "company_type": "developer", "is_hyperscaler": False,
        "hq_city": "Riverside", "hq_state": "MO",
    },
    "co-amazon": {
        "id": "co-amazon", "name": "Amazon.com Services LLC",
        "company_type": "end_user", "is_hyperscaler": True,
        "hq_city": "Seattle", "hq_state": "WA",
    },
    "co-stlukes": {
        "id": "co-stlukes", "name": "Saint Luke's Health System",
        "company_type": "owner", "is_hyperscaler": False,
        "hq_city": "Kansas City", "hq_state": "MO",
    },
    "co-mccarthy": {
        "id": "co-mccarthy", "name": "McCarthy Building Companies",
        "company_type": "general_contractor", "is_hyperscaler": False,
        "hq_city": "St. Louis", "hq_state": "MO",
    },
    "co-panasonic": {
        "id": "co-panasonic", "name": "Panasonic Energy of North America",
        "company_type": "owner", "is_hyperscaler": False,
        "hq_city": "De Soto", "hq_state": "KS",
    },
    "co-mizzou": {
        "id": "co-mizzou", "name": "University of Missouri System",
        "company_type": "owner", "is_hyperscaler": False,
        "hq_city": "Columbia", "hq_state": "MO",
    },
    "co-kiewit": {
        "id": "co-kiewit", "name": "Kiewit Corporation",
        "company_type": "general_contractor", "is_hyperscaler": False,
        "hq_city": "Omaha", "hq_state": "NE",
    },
    "co-google": {
        "id": "co-google", "name": "Google LLC",
        "company_type": "end_user", "is_hyperscaler": True,
        "hq_city": "Mountain View", "hq_state": "CA",
    },
}


def _team_member(company_id: str, role: str, confidence: float, label: str) -> Dict[str, Any]:
    co = COMPANIES[company_id]
    return {
        "company_id": co["id"],
        "company_name": co["name"],
        "company_type": co["company_type"],
        "role": role,
        "confidence": confidence,
        "confidence_label": label,
        "is_hyperscaler": co["is_hyperscaler"],
    }


# Role priority for selecting the "top" team member on a summary card.
_ROLE_PRIORITY = {
    "general_contractor": 0,
    "developer": 1,
    "owner": 2,
    "end_user": 3,
    "construction_manager": 4,
    "architect": 5,
    "engineer": 6,
    "utility": 7,
    "other": 8,
}


def _top_team_member(team: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not team:
        return None
    best = sorted(
        team,
        key=lambda m: (_ROLE_PRIORITY.get(m["role"], 99), -m.get("confidence", 0)),
    )[0]
    return {
        "company_name": best["company_name"],
        "role": best["role"],
        "confidence_label": best["confidence_label"],
    }


# ─── Projects (the central unit) ─────────────────────────────────────────
# Each entry is a full ProjectDetail; list/summary views project a subset.
_PROJECTS: List[Dict[str, Any]] = [
    # 1 — Data center, Council Bluffs IA (164.0 mi) — under construction, GC named, hot
    {
        "id": "prj-meta-cb",
        "title": "Meta Council Bluffs Data Center — Phase 4 Expansion",
        "summary": (
            "Meta is expanding its Council Bluffs hyperscale campus with a fourth "
            "building, adding roughly 250 MW of capacity. Site work is underway and a "
            "general contractor is mobilized; interior fit-out packages are expected to "
            "bid over the next two quarters."
        ),
        "project_type": "data_center",
        "stage": "under_construction",
        "address": "13800 Veterans Memorial Hwy",
        "city": "Council Bluffs", "state": "IA", "county": "Pottawattamie",
        "latitude": 41.2619, "longitude": -95.8608,
        "distance_mi": 164.0, "in_radius": True,
        "est_value_usd": 800000000, "est_sqft": 970000, "est_megawatts": 250,
        "relevance_score": 94, "relevance_tier": "hot",
        "relevance_reasoning": {
            "summary": "Active hyperscale build inside the 350mi ring with a named GC — prime fit-out window.",
            "factors": [
                "Hyperscaler end user (Meta) confirmed",
                "GC mobilized (Turner) — fit-out subcontracts imminent",
                "Large MW + sqft footprint",
                "Within data-center radius (164 / 350 mi)",
            ],
        },
        "team_confidence": "gc_named",
        "status": "pursuing",
        "first_seen_at": _days_ago(41),
        "last_signal_at": _days_ago(0.4),
        "team": [
            _team_member("co-turner", "general_contractor", 0.92, "confirmed"),
            _team_member("co-meta", "end_user", 0.97, "confirmed"),
            _team_member("co-meta", "owner", 0.9, "confirmed"),
        ],
    },
    # 2 — Data center, Altoona / Des Moines IA (185.3 mi) — planning, developer named, hot
    {
        "id": "prj-qts-altoona",
        "title": "QTS Des Moines Metro Data Center Campus (Altoona)",
        "summary": (
            "QTS has assembled land near Altoona for a multi-building data center campus "
            "serving the Des Moines metro. The project is in planning; rezoning and a "
            "utility interconnect study are in progress. No general contractor named yet."
        ),
        "project_type": "data_center",
        "stage": "planning",
        "address": "NE 8th St & US-65",
        "city": "Altoona", "state": "IA", "county": "Polk",
        "latitude": 41.6441, "longitude": -93.4647,
        "distance_mi": 185.3, "in_radius": True,
        "est_value_usd": 1200000000, "est_sqft": 1400000, "est_megawatts": 360,
        "relevance_score": 88, "relevance_tier": "hot",
        "relevance_reasoning": {
            "summary": "Very large early-stage hyperscale developer play in-ring; get in before GC selection.",
            "factors": [
                "Developer named (QTS) but GC still open — best timing for relationships",
                "Massive MW footprint (360 MW)",
                "Early stage (planning) = long runway",
                "Within data-center radius (185 / 350 mi)",
            ],
        },
        "team_confidence": "developer_named",
        "status": "active",
        "first_seen_at": _days_ago(18),
        "last_signal_at": _days_ago(1.2),
        "team": [
            _team_member("co-qts", "developer", 0.85, "likely"),
            _team_member("co-evergy", "utility", 0.6, "rumored"),
        ],
    },
    # 3 — Data center, St. Louis MO (237.8 mi) — design, owner only, warm
    {
        "id": "prj-aligned-stl",
        "title": "Aligned STL01 Data Center — Earth City",
        "summary": (
            "Aligned Data Centers filed design documents for a new facility in the Earth "
            "City industrial area west of St. Louis. The end user is undisclosed; design "
            "is progressing toward a permit submittal."
        ),
        "project_type": "data_center",
        "stage": "design",
        "address": "Earth City Expressway",
        "city": "St. Louis", "state": "MO", "county": "St. Louis",
        "latitude": 38.6270, "longitude": -90.1994,
        "distance_mi": 237.8, "in_radius": True,
        "est_value_usd": 600000000, "est_sqft": 720000, "est_megawatts": 180,
        "relevance_score": 71, "relevance_tier": "warm",
        "relevance_reasoning": {
            "summary": "Solid in-ring data center in design, but only the developer/owner is known so far.",
            "factors": [
                "Developer named (Aligned), owner/end-user undisclosed",
                "Design stage — GC selection upcoming",
                "Within data-center radius (238 / 350 mi)",
                "Further from KC reduces local-crew advantage",
            ],
        },
        "team_confidence": "owner_only",
        "status": "watching",
        "first_seen_at": _days_ago(27),
        "last_signal_at": _days_ago(5),
        "team": [
            _team_member("co-aligned", "developer", 0.8, "likely"),
            _team_member("co-aligned", "owner", 0.75, "likely"),
        ],
    },
    # 4 — Data center, Topeka KS (58.9 mi) — permitting, GC named, hot
    {
        "id": "prj-msft-topeka",
        "title": "Microsoft Topeka Data Center — Building A",
        "summary": (
            "Microsoft is permitting the first building of a planned data center campus "
            "south of Topeka, with Holder Construction selected as general contractor. "
            "Evergy is coordinating a substation upgrade for the load."
        ),
        "project_type": "data_center",
        "stage": "permitting",
        "address": "SW Wanamaker Rd",
        "city": "Topeka", "state": "KS", "county": "Shawnee",
        "latitude": 39.0473, "longitude": -95.6752,
        "distance_mi": 58.9, "in_radius": True,
        "est_value_usd": 1000000000, "est_sqft": 1100000, "est_megawatts": 300,
        "relevance_score": 96, "relevance_tier": "hot",
        "relevance_reasoning": {
            "summary": "Near-metro hyperscale build with a named GC entering permitting — top opportunity.",
            "factors": [
                "Hyperscaler end user (Microsoft) confirmed",
                "GC named (Holder) — fit-out and site subs about to bid",
                "Close to KC (59 mi) — strong local-crew fit",
                "Utility (Evergy) engaged on substation",
            ],
        },
        "team_confidence": "gc_named",
        "status": "pursuing",
        "first_seen_at": _days_ago(33),
        "last_signal_at": _days_ago(0.8),
        "team": [
            _team_member("co-holder", "general_contractor", 0.9, "confirmed"),
            _team_member("co-microsoft", "end_user", 0.95, "confirmed"),
            _team_member("co-microsoft", "owner", 0.88, "likely"),
            _team_member("co-evergy", "utility", 0.7, "likely"),
        ],
    },
    # 5 — Data center, Cedar Rapids IA (250.8 mi) — rumored, unknown team, warm
    {
        "id": "prj-edge-cedarrapids",
        "title": "Cedar Rapids Hyperscale Data Center (Unconfirmed)",
        "summary": (
            "Local reporting points to a large undisclosed technology company evaluating "
            "a Cedar Rapids site for a data center. EdgeConneX has been rumored as the "
            "developer but nothing is confirmed; treat as early intelligence."
        ),
        "project_type": "data_center",
        "stage": "rumored",
        "address": None,
        "city": "Cedar Rapids", "state": "IA", "county": "Linn",
        "latitude": 41.9779, "longitude": -91.6656,
        "distance_mi": 250.8, "in_radius": True,
        "est_value_usd": None, "est_sqft": None, "est_megawatts": 200,
        "relevance_score": 58, "relevance_tier": "warm",
        "relevance_reasoning": {
            "summary": "Edge of the ring, rumored only — worth watching but low certainty.",
            "factors": [
                "Stage is rumored — no confirmed team",
                "Estimated 200 MW if it proceeds",
                "Near the outer edge of the data-center radius (251 / 350 mi)",
                "Developer (EdgeConneX) only rumored",
            ],
        },
        "team_confidence": "unknown",
        "status": "watching",
        "first_seen_at": _days_ago(9),
        "last_signal_at": _days_ago(3),
        "team": [
            _team_member("co-edgeconnex", "developer", 0.35, "rumored"),
        ],
    },
    # 6 — Distribution center, Olathe KS (19.9 mi) — pre_bid, developer named, warm
    {
        "id": "prj-northpoint-olathe",
        "title": "NorthPoint Logistics Park — Olathe Building 2",
        "summary": (
            "NorthPoint Development is preparing to bid the second building of its Olathe "
            "logistics park, a ~1.1M sqft cross-dock distribution center. A general "
            "contractor has not been announced; the developer is leading procurement."
        ),
        "project_type": "distribution",
        "stage": "pre_bid",
        "address": "W 167th St & Lone Elm Rd",
        "city": "Olathe", "state": "KS", "county": "Johnson",
        "latitude": 38.8814, "longitude": -94.8191,
        "distance_mi": 19.9, "in_radius": True,
        "est_value_usd": 95000000, "est_sqft": 1100000, "est_megawatts": None,
        "relevance_score": 74, "relevance_tier": "warm",
        "relevance_reasoning": {
            "summary": "Big metro distribution build about to bid — strong local fit, developer-led.",
            "factors": [
                "Inside the 70-mile metro gate (20 mi)",
                "Pre-bid stage — flooring/coatings scopes imminent",
                "Developer named (NorthPoint), GC open",
                "Large sqft footprint",
            ],
        },
        "team_confidence": "developer_named",
        "status": "active",
        "first_seen_at": _days_ago(14),
        "last_signal_at": _days_ago(1),
        "team": [
            _team_member("co-northpoint", "developer", 0.82, "likely"),
            _team_member("co-amazon", "end_user", 0.4, "rumored"),
        ],
    },
    # 7 — Healthcare / hospital, Lee's Summit MO (16.8 mi) — procurement, GC named, hot
    {
        "id": "prj-stlukes-lees-summit",
        "title": "Saint Luke's East — Patient Tower Addition",
        "summary": (
            "Saint Luke's Health System is adding a five-story patient tower at its Lee's "
            "Summit campus. J.E. Dunn is the general contractor and trade procurement is "
            "underway, including interior finishes and specialty flooring packages."
        ),
        "project_type": "healthcare",
        "stage": "procurement",
        "address": "100 NE Saint Lukes Blvd",
        "city": "Lee's Summit", "state": "MO", "county": "Jackson",
        "latitude": 38.9108, "longitude": -94.3822,
        "distance_mi": 16.8, "in_radius": True,
        "est_value_usd": 140000000, "est_sqft": 210000, "est_megawatts": None,
        "relevance_score": 90, "relevance_tier": "hot",
        "relevance_reasoning": {
            "summary": "Metro healthcare build in active procurement with a hometown GC — ideal timing.",
            "factors": [
                "Inside the 70-mile metro gate (17 mi)",
                "GC named (J.E. Dunn) and actively procuring trades",
                "Healthcare = high-spec flooring/finishes",
                "Owner (Saint Luke's) confirmed",
            ],
        },
        "team_confidence": "gc_named",
        "status": "pursuing",
        "first_seen_at": _days_ago(22),
        "last_signal_at": _days_ago(0.6),
        "team": [
            _team_member("co-jecompany", "general_contractor", 0.93, "confirmed"),
            _team_member("co-stlukes", "owner", 0.95, "confirmed"),
        ],
    },
    # 8 — Manufacturing, Lenexa KS (13.1 mi) — design, owner only, cold
    {
        "id": "prj-panasonic-lenexa",
        "title": "Lenexa Advanced Manufacturing Facility",
        "summary": (
            "A manufacturer affiliated with Panasonic's regional supply chain is in design "
            "for a new advanced-manufacturing facility in Lenexa. No general contractor "
            "is named; the owner is leading early design."
        ),
        "project_type": "manufacturing",
        "stage": "design",
        "address": "Lackman Rd & 95th St",
        "city": "Lenexa", "state": "KS", "county": "Johnson",
        "latitude": 38.9536, "longitude": -94.7336,
        "distance_mi": 13.1, "in_radius": True,
        "est_value_usd": 65000000, "est_sqft": 320000, "est_megawatts": None,
        "relevance_score": 44, "relevance_tier": "cold",
        "relevance_reasoning": {
            "summary": "Local but early and owner-only; lower priority until a GC is engaged.",
            "factors": [
                "Inside the 70-mile metro gate (13 mi)",
                "Design stage, no GC — long runway, low certainty",
                "Owner-only team confidence",
                "Moderate footprint",
            ],
        },
        "team_confidence": "owner_only",
        "status": "watching",
        "first_seen_at": _days_ago(31),
        "last_signal_at": _days_ago(8),
        "team": [
            _team_member("co-panasonic", "owner", 0.7, "likely"),
        ],
    },
    # 9 — Higher ed, Columbia MO (120.9 mi) — planning, owner only, cold, OUT of radius
    {
        "id": "prj-mizzou-columbia",
        "title": "University of Missouri — Engineering Research Building",
        "summary": (
            "The University of Missouri System is planning a new engineering research "
            "building on the Columbia campus. At 121 miles from Kansas City it sits "
            "outside the 70-mile non-data-center gate, so it is logged as context only."
        ),
        "project_type": "higher_ed",
        "stage": "planning",
        "address": "S College Ave",
        "city": "Columbia", "state": "MO", "county": "Boone",
        "latitude": 38.9517, "longitude": -92.3341,
        "distance_mi": 120.9, "in_radius": False,
        "est_value_usd": 180000000, "est_sqft": 250000, "est_megawatts": None,
        "relevance_score": 28, "relevance_tier": "cold",
        "relevance_reasoning": {
            "summary": "Outside the 70-mile non-data-center radius; tracked for awareness only.",
            "factors": [
                "Out of radius (121 mi vs 70 mi gate for non-data-center)",
                "Planning stage, owner-only",
                "Public owner (UM System)",
            ],
        },
        "team_confidence": "owner_only",
        "status": "new",
        "first_seen_at": _days_ago(2),
        "last_signal_at": _days_ago(2),
        "team": [
            _team_member("co-mizzou", "owner", 0.8, "likely"),
        ],
    },
    # 10 — Industrial, Liberty MO (13.2 mi) — under construction, GC named, warm
    {
        "id": "prj-kiewit-liberty",
        "title": "Liberty Industrial Park — Speculative Building D",
        "summary": (
            "A speculative industrial building is under construction in Liberty with "
            "Kiewit as general contractor. Shell is topping out; interior tenant-finish "
            "scopes (including warehouse flooring) are expected to release soon."
        ),
        "project_type": "industrial",
        "stage": "under_construction",
        "address": "Withers Rd & I-35",
        "city": "Liberty", "state": "MO", "county": "Clay",
        "latitude": 39.2461, "longitude": -94.4191,
        "distance_mi": 13.2, "in_radius": True,
        "est_value_usd": 48000000, "est_sqft": 410000, "est_megawatts": None,
        "relevance_score": 68, "relevance_tier": "warm",
        "relevance_reasoning": {
            "summary": "Metro industrial build under way with a named GC — near-term finish scopes.",
            "factors": [
                "Inside the 70-mile metro gate (13 mi)",
                "Under construction with GC named (Kiewit)",
                "Interior finish/flooring scopes upcoming",
                "Speculative — end user not yet known",
            ],
        },
        "team_confidence": "gc_named",
        "status": "active",
        "first_seen_at": _days_ago(38),
        "last_signal_at": _days_ago(2.5),
        "team": [
            _team_member("co-kiewit", "general_contractor", 0.88, "confirmed"),
        ],
    },
]


# ─── Signals (evidence) keyed by project ─────────────────────────────────
_SIGNALS: Dict[str, List[Dict[str, Any]]] = {
    "prj-meta-cb": [
        {
            "id": "sig-meta-1", "signal_type": "news",
            "source_name": "Data Center Frontier",
            "url": "https://www.datacenterfrontier.com/hyperscale/article/meta-council-bluffs-phase-4",
            "title": "Meta Breaks Ground on Fourth Council Bluffs Data Center Building",
            "published_at": _days_ago(41),
            "snippet": "Meta confirmed a fourth building at its Council Bluffs campus, adding about 250 MW; Turner Construction is the general contractor.",
            "extraction_confidence": 0.93,
        },
        {
            "id": "sig-meta-2", "signal_type": "permit",
            "source_name": "Pottawattamie County Permits",
            "url": "https://example-permits.pottco.gov/records/2026-0417",
            "title": "Building permit issued — 13800 Veterans Memorial Hwy (data center shell)",
            "published_at": _days_ago(12),
            "snippet": "Shell permit issued for a 970,000 sqft data center structure; valuation listed at $800M.",
            "extraction_confidence": 0.81,
        },
        {
            "id": "sig-meta-3", "signal_type": "press_release",
            "source_name": "Turner Construction Newsroom",
            "url": "https://www.turnerconstruction.com/news/council-bluffs-mobilization",
            "title": "Turner Mobilizes Midwest Mission-Critical Team for Iowa Expansion",
            "published_at": _days_ago(0.4),
            "snippet": "Turner has mobilized its mission-critical group and will begin releasing interior fit-out bid packages this quarter.",
            "extraction_confidence": 0.86,
        },
    ],
    "prj-qts-altoona": [
        {
            "id": "sig-qts-1", "signal_type": "news",
            "source_name": "Des Moines Register",
            "url": "https://www.example-dmreg.com/business/qts-altoona-campus",
            "title": "QTS Eyes Altoona for Multi-Building Data Center Campus",
            "published_at": _days_ago(18),
            "snippet": "QTS has assembled land near Altoona for a campus that could exceed 1.4M sqft and 360 MW at full build-out.",
            "extraction_confidence": 0.84,
        },
        {
            "id": "sig-qts-2", "signal_type": "econ_dev_minutes",
            "source_name": "City of Altoona Council Minutes",
            "url": "https://www.example-altoona.gov/minutes/2026-05",
            "title": "Council Reviews Rezoning Request for Technology Campus",
            "published_at": _days_ago(1.2),
            "snippet": "The council heard a rezoning request tied to a large technology campus; a utility interconnect study is underway with the regional provider.",
            "extraction_confidence": 0.72,
        },
    ],
    "prj-aligned-stl": [
        {
            "id": "sig-aligned-1", "signal_type": "planning_filing",
            "source_name": "St. Louis County Planning",
            "url": "https://www.example-stlcountymo.gov/planning/earth-city-stl01",
            "title": "Design Review Submittal — Earth City Data Center (STL01)",
            "published_at": _days_ago(27),
            "snippet": "Aligned Data Centers submitted design-review documents for a 720,000 sqft facility; end user not disclosed.",
            "extraction_confidence": 0.79,
        },
        {
            "id": "sig-aligned-2", "signal_type": "news",
            "source_name": "St. Louis Business Journal",
            "url": "https://www.bizjournals.com/stlouis/news/aligned-earth-city",
            "title": "Aligned Advances Earth City Data Center Plans",
            "published_at": _days_ago(5),
            "snippet": "Aligned is moving toward a permit submittal for its Earth City site as it finalizes design.",
            "extraction_confidence": 0.77,
        },
    ],
    "prj-msft-topeka": [
        {
            "id": "sig-msft-1", "signal_type": "news",
            "source_name": "Topeka Capital-Journal",
            "url": "https://www.example-cjonline.com/business/microsoft-topeka-datacenter",
            "title": "Microsoft Selects Holder for Topeka Data Center Build",
            "published_at": _days_ago(33),
            "snippet": "Microsoft has selected Holder Construction as GC for the first building of a Topeka data center campus.",
            "extraction_confidence": 0.9,
        },
        {
            "id": "sig-msft-2", "signal_type": "utility_filing",
            "source_name": "Kansas Corporation Commission",
            "url": "https://www.example-kcc.ks.gov/filings/evergy-wanamaker-substation",
            "title": "Evergy Files for Wanamaker-Area Substation Upgrade",
            "published_at": _days_ago(6),
            "snippet": "Evergy filed for a substation upgrade to serve a 300 MW load south of Topeka.",
            "extraction_confidence": 0.83,
        },
        {
            "id": "sig-msft-3", "signal_type": "permit",
            "source_name": "Shawnee County Permits",
            "url": "https://www.example-snco.us/permits/2026-1188",
            "title": "Site/grading permit under review — SW Wanamaker Rd",
            "published_at": _days_ago(0.8),
            "snippet": "Grading and stormwater permit under review for a 1.1M sqft data center; building permit to follow.",
            "extraction_confidence": 0.8,
        },
    ],
    "prj-edge-cedarrapids": [
        {
            "id": "sig-edge-1", "signal_type": "news",
            "source_name": "The Gazette (Cedar Rapids)",
            "url": "https://www.example-thegazette.com/business/cedar-rapids-data-center-rumor",
            "title": "Mystery Tech Company Scouting Cedar Rapids Site, Sources Say",
            "published_at": _days_ago(9),
            "snippet": "Sources say a large technology company is evaluating a Cedar Rapids site; EdgeConneX has been mentioned as a possible developer.",
            "extraction_confidence": 0.55,
        },
        {
            "id": "sig-edge-2", "signal_type": "econ_dev_minutes",
            "source_name": "Linn County Econ Dev",
            "url": "https://www.example-linncounty.org/minutes/2026-05",
            "title": "Closed-Session Reference to 'Project Prairie'",
            "published_at": _days_ago(3),
            "snippet": "Minutes reference a confidential 'Project Prairie' incentive discussion; no company named publicly.",
            "extraction_confidence": 0.48,
        },
    ],
    "prj-northpoint-olathe": [
        {
            "id": "sig-np-1", "signal_type": "news",
            "source_name": "Kansas City Business Journal",
            "url": "https://www.bizjournals.com/kansascity/news/northpoint-olathe-building-2",
            "title": "NorthPoint Plans Second Olathe Logistics Building",
            "published_at": _days_ago(14),
            "snippet": "NorthPoint Development is preparing a ~1.1M sqft cross-dock building at its Olathe logistics park.",
            "extraction_confidence": 0.85,
        },
        {
            "id": "sig-np-2", "signal_type": "planning_filing",
            "source_name": "City of Olathe Planning",
            "url": "https://www.example-olatheks.org/planning/lone-elm-bldg2",
            "title": "Site plan approved — Lone Elm Logistics Building 2",
            "published_at": _days_ago(1),
            "snippet": "Site plan approved; the developer indicated trade bid packages would release shortly.",
            "extraction_confidence": 0.74,
        },
    ],
    "prj-stlukes-lees-summit": [
        {
            "id": "sig-sl-1", "signal_type": "press_release",
            "source_name": "Saint Luke's Health System",
            "url": "https://www.example-saintlukeskc.org/news/east-patient-tower",
            "title": "Saint Luke's East to Add Five-Story Patient Tower",
            "published_at": _days_ago(22),
            "snippet": "Saint Luke's announced a 210,000 sqft patient tower at its Lee's Summit campus with J.E. Dunn as GC.",
            "extraction_confidence": 0.92,
        },
        {
            "id": "sig-sl-2", "signal_type": "news",
            "source_name": "Kansas City Business Journal",
            "url": "https://www.bizjournals.com/kansascity/news/saint-lukes-east-tower-procurement",
            "title": "J.E. Dunn Begins Trade Buyout for Saint Luke's Tower",
            "published_at": _days_ago(0.6),
            "snippet": "J.E. Dunn has begun buying out trades for the Saint Luke's East tower, including interior finishes and flooring.",
            "extraction_confidence": 0.88,
        },
    ],
    "prj-panasonic-lenexa": [
        {
            "id": "sig-pan-1", "signal_type": "news",
            "source_name": "Kansas City Business Journal",
            "url": "https://www.bizjournals.com/kansascity/news/lenexa-advanced-manufacturing",
            "title": "Advanced Manufacturing Facility Planned in Lenexa",
            "published_at": _days_ago(31),
            "snippet": "A supplier tied to the regional EV battery supply chain is designing a 320,000 sqft facility in Lenexa.",
            "extraction_confidence": 0.66,
        },
    ],
    "prj-mizzou-columbia": [
        {
            "id": "sig-mu-1", "signal_type": "press_release",
            "source_name": "University of Missouri System",
            "url": "https://www.example-umsystem.edu/news/engineering-research-building",
            "title": "UM System Approves Planning for Engineering Research Building",
            "published_at": _days_ago(2),
            "snippet": "The UM System board approved planning funds for a 250,000 sqft engineering research building in Columbia.",
            "extraction_confidence": 0.78,
        },
    ],
    "prj-kiewit-liberty": [
        {
            "id": "sig-kw-1", "signal_type": "news",
            "source_name": "Kansas City Business Journal",
            "url": "https://www.bizjournals.com/kansascity/news/liberty-spec-building-d",
            "title": "Speculative Industrial Building Rises in Liberty",
            "published_at": _days_ago(38),
            "snippet": "Kiewit is building a 410,000 sqft speculative industrial building near I-35 in Liberty.",
            "extraction_confidence": 0.82,
        },
        {
            "id": "sig-kw-2", "signal_type": "permit",
            "source_name": "Clay County Permits",
            "url": "https://www.example-claycountymo.gov/permits/2026-2204",
            "title": "Tenant finish permit application — Withers Rd Building D",
            "published_at": _days_ago(2.5),
            "snippet": "A tenant-finish permit application was filed covering warehouse flooring and interior buildout.",
            "extraction_confidence": 0.75,
        },
    ],
}


# ─── Contacts keyed by project ───────────────────────────────────────────
def _contact(
    cid: str, company_id: str, full_name: Optional[str], title: Optional[str],
    email: Optional[str], phone: Optional[str], kind: str, source: str,
    source_url: str, verified: bool, dnc: bool = False,
) -> Dict[str, Any]:
    co = COMPANIES[company_id]
    return {
        "id": cid,
        "company_id": company_id,
        "company_name": co["name"],
        "full_name": full_name,
        "title": title,
        "email": email,
        "phone": phone,
        "contact_kind": kind,
        "source": source,
        "source_url": source_url,
        "verified": verified,
        "do_not_contact": dnc,
    }


_CONTACTS: Dict[str, List[Dict[str, Any]]] = {
    "prj-meta-cb": [
        _contact(
            "ct-meta-1", "co-turner", "Dana Whitfield",
            "Project Executive, Mission Critical", "dwhitfield@example-turner.com",
            "+1-712-555-0142", "named_person", "company_website",
            "https://www.turnerconstruction.com/people/dana-whitfield", True,
        ),
        _contact(
            "ct-meta-2", "co-turner", None, "Midwest Preconstruction Inbox",
            "midwest.precon@example-turner.com", None, "general_inbox",
            "company_website", "https://www.turnerconstruction.com/contact", True,
        ),
    ],
    "prj-qts-altoona": [
        _contact(
            "ct-qts-1", "co-qts", "Marcus Lindgren", "VP, Development — Central Region",
            "mlindgren@example-qts.com", "+1-913-555-0190", "named_person",
            "press_release", "https://www.example-qts.com/news/central-region", False,
        ),
    ],
    "prj-aligned-stl": [
        _contact(
            "ct-aligned-1", "co-aligned", None, "General Inquiries",
            "info@example-aligneddc.com", "+1-877-555-0100", "general_inbox",
            "company_website", "https://www.example-aligneddc.com/contact", True,
        ),
    ],
    "prj-msft-topeka": [
        _contact(
            "ct-msft-1", "co-holder", "Priya Nair", "Senior Project Manager",
            "pnair@example-holderconstruction.com", "+1-785-555-0177", "named_person",
            "public_filing", "https://www.example-snco.us/permits/2026-1188", True,
        ),
        _contact(
            "ct-msft-2", "co-evergy", None, "Large Load Interconnection",
            "largeload@example-evergy.com", "+1-800-555-0166", "general_inbox",
            "public_filing", "https://www.example-kcc.ks.gov/filings/evergy-wanamaker-substation", True,
        ),
    ],
    "prj-edge-cedarrapids": [],
    "prj-northpoint-olathe": [
        _contact(
            "ct-np-1", "co-northpoint", "Tyler Brennan", "Director of Construction",
            "tbrennan@example-northpoint.com", "+1-816-555-0133", "named_person",
            "company_website", "https://www.example-northpoint.com/team/tyler-brennan", True,
        ),
        _contact(
            "ct-np-2", "co-northpoint", None, "Main Line",
            None, "+1-816-555-0100", "main_line", "company_website",
            "https://www.example-northpoint.com/contact", True,
        ),
    ],
    "prj-stlukes-lees-summit": [
        _contact(
            "ct-sl-1", "co-jecompany", "Renee Calloway", "Senior Estimator — Healthcare",
            "rcalloway@example-jedunn.com", "+1-816-555-0151", "named_person",
            "company_website", "https://www.example-jedunn.com/people/renee-calloway", True,
        ),
        _contact(
            "ct-sl-2", "co-stlukes", "Office of Facilities", "Facilities Planning",
            "facilities@example-saintlukeskc.org", None, "general_inbox",
            "press_release", "https://www.example-saintlukeskc.org/news/east-patient-tower", False,
        ),
    ],
    "prj-panasonic-lenexa": [
        _contact(
            "ct-pan-1", "co-panasonic", None, "Site Development",
            "sitedev@example-panasonic-na.com", None, "general_inbox",
            "enrichment_api", "https://www.example-panasonic-na.com/contact", False,
            dnc=True,
        ),
    ],
    "prj-mizzou-columbia": [
        _contact(
            "ct-mu-1", "co-mizzou", None, "Capital Projects Office",
            "capitalprojects@example-umsystem.edu", "+1-573-555-0120", "general_inbox",
            "company_website", "https://www.example-umsystem.edu/facilities", True,
        ),
    ],
    "prj-kiewit-liberty": [
        _contact(
            "ct-kw-1", "co-kiewit", "Sam Ortega", "Project Manager — Building Group",
            "sortega@example-kiewit.com", "+1-402-555-0188", "named_person",
            "public_filing", "https://www.example-claycountymo.gov/permits/2026-2204", True,
        ),
    ],
}


# ─── Pipeline runs (observability) ───────────────────────────────────────
_RUNS: List[Dict[str, Any]] = [
    {
        "id": "run-001",
        "started_at": _days_ago(0.2),
        "finished_at": _iso(_NOW - timedelta(days=0.2) + timedelta(minutes=7)),
        "status": "success", "trigger": "scheduled",
        "sources_fetched": 18, "signals_ingested": 26,
        "projects_created": 1, "projects_updated": 4, "errors": [],
    },
    {
        "id": "run-002",
        "started_at": _days_ago(1.2),
        "finished_at": _iso(_NOW - timedelta(days=1.2) + timedelta(minutes=9)),
        "status": "partial", "trigger": "scheduled",
        "sources_fetched": 18, "signals_ingested": 21,
        "projects_created": 0, "projects_updated": 3,
        "errors": [{"source": "html_generic:kc-econ-dev", "error": "HTTP 503 from index page"}],
    },
    {
        "id": "run-003",
        "started_at": _days_ago(1.25),
        "finished_at": _iso(_NOW - timedelta(days=1.25) + timedelta(minutes=2)),
        "status": "success", "trigger": "manual",
        "sources_fetched": 3, "signals_ingested": 4,
        "projects_created": 0, "projects_updated": 1, "errors": [],
    },
    {
        "id": "run-004",
        "started_at": _days_ago(2.2),
        "finished_at": _iso(_NOW - timedelta(days=2.2) + timedelta(minutes=8)),
        "status": "success", "trigger": "scheduled",
        "sources_fetched": 18, "signals_ingested": 19,
        "projects_created": 1, "projects_updated": 2, "errors": [],
    },
    {
        "id": "run-005",
        "started_at": _days_ago(3.2),
        "finished_at": _iso(_NOW - timedelta(days=3.2) + timedelta(minutes=6)),
        "status": "failed", "trigger": "scheduled",
        "sources_fetched": 18, "signals_ingested": 0,
        "projects_created": 0, "projects_updated": 0,
        "errors": [{"stage": "extract", "error": "claude CLI timeout on batch 2"}],
    },
]


# ─── Daily digests ───────────────────────────────────────────────────────
def _digest_html(title_lines: List[str], for_date: str) -> str:
    cards = "".join(
        f'<div style="border:1px solid #DBEAFE;border-radius:8px;padding:12px;'
        f'margin-bottom:10px;font-family:Arial,Helvetica,sans-serif;">'
        f'<div style="font-weight:600;color:#1E40AF;">{t}</div></div>'
        for t in title_lines
    )
    return (
        f'<div style="background:#F8FAFC;padding:16px;">'
        f'<h2 style="font-family:Arial,Helvetica,sans-serif;color:#0F172A;">'
        f'Treadwell Radar — {for_date}</h2>{cards}'
        f'<p style="font-size:12px;color:#64748B;font-family:Arial,Helvetica,sans-serif;">'
        f'You are receiving this because you subscribed to Treadwell Radar. '
        f'<a href="https://newsfeed.wetreadwell.com/api/unsubscribe?token=DEMO-TOKEN">Unsubscribe</a>.'
        f'</p></div>'
    )


_DIGESTS: List[Dict[str, Any]] = [
    {
        "digest_date": _date_str(_TODAY),
        "project_ids": ["prj-msft-topeka", "prj-meta-cb", "prj-stlukes-lees-summit", "prj-northpoint-olathe"],
        "new_count": 1, "updated_count": 3,
        "html_body": _digest_html(
            [
                "Microsoft Topeka Data Center — Building A (permitting, GC named)",
                "Meta Council Bluffs Data Center — Phase 4 (under construction)",
                "Saint Luke's East — Patient Tower Addition (procurement)",
                "NorthPoint Logistics Park — Olathe Building 2 (pre-bid)",
            ],
            _date_str(_TODAY),
        ),
    },
    {
        "digest_date": _date_str(_TODAY - timedelta(days=1)),
        "project_ids": ["prj-qts-altoona", "prj-meta-cb", "prj-aligned-stl"],
        "new_count": 0, "updated_count": 3,
        "html_body": _digest_html(
            [
                "QTS Des Moines Metro Data Center Campus (planning)",
                "Meta Council Bluffs Data Center — Phase 4 (under construction)",
                "Aligned STL01 Data Center — Earth City (design)",
            ],
            _date_str(_TODAY - timedelta(days=1)),
        ),
    },
    {
        "digest_date": _date_str(_TODAY - timedelta(days=2)),
        "project_ids": ["prj-edge-cedarrapids", "prj-kiewit-liberty"],
        "new_count": 1, "updated_count": 1,
        "html_body": _digest_html(
            [
                "Cedar Rapids Hyperscale Data Center (rumored)",
                "Liberty Industrial Park — Speculative Building D (under construction)",
            ],
            _date_str(_TODAY - timedelta(days=2)),
        ),
    },
]


# ─── Projection helpers (full detail -> summary / detail shapes) ──────────
_SUMMARY_KEYS = (
    "id", "title", "project_type", "stage", "city", "state", "county",
    "distance_mi", "in_radius", "relevance_score", "relevance_tier",
    "team_confidence", "est_megawatts", "est_value_usd", "est_sqft", "status",
    "last_signal_at", "first_seen_at",
)


def _to_summary(p: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: p.get(k) for k in _SUMMARY_KEYS}
    out["top_team_member"] = _top_team_member(p.get("team", []))
    out["signals_count"] = len(_SIGNALS.get(p["id"], []))
    return out


def _to_detail(p: Dict[str, Any]) -> Dict[str, Any]:
    out = _to_summary(p)
    out.update(
        {
            "summary": p.get("summary"),
            "address": p.get("address"),
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "relevance_reasoning": p.get("relevance_reasoning"),
            "team": copy.deepcopy(p.get("team", [])),
            "contacts_count": len(_CONTACTS.get(p["id"], [])),
        }
    )
    return out


def _csv_set(value: Optional[str]) -> Optional[set]:
    """Parse a comma-separated filter value into a lowercased set, or None."""
    if not value:
        return None
    parts = {part.strip().lower() for part in value.split(",") if part.strip()}
    return parts or None


# ─── Public accessors used by the routers in DEMO_MODE ───────────────────
def list_projects(filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a paginated ProjectListEnvelope dict honoring SPEC query filters.

    Supported filter keys (all optional): q, project_type, stage, in_radius,
    tier, team_confidence, status, sort, page, page_size. Defaults: status
    excludes archived/dismissed, sort=relevance, page=1, page_size=25.
    """
    filters = filters or {}
    rows = [copy.deepcopy(p) for p in _PROJECTS]

    # ── text search across title/summary/city ──
    q = (filters.get("q") or "").strip().lower()
    if q:
        rows = [
            p for p in rows
            if q in (p.get("title") or "").lower()
            or q in (p.get("summary") or "").lower()
            or q in (p.get("city") or "").lower()
        ]

    # ── csv enum filters ──
    types = _csv_set(filters.get("project_type"))
    if types:
        rows = [p for p in rows if (p.get("project_type") or "").lower() in types]

    stages = _csv_set(filters.get("stage"))
    if stages:
        rows = [p for p in rows if (p.get("stage") or "").lower() in stages]

    tiers = _csv_set(filters.get("tier"))
    if tiers:
        rows = [p for p in rows if (p.get("relevance_tier") or "").lower() in tiers]

    team_conf = _csv_set(filters.get("team_confidence"))
    if team_conf:
        rows = [p for p in rows if (p.get("team_confidence") or "").lower() in team_conf]

    # ── status (default excludes archived + dismissed) ──
    statuses = _csv_set(filters.get("status"))
    if statuses:
        rows = [p for p in rows if (p.get("status") or "").lower() in statuses]
    else:
        rows = [p for p in rows if (p.get("status") or "").lower() not in ("archived", "dismissed")]

    # ── in_radius bool ──
    in_radius = filters.get("in_radius")
    if in_radius is not None:
        if isinstance(in_radius, str):
            in_radius = in_radius.strip().lower() in ("1", "true", "yes", "on")
        rows = [p for p in rows if bool(p.get("in_radius")) == bool(in_radius)]

    # ── sort ──
    sort = (filters.get("sort") or "relevance").lower()
    if sort == "distance":
        rows.sort(key=lambda p: (p.get("distance_mi") is None, p.get("distance_mi") or 0.0))
    elif sort == "recent":
        rows.sort(key=lambda p: (p.get("last_signal_at") or ""), reverse=True)
    else:  # relevance (default)
        rows.sort(key=lambda p: (p.get("relevance_score") or 0), reverse=True)

    total = len(rows)

    # ── pagination ──
    try:
        page = max(1, int(filters.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(filters.get("page_size") or 25)
    except (TypeError, ValueError):
        page_size = 25
    page_size = max(1, min(page_size, 100))

    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]
    total_pages = (total + page_size - 1) // page_size if page_size else 0

    return {
        "items": [_to_summary(p) for p in page_rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """Return a ProjectDetail dict for the given id, or None if not found."""
    for p in _PROJECTS:
        if p["id"] == project_id:
            return _to_detail(p)
    return None


def project_exists(project_id: str) -> bool:
    return any(p["id"] == project_id for p in _PROJECTS)


def get_signals(project_id: str) -> List[Dict[str, Any]]:
    """Return the Signal[] for a project (empty list if none / unknown id)."""
    return copy.deepcopy(_SIGNALS.get(project_id, []))


def get_contacts(project_id: str) -> List[Dict[str, Any]]:
    """Return the Contact[] for a project (empty list if none / unknown id)."""
    return copy.deepcopy(_CONTACTS.get(project_id, []))


def get_stats() -> Dict[str, Any]:
    """Return the top-of-feed counters (excludes archived/dismissed from total)."""
    visible = [p for p in _PROJECTS if (p.get("status") or "").lower() not in ("archived", "dismissed")]
    today_iso = _TODAY.isoformat()
    return {
        "total": len(visible),
        "new": sum(1 for p in visible if (p.get("status") or "").lower() == "new"),
        "today": sum(
            1 for p in visible
            if (p.get("first_seen_at") or "").startswith(today_iso)
            or (p.get("last_signal_at") or "").startswith(today_iso)
        ),
        "hot": sum(1 for p in visible if (p.get("relevance_tier") or "").lower() == "hot"),
        "in_radius": sum(1 for p in visible if p.get("in_radius")),
        "data_centers": sum(1 for p in visible if (p.get("project_type") or "") == "data_center"),
    }


def get_digests() -> List[Dict[str, Any]]:
    """Return DigestSummary[] (date desc)."""
    out = [
        {
            "digest_date": d["digest_date"],
            "new_count": d["new_count"],
            "updated_count": d["updated_count"],
            "project_count": len(d["project_ids"]),
        }
        for d in _DIGESTS
    ]
    out.sort(key=lambda d: d["digest_date"], reverse=True)
    return out


def get_digest(digest_date: str) -> Optional[Dict[str, Any]]:
    """Return the full digest detail for a date string (YYYY-MM-DD), or None."""
    for d in _DIGESTS:
        if d["digest_date"] == digest_date:
            return {
                "digest_date": d["digest_date"],
                "html_body": d["html_body"],
                "project_ids": list(d["project_ids"]),
                "new_count": d["new_count"],
                "updated_count": d["updated_count"],
            }
    return None


def get_runs(limit: int = 25) -> List[Dict[str, Any]]:
    """Return PipelineRun[] (started_at desc, capped at limit)."""
    runs = sorted(_RUNS, key=lambda r: (r.get("started_at") or ""), reverse=True)
    return copy.deepcopy(runs[: max(1, limit)])
