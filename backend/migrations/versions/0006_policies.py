"""Policies and the reference masters they point at.

`masters` holds a tenant's insurers, banks, branches and relations. A table rather
than a settings blob because policies reference these rows: an agency retiring an
insurer must not silently rewrite every historical policy written with it, which is
also why deleting one that is in use deactivates it instead.

`policies` keeps fields common to every line as columns and the line-specific ones in
`details`. The exceptions promoted to columns — expiry date, premium, insurer, bank,
product line, status, registration number — are the ones filtered, sorted and summed
on every screen; a JSON path is the wrong place for "everything expiring next month".

Nominees gain a nullable `policy_id` so a policy can carry its own, defaulting to the
customer's.

Revision ID: 0006_policies
Revises: 0005_customer_pii
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_policies"
down_revision = "0005_customer_pii"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "masters",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "type", "name", name="uq_masters_tenant_type_name"),
    )
    for column in ("created_at", "tenant_id", "type", "name", "is_active"):
        op.create_index(f"ix_masters_{column}", "masters", [column])

    op.create_table(
        "policies",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("policy_number", sa.String(length=80), nullable=False),
        sa.Column("product_line", sa.String(length=20), nullable=False),
        sa.Column("plan_name", sa.String(length=200), nullable=True),
        sa.Column("insurer_id", sa.String(length=32), nullable=True),
        sa.Column("bank_id", sa.String(length=32), nullable=True),
        sa.Column("branch", sa.String(length=150), nullable=True),
        sa.Column("sourcing_channel", sa.String(length=20), nullable=True),
        sa.Column("customer_id", sa.String(length=32), nullable=False),
        sa.Column("proposer_id", sa.String(length=32), nullable=True),
        sa.Column("owner_id", sa.String(length=32), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("premium_net", sa.Numeric(14, 2), nullable=False),
        sa.Column("premium_gst", sa.Numeric(14, 2), nullable=False),
        sa.Column("premium_gross", sa.Numeric(14, 2), nullable=False),
        sa.Column("sum_insured", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("payment_mode", sa.String(length=20), nullable=True),
        sa.Column("payment_frequency", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("renewal_of_id", sa.String(length=32), nullable=True),
        sa.Column("renewed_to_id", sa.String(length=32), nullable=True),
        sa.Column("commission_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("commission_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("registration_no", sa.String(length=20), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("custom", sa.JSON(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["insurer_id"], ["masters.id"]),
        sa.ForeignKeyConstraint(["bank_id"], ["masters.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["proposer_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "policy_number", name="uq_policies_tenant_number"),
    )
    for column in (
        "created_at", "tenant_id", "policy_number", "product_line", "insurer_id", "bank_id",
        "sourcing_channel", "customer_id", "owner_id", "expiry_date", "premium_gross",
        "status", "renewal_of_id", "registration_no",
    ):
        op.create_index(f"ix_policies_{column}", "policies", [column])

    # A policy's own nominees, defaulting to the customer's.
    op.add_column("nominees", sa.Column("policy_id", sa.String(length=32), nullable=True))
    op.create_index("ix_nominees_policy_id", "nominees", ["policy_id"])


def downgrade() -> None:
    op.drop_index("ix_nominees_policy_id", table_name="nominees")
    op.drop_column("nominees", "policy_id")
    op.drop_table("policies")
    op.drop_table("masters")
