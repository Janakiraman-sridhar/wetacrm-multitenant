"""What fields a module has, before a tenant customises it.

Base fields are **derived from the SQLAlchemy models** rather than listed by hand.
A hand-written list would be a second source of truth that silently drifts every
time a column is added; deriving it means the field editor always offers exactly
the fields that exist.

Only labels and a few type hints are curated below, where the column name alone
does not read well to a user.
"""

from dataclasses import dataclass, field as dataclass_field
from typing import Any

from sqlalchemy import (
    Boolean, Date, DateTime, Integer, JSON, Numeric, String, Text,
)
from sqlalchemy.orm import class_mapper

from app.companies.models import Company
from app.contacts.models import Contact
from app.deals.models import Deal
from app.leads.models import Lead
from app.products.models import Product
from app.projects.models import Project
from app.support.models import Ticket
from app.loans.models import Loan
from app.policies.models import Policy
from app.tasks.models import Task

#: Modules that support per-tenant custom fields. Each maps to the model whose
#: `custom` JSON column holds the values.
CUSTOMISABLE_MODELS: dict[str, Any] = {
    "companies": Company,
    "contacts": Contact,
    "leads": Lead,
    "deals": Deal,
    "tasks": Task,
    "products": Product,
    "projects": Project,
    "support": Ticket,
    "policies": Policy,
    "loans": Loan,
}

CUSTOMISABLE_MODULES = list(CUSTOMISABLE_MODELS)

# Columns that are plumbing, not fields a user would ever configure.
_HIDDEN_COLUMNS = {"id", "created_at", "updated_at", "tenant_id", "custom"}

#: Storage a column happens to need, which is not a field.
#:
#: A blind index and a ciphertext are how a PAN is *stored*; the field is `pan`, and
#: the page supplies it. Offering these meant Settings → Fields listed six entries
#: nobody could act on — you cannot usefully relabel `pan_index` or hide
#: `aadhaar_encrypted` — and every one of them was another line between an agent and
#: the field they were looking for. Derived columns go here too: `birthday_key` is
#: computed from the date of birth and editing it would mean nothing.
_INTERNAL_COLUMNS: dict[str, set[str]] = {
    "contacts": {
        "pan_encrypted", "pan_index",
        "aadhaar_encrypted", "aadhaar_index", "aadhaar_last4",
        "birthday_key",
    },
    # The renewal chain is written by `renew()`, both ends of it. A policy's
    # predecessor is not something anyone types into a form.
    "policies": {"renewal_of_id", "renewed_to_id"},
}

# Columns a user may relabel but must not hide or make optional, because business
# logic depends on them being present.
_LOCKED_COLUMNS: dict[str, set[str]] = {
    "companies": {"name"},
    "contacts": {"first_name"},
    "leads": {"title", "status"},
    "deals": {"title", "stage_id", "status"},
    "tasks": {"title", "status"},
    "products": {"name"},
    "projects": {"name", "status"},
    "support": {"number", "subject", "status"},
    "policies": {"policy_number", "product_line", "customer_id", "status"},
    "loans": {"customer_id", "loan_type", "status"},
}

# Labels the column name does not produce well on its own.
_LABEL_OVERRIDES = {
    "gst_number": "GST number",
    "owner_id": "Owner",
    "assigned_to_id": "Assigned to",
    "created_by_id": "Created by",
    "company_id": "Company",
    "contact_id": "Contact",
    "stage_id": "Stage",
    "source_id": "Source",
    "project_id": "Project",
    "sku": "SKU",
    "postal_code": "Postal code",
    "unit_price": "Unit price",
    "tax_rate": "Tax rate (%)",
    "stock_qty": "Stock quantity",
    "expected_close_date": "Expected close date",
    "follow_up_at": "Follow-up date",
    "converted_deal_id": "Converted deal",
    "team_ids": "Team",
    "is_active": "Active",
    "insurer_id": "Insurer",
    #: The intermediary, not the underwriter. Named here rather than in the page so
    #: the form, the column picker and the filter cannot disagree about what it is
    #: called — the derived label would otherwise read "Broker" in some places and
    #: whatever a page hardcoded in others.
    "broker_id": "Insurance company",
    "bank_id": "Bank",
    "customer_id": "Customer",
    "proposer_id": "Proposer",
    "policy_number": "Policy number",
    "product_line": "Product line",
    "plan_name": "Plan",
    "premium_net": "Premium (net)",
    "premium_gst": "GST",
    "premium_gross": "Premium (gross)",
    "sum_insured": "Sum insured",
    "registration_no": "Registration number",
    "expiry_date": "Expiry date",
    "renewal_of_id": "Renewal of",
    "renewed_to_id": "Renewed to",
    "commission_percent": "Commission %",
    "commission_amount": "Commission amount",
    "sourcing_channel": "Sourcing channel",
    "lender_id": "Lender",
    "loan_type": "Loan type",
    "amount_requested": "Amount requested",
    "amount_sanctioned": "Amount sanctioned",
    "tenure_months": "Tenure (months)",
    "interest_rate": "Interest rate (%)",
    "payout_percent": "Payout %",
    "expected_payout": "Expected payout",
    "actual_payout": "Payout received",
    "applied_on": "Applied on",
    "sanctioned_on": "Sanctioned on",
    "disbursed_on": "Disbursed on",
}

FIELD_TYPES = [
    "text", "textarea", "number", "decimal", "date", "datetime", "select",
    "multiselect", "checkbox", "email", "phone", "url", "currency",
]


@dataclass
class BaseField:
    key: str
    label: str
    type: str
    required: bool = False
    locked: bool = False
    options: list[dict] = dataclass_field(default_factory=list)


def _humanise(name: str) -> str:
    cleaned = name[:-3] if name.endswith("_id") else name
    return _LABEL_OVERRIDES.get(name) or cleaned.replace("_", " ").capitalize()


def _column_type(column) -> str:
    """Map a SQLAlchemy column to the field type the form renderer understands."""
    if column.foreign_keys:
        return "select"
    type_ = column.type
    if isinstance(type_, Boolean):
        return "checkbox"
    if isinstance(type_, DateTime):
        return "datetime"
    if isinstance(type_, Date):
        return "date"
    if isinstance(type_, Integer):
        return "number"
    if isinstance(type_, Numeric):
        return "decimal"
    if isinstance(type_, JSON):
        return "multiselect"
    if isinstance(type_, Text):
        return "textarea"
    if isinstance(type_, String):
        name = column.name
        if "email" in name:
            return "email"
        if "phone" in name or "mobile" in name:
            return "phone"
        if "website" in name or "url" in name:
            return "url"
    return "text"


def base_fields(module: str) -> list[BaseField]:
    """The fields a module has out of the box, read straight off its model."""
    model = CUSTOMISABLE_MODELS.get(module)
    if model is None:
        return []

    locked = _LOCKED_COLUMNS.get(module, set())
    internal = _INTERNAL_COLUMNS.get(module, set())
    fields: list[BaseField] = []
    for column in class_mapper(model).columns:
        if column.name in _HIDDEN_COLUMNS or column.name in internal:
            continue
        fields.append(
            BaseField(
                key=column.name,
                label=_humanise(column.name),
                type=_column_type(column),
                required=not column.nullable and column.default is None,
                locked=column.name in locked,
            )
        )
    return fields


def base_field_keys(module: str) -> set[str]:
    return {f.key for f in base_fields(module)}


def model_for(module: str):
    return CUSTOMISABLE_MODELS.get(module)
