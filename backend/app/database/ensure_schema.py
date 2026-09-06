"""Lightweight additive migrations run at startup.

`Base.metadata.create_all()` creates missing *tables* but never ALTERs an
existing one, so a column added to a model that already has a table in a
live database would never appear. This module adds such columns idempotently
(works on both SQLite dev and Postgres), so `git pull` + restart is enough to
roll out additive schema changes without a separate migration step.
"""

import logging

from sqlalchemy import inspect, text

log = logging.getLogger("weta.schema")

# (table, column, column DDL type). Only additive, nullable/defaulted columns
# belong here — anything more involved needs a real migration.
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    ("leads", "tags", "JSON"),
    ("deals", "tags", "JSON"),
]


def ensure_columns(engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table, column, ddl in _ADDED_COLUMNS:
        if table not in tables:
            continue  # a brand-new table is created by create_all with the column already present
        columns = {c["name"] for c in inspector.get_columns(table)}
        if column in columns:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                conn.execute(text(f"UPDATE {table} SET {column} = '[]' WHERE {column} IS NULL"))
            log.info("Added missing column %s.%s", table, column)
        except Exception:
            log.exception("Could not add column %s.%s", table, column)
