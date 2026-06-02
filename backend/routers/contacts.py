"""
Contacts router.

The single contacts endpoint honors CONTACTS_GATE_PASSWORD: if that env var is
set, the caller must send a matching `X-Contacts-Key` header (the public-page
carve-out). If it is empty, contacts are open. Returns Contact[] per SPEC §4.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException

from config import settings
from models.schemas import Contact

router = APIRouter(tags=["contacts"])


def _gate(provided_key: Optional[str]) -> None:
    """Raise 401 if the contacts gate is enabled and the key doesn't match."""
    required = settings.CONTACTS_GATE_PASSWORD or ""
    if required and provided_key != required:
        raise HTTPException(
            status_code=401,
            detail="Contacts are gated. Provide a valid X-Contacts-Key header.",
        )


@router.get("/projects/{project_id}/contacts", response_model=List[Contact])
def get_project_contacts(
    project_id: str,
    x_contacts_key: Optional[str] = Header(None, alias="X-Contacts-Key"),
) -> List[Contact]:
    """Contacts for a project's team companies (gated by X-Contacts-Key if set)."""
    _gate(x_contacts_key)

    if settings.demo_mode:
        from services import fixtures

        if not fixtures.project_exists(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return [Contact(**c) for c in fixtures.get_contacts(project_id)]

    from services.supabase_client import get_supabase, with_supabase_retry

    rows = with_supabase_retry(
        lambda: get_supabase()
        .table("contacts")
        .select("*, companies(name)")
        .eq("project_id", project_id)
        .order("contact_kind")
        .execute()
        .data
    ) or []

    out: List[Contact] = []
    for r in rows:
        co = r.get("companies") or {}
        out.append(
            Contact(
                id=r.get("id"),
                company_id=r.get("company_id"),
                company_name=co.get("name"),
                full_name=r.get("full_name"),
                title=r.get("title"),
                email=r.get("email"),
                phone=r.get("phone"),
                contact_kind=r.get("contact_kind", "named_person"),
                source=r.get("source"),
                source_url=r.get("source_url"),
                linkedin_url=r.get("linkedin_url"),
                verified=bool(r.get("verified")),
                do_not_contact=bool(r.get("do_not_contact")),
            )
        )
    return out
