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

from sqlalchemy import and_, cast, or_
from sqlalchemy.types import String as SAString

from app.companies.models import Company
from app.contacts.models import Contact
from app.deals.models import Deal
from app.invoices.models import Invoice
from app.leads.models import Lead
from app.loans.models import Loan
from app.policies.models import Policy
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


def custom_field_conditions(model, items: list[dict], allowed: dict[str, str]):
    """Build conditions for filters that target a tenant's custom fields.

    Custom values live in a JSON column, so there is no `Column` object to hand to
    `FF`. Comparison goes through the JSON path instead, cast to text — enough for
    the text, select and number filters the field editor can produce, and indexed
    by GIN on Postgres.

    `allowed` is the whitelist: only keys the tenant marked filterable are honoured,
    so this stays as injection-safe as the static registry.
    """
    conditions = []
    for item in items:
        key = item.get("key", "")
        if not key.startswith("custom."):
            continue
        field_key = key[len("custom."):]
        kind = allowed.get(field_key)
        if kind is None:
            continue

        path = model.custom[field_key]
        try:
            if kind in ("text", "textarea", "email", "phone", "url"):
                value = str(item.get("value", "")).strip()
                if value:
                    conditions.append(path.as_string().ilike(f"%{value}%"))
            elif kind == "select":
                values = [str(v) for v in (item.get("value") or []) if v not in (None, "")]
                if values:
                    conditions.append(path.as_string().in_(values))
            elif kind == "multiselect":
                # Stored as a JSON list, so match on the serialised text.
                values = [str(v) for v in (item.get("value") or []) if v not in (None, "")]
                if values:
                    conditions.append(
                        or_(*[cast(path, SAString).ilike(f'%"{v}"%') for v in values])
                    )
            elif kind in ("number", "decimal", "currency"):
                raw_value = item.get("value")
                if raw_value not in (None, ""):
                    value = float(raw_value)
                    column = path.as_float()
                    op = item.get("op", "eq")
                    conditions.append(
                        {"gte": column >= value, "lte": column <= value}.get(op, column == value)
                    )
            elif kind in ("date", "datetime"):
                # ISO strings sort lexicographically, so a plain range works.
                text = path.as_string()
                if item.get("from"):
                    conditions.append(text >= str(item["from"])[:10])
                if item.get("to"):
                    conditions.append(text <= str(item["to"])[:10] + "\uffff")
            elif kind == "checkbox":
                value = item.get("value")
                if isinstance(value, bool):
                    conditions.append(path.as_boolean().is_(value))
        except (ValueError, TypeError):
            continue
    return conditions


def apply_filters(stmt, fields: dict[str, FF], raw: str | None, model=None, custom_allowed=None):
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

    if model is not None and custom_allowed:
        try:
            conds.extend(custom_field_conditions(model, items, custom_allowed))
        except Exception:  # a bad custom filter must not break the whole list
            pass

    return stmt.where(and_(*conds)) if conds else stmt


# Whitelist of filterable fields per entity (keys must match the frontend defs).
FILTERS: dict[str, dict[str, FF]] = {
    # The filters an agent actually works a book of business with: what is expiring,
    # from which insurer, sourced through which bank.
    "policies": {
        "product_line": FF(Policy.product_line, "select"),
        "status": FF(Policy.status, "select"),
        "insurer_id": FF(Policy.insurer_id, "select"),
        "broker_id": FF(Policy.broker_id, "select"),
        "bank_id": FF(Policy.bank_id, "select"),
        "sourcing_channel": FF(Policy.sourcing_channel, "select"),
        "owner_id": FF(Policy.owner_id, "select"),
        "branch": FF(Policy.branch, "text"),
        "registration_no": FF(Policy.registration_no, "text"),
        "expiry_date": FF(Policy.expiry_date, "date"),
        "issue_date": FF(Policy.issue_date, "date"),
        "start_date": FF(Policy.start_date, "date"),
        "premium_gross": FF(Policy.premium_gross, "number"),
        "sum_insured": FF(Policy.sum_insured, "number"),
    },
    "loans": {
        "loan_type": FF(Loan.loan_type, "select"),
        "status": FF(Loan.status, "select"),
        "lender_id": FF(Loan.lender_id, "select"),
        "owner_id": FF(Loan.owner_id, "select"),
        "amount_requested": FF(Loan.amount_requested, "number"),
        "amount_sanctioned": FF(Loan.amount_sanctioned, "number"),
        "applied_on": FF(Loan.applied_on, "date"),
        "disbursed_on": FF(Loan.disbursed_on, "date"),
    },
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


def custom_filterable(db, module: str) -> dict[str, str]:
    """Custom fields this tenant marked filterable, as {key: type}.

    Doubles as the whitelist for `custom_field_conditions` — a key not in here is
    ignored, so the JSON path is never built from arbitrary user input.
    """
    from app.platform.schema_service import active_custom_fields
    from app.schema_registry import CUSTOMISABLE_MODULES

    if module not in CUSTOMISABLE_MODULES:
        return {}
    return {
        d.key: d.field_type for d in active_custom_fields(db, module) if d.filterable
    }


def apply_filters_for(db, stmt, module: str, raw: str | None):
    """Apply both the built-in filter whitelist and the tenant's custom fields.

    Routers call this instead of `apply_filters` so a custom field becomes
    filterable everywhere at once — list endpoints and CSV export alike.
    """
    from app.schema_registry import model_for

    return apply_filters(
        stmt,
        FILTERS.get(module, {}),
        raw,
        model=model_for(module),
        custom_allowed=custom_filterable(db, module),
    )
