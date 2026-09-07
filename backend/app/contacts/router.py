from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.contacts import service as customer_service
from app.contacts.customer_fields import birthday_key_for
from app.contacts.models import Contact, CustomerNote, Nominee
from app.contacts.schemas import (
    BirthdayOut, ContactCreate, ContactOut, ContactUpdate, CustomerNoteIn, CustomerNoteOut,
    IdentityLookupOut, NomineeIn, RevealIn, RevealOut,
)
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.core.rate_limit import rate_limiter
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.filtering import apply_filters_for
from app.services import search_sync
from app.users.models import User

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _out(contact: Contact) -> dict:
    """Serialise a contact with its identity numbers masked.

    Every read path goes through here, so a full PAN or Aadhaar cannot escape by
    someone forgetting to mask it in one endpoint.
    """
    data = ContactOut.model_validate(contact).model_dump()
    data.update(customer_service.masked_identity(contact))
    return data


def _replace_nominees(db: Session, contact: Contact, nominees: list[NomineeIn]) -> None:
    """Replace a customer's nominees, checking the rules an insurer would."""
    total = sum(n.share_percent for n in nominees)
    if nominees and total != 100:
        raise AppError(f"Nominee shares must total 100% (currently {total}%)")
    for nominee in nominees:
        age = nominee.age
        if age is None and nominee.date_of_birth:
            today = date.today()
            age = today.year - nominee.date_of_birth.year - (
                (today.month, today.day) < (nominee.date_of_birth.month, nominee.date_of_birth.day)
            )
        if age is not None and age < 18 and not nominee.appointee_name:
            raise AppError(f"{nominee.name} is a minor and needs an appointee")

    contact.nominees.clear()
    db.flush()
    for position, nominee in enumerate(nominees):
        contact.nominees.append(Nominee(**nominee.model_dump(), position=position))


# --- list and read ------------------------------------------------------------

@router.get("", response_model=Page[dict], dependencies=[Depends(require_perm("contacts:read"))])
def list_contacts(
    filters: str | None = Query(None),
    company_id: str | None = None,
    stage: str | None = None,
    owner_id: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Contact)
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    if stage:
        stmt = stmt.where(Contact.stage == stage)
    if owner_id:
        stmt = stmt.where(Contact.owner_id == owner_id)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(
            or_(
                Contact.first_name.ilike(q), Contact.last_name.ilike(q),
                Contact.position.ilike(q), Contact.mobile.ilike(q), Contact.alt_mobile.ilike(q),
            )
        )
    stmt = apply_sort(stmt, Contact, params.sort)
    stmt = apply_filters_for(db, stmt, "contacts", filters)
    page = paginate(db, stmt, params)
    page["items"] = [_out(c) for c in page["items"]]
    return page


@router.get("/birthdays", response_model=list[BirthdayOut], dependencies=[Depends(require_perm("contacts:read"))])
def birthdays(
    within_days: int = Query(7, ge=0, le=366),
    db: Session = Depends(get_db),
):
    """Customers with a birthday in the next N days.

    Matched on `birthday_key` (MMDD) so it is an indexed range scan rather than a
    date function over every row, and the year-end wrap is handled by asking for
    two ranges instead of one.
    """
    today = date.today()
    keys = [birthday_key_for(today + timedelta(days=offset)) for offset in range(within_days + 1)]
    rows = db.scalars(
        select(Contact).where(Contact.birthday_key.in_(keys), Contact.date_of_birth.isnot(None))
    ).all()

    out = []
    for contact in rows:
        dob = contact.date_of_birth
        this_year = date(today.year, dob.month, dob.day)
        if this_year < today:
            this_year = date(today.year + 1, dob.month, dob.day)
        out.append(
            {
                "id": contact.id,
                "full_name": contact.full_name,
                "date_of_birth": dob,
                "turning": this_year.year - dob.year,
                "days_away": (this_year - today).days,
                "primary_phone": contact.primary_phone,
                "email": (contact.emails or [None])[0],
                "owner": contact.owner,
            }
        )
    out.sort(key=lambda item: item["days_away"])
    return out


@router.get("/lookup", response_model=IdentityLookupOut, dependencies=[Depends(require_perm("contacts:read"))])
def lookup_by_identity(
    pan: str | None = None,
    aadhaar: str | None = None,
    db: Session = Depends(get_db),
):
    """Find a customer by PAN or Aadhaar without decrypting anything.

    Uses the blind index: the search term is hashed the same way the stored value
    was, and the hashes are compared. Nothing reversible is stored or returned.
    """
    if not pan and not aadhaar:
        raise AppError("Provide a PAN or an Aadhaar number to look up")
    match = customer_service.find_by_identity(db, pan=pan, aadhaar=aadhaar)
    if not match:
        return {"found": False}
    return {"found": True, "contact_id": match.id, "full_name": match.full_name}


@router.get("/{contact_id}", response_model=dict, dependencies=[Depends(require_perm("contacts:read"))])
def get_contact(contact_id: str, db: Session = Depends(get_db)):
    return _out(get_or_404(db, Contact, contact_id, "Contact"))


# --- write --------------------------------------------------------------------

