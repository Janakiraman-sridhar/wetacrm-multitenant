"""Email templates carry their trigger, and automated sends are logged.

Before this the link between a template and the moment it fires was a string at a
call site, which meant `notification_settings` was stored and never read, and the
insurance template's renewal and birthday emails were configured but unreachable.

`sent_emails` exists so a daily job cannot send the same reminder every day for the
whole renewal window. It also answers "did we email this customer?", which is asked
far more often than anything about scheduling.

Existing rows are backfilled: the four templates that already had senders get their
trigger, and stay enabled so nothing that worked stops working. The two that never
fired are bound to their triggers but left **off** — switching them on emails a
client's whole book, which is a decision somebody has to make on purpose.

Revision ID: 0011_email_workflows
Revises: 0010_tenant_composite_indexes
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_email_workflows"
down_revision = "0010_tenant_composite_indexes"
branch_labels = None
depends_on = None

#: template name -> (trigger, enabled). The four with senders keep working; the two
#: customer-facing ones arrive switched off.
BACKFILL = {
    "welcome": ("welcome", True),
    "password_reset": ("password_reset", True),
    "lead_assigned": ("lead_assigned", True),
    "quotation": ("quotation", True),
    "renewal_reminder": ("policy_renewal_due", False),
    "birthday_wish": ("customer_birthday", False),
    "task_assigned": ("task_assigned", False),
}


def upgrade() -> None:
    with op.batch_alter_table("email_templates") as batch:
        batch.add_column(sa.Column("trigger", sa.String(length=50), nullable=True))
        batch.add_column(sa.Column("enabled", sa.Boolean(), nullable=False,
                                   server_default=sa.true()))
        batch.add_column(sa.Column("config", sa.JSON(), nullable=True))
    op.create_index("ix_email_templates_trigger", "email_templates", ["trigger"])
    op.create_index("ix_email_templates_enabled", "email_templates", ["enabled"])

    connection = op.get_bind()
    connection.execute(sa.text("UPDATE email_templates SET config = '{}' WHERE config IS NULL"))
    for name, (trigger, enabled) in BACKFILL.items():
        connection.execute(
            sa.text(
                "UPDATE email_templates SET trigger = :trigger, enabled = :enabled "
                "WHERE name = :name"
            ),
            {"trigger": trigger, "enabled": enabled, "name": name},
        )

    op.create_table(
        "sent_emails",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("trigger", sa.String(length=50), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.String(length=32), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # The dedupe itself, enforced by the database rather than by a check-then-act
        # that two workers could both pass.
        sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_sent_emails_tenant_key"),
    )
    for column in ("created_at", "tenant_id", "trigger", "dedupe_key", "recipient", "entity_id"):
        op.create_index(f"ix_sent_emails_{column}", "sent_emails", [column])


def downgrade() -> None:
    op.drop_table("sent_emails")
    op.drop_index("ix_email_templates_enabled", table_name="email_templates")
    op.drop_index("ix_email_templates_trigger", table_name="email_templates")
    with op.batch_alter_table("email_templates") as batch:
        batch.drop_column("config")
        batch.drop_column("enabled")
        batch.drop_column("trigger")
