"""The indexes exist, and the two places that declare them agree.

The models and the migration each carry the composite-index list. That duplication
is deliberate — a migration that imports live app code stops describing the schema
it actually produced, and re-runs differently a year later. The cost of duplicating
is drift, so this is what stops it drifting.
"""

import importlib

import pytest
from sqlalchemy import inspect

from app import models_registry
from app.database.base import Base
from app.database.session import engine

MIGRATION = importlib.import_module(
    "migrations.versions.0010_tenant_composite_indexes"
)


def test_the_models_and_the_migration_declare_the_same_indexes():
    assert sorted(models_registry.TENANT_COMPOSITE_INDEXES) == sorted(MIGRATION.INDEXES), (
        "models_registry and migration 0010 have drifted — a database created by "
        "create_all would not match one built by migrations"
    )


@pytest.mark.parametrize(
    "name,table,columns", models_registry.TENANT_COMPOSITE_INDEXES,
    ids=[i[0] for i in models_registry.TENANT_COMPOSITE_INDEXES],
)
def test_each_index_is_on_the_table(name, table, columns):
    """And names real columns — a typo here is silent until someone profiles."""
    metadata_table = Base.metadata.tables[table]
    index = next((ix for ix in metadata_table.indexes if ix.name == name), None)
    assert index is not None, f"{name} is not declared on {table}"
    assert [c.name for c in index.columns] == columns


@pytest.mark.parametrize(
    "name,table,columns", models_registry.TENANT_COMPOSITE_INDEXES,
    ids=[i[0] for i in models_registry.TENANT_COMPOSITE_INDEXES],
)
def test_every_composite_index_leads_with_tenant_id(name, table, columns):
    """The whole point: a query that does not start there cannot use the index.

    Every list, count and dashboard figure in the product is scoped to one tenant,
    so an index that leads with anything else is one the planner will skip.
    """
    assert columns[0] == "tenant_id", f"{name} leads with {columns[0]}, not tenant_id"


def test_the_indexes_are_actually_in_the_database():
    """create_all is what the test database uses; this proves they arrive."""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    for name, table, _columns in models_registry.TENANT_COMPOSITE_INDEXES:
        present = {ix["name"] for ix in inspector.get_indexes(table)}
        assert name in present, f"{name} missing from {table} in the live schema"


def test_hot_tables_are_covered():
    """A checklist, so adding a module does not quietly skip this step.

    Every table here backs a list page or a dashboard figure that is filtered or
    grouped inside one tenant. If a new one joins them, it belongs on the list.
    """
    covered = {table for _name, table, _cols in models_registry.TENANT_COMPOSITE_INDEXES}
    expected = {
        "policies", "contacts", "loans", "tasks", "deals",
        "invoices", "quotations", "activities", "documents",
    }
    assert expected <= covered, f"no composite index for {sorted(expected - covered)}"
