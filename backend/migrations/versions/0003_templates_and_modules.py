"""Templates and per-tenant module configuration.

`crm_templates` holds the recipes a tenant is provisioned from (loaded from
`app/platform/templates/*.json` at startup). `tenant_modules` holds the result for
one tenant: which modules it has, what they are called, and in what order — which
is how the same code shows "Contacts" to a general CRM and "Customers" to an
insurance agency.

Existing tenants get their module rows backfilled on the next startup by
`ensure_default_tenant()`, so this migration only has to create the tables.

Revision ID: 0003_templates_and_modules
Revises: 0002_multitenant
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_templates_and_modules"
down_revision = "0002_multitenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_templates",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crm_templates_created_at", "crm_templates", ["created_at"])
    op.create_index("ix_crm_templates_key", "crm_templates", ["key"], unique=True)
    op.create_index("ix_crm_templates_is_system", "crm_templates", ["is_system"])

    op.create_table(
        "tenant_modules",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("module_key", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "module_key", name="uq_tenant_modules_tenant_key"),
    )
    op.create_index("ix_tenant_modules_created_at", "tenant_modules", ["created_at"])
    op.create_index("ix_tenant_modules_tenant_id", "tenant_modules", ["tenant_id"])
    op.create_index("ix_tenant_modules_module_key", "tenant_modules", ["module_key"])
    op.create_index("ix_tenant_modules_enabled", "tenant_modules", ["enabled"])


def downgrade() -> None:
    op.drop_table("tenant_modules")
    op.drop_table("crm_templates")
