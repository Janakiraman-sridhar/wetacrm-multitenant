"""Poster Studio and the WhatsApp message log.

A poster design is stored as a list of layers rather than an image, so the same spec
renders the editor preview, the batch output and whatever is sent — one renderer, no
drift between what an agent designs and what a customer receives.

`whatsapp_messages` records click-to-chat as well as API sends. Nothing leaves the
server for a click-to-chat, but the workspace still needs to know a customer was
already messaged this morning, or three agents wish the same person happy birthday.

Revision ID: 0007_poster_whatsapp
Revises: 0006_policies
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_poster_whatsapp"
down_revision = "0006_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "poster_templates",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("size", sa.String(length=20), nullable=False),
        sa.Column("layers", sa.JSON(), nullable=False),
        sa.Column("background", sa.JSON(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("created_at", "tenant_id", "name", "category", "is_system", "is_active"):
        op.create_index(f"ix_poster_templates_{column}", "poster_templates", [column])

    op.create_table(
        "poster_batches",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("template_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("audience", sa.String(length=40), nullable=False),
        sa.Column("audience_params", sa.JSON(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["poster_templates.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("created_at", "tenant_id"):
        op.create_index(f"ix_poster_batches_{column}", "poster_batches", [column])

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("contact_id", sa.String(length=32), nullable=True),
        sa.Column("policy_id", sa.String(length=32), nullable=True),
        sa.Column("to_number", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("media_key", sa.String(length=500), nullable=True),
        sa.Column("template_name", sa.String(length=100), nullable=True),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_by_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["sent_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("created_at", "tenant_id", "contact_id", "policy_id",
                   "to_number", "channel", "provider_message_id", "status"):
        op.create_index(f"ix_whatsapp_messages_{column}", "whatsapp_messages", [column])


def downgrade() -> None:
    op.drop_table("whatsapp_messages")
    op.drop_table("poster_batches")
    op.drop_table("poster_templates")
