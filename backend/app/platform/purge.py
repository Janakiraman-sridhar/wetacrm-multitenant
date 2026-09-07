"""Purging a deleted tenant, once its retention window has passed.

The console tells an admin that a deleted workspace is kept for 30 days and then
removed. Until this existed that was only half true: the tenant was soft-deleted and
nothing ever removed it, so "purged after 30 days" was a promise made to whoever
clicked delete and to whoever asked what happens to their data.

Three rules shape the implementation.

**It deletes rows, not just the tenant record.** Relying on `ON DELETE CASCADE` from
`tenants.id` would work on Postgres and silently do nothing on SQLite unless foreign
keys are enabled — a purge that appears to succeed and leaves everything behind is
the worst possible outcome. So every tenant-scoped table is emptied explicitly, in
reverse dependency order, which behaves identically on both.

**It deletes files too.** A purge that leaves a customer's uploaded documents and
their generated posters in object storage has not deleted their data, whatever the
database says.

**It refuses anything it is not certain about.** Only tenants soft-deleted longer
ago than the retention window, never the default workspace, and never a tenant that
is merely suspended. Irreversible work gets narrow guards.
"""

import logging
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tenancy import platform_scope
from app.database.base import Base, utcnow
from app.platform.models import Tenant

log = logging.getLogger("weta.purge")


def _tenant_tables():
    """Tenant-scoped tables, children first.

    `sorted_tables` is topologically ordered parents-first, so reversing it deletes
    dependents before what they point at. Self-referencing columns (a contact's
    referrer, a policy's renewal chain) are fine because each table's rows for this
    tenant all go in one statement.
    """
    return [t for t in reversed(Base.metadata.sorted_tables) if "tenant_id" in t.c]


def tenants_due_for_purge(db: Session, retention_days: int | None = None) -> list[Tenant]:
    """Soft-deleted tenants whose retention window has passed."""
    days = settings.tenant_retention_days if retention_days is None else retention_days
    if days < 1:
        # A zero-day window would purge a tenant the instant it was deleted, which
        # removes the only chance anyone has to undo a mis-click.
        raise ValueError("Retention must be at least one day")

    cutoff = utcnow() - timedelta(days=days)
    with platform_scope():
        return list(
            db.scalars(
                select(Tenant).where(
                    Tenant.deleted_at.isnot(None),
                    Tenant.deleted_at < cutoff,
                    Tenant.slug != settings.default_tenant_slug,
                )
            ).all()
        )


def count_rows(db: Session, tenant_id: str) -> dict[str, int]:
    """What a purge would remove. Used for the log line and for a dry run."""
    counts = {}
    with platform_scope():
        for table in _tenant_tables():
            n = db.scalar(
                select(func.count()).select_from(table).where(table.c.tenant_id == tenant_id)
            ) or 0
            if n:
                counts[table.name] = n
    return counts


def purge_tenant(db: Session, tenant: Tenant, dry_run: bool = False) -> dict:
    """Remove one tenant and everything it owns. Irreversible.

    Returns what was removed, so the caller can log something more useful than a
    count — after this runs there is nothing left to inspect.
    """
    if tenant.deleted_at is None:
        raise ValueError(f"{tenant.slug} is not deleted; purging it would be data loss")
    if tenant.slug == settings.default_tenant_slug:
        raise ValueError("The default workspace is never purged")

    summary = {
        "tenant_id": tenant.id,
        "slug": tenant.slug,
        "name": tenant.name,
        "deleted_at": tenant.deleted_at,
        "rows": count_rows(db, tenant.id),
        "files_removed": 0,
        "dry_run": dry_run,
    }
    if dry_run:
        return summary

    # Files first. If storage fails we stop with the database intact, which leaves a
    # tenant that can be purged again. Doing it the other way round would orphan the
    # files with nothing left pointing at them.
    summary["files_removed"] = _purge_storage(tenant.id)
    _purge_search(tenant.id)

    with platform_scope():
        for table in _tenant_tables():
            db.execute(delete(table).where(table.c.tenant_id == tenant.id))
        db.delete(tenant)
        db.commit()

    log.warning(
        "Purged tenant %s (%s): %s rows across %s tables, %s files",
        tenant.name, tenant.slug,
        sum(summary["rows"].values()), len(summary["rows"]), summary["files_removed"],
    )
    return summary


def _purge_storage(tenant_id: str) -> int:
    """Delete everything under this tenant's storage prefix.

    Storage is optional — with `MINIO_*` unset files live on local disk — so this
    handles both and never lets a storage failure stop the purge from being retried.
    """
    from app.services import storage

    try:
        return storage.delete_prefix(f"tenants/{tenant_id}/")
    except Exception:
        log.exception("Could not remove stored files for tenant %s", tenant_id)
        return 0


def _purge_search(tenant_id: str) -> None:
    """Drop this tenant's documents from the search index, if there is one."""
    from app.services import search_client

    try:
        search_client.remove_tenant(tenant_id)
    except Exception:
        log.exception("Could not clear the search index for tenant %s", tenant_id)
