from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.filtering import apply_filters_for
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.notifications.service import notify
from app.services.numbering import next_number
from app.support.models import TICKET_PRIORITIES, TICKET_STATUSES, Ticket
from app.support.schemas import TicketCreate, TicketOut, TicketUpdate
from app.users.models import User

router = APIRouter(prefix="/tickets", tags=["support"])


def _validate(data: dict) -> None:
    if data.get("priority") and data["priority"] not in TICKET_PRIORITIES:
        raise AppError(f"Invalid priority. Expected one of {TICKET_PRIORITIES}")
    if data.get("status") and data["status"] not in TICKET_STATUSES:
        raise AppError(f"Invalid status. Expected one of {TICKET_STATUSES}")


@router.get("", response_model=Page[TicketOut], dependencies=[Depends(require_perm("support:read"))])
def list_tickets(filters: str | None = Query(None), 
    status: str | None = None,
    priority: str | None = None,
    assigned_to_id: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Ticket)
    if status:
        stmt = stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if assigned_to_id:
        stmt = stmt.where(Ticket.assigned_to_id == assigned_to_id)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(Ticket.subject.ilike(q), Ticket.number.ilike(q)))
    stmt = apply_sort(stmt, Ticket, params.sort)
    stmt = apply_filters_for(db, stmt, "support", filters)
    return paginate(db, stmt, params)


@router.get("/{ticket_id}", response_model=TicketOut, dependencies=[Depends(require_perm("support:read"))])
def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Ticket, ticket_id, "Ticket")


@router.post("", response_model=TicketOut)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("support:write"))):
    data = payload.model_dump()
    _validate(data)
    ticket = Ticket(**data, number=next_number(db, "ticket"))
    db.add(ticket)
    db.flush()
    audit(db, user.id, "create", "ticket", ticket.id, {"number": ticket.number})
    if ticket.assigned_to_id and ticket.assigned_to_id != user.id:
        notify(db, ticket.assigned_to_id, "ticket_assigned", f"Ticket assigned: {ticket.subject}",
               f"{ticket.number} — {ticket.priority} priority", "/support")
    db.commit()
    return ticket


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: str, payload: TicketUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("support:write"))):
    ticket = get_or_404(db, Ticket, ticket_id, "Ticket")
    data = payload.model_dump(exclude_unset=True)
    _validate(data)
    previous_assignee = ticket.assigned_to_id
    changes = apply_updates(ticket, data)
    if changes:
        audit(db, user.id, "update", "ticket", ticket.id, changes)
    if "assigned_to_id" in changes and ticket.assigned_to_id and ticket.assigned_to_id != previous_assignee and ticket.assigned_to_id != user.id:
        notify(db, ticket.assigned_to_id, "ticket_assigned", f"Ticket assigned: {ticket.subject}",
               f"{ticket.number}", "/support")
    db.commit()
    return ticket


@router.delete("/{ticket_id}", response_model=Message)
def delete_ticket(ticket_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("support:delete"))):
    ticket = get_or_404(db, Ticket, ticket_id, "Ticket")
    number = ticket.number
    db.delete(ticket)
    audit(db, user.id, "delete", "ticket", ticket_id, {"number": number})
    db.commit()
    return {"detail": "Ticket deleted"}
