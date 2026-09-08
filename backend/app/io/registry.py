"""Per-entity import/export specs for every module that supports CSV I/O."""

from collections import OrderedDict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.companies.models import Company
from app.contacts.models import Contact
from app.deals.models import Deal, DealStage
from app.invoices.models import Invoice, InvoiceItem
from app.leads.models import LEAD_STATUSES, Lead, LeadSource
from app.io.spec import (
    IOColumn, IOSpec, ImportResult, as_date, as_datetime, as_float, as_int, as_list,
    as_str, require, row_importer,
)
from app.projects.models import PROJECT_STATUSES, Project
from app.quotations.models import Quotation, QuotationItem
from app.services import billing
from app.services.numbering import next_number
from app.support.models import TICKET_PRIORITIES, TICKET_STATUSES, Ticket
from app.tasks.models import TASK_PRIORITIES, TASK_STATUSES, Task
from app.users.models import User


# --- reference resolvers ---------------------------------------------------

def find_company(db: Session, name: str | None):
    name = (name or "").strip()
    return db.scalar(select(Company).where(Company.name == name)) if name else None


def find_user(db: Session, email: str | None):
    email = (email or "").strip()
    return db.scalar(select(User).where(User.email == email)) if email else None


def find_source(db: Session, name: str | None):
    name = (name or "").strip()
    return db.scalar(select(LeadSource).where(LeadSource.name == name)) if name else None


def find_stage(db: Session, name: str | None):
    name = (name or "").strip()
    return db.scalar(select(DealStage).where(DealStage.name == name)) if name else None


