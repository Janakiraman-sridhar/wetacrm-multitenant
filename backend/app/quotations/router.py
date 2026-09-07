from datetime import date

from fastapi import APIRouter, Depends, Response, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.filtering import apply_filters_for
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.invoices.models import Invoice, InvoiceItem
from app.invoices.schemas import InvoiceOut
from app.quotations.models import QUOTATION_STATUSES, Quotation, QuotationItem
from app.quotations.schemas import QuotationCreate, QuotationOut, QuotationUpdate, SendQuotationIn
from app.services import billing, storage
from app.services.email import email_configured, send_templated
from app.services.numbering import next_number
from app.services.pdf import document_pdf
from app.settings.models import Setting
from app.users.models import User

router = APIRouter(prefix="/quotations", tags=["quotations"])


def _set_items(db: Session, quotation: Quotation, items: list[dict], discount) -> None:
    computed, subtotal, tax_total = billing.compute_items(items)
    quotation.items.clear()
    for item in computed:
        quotation.items.append(QuotationItem(**item))
    quotation.subtotal = subtotal
    quotation.tax_total = tax_total
    quotation.discount = discount or 0
    quotation.total = billing.compute_total(subtotal, tax_total, discount)


def _setting(db: Session, key: str) -> dict:
    row = db.scalar(select(Setting).where(Setting.key == key))
    return row.value if row else {}


def _company_profile(db: Session) -> dict:
    return _setting(db, "company_profile")


def _logo_bytes(db: Session) -> bytes | None:
    key = _company_profile(db).get("logo_key")
    if not key:
        return None
    try:
        return storage.read_file(key)
    except Exception:
        return None


@router.get("", response_model=Page[QuotationOut], dependencies=[Depends(require_perm("quotations:read"))])
def list_quotations(filters: str | None = Query(None), status: str | None = None, params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Quotation)
    if status:
        stmt = stmt.where(Quotation.status == status)
    if params.search:
        stmt = stmt.where(or_(Quotation.number.ilike(f"%{params.search}%"), Quotation.notes.ilike(f"%{params.search}%")))
    stmt = apply_sort(stmt, Quotation, params.sort)
    stmt = apply_filters_for(db, stmt, "quotations", filters)
    return paginate(db, stmt, params)


@router.get("/{quotation_id}", response_model=QuotationOut, dependencies=[Depends(require_perm("quotations:read"))])
def get_quotation(quotation_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Quotation, quotation_id, "Quotation")


@router.post("", response_model=QuotationOut)
def create_quotation(payload: QuotationCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("quotations:write"))):
    data = payload.model_dump()
    items = data.pop("items", [])
    discount = data.pop("discount", 0)
    data["issue_date"] = data.get("issue_date") or date.today()
    template = _setting(db, "quotation_template")
    if not data.get("terms") and template.get("default_terms"):
        data["terms"] = template["default_terms"]
    quotation = Quotation(**data, number=next_number(db, "quotation"), created_by_id=user.id)
    db.add(quotation)
    db.flush()
    _set_items(db, quotation, items, discount)
    audit(db, user.id, "create", "quotation", quotation.id, {"number": quotation.number})
    if quotation.deal_id:
        log_activity(db, "deal", quotation.deal_id, "system", f"Quotation {quotation.number} created", user_id=user.id)
    db.commit()
    return quotation


@router.patch("/{quotation_id}", response_model=QuotationOut)
def update_quotation(quotation_id: str, payload: QuotationUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("quotations:write"))):
    quotation = get_or_404(db, Quotation, quotation_id, "Quotation")
    data = payload.model_dump(exclude_unset=True)
    if data.get("status") and data["status"] not in QUOTATION_STATUSES:
        raise AppError(f"Invalid status. Expected one of {QUOTATION_STATUSES}")
    items = data.pop("items", None)
    discount = data.pop("discount", None)
    changes = apply_updates(quotation, data)
    if items is not None or discount is not None:
        _set_items(db, quotation,
                   items if items is not None else [
                       {"product_id": i.product_id, "name": i.name, "description": i.description,
                        "quantity": i.quantity, "unit_price": i.unit_price, "tax_rate": i.tax_rate}
                       for i in quotation.items
                   ],
                   discount if discount is not None else quotation.discount)
        changes["items"] = ["updated", "updated"]
    if changes:
        audit(db, user.id, "update", "quotation", quotation.id, {k: v for k, v in changes.items() if k != "items"})
    db.commit()
    return quotation


