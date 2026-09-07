from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.companies.models import Company
from app.contacts.models import Contact
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.filtering import apply_filters_for
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.deals.models import Deal, DealStage
from app.deals.schemas import DealOut
from app.leads.models import LEAD_STATUSES, Lead, LeadSource
from app.leads.schemas import LeadConvertIn, LeadCreate, LeadOut, LeadUpdate, SourceOut
from app.notifications.service import notify
from app.services import search_sync
from app.services.email import send_templated
from app.users.models import User

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=Page[LeadOut], dependencies=[Depends(require_perm("leads:read"))])
def list_leads(filters: str | None = Query(None), 
    status: str | None = None,
    assigned_to_id: str | None = None,
    source_id: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Lead)
    if status:
        stmt = stmt.where(Lead.status == status)
    if assigned_to_id:
        stmt = stmt.where(Lead.assigned_to_id == assigned_to_id)
    if source_id:
        stmt = stmt.where(Lead.source_id == source_id)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(Lead.title.ilike(q), Lead.contact_name.ilike(q), Lead.company_name.ilike(q), Lead.email.ilike(q)))
    stmt = apply_sort(stmt, Lead, params.sort)
    stmt = apply_filters_for(db, stmt, "leads", filters)
    return paginate(db, stmt, params)


@router.get("/sources", response_model=list[SourceOut], dependencies=[Depends(require_perm("leads:read"))])
def list_sources(db: Session = Depends(get_db)):
    return db.scalars(select(LeadSource).order_by(LeadSource.name)).all()


@router.get("/{lead_id}", response_model=LeadOut, dependencies=[Depends(require_perm("leads:read"))])
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Lead, lead_id, "Lead")


def _notify_assignment(db: Session, lead: Lead, actor: User) -> None:
    if lead.assigned_to_id and lead.assigned_to_id != actor.id:
        notify(db, lead.assigned_to_id, "lead_assigned", f"Lead assigned: {lead.title}",
               f"Assigned by {actor.full_name}", f"/leads?id={lead.id}")
        assignee = db.get(User, lead.assigned_to_id)
        if assignee:
            send_templated(db, assignee.email, "lead_assigned",
                           {"first_name": assignee.first_name, "lead_title": lead.title})


@router.post("", response_model=LeadOut)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("leads:write"))):
    if payload.status not in LEAD_STATUSES:
        raise AppError(f"Invalid status. Expected one of {LEAD_STATUSES}")
    lead = Lead(**payload.model_dump())
    db.add(lead)
    db.flush()
    log_activity(db, "lead", lead.id, "system", "Lead created", user_id=user.id)
    audit(db, user.id, "create", "lead", lead.id, {"title": lead.title})
    _notify_assignment(db, lead, user)
    db.commit()
    search_sync.sync_lead(lead)
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: str, payload: LeadUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("leads:write"))):
    lead = get_or_404(db, Lead, lead_id, "Lead")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in LEAD_STATUSES:
        raise AppError(f"Invalid status. Expected one of {LEAD_STATUSES}")
    previous_assignee = lead.assigned_to_id
    changes = apply_updates(lead, data)
    if "status" in changes:
        log_activity(db, "lead", lead.id, "status_change",
                     f"Status changed to {lead.status}", user_id=user.id, meta=changes)
    if "assigned_to_id" in changes and lead.assigned_to_id != previous_assignee:
        log_activity(db, "lead", lead.id, "assignment", "Lead reassigned", user_id=user.id)
        _notify_assignment(db, lead, user)
    if changes:
        audit(db, user.id, "update", "lead", lead.id, changes)
    db.commit()
    search_sync.sync_lead(lead)
    return lead


@router.post("/{lead_id}/convert", response_model=DealOut)
def convert_lead(lead_id: str, payload: LeadConvertIn, db: Session = Depends(get_db), user: User = Depends(require_perm("deals:write"))):
    lead = get_or_404(db, Lead, lead_id, "Lead")
    if lead.status == "converted":
        raise AppError("Lead is already converted", 409)

    company_id = payload.company_id
    if not company_id and payload.create_company and lead.company_name:
        company = db.scalar(select(Company).where(Company.name == lead.company_name))
        if not company:
            company = Company(name=lead.company_name, owner_id=lead.assigned_to_id)
            db.add(company)
            db.flush()
        company_id = company.id

    contact_id = payload.contact_id
    if not contact_id and payload.create_contact and lead.contact_name:
        parts = lead.contact_name.split(" ", 1)
        contact = Contact(
            first_name=parts[0], last_name=parts[1] if len(parts) > 1 else "",
            company_id=company_id, emails=[lead.email] if lead.email else [],
            phones=[lead.phone] if lead.phone else [], owner_id=lead.assigned_to_id,
        )
        db.add(contact)
        db.flush()
        contact_id = contact.id

    first_stage = db.scalar(select(DealStage).where(DealStage.is_won.is_(False), DealStage.is_lost.is_(False)).order_by(DealStage.order))
    deal = Deal(
        title=payload.deal_title or lead.title,
        value=payload.value,
        stage_id=first_stage.id,
        probability=first_stage.probability,
        company_id=company_id,
        contact_id=contact_id,
        owner_id=lead.assigned_to_id or user.id,
    )
    db.add(deal)
    db.flush()

    lead.status = "converted"
    lead.converted_deal_id = deal.id
    log_activity(db, "lead", lead.id, "status_change", "Lead converted to deal", user_id=user.id, meta={"deal_id": deal.id})
    log_activity(db, "deal", deal.id, "system", f"Created from lead: {lead.title}", user_id=user.id)
    audit(db, user.id, "convert", "lead", lead.id, {"deal_id": deal.id})
    db.commit()
    search_sync.sync_lead(lead)
    search_sync.sync_deal(deal)
    return deal


@router.delete("/{lead_id}", response_model=Message)
def delete_lead(lead_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("leads:delete"))):
    lead = get_or_404(db, Lead, lead_id, "Lead")
    title = lead.title
    db.delete(lead)
    audit(db, user.id, "delete", "lead", lead_id, {"title": title})
    db.commit()
    search_sync.remove("leads", lead_id)
    return {"detail": "Lead deleted"}
