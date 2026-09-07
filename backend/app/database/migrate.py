"""Run Alembic migrations from inside the app.

Schema used to be created by `Base.metadata.create_all()` plus an additive-column
patcher. Neither can express the multi-tenant change (new columns on ~25 tables,
rewritten unique constraints, a data backfill), so migrations are now the only way
the schema changes.

Applying them at startup keeps the local workflow to "run uvicorn". Set
`AUTO_MIGRATE=false` where the deploy pipeline runs `alembic upgrade head` itself.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

log = logging.getLogger("weta.migrate")

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


def upgrade_to_head() -> None:
    log.info("Applying database migrations…")
    command.upgrade(alembic_config(), "head")
    log.info("Database is up to date")