@router.get("/{quotation_id}/pdf", dependencies=[Depends(require_perm("quotations:read"))])
def quotation_pdf(quotation_id: str, db: Session = Depends(get_db)):
    quotation = get_or_404(db, Quotation, quotation_id, "Quotation")
    pdf = document_pdf("quotation", quotation, _company_profile(db), _setting(db, "quotation_template"), _logo_bytes(db))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{quotation.number}.pdf"'})


@router.post("/{quotation_id}/send", response_model=QuotationOut)
def send_quotation(quotation_id: str, payload: SendQuotationIn, db: Session = Depends(get_db), user: User = Depends(require_perm("quotations:write"))):
    quotation = get_or_404(db, Quotation, quotation_id, "Quotation")
    to = payload.to_email or (quotation.contact.emails[0] if quotation.contact and quotation.contact.emails else None)
    if not to:
        raise AppError("No recipient email — set one on the contact or pass to_email", 400)
    if not email_configured():
        raise AppError(
            "Email isn't configured yet, so the quotation can't be sent. Add SMTP settings in the "
            "backend environment (see Settings → System). You can still download the PDF and send it manually.",
            400,
        )
    profile = _company_profile(db)
    pdf = document_pdf("quotation", quotation, profile, _setting(db, "quotation_template"), _logo_bytes(db))
    contact_name = f"{quotation.contact.first_name}" if quotation.contact else "Customer"
    sent = send_templated(db, to, "quotation",
                          {"contact_name": contact_name, "number": quotation.number,
                           "total": f"{quotation.currency} {quotation.total}", "company_name": profile.get("name", "WeTa CRM")},
                          attachments=[(f"{quotation.number}.pdf", pdf, "application/pdf")])
    if not sent:
        raise AppError("The quotation email could not be sent. Please check the SMTP settings and try again.", 502)
    if quotation.status == "draft":
        quotation.status = "sent"
    log_activity(db, "quotation", quotation.id, "email", f"Quotation emailed to {to}", user_id=user.id)
    audit(db, user.id, "send", "quotation", quotation.id, {"to": to})
    db.commit()
    return quotation


@router.post("/{quotation_id}/convert", response_model=InvoiceOut)
def convert_to_invoice(quotation_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("invoices:write"))):
    quotation = get_or_404(db, Quotation, quotation_id, "Quotation")
    if quotation.status == "converted":
        raise AppError("Quotation is already converted to an invoice", 409)
    invoice = Invoice(
        number=next_number(db, "invoice"),
        quotation_id=quotation.id,
        company_id=quotation.company_id,
        contact_id=quotation.contact_id,
        issue_date=date.today(),
        currency=quotation.currency,
        subtotal=quotation.subtotal,
        tax_total=quotation.tax_total,
        discount=quotation.discount,
        total=quotation.total,
        notes=quotation.notes,
        created_by_id=user.id,
    )
    db.add(invoice)
    db.flush()
    for item in quotation.items:
        invoice.items.append(InvoiceItem(
            product_id=item.product_id, name=item.name, description=item.description,
            quantity=item.quantity, unit_price=item.unit_price, tax_rate=item.tax_rate,
            line_total=item.line_total, position=item.position,
        ))
    quotation.status = "converted"
    audit(db, user.id, "convert", "quotation", quotation.id, {"invoice": invoice.number})
    db.commit()
    return invoice


@router.delete("/{quotation_id}", response_model=Message)
def delete_quotation(quotation_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("quotations:delete"))):
    quotation = get_or_404(db, Quotation, quotation_id, "Quotation")
    number = quotation.number
    db.delete(quotation)
    audit(db, user.id, "delete", "quotation", quotation_id, {"number": number})
    db.commit()
    return {"detail": "Quotation deleted"}
