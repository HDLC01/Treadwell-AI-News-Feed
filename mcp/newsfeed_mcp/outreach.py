"""Compose a grounded outreach letter from a real feed project + contact.

The connector does NOT send anything. It returns {to, subject, body, ...} so the
caller hands it to their own Gmail connector (create_draft) for human review.
This mirrors the feed's golden rule: AI drafts, humans decide — no batch send.

Style: plain, specific, no filler. Every claim is grounded in the project facts
we actually have. No "I hope this finds you well", no "excited to reach out",
no "leverage/seamless/elevate".
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Project type -> the Treadwell flooring angle that actually fits it.
_FLOORING_ANGLE = {
    "data_center": "seamless epoxy and polished-concrete systems built for heavy equipment loads and clean, low-dust environments",
    "warehouse": "high-durability epoxy and polished concrete for forklift traffic and racking loads",
    "industrial": "chemical- and abrasion-resistant epoxy floor systems",
    "manufacturing": "epoxy and urethane-cement systems for production floors",
    "distribution": "polished concrete and epoxy for high-traffic distribution space",
    "healthcare": "seamless, sanitary epoxy flooring for clinical and processing areas",
    "education": "durable polished concrete and epoxy for schools and campus facilities",
    "retail": "polished concrete and decorative epoxy for retail environments",
    "office": "polished concrete and resinous flooring for commercial interiors",
    "government": "compliant, long-wearing epoxy and polished-concrete systems",
    "aviation": "hangar-grade epoxy and polished concrete for aviation facilities",
}
_DEFAULT_ANGLE = "commercial epoxy and polished-concrete flooring"

# Roles we prefer to address, best first.
_ROLE_RANK = {
    "general_contractor": 0,
    "construction_manager": 1,
    "developer": 2,
    "owner": 3,
    "end_user": 4,
    "architect": 5,
    "engineer": 6,
}


def _signer(signer_name: Optional[str], signer_email: Optional[str]) -> Dict[str, str]:
    return {
        "name": signer_name or os.environ.get("TREADWELL_SIGNER_NAME", "Treadwell"),
        "email": signer_email or os.environ.get("TREADWELL_SIGNER_EMAIL", ""),
        "phone": os.environ.get("TREADWELL_PHONE", ""),
    }


def pick_contact(
    contacts: List[Dict[str, Any]],
    team: List[Dict[str, Any]],
    contact_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Choose the best contact to address: explicit id wins; else a named person
    with an email, preferring contacts at the highest-priority team company."""
    if not contacts:
        return None
    if contact_id:
        for c in contacts:
            if str(c.get("id")) == str(contact_id):
                return c
    # rank companies by role so we prefer the GC's estimator over, say, the architect's
    role_by_company = {m.get("company_id"): m.get("role") for m in team}

    def score(c: Dict[str, Any]) -> tuple:
        named = c.get("contact_kind") == "named_person" and bool(c.get("full_name"))
        has_email = bool(c.get("email"))
        role = role_by_company.get(c.get("company_id"), "")
        return (
            0 if not c.get("do_not_contact") else 1,   # never prefer do-not-contact
            0 if has_email else 1,
            0 if named else 1,
            _ROLE_RANK.get(role, 99),
            0 if c.get("verified") else 1,
        )

    return sorted(contacts, key=score)[0]


def _loc(project: Dict[str, Any]) -> str:
    city, state = project.get("city"), project.get("state")
    if city and state:
        return f"{city}, {state}"
    return city or state or "your area"


def _scale_clause(project: Dict[str, Any]) -> str:
    bits = []
    sqft = project.get("est_sqft")
    if sqft:
        try:
            bits.append(f"~{int(sqft):,} sq ft")
        except (TypeError, ValueError):
            pass
    mw = project.get("est_megawatts")
    if mw:
        bits.append(f"~{mw} MW")
    return f" ({', '.join(bits)})" if bits else ""


def compose_outreach(
    project: Dict[str, Any],
    contact: Optional[Dict[str, Any]],
    signer_name: Optional[str] = None,
    signer_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Build {to, subject, body, rationale, warnings} for the Gmail connector."""
    warnings: List[str] = []
    sign = _signer(signer_name, signer_email)

    title = project.get("title") or "your upcoming project"
    ptype = (project.get("project_type") or "").lower()
    angle = _FLOORING_ANGLE.get(ptype, _DEFAULT_ANGLE)
    where = _loc(project)
    stage = (project.get("stage") or "").replace("_", " ")
    scale = _scale_clause(project)

    to = ""
    greeting = "Hello,"
    company = ""
    if contact:
        company = contact.get("company_name") or ""
        if contact.get("do_not_contact"):
            warnings.append(
                f"Contact {contact.get('full_name') or contact.get('email')} is flagged "
                "do_not_contact — do NOT send. Pick another contact."
            )
        to = contact.get("email") or ""
        if not to:
            warnings.append("Chosen contact has no email on file — fill in a recipient before sending.")
        name = contact.get("full_name")
        if name:
            greeting = f"Hi {name.split()[0]},"
    else:
        warnings.append("No contact available for this project — recipient left blank.")

    stage_clause = f", which we're tracking at the {stage} stage" if stage else ""
    co_clause = f" at {company}" if company else ""

    subject = f"Treadwell flooring for {title}"

    lines = [
        greeting,
        "",
        f"I'm with Treadwell, a Kansas City commercial flooring contractor. We came across "
        f"{title} in {where}{stage_clause}{scale} and wanted to introduce ourselves early.",
        "",
        f"We install {angle}. If the flooring scope is still being put together{co_clause}, "
        f"we'd like to be considered and can turn around budget pricing quickly.",
        "",
        "Could I send a short capabilities sheet and a few comparable projects, or connect with "
        "whoever is handling the flooring estimate?",
        "",
        "Thanks,",
        sign["name"],
    ]
    if sign["email"]:
        lines.append(sign["email"])
    if sign["phone"]:
        lines.append(sign["phone"])

    return {
        "to": to,
        "subject": subject,
        "body": "\n".join(lines),
        "rationale": (
            f"Grounded in feed facts: type={ptype or 'unknown'}, stage={stage or 'unknown'}, "
            f"location={where}. Flooring angle chosen for project type. Addressed to "
            f"{(contact or {}).get('full_name') or (contact or {}).get('company_name') or 'unknown contact'}."
        ),
        "warnings": warnings,
    }
