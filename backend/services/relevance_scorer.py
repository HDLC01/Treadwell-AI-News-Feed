"""
Relevance scoring: a 0-100 score + hot/warm/cold tier + reasoning for a project.

Primary path: `claude -p` with a strict-JSON prompt that weighs Treadwell's fit
(commercial flooring; data centers prized; earlier stages = more time to engage;
in-radius matters; a named GC means a reachable buyer).

Fallback path: a deterministic, fully-local rule-based score so the pipeline keeps
working when the Claude CLI is unavailable. The deterministic score is also what we
use to validate / clamp the model's output.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.claude_cli import call_claude_json

log = logging.getLogger("newsfeed.score")

_TIERS = {"hot", "warm", "cold"}

SYSTEM_PROMPT = """You are a sales-opportunity scorer for Treadwell, a commercial flooring \
contractor in Kansas City (epoxy, polished concrete, resinous and industrial floor systems). \
You score how valuable a construction PROJECT is as a FLOORING sales opportunity.

The core driver is FLOOR AREA. Treadwell pours floors, so ANY large commercial or industrial \
facility is a big opportunity — NOT just data centers. Data centers, distribution / fulfillment \
warehouses, manufacturing & food-processing plants, healthcare, higher-ed, and other large \
commercial are ALL eligible for the top "hot" tier when the floor area (est_sqft) is large. \
Do NOT down-rank a project just because it is not a data center.

Weigh, roughly in priority:
- scale / floor area: larger est_sqft (and est_megawatts for data centers, or est_value_usd) = \
bigger flooring scope. This is the STRONGEST factor — a 1M-sqft warehouse rivals a data center.
- in_radius / proximity: nearer the Kansas City office is more actionable.
- stage: earlier reachable stages (planning, design, permitting, procurement, pre_bid) give \
Treadwell time to get in front of the team; under_construction is late; complete/dead near-zero.
- team_confidence: a named general contractor (gc_named) is a reachable buyer (best); \
developer_named good; owner_only a lead; unknown weakest.
- project_type: data_center, mission_critical, distribution, manufacturing and industrial are \
all strong (big slabs); healthcare/higher-ed good; only small other_commercial is lower.

