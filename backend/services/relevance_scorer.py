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
You score how valuable a construction PROJECT is as a flooring sales opportunity.

Weigh:
- project_type: data centers and mission-critical facilities are the top prize; large \
distribution/manufacturing/industrial are strong; healthcare/higher-ed are good; other_commercial lower.
- in_radius: out-of-radius projects are far less actionable.
- stage: earlier reachable stages (planning, design, permitting, procurement, pre_bid) give \
Treadwell time to get in front of the team; under_construction is late; complete/dead are near-zero.
- team_confidence: a named general contractor (gc_named) means a reachable buyer (highest); \
developer_named is good; owner_only is a lead; unknown is weakest.
- scale: bigger est_value_usd / est_sqft / est_megawatts = bigger flooring scope.

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

    # ── project_type (0-35) ──
    ptype = (project.get("project_type") or "").lower()
    type_points = {
        "data_center": 35,
        "mission_critical": 32,
        "distribution": 24,
        "manufacturing": 24,
        "industrial": 22,
        "healthcare": 18,
        "higher_ed": 16,
        "other_commercial": 10,
    }.get(ptype, 10)
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

    # ── scale (0-10) ──
    scale_points = 0
    mw = _num(project.get("est_megawatts"))
    sqft = _num(project.get("est_sqft"))
    value = _num(project.get("est_value_usd"))
    if mw and mw >= 50:
        scale_points = 10
    elif mw and mw >= 10:
        scale_points = 7
    elif value and value >= 100_000_000:
        scale_points = 9
    elif value and value >= 25_000_000:
        scale_points = 6
    elif sqft and sqft >= 500_000:
        scale_points = 6
    elif sqft and sqft >= 100_000:
        scale_points = 4
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
