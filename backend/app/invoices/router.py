from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Response, Query
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
from app.invoices.models import INVOICE_STATUSES, Invoice, InvoiceItem
from app.invoices.schemas import InvoiceCreate, InvoiceOut, InvoiceUpdate, PaymentIn
from app.services import billing, storage
from app.services.numbering import next_number
from app.services.pdf import document_pdf
from app.settings.models import Setting
from app.users.models import User

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _set_items(db: Session, invoice: Invoice, items: list[dict], discount) -> None:
    computed, subtotal, tax_total = billing.compute_items(items)
    invoice.items.clear()
    for item in computed:
        invoice.items.append(InvoiceItem(**item))
    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.discount = discount or 0
    invoice.total = billing.compute_total(subtotal, tax_total, discount)


@router.get("", response_model=Page[InvoiceOut], dependencies=[Depends(require_perm("invoices:read"))])
def list_invoices(filters: str | None = Query(None), status: str | None = None, params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Invoice)
    if status:
        stmt = stmt.where(Invoice.status == status)
    if params.search:
        stmt = stmt.where(or_(Invoice.number.ilike(f"%{params.search}%"), Invoice.notes.ilike(f"%{params.search}%")))
    stmt = apply_sort(stmt, Invoice, params.sort)
    stmt = apply_filters_for(db, stmt, "invoices", filters)
    return paginate(db, stmt, params)


@router.get("/{invoice_id}", response_model=InvoiceOut, dependencies=[Depends(require_perm("invoices:read"))])
def get_invoice(invoice_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Invoice, invoice_id, "Invoice")


@router.post("", response_model=InvoiceOut)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("invoices:write"))):
    data = payload.model_dump()
    items = data.pop("items", [])
    discount = data.pop("discount", 0)
    data["issue_date"] = data.get("issue_date") or date.today()
    template_row = db.scalar(select(Setting).where(Setting.key == "invoice_template"))
    template = template_row.value if template_row else {}
    if not data.get("notes") and template.get("default_notes"):
        data["notes"] = template["default_notes"]
    invoice = Invoice(**data, number=next_number(db, "invoice"), created_by_id=user.id)
    db.add(invoice)
    db.flush()
    _set_items(db, invoice, items, discount)
    audit(db, user.id, "create", "invoice", invoice.id, {"number": invoice.number})
    db.commit()
    return invoice


@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(invoice_id: str, payload: InvoiceUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("invoices:write"))):
    invoice = get_or_404(db, Invoice, invoice_id, "Invoice")
    data = payload.model_dump(exclude_unset=True)
    if data.get("status") and data["status"] not in INVOICE_STATUSES:
        raise AppError(f"Invalid status. Expected one of {INVOICE_STATUSES}")
    items = data.pop("items", None)
    discount = data.pop("discount", None)
    changes = apply_updates(invoice, data)
    if items is not None or discount is not None:
        _set_items(db, invoice,
                   items if items is not None else [
                       {"product_id": i.product_id, "name": i.name, "description": i.description,
                        "quantity": i.quantity, "unit_price": i.unit_price, "tax_rate": i.tax_rate}
                       for i in invoice.items
                   ],
                   discount if discount is not None else invoice.discount)
        changes["items"] = ["updated", "updated"]
    if changes:
        audit(db, user.id, "update", "invoice", invoice.id, {k: v for k, v in changes.items() if k != "items"})
    db.commit()
    return invoice


@router.get("/{invoice_id}/pdf", dependencies=[Depends(require_perm("invoices:read"))])
def invoice_pdf(invoice_id: str, db: Session = Depends(get_db)):
    invoice = get_or_404(db, Invoice, invoice_id, "Invoice")
    profile_row = db.scalar(select(Setting).where(Setting.key == "company_profile"))
    template_row = db.scalar(select(Setting).where(Setting.key == "invoice_template"))
    profile = profile_row.value if profile_row else {}
    logo = None
    if profile.get("logo_key"):
        try:
            logo = storage.read_file(profile["logo_key"])
        except Exception:
            logo = None
    pdf = document_pdf("invoice", invoice, profile, template_row.value if template_row else {}, logo)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{invoice.number}.pdf"'})


@router.post("/{invoice_id}/payments", response_model=InvoiceOut)
def record_payment(invoice_id: str, payload: PaymentIn, db: Session = Depends(get_db), user: User = Depends(require_perm("invoices:write"))):
    invoice = get_or_404(db, Invoice, invoice_id, "Invoice")
    invoice.amount_paid = Decimal(str(invoice.amount_paid or 0)) + Decimal(str(payload.amount))
    invoice.status = "paid" if invoice.amount_paid >= Decimal(str(invoice.total or 0)) else "partial"
    audit(db, user.id, "payment", "invoice", invoice.id, {"amount": payload.amount})
    db.commit()
    return invoice


@router.delete("/{invoice_id}", response_model=Message)
def delete_invoice(invoice_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("invoices:delete"))):
    invoice = get_or_404(db, Invoice, invoice_id, "Invoice")
    number = invoice.number
    db.delete(invoice)
    audit(db, user.id, "delete", "invoice", invoice_id, {"number": number})
    db.commit()
    return {"detail": "Invoice deleted"}
