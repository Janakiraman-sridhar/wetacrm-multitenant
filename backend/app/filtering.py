"""Generic, whitelist-driven filtering for list and export endpoints.

The frontend sends a `filters` query param: a JSON array of filter items, e.g.

    [{"key":"status","type":"select","value":["new","contacted"]},
     {"key":"created_at","type":"datetime","from":"2026-01-01","to":"2026-06-30"},
     {"key":"value","type":"number","op":"gte","value":100000}]

Only keys declared in FILTERS[entity] are honoured (SQL-injection-safe: the
column objects are fixed, never built from user input). The same registry is
used by the module list endpoints and by /io/<entity>/export, so an export
always matches the on-screen filter.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import and_

from app.companies.models import Company
from app.contacts.models import Contact
from app.deals.models import Deal
from app.invoices.models import Invoice
from app.leads.models import Lead
from app.projects.models import Project
from app.quotations.models import Quotation
from app.support.models import Ticket
from app.tasks.models import Task


@dataclass
class FF:
    """A filterable field: the model column and its filter type."""

    column: Any
    type: str  # text | select | date | datetime | number | boolean


def _start(value: str, t: str):
    d = date.fromisoformat(str(value)[:10])
    return d if t == "date" else datetime.combine(d, time.min)


def _end(value: str, t: str):
    d = date.fromisoformat(str(value)[:10])
    return d if t == "date" else datetime.combine(d, time.max)


def apply_filters(stmt, fields: dict[str, FF], raw: str | None):
    if not raw:
        return stmt
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return stmt
    if not isinstance(items, list):
        return stmt

    conds = []
    for it in items:
        if not isinstance(it, dict):
            continue
        ff = fields.get(it.get("key"))
        if not ff:
            continue
        col, t = ff.column, ff.type
        try:
            if t == "text":
                v = str(it.get("value", "")).strip()
                if v:
                    conds.append(col.ilike(f"%{v}%"))
            elif t == "select":
                vals = [v for v in (it.get("value") or []) if v not in (None, "")]
                if vals:
                    conds.append(col.in_(vals))
            elif t in ("date", "datetime"):
                if it.get("from"):
                    conds.append(col >= _start(it["from"], t))
                if it.get("to"):
                    conds.append(col <= _end(it["to"], t))
            elif t == "number":
                raw_v = it.get("value")
                if raw_v not in (None, ""):
                    v = float(raw_v)
                    op = it.get("op", "eq")
                    conds.append({"gte": col >= v, "lte": col <= v}.get(op, col == v))
            elif t == "boolean":
                v = it.get("value")
                if isinstance(v, bool):
                    conds.append(col.is_(v))
        except (ValueError, TypeError):
            continue

    return stmt.where(and_(*conds)) if conds else stmt


# Whitelist of filterable fields per entity (keys must match the frontend defs).
FILTERS: dict[str, dict[str, FF]] = {
    "companies": {
        "industry": FF(Company.industry, "text"),
        "city": FF(Company.city, "text"),
        "country": FF(Company.country, "text"),
        "owner_id": FF(Company.owner_id, "select"),
        "created_at": FF(Company.created_at, "datetime"),
    },
    "contacts": {
        "position": FF(Contact.position, "text"),
        "company_id": FF(Contact.company_id, "select"),
        "owner_id": FF(Contact.owner_id, "select"),
        "created_at": FF(Contact.created_at, "datetime"),
    },
    "leads": {
        "status": FF(Lead.status, "select"),
        "source_id": FF(Lead.source_id, "select"),
        "assigned_to_id": FF(Lead.assigned_to_id, "select"),
        "score": FF(Lead.score, "number"),
        "follow_up_at": FF(Lead.follow_up_at, "datetime"),
        "created_at": FF(Lead.created_at, "datetime"),
    },
    "deals": {
        "status": FF(Deal.status, "select"),
        "stage_id": FF(Deal.stage_id, "select"),
        "owner_id": FF(Deal.owner_id, "select"),
        "company_id": FF(Deal.company_id, "select"),
        "value": FF(Deal.value, "number"),
        "expected_close_date": FF(Deal.expected_close_date, "date"),
        "created_at": FF(Deal.created_at, "datetime"),
    },
    "tasks": {
        "status": FF(Task.status, "select"),
        "priority": FF(Task.priority, "select"),
        "assigned_to_id": FF(Task.assigned_to_id, "select"),
        "due_date": FF(Task.due_date, "datetime"),
        "created_at": FF(Task.created_at, "datetime"),
    },
    "projects": {
        "status": FF(Project.status, "select"),
        "company_id": FF(Project.company_id, "select"),
        "owner_id": FF(Project.owner_id, "select"),
        "start_date": FF(Project.start_date, "date"),
        "end_date": FF(Project.end_date, "date"),
        "created_at": FF(Project.created_at, "datetime"),
    },
    "support": {
        "status": FF(Ticket.status, "select"),
        "priority": FF(Ticket.priority, "select"),
        "company_id": FF(Ticket.company_id, "select"),
        "assigned_to_id": FF(Ticket.assigned_to_id, "select"),
        "created_at": FF(Ticket.created_at, "datetime"),
    },
    "quotations": {
        "status": FF(Quotation.status, "select"),
        "company_id": FF(Quotation.company_id, "select"),
        "total": FF(Quotation.total, "number"),
        "issue_date": FF(Quotation.issue_date, "date"),
        "valid_until": FF(Quotation.valid_until, "date"),
        "created_at": FF(Quotation.created_at, "datetime"),
    },
    "invoices": {
        "status": FF(Invoice.status, "select"),
        "company_id": FF(Invoice.company_id, "select"),
        "total": FF(Invoice.total, "number"),
        "amount_paid": FF(Invoice.amount_paid, "number"),
        "issue_date": FF(Invoice.issue_date, "date"),
        "due_date": FF(Invoice.due_date, "date"),
        "created_at": FF(Invoice.created_at, "datetime"),
    },
}