Return ONLY this JSON object (no prose, no fences):
{
  "relevance_score": integer 0-100,
  "relevance_tier": "hot" | "warm" | "cold",
  "relevance_reasoning": {
    "summary": string,                 // one or two sentences
    "factors": [string],               // short bullet phrases
    "type_fit": string,
    "stage_fit": string,
    "radius": string,
    "team": string,
    "scale": string
  }
}
Tier mapping: score >= 70 -> hot, 40-69 -> warm, < 40 -> cold."""


def score_project(project: dict) -> dict:
    """Return {relevance_score, relevance_tier, relevance_reasoning} for a project dict.

    Tries claude -p first; on any failure (or off-list output) falls back to a
    deterministic rule-based score. The returned tier is always derived from the
    final score so score/tier never disagree.
    """
    result = _score_via_claude(project)
    if result is None:
        result = _score_via_rules(project)

    score = int(max(0, min(100, round(result.get("relevance_score", 0)))))
    tier = _tier_for(score)
    reasoning = result.get("relevance_reasoning") or {}
    if not isinstance(reasoning, dict):
        reasoning = {"summary": str(reasoning)}

    # Recency override: a stale latest article means it is not a current opportunity.
    if _stale(project.get("last_signal_at")):
        score = min(score, 35)
        tier = "cold"
        reasoning["recency"] = "stale — latest article older than the freshness window"

    return {
        "relevance_score": score,
        "relevance_tier": tier,
        "relevance_reasoning": reasoning,
    }


def _score_via_claude(project: dict) -> Optional[dict]:
    """Ask claude -p for a score. Returns a dict or None on failure/off-list tier."""
    import json

    blob = {
        "title": project.get("title"),
        "project_type": project.get("project_type"),
        "stage": project.get("stage"),
        "city": project.get("city"),
        "state": project.get("state"),
        "in_radius": project.get("in_radius"),
        "distance_mi": project.get("distance_mi"),
        "team_confidence": project.get("team_confidence"),
        "est_value_usd": project.get("est_value_usd"),
        "est_sqft": project.get("est_sqft"),
        "est_megawatts": project.get("est_megawatts"),
    }
    prompt = "Score this project:\n" + json.dumps(blob, ensure_ascii=False)
    result = call_claude_json(prompt, SYSTEM_PROMPT, timeout=90)
    if not isinstance(result, dict):
        return None
    if "relevance_score" not in result:
        return None
    return result


def _score_via_rules(project: dict) -> dict:
    """Deterministic, fully-local fallback scorer. Always returns a complete dict."""
    factors: list[str] = []
    score = 0.0

    # ── project_type (0-25) — big-slab types tied at the top; type no longer dominates ──
    ptype = (project.get("project_type") or "").lower()
    type_points = {
        "data_center": 25,
        "distribution": 25,
        "manufacturing": 25,
        "mission_critical": 24,
        "industrial": 23,
        "healthcare": 18,
        "higher_ed": 16,
        "other_commercial": 12,
    }.get(ptype, 12)
    score += type_points
    factors.append(f"type:{ptype or 'unknown'}(+{type_points})")

    # ── in_radius gate (0-20) ──
    in_radius = project.get("in_radius")
    if in_radius is True:
        score += 20
        factors.append("in radius(+20)")
    elif in_radius is False:
        factors.append("out of radius(+0)")
    else:
        score += 8  # unknown radius — partial credit
        factors.append("radius unknown(+8)")

    # ── stage (0-20): earlier reachable stage scores higher ──
    stage = (project.get("stage") or "").lower()
    stage_points = {
        "rumored": 10,
        "planning": 18,
        "design": 20,
        "permitting": 18,
        "procurement": 16,
        "pre_bid": 17,
        "under_construction": 8,
        "complete": 0,
        "dead": 0,
    }.get(stage, 10)
    score += stage_points
    factors.append(f"stage:{stage or 'unknown'}(+{stage_points})")

    # ── team_confidence (0-15) ──
    team = (project.get("team_confidence") or "unknown").lower()
    team_points = {
        "gc_named": 15,
        "developer_named": 11,
        "owner_only": 6,
        "unknown": 2,
    }.get(team, 2)
    score += team_points
    factors.append(f"team:{team}(+{team_points})")

    # ── scale (0-20) — floor area first; this is the strongest single factor ──
    scale_points = 0
    mw = _num(project.get("est_megawatts"))
    sqft = _num(project.get("est_sqft"))
    value = _num(project.get("est_value_usd"))
    if sqft and sqft >= 1_000_000:
        scale_points = 20
    elif sqft and sqft >= 500_000:
        scale_points = 16
    elif sqft and sqft >= 250_000:
        scale_points = 12
    elif sqft and sqft >= 100_000:
        scale_points = 8
    elif sqft and sqft >= 50_000:
        scale_points = 5
    elif mw and mw >= 100:
        scale_points = 18
    elif mw and mw >= 20:
        scale_points = 12
    elif value and value >= 100_000_000:
        scale_points = 14
    elif value and value >= 25_000_000:
        scale_points = 8
    elif any([mw, sqft, value]):
        scale_points = 3
    score += scale_points
    factors.append(f"scale(+{scale_points})")

    score = int(max(0, min(100, round(score))))
    tier = _tier_for(score)

    return {
        "relevance_score": score,
        "relevance_tier": tier,
        "relevance_reasoning": {
            "summary": f"Rule-based score {score} ({tier}).",
            "factors": factors,
            "type_fit": ptype or "unknown",
            "stage_fit": stage or "unknown",
            "radius": "in" if in_radius is True else ("out" if in_radius is False else "unknown"),
            "team": team,
            "scale": f"mw={mw} sqft={sqft} value={value}",
            "method": "rule_based_fallback",
        },
    }


def _tier_for(score: int) -> str:
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


def _num(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _stale(last_signal_at) -> bool:
    """True if the project's latest signal is older than settings.STALE_MONTHS."""
    try:
        from config import settings
        from services import recency

        return recency.is_older_than_months(last_signal_at, int(getattr(settings, "STALE_MONTHS", 18) or 18))
    except Exception:  # noqa: BLE001
        return False


def rescore_all_rule_based() -> dict:
    """Re-score every non-merged project with the (rebalanced) rule-based scorer.

    Fast, no Claude. Updates relevance_score + relevance_tier ONLY — preserves the
    existing relevance_reasoning so email descriptions (which fall back to the
    reasoning summary) stay intact. Returns counts by tier. Safe no-op without DB.
    """
    from services.supabase_client import get_supabase, is_configured, with_supabase_retry

    if not is_configured():
        return {"skipped": True, "reason": "no DB configured"}

    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("projects")
        .select(
            "id, project_type, stage, in_radius, distance_mi, team_confidence, "
            "est_value_usd, est_sqft, est_megawatts, last_signal_at"
        )
        .is_("merged_into", "null")
        .execute()
        .data
    ) or []

    tally = {"hot": 0, "warm": 0, "cold": 0}
    for p in rows:
        r = _score_via_rules(p)
        sc, tier = r["relevance_score"], r["relevance_tier"]
        if _stale(p.get("last_signal_at")):
            sc, tier = min(sc, 35), "cold"
        tally[tier] = tally.get(tier, 0) + 1
        pid = p["id"]
        with_supabase_retry(
            lambda: get_supabase()
            .table("projects")
            .update({"relevance_score": sc, "relevance_tier": tier})
            .eq("id", pid)
            .execute()
        )
    return {"rescored": len(rows), **tally}
