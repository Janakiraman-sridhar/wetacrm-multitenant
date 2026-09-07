"""Global search: Meilisearch when available, SQL ILIKE fallback otherwise."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.companies.models import Company
from app.contacts.models import Contact
from app.core.deps import get_current_user, module_enabled
from app.core.exceptions import PermissionDeniedError
from app.core.permissions import has_permission
from app.core.tenancy import require_tenant_id
from app.core.validators import PAN_PATTERN, normalise_phone
from app.database.session import get_db
from app.deals.models import Deal
from app.leads.models import Lead
from app.loans.models import Loan
from app.policies.models import Policy
from app.projects.models import Project
from app.quotations.models import Quotation
from app.services import crypto
from app.services.search_client import search_all
from app.tasks.models import Task
from app.users.models import User

router = APIRouter(prefix="/search", tags=["search"])

READ_PERMS = {
    "leads": "leads:read", "companies": "companies:read", "contacts": "contacts:read",
    "deals": "deals:read", "tasks": "tasks:read", "projects": "projects:read",
    "policies": "policies:read", "loans": "loans:read", "quotations": "quotations:read",
}


def _people(db: Session, q: str, limit: int) -> list[dict]:
    """Customers by name, phone, or an exact PAN.

    An agent searching a phone number is the common case — someone rings, the number
    is on screen, and they need the record before the third ring. PAN goes through
    the blind index because the stored value is encrypted and cannot be matched with
    LIKE; it is exact-match only, which is what a PAN lookup wants anyway.
    """
    like = f"%{q}%"
    conditions = [
        Contact.first_name.ilike(like),
        Contact.last_name.ilike(like),
        Contact.mobile.ilike(like),
        Contact.alt_mobile.ilike(like),
    ]

    digits = "".join(ch for ch in q if ch.isdigit())
    if len(digits) >= 6:
        normalised = normalise_phone(q)
        if normalised:
            conditions.append(Contact.mobile == normalised)
            conditions.append(Contact.alt_mobile == normalised)

    # Pattern-matched rather than run through `normalise_pan`, which *raises* on
    # anything that is not a PAN — and a search box is fed arbitrary text.
    pan = q.strip().upper().replace(" ", "")
    if PAN_PATTERN.match(pan):
        try:
            conditions.append(Contact.pan_index == crypto.blind_index(require_tenant_id(), pan))
        except Exception:
            # No data key for this tenant — name and phone search still works.
            pass

    return [
        {
            "id": c.id, "type": "contact", "title": c.full_name,
            "subtitle": c.primary_phone or c.position or "",
            "extra": c.city or "",
        }
        for c in db.scalars(select(Contact).where(or_(*conditions)).limit(limit))
    ]


def _insurance(db: Session, q: str, limit: int) -> dict[str, list[dict]]:
    """Policies, loans and quotations — the records an agency looks up by number."""
    like = f"%{q}%"
    return {
        "policies": [
            {
                "id": p.id, "type": "policy", "title": p.policy_number,
                "subtitle": p.customer.full_name if p.customer else "",
                "extra": f"{p.product_line} · {p.status}",
            }
            for p in db.scalars(
                select(Policy)
                .where(or_(Policy.policy_number.ilike(like), Policy.registration_no.ilike(like),
                           Policy.plan_name.ilike(like)))
                .limit(limit)
            )
        ],
        "loans": [
            {
                "id": l.id, "type": "loan", "title": l.loan_type,
                "subtitle": l.customer.full_name if l.customer else "",
                "extra": l.status.replace("_", " "),
            }
            for l in db.scalars(
                select(Loan).where(or_(Loan.loan_type.ilike(like), Loan.remarks.ilike(like))).limit(limit)
            )
        ],
        "quotations": [
            {
                "id": qt.id, "type": "quotation", "title": qt.number,
                "subtitle": qt.contact.full_name if qt.contact else (qt.company.name if qt.company else ""),
                "extra": qt.status,
            }
            for qt in db.scalars(
                select(Quotation).where(Quotation.number.ilike(like)).limit(limit)
            )
        ],
    }


def _sql_search(db: Session, q: str, limit: int) -> dict[str, list[dict]]:
    like = f"%{q}%"
    results: dict[str, list[dict]] = {}
    results["companies"] = [
        {"id": c.id, "type": "company", "title": c.name, "subtitle": c.industry or "", "extra": c.city or ""}
        for c in db.scalars(select(Company).where(Company.name.ilike(like)).limit(limit))
    ]
    results["contacts"] = _people(db, q, limit)
    results["leads"] = [
        {"id": l.id, "type": "lead", "title": l.title, "subtitle": l.company_name or "", "extra": l.status}
        for l in db.scalars(
            select(Lead).where(or_(Lead.title.ilike(like), Lead.contact_name.ilike(like), Lead.company_name.ilike(like))).limit(limit)
        )
    ]
    results["deals"] = [
        {"id": d.id, "type": "deal", "title": d.title, "subtitle": d.company.name if d.company else "", "extra": str(d.value)}
        for d in db.scalars(select(Deal).where(Deal.title.ilike(like)).limit(limit))
    ]
    results["tasks"] = [
        {"id": t.id, "type": "task", "title": t.title, "subtitle": t.status, "extra": t.priority}
        for t in db.scalars(select(Task).where(Task.title.ilike(like)).limit(limit))
    ]
    results["projects"] = [
        {"id": p.id, "type": "project", "title": p.name, "subtitle": p.status, "extra": ""}
        for p in db.scalars(select(Project).where(Project.name.ilike(like)).limit(limit))
    ]
    results.update(_insurance(db, q, limit))
    return results


@router.get("")
def global_search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.is_platform_admin:
        # There is no "everything" to search: an admin has no workspace, and searching
        # across all of them is precisely what tenant isolation exists to prevent.
        raise PermissionDeniedError("Platform administrators cannot use tenant endpoints")

    results = search_all(q, limit)
    engine = "meilisearch"
    if results is None:
        results = _sql_search(db, q, limit)
        engine = "sql"
    else:
        # Meilisearch indexes neither the insurance records nor a customer's phone
        # and PAN, so those are searched in SQL either way. Without this a workspace
        # that switched Meili on would quietly lose policy search.
        results.update(_insurance(db, q, limit))
        results["contacts"] = _people(db, q, limit)
        engine = "meilisearch+sql"

    # Strip groups the user cannot read, and groups this workspace does not have —
    # a general CRM should not get a "Policies" heading in its search dropdown for a
    # module it switched off. Group keys are catalog module keys, so both apply here.
    perms = user.role.permissions if user.role else []
    filtered = {
        key: hits
        for key, hits in results.items()
        if has_permission(perms, READ_PERMS.get(key, "settings:read"))
        and module_enabled(db, key)
    }
    return {"engine": engine, "query": q, "results": filtered}
