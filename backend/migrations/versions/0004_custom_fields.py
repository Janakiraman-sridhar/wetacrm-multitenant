"""Per-tenant custom fields.

`field_defs` holds both custom fields a tenant added and overrides on the fields the
product ships; `custom` is the JSON column their values live in.

Values go in JSON rather than real columns so that adding a field for one client
never alters the schema, never blocks on a migration, and stays invisible to every
other tenant. On Postgres the column is JSONB with a GIN index so filtering on a
custom field stays fast; SQLite gets plain JSON.

Revision ID: 0004_custom_fields
Revises: 0003_templates_and_modules
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_custom_fields"
down_revision = "0003_templates_and_modules"
branch_labels = None
depends_on = None

CUSTOM_TABLES = [
    "companies", "contacts", "leads", "deals",
    "tasks", "products", "projects", "tickets",
]


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.create_table(
        "field_defs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("field_type", sa.String(length=30), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("section", sa.String(length=80), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("help_text", sa.String(length=300), nullable=True),
        sa.Column("placeholder", sa.String(length=150), nullable=True),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("is_custom", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("show_in_table", sa.Boolean(), nullable=False),
        sa.Column("filterable", sa.Boolean(), nullable=False),
        sa.Column("is_pii", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "module", "key", name="uq_field_defs_tenant_module_key"),
    )
    op.create_index("ix_field_defs_created_at", "field_defs", ["created_at"])
    op.create_index("ix_field_defs_tenant_id", "field_defs", ["tenant_id"])
    op.create_index("ix_field_defs_module", "field_defs", ["module"])
    op.create_index("ix_field_defs_key", "field_defs", ["key"])
    op.create_index("ix_field_defs_is_custom", "field_defs", ["is_custom"])
    op.create_index("ix_field_defs_is_active", "field_defs", ["is_active"])

    column_type = sa.dialects.postgresql.JSONB if is_postgres else sa.JSON
    for table in CUSTOM_TABLES:
        op.add_column(table, sa.Column("custom", column_type(), nullable=True))
        op.execute(f"UPDATE {table} SET custom = '{{}}' WHERE custom IS NULL")
        if is_postgres:
            # GIN keeps custom-field filtering usable as a tenant's data grows.
            op.create_index(
                f"ix_{table}_custom_gin", table, ["custom"], postgresql_using="gin"
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    for table in CUSTOM_TABLES:
        if is_postgres:
            op.drop_index(f"ix_{table}_custom_gin", table_name=table)
        op.drop_column(table, "custom")
    op.drop_table("field_defs")
