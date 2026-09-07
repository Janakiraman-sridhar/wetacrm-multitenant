"""Loan cases.

Deliberately thinner than a policy: the lender owns the underwriting, so what an
agency tracks is whose case it is, how far it has got, and what it earns.

`expected_payout` is a stored column but always derived from the sanctioned amount
and the payout percentage — kept rather than computed on read so payout reports can
sum it in SQL without loading every row.

Revision ID: 0008_loans
Revises: 0007_poster_whatsapp
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_loans"
down_revision = "0007_poster_whatsapp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loans",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("customer_id", sa.String(length=32), nullable=False),
        sa.Column("loan_type", sa.String(length=60), nullable=False),
        sa.Column("lender_id", sa.String(length=32), nullable=True),
        sa.Column("owner_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("amount_requested", sa.Numeric(14, 2), nullable=True),
        sa.Column("amount_sanctioned", sa.Numeric(14, 2), nullable=True),
        sa.Column("tenure_months", sa.Integer(), nullable=True),
        sa.Column("interest_rate", sa.Numeric(6, 2), nullable=True),
        sa.Column("payout_percent", sa.Numeric(6, 2), nullable=True),
        sa.Column("expected_payout", sa.Numeric(14, 2), nullable=True),
        sa.Column("actual_payout", sa.Numeric(14, 2), nullable=True),
        sa.Column("applied_on", sa.Date(), nullable=True),
        sa.Column("sanctioned_on", sa.Date(), nullable=True),
        sa.Column("disbursed_on", sa.Date(), nullable=True),
        sa.Column("rejected_reason", sa.String(length=300), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("custom", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["lender_id"], ["masters.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("created_at", "tenant_id", "customer_id", "loan_type",
                   "lender_id", "owner_id", "status", "disbursed_on"):
        op.create_index(f"ix_loans_{column}", "loans", [column])


def downgrade() -> None:
    op.drop_table("loans")