@router.post("", response_model=dict)
def create_contact(
    payload: ContactCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("contacts:write"))
):
    data = payload.model_dump()
    pan, aadhaar = data.pop("pan", None), data.pop("aadhaar", None)
    nominees = data.pop("nominees", None)
    data = customer_service.normalise_customer_fields(db, data)

    contact = Contact(**data)
    db.add(contact)
    db.flush()

    customer_service.apply_identity(db, contact, pan, aadhaar)
    if nominees is not None:
        _replace_nominees(db, contact, [NomineeIn(**n) for n in nominees])

    log_activity(db, "contact", contact.id, "system", "Customer created", user_id=user.id)
    audit(db, user.id, "create", "contact", contact.id, {"name": contact.full_name})
    db.commit()
    search_sync.sync_contact(contact)
    return _out(contact)


@router.patch("/{contact_id}", response_model=dict)
def update_contact(
    contact_id: str,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("contacts:write")),
):
    contact = get_or_404(db, Contact, contact_id, "Contact")
    data = payload.model_dump(exclude_unset=True)
    pan, aadhaar = data.pop("pan", None), data.pop("aadhaar", None)
    nominees = data.pop("nominees", None)
    data = customer_service.normalise_customer_fields(db, data)

    previous_stage = contact.stage
    changes = apply_updates(contact, data)
    customer_service.apply_identity(db, contact, pan, aadhaar)
    if nominees is not None:
        _replace_nominees(db, contact, [NomineeIn(**n) for n in nominees])

    if "stage" in changes and contact.stage != previous_stage:
        log_activity(
            db, "contact", contact.id, "status_change",
            f"Stage changed to {contact.stage}", user_id=user.id, meta=changes,
        )
    if pan is not None or aadhaar is not None:
        # Record that identity data changed, without recording the values.
        audit(db, user.id, "update", "contact", contact.id, {"identity_updated": True})
    if changes:
        audit(db, user.id, "update", "contact", contact.id, changes)
    db.commit()
    search_sync.sync_contact(contact)
    return _out(contact)


@router.delete("/{contact_id}", response_model=Message)
def delete_contact(
    contact_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("contacts:delete"))
):
    contact = get_or_404(db, Contact, contact_id, "Contact")
    name = contact.full_name
    db.delete(contact)
    audit(db, user.id, "delete", "contact", contact_id, {"name": name})
    db.commit()
    search_sync.remove("contacts", contact_id)
    return {"detail": "Contact deleted"}


# --- identity -----------------------------------------------------------------

@router.post(
    "/{contact_id}/reveal",
    response_model=RevealOut,
    dependencies=[Depends(rate_limiter("reveal_pii", 30))],
)
def reveal(
    contact_id: str,
    payload: RevealIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("contacts:read")),
):
    """Return a full PAN or Aadhaar. Needs `contacts:reveal_pii`, and is audited.

    Rate limited as well as permissioned: the permission stops the wrong people
    looking, the limit stops the right people bulk-harvesting.
    """
    contact = get_or_404(db, Contact, contact_id, "Contact")
    value = customer_service.reveal_field(
        db, contact, payload.field, user, request.client.host if request.client else None
    )
    return {"field": payload.field, "value": value}


@router.get("/{contact_id}/pii-access", dependencies=[Depends(require_perm("settings:read"))])
def pii_access_log(contact_id: str, db: Session = Depends(get_db)):
    """Who has viewed this customer's identity numbers."""
    from app.activities.models import AuditLog

    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "contact", AuditLog.entity_id == contact_id,
               AuditLog.action == "reveal_pii")
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "id": row.id,
            "field": (row.changes or {}).get("field"),
            "user": {"id": row.user.id, "name": row.user.full_name} if row.user else None,
            "ip_address": row.ip_address,
            "at": row.created_at,
        }
        for row in rows
    ]


# --- notes --------------------------------------------------------------------

@router.get("/{contact_id}/notes", response_model=list[CustomerNoteOut],
            dependencies=[Depends(require_perm("contacts:read"))])
def list_notes(contact_id: str, db: Session = Depends(get_db)):
    get_or_404(db, Contact, contact_id, "Contact")
    return db.scalars(
        select(CustomerNote)
        .where(CustomerNote.contact_id == contact_id)
        .order_by(CustomerNote.is_pinned.desc(), CustomerNote.created_at.desc())
    ).all()


@router.post("/{contact_id}/notes", response_model=CustomerNoteOut)
def add_note(
    contact_id: str,
    payload: CustomerNoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("contacts:write")),
):
    contact = get_or_404(db, Contact, contact_id, "Contact")
    note = CustomerNote(contact_id=contact.id, body=payload.body,
                        is_pinned=payload.is_pinned, author_id=user.id)
    db.add(note)
    log_activity(db, "contact", contact.id, "note", "Note added",
                 body=payload.body[:500], user_id=user.id)
    db.commit()
    return note


@router.patch("/{contact_id}/notes/{note_id}", response_model=CustomerNoteOut)
def update_note(
    contact_id: str,
    note_id: str,
    payload: CustomerNoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("contacts:write")),
):
    note = get_or_404(db, CustomerNote, note_id, "Note")
    if note.contact_id != contact_id:
        raise AppError("Note does not belong to this customer", 404)
    note.body = payload.body
    note.is_pinned = payload.is_pinned
    db.commit()
    return note


@router.delete("/{contact_id}/notes/{note_id}", response_model=Message)
def delete_note(
    contact_id: str,
    note_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("contacts:write")),
):
    note = get_or_404(db, CustomerNote, note_id, "Note")
    if note.contact_id != contact_id:
        raise AppError("Note does not belong to this customer", 404)
    db.delete(note)
    db.commit()
    return {"detail": "Note deleted"}
