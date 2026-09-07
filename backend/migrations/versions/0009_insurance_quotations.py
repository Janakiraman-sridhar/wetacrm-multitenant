"""Insurance quotations: competing insurer options on a quotation.

`kind` splits the two shapes a quotation can take. `insurance` holds the risk being
quoted plus the options; they are not `quotation_items` because items are summed and
these must not be — see `app/quotations/insurance.py`.

Revision ID: 0009_insurance_quotations
Revises: 0008_loans
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_insurance_quotations"
down_revision = "0008_loans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("quotations") as batch:
        batch.add_column(sa.Column("kind", sa.String(length=20), nullable=False, server_default="standard"))
        batch.add_column(sa.Column("insurance", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("policy_id", sa.String(length=32), nullable=True))
        batch.create_foreign_key("fk_quotations_policy_id", "policies", ["policy_id"], ["id"])
    op.create_index("ix_quotations_kind", "quotations", ["kind"])
    op.create_index("ix_quotations_policy_id", "quotations", ["policy_id"])
    # Existing rows predate the column; an empty object keeps every read the same shape.
    op.execute("UPDATE quotations SET insurance = '{}' WHERE insurance IS NULL")


def downgrade() -> None:
    op.drop_index("ix_quotations_policy_id", table_name="quotations")
    op.drop_index("ix_quotations_kind", table_name="quotations")
    with op.batch_alter_table("quotations") as batch:
        batch.drop_constraint("fk_quotations_policy_id", type_="foreignkey")
        batch.drop_column("policy_id")
        batch.drop_column("insurance")
        batch.drop_column("kind")
