from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.contacts.models import Contact
from app.contacts.schemas import ContactCreate, ContactOut, ContactUpdate
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.filtering import apply_filters_for
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.services import search_sync
from app.users.models import User

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=Page[ContactOut], dependencies=[Depends(require_perm("contacts:read"))])
def list_contacts(filters: str | None = Query(None), 
    company_id: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Contact)
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(Contact.first_name.ilike(q), Contact.last_name.ilike(q), Contact.position.ilike(q)))
    stmt = apply_sort(stmt, Contact, params.sort)
    stmt = apply_filters_for(db, stmt, "contacts", filters)
    return paginate(db, stmt, params)


@router.get("/{contact_id}", response_model=ContactOut, dependencies=[Depends(require_perm("contacts:read"))])
def get_contact(contact_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Contact, contact_id, "Contact")


@router.post("", response_model=ContactOut)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("contacts:write"))):
    contact = Contact(**payload.model_dump())
    db.add(contact)
    db.flush()
    log_activity(db, "contact", contact.id, "system", "Contact created", user_id=user.id)
    audit(db, user.id, "create", "contact", contact.id, {"name": contact.full_name})
    db.commit()
    search_sync.sync_contact(contact)
    return contact


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: str, payload: ContactUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("contacts:write"))):
    contact = get_or_404(db, Contact, contact_id, "Contact")
    changes = apply_updates(contact, payload.model_dump(exclude_unset=True))
    if changes:
        audit(db, user.id, "update", "contact", contact.id, changes)
    db.commit()
    search_sync.sync_contact(contact)
    return contact


@router.delete("/{contact_id}", response_model=Message)
def delete_contact(contact_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("contacts:delete"))):
    contact = get_or_404(db, Contact, contact_id, "Contact")
    name = contact.full_name
    db.delete(contact)
    audit(db, user.id, "delete", "contact", contact_id, {"name": name})
    db.commit()
    search_sync.remove("contacts", contact_id)
    return {"detail": "Contact deleted"}
