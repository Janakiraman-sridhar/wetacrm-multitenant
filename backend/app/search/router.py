"""Global search: Meilisearch when available, SQL ILIKE fallback otherwise."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.companies.models import Company
from app.contacts.models import Contact
from app.core.deps import get_current_user
from app.core.permissions import has_permission
from app.database.session import get_db
from app.deals.models import Deal
from app.leads.models import Lead
from app.projects.models import Project
from app.services.search_client import search_all
from app.tasks.models import Task
from app.users.models import User

router = APIRouter(prefix="/search", tags=["search"])

READ_PERMS = {
    "leads": "leads:read", "companies": "companies:read", "contacts": "contacts:read",
    "deals": "deals:read", "tasks": "tasks:read", "projects": "projects:read",
}


def _sql_search(db: Session, q: str, limit: int) -> dict[str, list[dict]]:
    like = f"%{q}%"
    results: dict[str, list[dict]] = {}
    results["companies"] = [
        {"id": c.id, "type": "company", "title": c.name, "subtitle": c.industry or "", "extra": c.city or ""}
        for c in db.scalars(select(Company).where(Company.name.ilike(like)).limit(limit))
    ]
    results["contacts"] = [
        {"id": c.id, "type": "contact", "title": c.full_name, "subtitle": c.position or "", "extra": ""}
        for c in db.scalars(
            select(Contact).where(or_(Contact.first_name.ilike(like), Contact.last_name.ilike(like))).limit(limit)
        )
    ]
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
    return results


@router.get("")
def global_search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    results = search_all(q, limit)
    engine = "meilisearch"
    if results is None:
        results = _sql_search(db, q, limit)
        engine = "sql"
    # Strip result groups the user has no permission to read.
    perms = user.role.permissions if user.role else []
    filtered = {k: v for k, v in results.items() if has_permission(perms, READ_PERMS.get(k, "settings:read"))}
    return {"engine": engine, "query": q, "results": filtered}
