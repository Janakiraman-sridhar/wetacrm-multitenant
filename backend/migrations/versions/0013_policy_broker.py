"""The intermediary a policy was placed through.

Distinct from the insurer on purpose: one underwrites the risk, the other carries
the agency code the commission is paid against. An agency reconciles by both, and
folding them into one field loses the ability to answer "what did we place through
this broker last quarter".

It points at `masters` like the insurer and the bank do, so the list is one a
workspace maintains for itself rather than something hardcoded here.

Revision ID: 0013_policy_broker
Revises: 0012_poster_assets
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_policy_broker"
down_revision = "0012_poster_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode: SQLite cannot add a foreign key with a plain ALTER.
    with op.batch_alter_table("policies") as batch:
        batch.add_column(sa.Column("broker_id", sa.String(length=32), nullable=True))
        batch.create_foreign_key("fk_policies_broker_id", "masters", ["broker_id"], ["id"])
    op.create_index("ix_policies_broker_id", "policies", ["broker_id"])


def downgrade() -> None:
    op.drop_index("ix_policies_broker_id", table_name="policies")
    with op.batch_alter_table("policies") as batch:
        batch.drop_constraint("fk_policies_broker_id", type_="foreignkey")
        batch.drop_column("broker_id")