def find_contact(db: Session, full_name: str | None):
    full_name = (full_name or "").strip()
    if not full_name:
        return None
    parts = full_name.split(" ", 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""
    q = select(Contact).where(Contact.first_name == first)
    if last:
        q = q.where(Contact.last_name == last)
    return db.scalar(q)


def contact_name(c) -> str:
    return f"{c.first_name} {c.last_name}".strip() if c else ""


# --- optional side-effects (assignment emails/notifications) ---------------
# Queued on opts.pending and fired only after the whole import commits, and only
# when the importer chose to send configured emails.

def _queue_lead_assignment(db, opts, lead, actor) -> None:
    if not opts.send_emails or not lead.assigned_to_id or lead.assigned_to_id == actor.id:
        return

    def effect():
        from app.notifications.service import notify
        from app.settings import workflows

        notify(db, lead.assigned_to_id, "lead_assigned", f"Lead assigned: {lead.title}",
               f"Assigned by {actor.full_name}", f"/leads?id={lead.id}")
        assignee = db.get(User, lead.assigned_to_id)
        if assignee:
            workflows.fire(db, "lead_assigned", assignee.email,
                           {"first_name": assignee.first_name, "lead_title": lead.title})

    opts.pending.append(effect)


def _queue_notification(db, opts, *, user_id, actor, type_, title, body, link) -> None:
    if not opts.send_emails or not user_id or user_id == actor.id:
        return

    def effect():
        from app.notifications.service import notify

        notify(db, user_id, type_, title, body, link)

    opts.pending.append(effect)


# --- companies -------------------------------------------------------------

def _create_company(db, user, row, opts):
    c = Company(
        name=require(row, "name", "Company name"),
        industry=as_str(row.get("industry")),
        website=as_str(row.get("website")),
        gst_number=as_str(row.get("gst_number")),
        phone=as_str(row.get("phone")),
        email=as_str(row.get("email")),
        address=as_str(row.get("address")),
        city=as_str(row.get("city")),
        state=as_str(row.get("state")),
        country=as_str(row.get("country")),
        postal_code=as_str(row.get("postal_code")),
        notes=as_str(row.get("notes")),
        tags=as_list(row.get("tags")),
        owner_id=(o := find_user(db, row.get("owner_email"))) and o.id,
    )
    db.add(c)
    audit(db, user.id, "import", "company", None, {"name": c.name})


COMPANY_SPEC = IOSpec(
    module="companies", label="Companies", filename="companies",
    columns=[
        IOColumn("name", "Name"),
        IOColumn("industry", "Industry"),
        IOColumn("website", "Website"),
        IOColumn("email", "Email"),
        IOColumn("phone", "Phone"),
        IOColumn("gst_number", "GST Number"),
        IOColumn("address", "Address"),
        IOColumn("city", "City"),
        IOColumn("state", "State"),
        IOColumn("country", "Country"),
        IOColumn("postal_code", "Postal Code"),
        IOColumn("tags", "Tags"),
        IOColumn("notes", "Notes"),
        IOColumn("owner_email", "Account Manager Email", lambda c: c.owner.email if c.owner else ""),
        IOColumn("created_at", "Created At"),
    ],
    base_select=lambda: select(Company).order_by(Company.created_at.desc()),
    filter_key="companies",
    import_rows=row_importer(_create_company),
    sample={
        "name": "Acme Industries", "industry": "Manufacturing", "website": "https://acme.example",
        "email": "hello@acme.example", "phone": "+91 98765 43210", "gst_number": "22AAAAA0000A1Z5",
        "address": "12 MG Road", "city": "Chennai", "state": "Tamil Nadu", "country": "India",
        "postal_code": "600001", "tags": "vip; manufacturing", "notes": "Key account",
        "owner_email": "admin@wetacrm.com",
    },
)


# --- contacts --------------------------------------------------------------

def _create_contact(db, user, row, opts):
    c = Contact(
        first_name=require(row, "first_name", "First name"),
        last_name=as_str(row.get("last_name")) or "",
        position=as_str(row.get("position")),
        company_id=(co := find_company(db, row.get("company"))) and co.id,
        emails=as_list(row.get("emails")),
        phones=as_list(row.get("phones")),
        social_links={k: v for k, v in {"linkedin": as_str(row.get("linkedin")), "twitter": as_str(row.get("twitter"))}.items() if v},
        notes=as_str(row.get("notes")),
        tags=as_list(row.get("tags")),
        owner_id=(o := find_user(db, row.get("owner_email"))) and o.id,
    )
    db.add(c)
    audit(db, user.id, "import", "contact", None, {"name": c.full_name})


CONTACT_SPEC = IOSpec(
    module="contacts", label="Contacts", filename="contacts",
    columns=[
        IOColumn("first_name", "First Name"),
        IOColumn("last_name", "Last Name"),
        IOColumn("position", "Position"),
        IOColumn("company", "Company", lambda c: c.company.name if c.company else ""),
        IOColumn("emails", "Emails", lambda c: "; ".join(c.emails or [])),
        IOColumn("phones", "Phones", lambda c: "; ".join(c.phones or [])),
        IOColumn("linkedin", "LinkedIn", lambda c: (c.social_links or {}).get("linkedin", "")),
        IOColumn("twitter", "Twitter", lambda c: (c.social_links or {}).get("twitter", "")),
        IOColumn("tags", "Tags"),
        IOColumn("notes", "Notes"),
        IOColumn("owner_email", "Owner Email", lambda c: c.owner.email if c.owner else ""),
        IOColumn("created_at", "Created At"),
    ],
    base_select=lambda: select(Contact).order_by(Contact.created_at.desc()),
    filter_key="contacts",
    import_rows=row_importer(_create_contact),
    sample={
        "first_name": "Priya", "last_name": "Sharma", "position": "Procurement Head",
        "company": "Acme Industries", "emails": "priya@acme.example; priya.s@gmail.example",
        "phones": "+91 98765 43210", "linkedin": "https://linkedin.com/in/priya",
        "twitter": "@priya", "tags": "decision-maker", "notes": "", "owner_email": "admin@wetacrm.com",
    },
)


# --- leads -----------------------------------------------------------------

def _create_lead(db, user, row, opts):
    status = (as_str(row.get("status")) or "new").lower()
    if status not in LEAD_STATUSES:
        from app.core.exceptions import AppError
        raise AppError(f"Invalid status '{status}'. Expected one of {', '.join(LEAD_STATUSES)}")
    lead = Lead(
        title=require(row, "title", "Lead title"),
        contact_name=as_str(row.get("contact_name")),
        email=as_str(row.get("email")),
        phone=as_str(row.get("phone")),
        company_name=as_str(row.get("company_name")),
        source_id=(s := find_source(db, row.get("source"))) and s.id,
        status=status,
        score=max(0, min(100, as_int(row.get("score"), 0, "score"))),
        assigned_to_id=(u := find_user(db, row.get("assigned_to_email"))) and u.id,
        follow_up_at=as_datetime(row.get("follow_up_at"), "follow-up"),
        notes=as_str(row.get("notes")),
        tags=as_list(row.get("tags")),
    )
    db.add(lead)
    audit(db, user.id, "import", "lead", None, {"title": lead.title})
    _queue_lead_assignment(db, opts, lead, user)


LEAD_SPEC = IOSpec(
    module="leads", label="Leads", filename="leads",
    columns=[
        IOColumn("title", "Title"),
        IOColumn("company_name", "Company"),
        IOColumn("contact_name", "Contact"),
        IOColumn("email", "Email"),
        IOColumn("phone", "Phone"),
        IOColumn("source", "Source", lambda l: l.source.name if l.source else ""),
        IOColumn("status", "Status"),
        IOColumn("score", "Score"),
        IOColumn("assigned_to_email", "Assigned To Email", lambda l: l.assigned_to.email if l.assigned_to else ""),
        IOColumn("follow_up_at", "Follow-up At"),
        IOColumn("tags", "Tags"),
        IOColumn("notes", "Notes"),
        IOColumn("created_at", "Created At"),
    ],
    base_select=lambda: select(Lead).order_by(Lead.created_at.desc()),
    filter_key="leads",
    import_rows=row_importer(_create_lead),
    sample={
        "title": "Acme ERP rollout", "company_name": "Acme Industries", "contact_name": "Priya Sharma",
        "email": "priya@acme.example", "phone": "+91 98765 43210", "source": "Exhibition",
        "status": "new", "score": "70", "assigned_to_email": "admin@wetacrm.com",
        "follow_up_at": "2026-10-01 10:00", "tags": "ERP; hot", "notes": "Met at trade show",
    },
)


# --- deals -----------------------------------------------------------------

def _create_deal(db, user, row, opts):
    from app.core.exceptions import AppError
    stage = find_stage(db, row.get("stage"))
    if not stage:
        stage = db.scalar(
            select(DealStage).where(DealStage.is_won.is_(False), DealStage.is_lost.is_(False)).order_by(DealStage.order)
        )
        if not stage:
            raise AppError("No pipeline stages configured")
    deal = Deal(
        title=require(row, "title", "Deal title"),
        value=as_float(row.get("value"), 0, "value"),
        currency=as_str(row.get("currency")) or "INR",
        probability=max(0, min(100, as_int(row.get("probability"), stage.probability, "probability"))),
        expected_close_date=as_date(row.get("expected_close_date"), "expected close"),
        stage_id=stage.id,
        company_id=(co := find_company(db, row.get("company"))) and co.id,
        contact_id=(ct := find_contact(db, row.get("contact"))) and ct.id,
        owner_id=(o := find_user(db, row.get("owner_email"))) and o.id,
        competitors=as_str(row.get("competitors")),
        notes=as_str(row.get("notes")),
        tags=as_list(row.get("tags")),
        status="won" if stage.is_won else "lost" if stage.is_lost else "open",
    )
    db.add(deal)
    audit(db, user.id, "import", "deal", None, {"title": deal.title})
    _queue_notification(db, opts, user_id=deal.owner_id, actor=user, type_="deal_updated",
                        title=f"Deal assigned: {deal.title}", body=f"Assigned by {user.full_name}",
                        link=f"/deals?id={deal.id}")


DEAL_SPEC = IOSpec(
    module="deals", label="Deals", filename="deals",
    columns=[
        IOColumn("title", "Title"),
        IOColumn("value", "Value"),
        IOColumn("currency", "Currency"),
        IOColumn("stage", "Stage", lambda d: d.stage.name if d.stage else ""),
        IOColumn("probability", "Probability"),
        IOColumn("status", "Status"),
        IOColumn("company", "Company", lambda d: d.company.name if d.company else ""),
        IOColumn("contact", "Contact", lambda d: contact_name(d.contact)),
        IOColumn("owner_email", "Owner Email", lambda d: d.owner.email if d.owner else ""),
        IOColumn("expected_close_date", "Expected Close Date"),
        IOColumn("competitors", "Competitors"),
        IOColumn("tags", "Tags"),
        IOColumn("notes", "Notes"),
        IOColumn("created_at", "Created At"),
    ],
    base_select=lambda: select(Deal).order_by(Deal.created_at.desc()),
    filter_key="deals",
    import_rows=row_importer(_create_deal),
    sample={
        "title": "Acme ERP implementation", "value": "850000", "currency": "INR", "stage": "Proposal",
        "probability": "65", "company": "Acme Industries", "contact": "Priya Sharma",
        "owner_email": "admin@wetacrm.com", "expected_close_date": "2026-11-30",
        "competitors": "OtherCRM", "tags": "ERP; enterprise", "notes": "",
    },
)


# --- tasks -----------------------------------------------------------------

def _create_task(db, user, row, opts):
    from app.core.exceptions import AppError
    priority = (as_str(row.get("priority")) or "medium").lower()
    status = (as_str(row.get("status")) or "todo").lower()
    if priority not in TASK_PRIORITIES:
        raise AppError(f"Invalid priority '{priority}'. Expected one of {', '.join(TASK_PRIORITIES)}")
    if status not in TASK_STATUSES:
        raise AppError(f"Invalid status '{status}'. Expected one of {', '.join(TASK_STATUSES)}")
    task = Task(
        title=require(row, "title", "Task title"),
        description=as_str(row.get("description")),
        priority=priority,
        status=status,
        due_date=as_datetime(row.get("due_date"), "due date"),
        assigned_to_id=(u := find_user(db, row.get("assigned_to_email"))) and u.id,
        created_by_id=user.id,
    )
    db.add(task)
    audit(db, user.id, "import", "task", None, {"title": task.title})


TASK_SPEC = IOSpec(
    module="tasks", label="Tasks", filename="tasks",
    columns=[
        IOColumn("title", "Title"),
        IOColumn("priority", "Priority"),
        IOColumn("status", "Status"),
        IOColumn("due_date", "Due Date"),
        IOColumn("assigned_to_email", "Assigned To Email", lambda t: t.assigned_to.email if t.assigned_to else ""),
        IOColumn("description", "Description"),
        IOColumn("created_at", "Created At"),
    ],
    base_select=lambda: select(Task).order_by(Task.created_at.desc()),
    filter_key="tasks",
    import_rows=row_importer(_create_task),
    sample={
        "title": "Send onboarding docs", "priority": "high", "status": "todo",
        "due_date": "2026-10-05 17:00", "assigned_to_email": "admin@wetacrm.com",
        "description": "Email the welcome pack",
    },
)


# --- projects --------------------------------------------------------------

def _create_project(db, user, row, opts):
    from app.core.exceptions import AppError
    status = (as_str(row.get("status")) or "planned").lower()
    if status not in PROJECT_STATUSES:
        raise AppError(f"Invalid status '{status}'. Expected one of {', '.join(PROJECT_STATUSES)}")
    project = Project(
        name=require(row, "name", "Project name"),
        description=as_str(row.get("description")),
        company_id=(co := find_company(db, row.get("company"))) and co.id,
        status=status,
        start_date=as_date(row.get("start_date"), "start date"),
        end_date=as_date(row.get("end_date"), "end date"),
        budget=as_float(row.get("budget"), None, "budget") if as_str(row.get("budget")) else None,
        owner_id=(o := find_user(db, row.get("owner_email"))) and o.id,
    )
    db.add(project)
    audit(db, user.id, "import", "project", None, {"name": project.name})


PROJECT_SPEC = IOSpec(
    module="projects", label="Projects", filename="projects",
    columns=[
        IOColumn("name", "Name"),
        IOColumn("company", "Customer", lambda p: p.company.name if p.company else ""),
        IOColumn("status", "Status"),
        IOColumn("start_date", "Start Date"),
        IOColumn("end_date", "End Date"),
        IOColumn("budget", "Budget"),
        IOColumn("owner_email", "Owner Email", lambda p: p.owner.email if p.owner else ""),
        IOColumn("description", "Description"),
        IOColumn("created_at", "Created At"),
    ],
    base_select=lambda: select(Project).order_by(Project.created_at.desc()),
    filter_key="projects",
    import_rows=row_importer(_create_project),
    sample={
        "name": "Acme ERP Implementation", "company": "Acme Industries", "status": "active",
        "start_date": "2026-10-01", "end_date": "2027-03-31", "budget": "500000",
        "owner_email": "admin@wetacrm.com", "description": "Phase 1 rollout",
    },
)


# --- support tickets -------------------------------------------------------

def _create_ticket(db, user, row, opts):
    from app.core.exceptions import AppError
    priority = (as_str(row.get("priority")) or "medium").lower()
    status = (as_str(row.get("status")) or "open").lower()
    if priority not in TICKET_PRIORITIES:
        raise AppError(f"Invalid priority '{priority}'. Expected one of {', '.join(TICKET_PRIORITIES)}")
    if status not in TICKET_STATUSES:
        raise AppError(f"Invalid status '{status}'. Expected one of {', '.join(TICKET_STATUSES)}")
    ticket = Ticket(
        number=next_number(db, "ticket"),
        subject=require(row, "subject", "Subject"),
        description=as_str(row.get("description")),
        company_id=(co := find_company(db, row.get("company"))) and co.id,
        contact_id=(ct := find_contact(db, row.get("contact"))) and ct.id,
        priority=priority,
        status=status,
        assigned_to_id=(u := find_user(db, row.get("assigned_to_email"))) and u.id,
        resolution=as_str(row.get("resolution")),
    )
    db.add(ticket)
    audit(db, user.id, "import", "ticket", None, {"subject": ticket.subject})
    _queue_notification(db, opts, user_id=ticket.assigned_to_id, actor=user, type_="ticket_assigned",
                        title=f"Ticket assigned: {ticket.subject}",
                        body=f"{ticket.number} — {ticket.priority} priority", link="/support")


SUPPORT_SPEC = IOSpec(
    module="support", label="Support Tickets", filename="tickets",
    columns=[
        IOColumn("number", "Ticket #"),
        IOColumn("subject", "Subject"),
        IOColumn("company", "Company", lambda t: t.company.name if t.company else ""),
        IOColumn("contact", "Contact", lambda t: contact_name(t.contact)),
        IOColumn("priority", "Priority"),
        IOColumn("status", "Status"),
        IOColumn("assigned_to_email", "Assigned To Email", lambda t: t.assigned_to.email if t.assigned_to else ""),
        IOColumn("description", "Description"),
        IOColumn("resolution", "Resolution"),
        IOColumn("created_at", "Created At"),
    ],
    base_select=lambda: select(Ticket).order_by(Ticket.created_at.desc()),
    filter_key="support",
    import_rows=row_importer(_create_ticket),
    sample={
        "number": "(auto-generated — leave blank on import)", "subject": "Cannot export report",
        "company": "Acme Industries", "contact": "Priya Sharma", "priority": "high", "status": "open",
        "assigned_to_email": "admin@wetacrm.com", "description": "Excel export fails",
        "resolution": "",
    },
)


# --- quotations & invoices (line-item, grouped by document ref) ------------

def _billing_import(kind: str):
    """Build an import_rows that groups line-item rows into documents."""

    def run(db, user, rows, opts) -> ImportResult:
        result = ImportResult()
        groups: "OrderedDict[str, dict]" = OrderedDict()
        for i, row in enumerate(rows, start=2):
            if not any(v for v in row.values()):
                continue
            ref = (row.get("doc_ref") or "").strip() or f"__row{i}"
            g = groups.setdefault(ref, {"row": i, "head": row, "items": []})
            if (row.get("item_name") or "").strip():
                g["items"].append(row)

        for ref, g in groups.items():
            head = g["head"]
            try:
                with db.begin_nested():
                    items_payload = [
                        {
                            "name": require(it, "item_name", "Item name"),
                            "description": as_str(it.get("item_description")),
                            "quantity": as_float(it.get("item_quantity"), 1, "quantity"),
                            "unit_price": as_float(it.get("item_unit_price"), 0, "unit price"),
                            "tax_rate": as_float(it.get("item_tax_rate"), 0, "tax rate"),
                        }
                        for it in g["items"]
                    ]
                    if not items_payload:
                        from app.core.exceptions import AppError
                        raise AppError("No line items for this document")
                    computed, subtotal, tax_total = billing.compute_items(items_payload)
                    discount = as_float(head.get("discount"), 0, "discount")
                    company = find_company(db, head.get("company"))
                    contact = find_contact(db, head.get("contact"))
                    common = dict(
                        company_id=company and company.id,
                        contact_id=contact and contact.id,
                        currency=as_str(head.get("currency")) or "INR",
                        subtotal=subtotal, tax_total=tax_total, discount=discount,
                        total=billing.compute_total(subtotal, tax_total, discount),
                        notes=as_str(head.get("notes")), created_by_id=user.id,
                    )
                    if kind == "quotation":
                        doc = Quotation(
                            number=next_number(db, "quotation"),
                            issue_date=as_date(head.get("issue_date"), "issue date") or date.today(),
                            valid_until=as_date(head.get("valid_until"), "valid until"),
                            terms=as_str(head.get("terms")), **common,
                        )
                        db.add(doc)
                        db.flush()
                        for it in computed:
                            doc.items.append(QuotationItem(**it))
                    else:
                        doc = Invoice(
                            number=next_number(db, "invoice"),
                            issue_date=as_date(head.get("issue_date"), "issue date") or date.today(),
                            due_date=as_date(head.get("due_date"), "due date"),
                            **common,
                        )
                        db.add(doc)
                        db.flush()
                        for it in computed:
                            doc.items.append(InvoiceItem(**it))
                    db.flush()
                    audit(db, user.id, "import", kind, None, {"number": doc.number})
                result.created += 1
            except Exception as e:  # noqa: BLE001
                result.failed += 1
                msg = getattr(e, "detail", None) or str(e)
                result.errors.append({"row": g["row"], "message": str(msg)[:200]})
        db.commit()
        return result

    return run


def _billing_columns(second_date_key: str, second_date_label: str, extra_head=None):
    cols = [
        IOColumn("doc_ref", "Document Ref"),
        IOColumn("number", "Number"),
        IOColumn("company", "Company", lambda d: d.company.name if d.company else ""),
        IOColumn("contact", "Contact", lambda d: contact_name(d.contact)),
        IOColumn("status", "Status"),
        IOColumn("issue_date", "Issue Date"),
        IOColumn(second_date_key, second_date_label),
        IOColumn("currency", "Currency"),
        IOColumn("discount", "Discount"),
        IOColumn("notes", "Notes"),
    ]
    if extra_head:
        cols.extend(extra_head)
    cols.extend([
        IOColumn("item_name", "Item Name"),
        IOColumn("item_description", "Item Description"),
        IOColumn("item_quantity", "Item Qty"),
        IOColumn("item_unit_price", "Item Unit Price"),
        IOColumn("item_tax_rate", "Item Tax %"),
        IOColumn("total", "Document Total"),
    ])
    return cols


def _billing_expand(docs):
    rows = []
    for doc in docs:
        for item in (doc.items or [None]):
            rows.append(_BillingRow(doc, item))
    return rows


class _BillingRow:
    """Adapter that presents one (document, line-item) pair as a flat export row."""

    def __init__(self, doc, item):
        self.doc_ref = doc.number
        self.number = doc.number
        self.company = doc.company
        self.contact = doc.contact
        self.status = doc.status
        self.issue_date = doc.issue_date
        self.valid_until = getattr(doc, "valid_until", None)
        self.due_date = getattr(doc, "due_date", None)
        self.currency = doc.currency
        self.discount = float(doc.discount or 0)
        self.notes = doc.notes
        self.terms = getattr(doc, "terms", None)
        self.amount_paid = float(getattr(doc, "amount_paid", 0) or 0)
        self.total = float(doc.total or 0)
        self.item_name = item.name if item else ""
        self.item_description = (item.description if item else "") or ""
        self.item_quantity = float(item.quantity) if item else ""
        self.item_unit_price = float(item.unit_price) if item else ""
        self.item_tax_rate = float(item.tax_rate) if item else ""
        self.created_at = doc.created_at


QUOTATION_SPEC = IOSpec(
    module="quotations", label="Quotations", filename="quotations",
    columns=_billing_columns("valid_until", "Valid Until", extra_head=[IOColumn("terms", "Terms")]),
    base_select=lambda: select(Quotation).order_by(Quotation.created_at.desc()),
    filter_key="quotations",
    expand=_billing_expand,
    import_rows=_billing_import("quotation"),
    sample={
        "doc_ref": "Q-A (rows sharing this become one quotation)", "number": "(auto)",
        "company": "Acme Industries", "contact": "Priya Sharma", "issue_date": "2026-10-01",
        "valid_until": "2026-10-31", "currency": "INR", "discount": "5000", "notes": "",
        "terms": "Valid for 30 days", "item_name": "ERP License", "item_description": "Annual",
        "item_quantity": "5", "item_unit_price": "50000", "item_tax_rate": "18",
    },
)

INVOICE_SPEC = IOSpec(
    module="invoices", label="Invoices", filename="invoices",
    columns=_billing_columns("due_date", "Due Date"),
    base_select=lambda: select(Invoice).order_by(Invoice.created_at.desc()),
    filter_key="invoices",
    expand=_billing_expand,
    import_rows=_billing_import("invoice"),
    sample={
        "doc_ref": "INV-A (rows sharing this become one invoice)", "number": "(auto)",
        "company": "Acme Industries", "contact": "Priya Sharma", "issue_date": "2026-10-01",
        "due_date": "2026-10-15", "currency": "INR", "discount": "0", "notes": "",
        "item_name": "ERP License", "item_description": "Annual", "item_quantity": "5",
        "item_unit_price": "50000", "item_tax_rate": "18",
    },
)


SPECS: dict[str, IOSpec] = {
    "companies": COMPANY_SPEC,
    "contacts": CONTACT_SPEC,
    "leads": LEAD_SPEC,
    "deals": DEAL_SPEC,
    "tasks": TASK_SPEC,
    "projects": PROJECT_SPEC,
    "support": SUPPORT_SPEC,
    "quotations": QUOTATION_SPEC,
    "invoices": INVOICE_SPEC,
}
