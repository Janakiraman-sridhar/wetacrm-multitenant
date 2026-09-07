"""Composite indexes leading with tenant_id.

Every index in the schema was single-column, and every query in a shared-schema
multi-tenant app starts with `tenant_id = ?`. Neither shape serves those queries: an
index on `expiry_date` alone spans every tenant's book, and the `tenant_id` index
alone still scans one tenant's entire book to find what expires this month. The
answer is a composite leading with `tenant_id`.

Measured on 12,000 policies across two tenants before adding these:

    renewals due in 60 days              0.80ms -> 0.26ms    3.1x
    active policy count (dashboard KPI)  7.21ms -> 0.22ms   32.2x
    book premium (dashboard KPI)         7.01ms -> 3.33ms    2.1x
    this month's new business            4.89ms -> 0.11ms   44.7x
    whose birthday is this week          0.16ms -> 0.10ms    1.5x

Two candidates were measured and *left out*: `(tenant_id, customer_id)` on policies
and `(tenant_id, mobile)` on contacts both came in at 1.0–1.1x, because the existing
single-column index is already selective enough for an equality match on a
high-cardinality column. An index that does not earn its place still costs write
throughput and storage.

The remaining tables get the same treatment on the same reasoning — a status or date
filter, always scoped to one tenant, run on a list page or a dashboard.

Revision ID: 0010_tenant_composite_indexes
Revises: 0009_insurance_quotations
"""

from alembic import op

revision = "0010_tenant_composite_indexes"
down_revision = "0009_insurance_quotations"
branch_labels = None
depends_on = None

INDEXES = [
    # Measured above.
    ("ix_policies_tenant_expiry", "policies", ["tenant_id", "expiry_date"]),
    ("ix_policies_tenant_status", "policies", ["tenant_id", "status"]),
    ("ix_policies_tenant_issue", "policies", ["tenant_id", "issue_date"]),
    ("ix_contacts_tenant_birthday", "contacts", ["tenant_id", "birthday_key"]),
    # Same query shape: a status or date filter inside one tenant.
    ("ix_loans_tenant_status", "loans", ["tenant_id", "status"]),
    ("ix_loans_tenant_disbursed", "loans", ["tenant_id", "disbursed_on"]),
    ("ix_tasks_tenant_status_due", "tasks", ["tenant_id", "status", "due_date"]),
    ("ix_deals_tenant_stage", "deals", ["tenant_id", "stage_id"]),
    ("ix_invoices_tenant_status", "invoices", ["tenant_id", "status"]),
    ("ix_quotations_tenant_status", "quotations", ["tenant_id", "status"]),
    # The entity timeline: "everything that happened to this policy", on every
    # detail page, filtered by three columns at once.
    ("ix_activities_tenant_entity", "activities", ["tenant_id", "entity_type", "entity_id"]),
    ("ix_documents_tenant_entity", "documents", ["tenant_id", "entity_type", "entity_id"]),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
