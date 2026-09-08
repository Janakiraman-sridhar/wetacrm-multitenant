"""Uploaded images an agent can put on a poster.

Before this the only picture a design could carry was the workspace logo, resolved
by name. An asset is referred to by **id** in a layer's `source`, which is the same
shape the renderer already used for "logo" — so the spec and the renderer needed no
change, only somewhere for the bytes to come from.

No composite index: a workspace's poster pictures number in the tens, so the
tenant index already answers the only query there is, and an index that does not
earn its place still costs write throughput.

Revision ID: 0012_poster_assets
Revises: 0011_email_workflows
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_poster_assets"
down_revision = "0011_email_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "poster_assets",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("file_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_poster_assets_tenant_id", "poster_assets", ["tenant_id"])
    op.create_index("ix_poster_assets_name", "poster_assets", ["name"])


def downgrade() -> None:
    op.drop_index("ix_poster_assets_name", table_name="poster_assets")
    op.drop_index("ix_poster_assets_tenant_id", table_name="poster_assets")
    op.drop_table("poster_assets")
