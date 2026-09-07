"""Tenant context and the global query filter that enforces isolation.

This module is the security boundary of the multi-tenant build. Every SELECT that
touches a :class:`~app.database.base.TenantScoped` model is filtered here, once,
and every INSERT is stamped here, once. Routers and services must never filter by
``tenant_id`` themselves: a hand-written filter is a filter that can be forgotten,
and a forgotten filter shows one client's data to another.

Three scopes exist:

``tenant_scope(tid)``
    Normal request handling and per-tenant background jobs. Queries see exactly
    one tenant's rows.

``platform_scope()``
    Deliberate cross-tenant access: the Super Admin console, provisioning, and
    the auth lookups that have to find a user *before* their tenant is known.
    Filtering is switched off, so every use should be short and obvious.

no scope at all
    A bug. Any query touching a tenant-scoped model raises
    :class:`TenantContextMissing` rather than silently returning another
    tenant's rows (or everyone's).
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.database.base import TenantScoped

_tenant_id: ContextVar[str | None] = ContextVar("weta_tenant_id", default=None)
_bypass: ContextVar[bool] = ContextVar("weta_tenant_bypass", default=False)

#: Cache of tenant-scoped table names, filled the first time it is needed.
_scoped_tables: set[str] | None = None

#: Execution option that skips filtering for a single statement. Prefer
#: ``platform_scope()``; this exists for the rare statement that cannot be wrapped.
SKIP_TENANT_FILTER = "skip_tenant_filter"


class TenantContextMissing(RuntimeError):
    """A tenant-scoped query ran without a tenant and without an explicit bypass."""


def current_tenant_id() -> str | None:
    return _tenant_id.get()


def is_platform_scope() -> bool:
    return _bypass.get()


def require_tenant_id() -> str:
    tid = _tenant_id.get()
    if tid is None:
        raise TenantContextMissing("No tenant in context")
    return tid


@contextmanager
def tenant_scope(tenant_id: str) -> Iterator[str]:
    """Run a block as one tenant. Used by request handling and background jobs."""
    token = _tenant_id.set(tenant_id)
    bypass_token = _bypass.set(False)
    try:
        yield tenant_id
    finally:
        _tenant_id.reset(token)
        _bypass.reset(bypass_token)


@contextmanager
def platform_scope() -> Iterator[None]:
    """Run a block with tenant filtering disabled (Super Admin, provisioning, auth lookups)."""
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


def set_request_tenant(tenant_id: str | None) -> object:
    """Set the tenant for the current request. Returns a token for `reset_request_tenant`."""
    return _tenant_id.set(tenant_id)


def reset_request_tenant(token) -> None:
    _tenant_id.reset(token)


def _statement_touches_tenant_scoped(state: ORMExecuteState) -> bool:
    try:
        mappers = state.all_mappers
    except Exception:  # pragma: no cover - defensive; some statements expose no mappers
        return False
    return any(issubclass(mapper.class_, TenantScoped) for mapper in mappers)


def tenant_scoped_tables() -> set[str]:
    """Table names of every tenant-scoped model, resolved once the mappers exist."""
    global _scoped_tables
    if _scoped_tables is None:
        from app.database.base import Base

        _scoped_tables = {
            mapper.local_table.name
            for mapper in Base.registry.mappers
            if issubclass(mapper.class_, TenantScoped) and mapper.local_table is not None
        }
    return _scoped_tables


def _augment_aggregate(statement, tenant_id: str):
    """Add an explicit tenant predicate to a non-ORM aggregate statement.

    `with_loader_criteria` only reaches ORM *entities*. A statement like
    ``select(func.count()).select_from(Deal)`` selects no entity, so the loader
    criteria never applies and the count would span every tenant. Those statements
    are caught here by looking at the tables they select from.

    Statements that count over an anonymous subquery cannot be rewritten this way —
    `paginate()` handles that case by filtering the inner statement before it is
    turned into a subquery.
    """
    try:
        froms = statement.get_final_froms()
    except Exception:  # pragma: no cover - not all statements expose froms
        return None

    scoped = tenant_scoped_tables()
    conditions = []
    for from_obj in froms:
        name = getattr(from_obj, "name", None)
        columns = getattr(from_obj, "c", None)
        if name in scoped and columns is not None and "tenant_id" in columns:
            conditions.append(columns["tenant_id"] == tenant_id)
    if not conditions:
        return None
    return statement.where(*conditions)


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(state: ORMExecuteState) -> None:
    """Inject `WHERE tenant_id = :current` into every tenant-scoped SELECT.

    Relationship loads are filtered too, so following a foreign key can never
    cross a tenant boundary. Column refreshes are skipped: the row's identity has
    already been established by a filtered query.
    """
    if not state.is_select or state.is_column_load:
        return
    if state.execution_options.get(SKIP_TENANT_FILTER):
        return
    if _bypass.get():
        return

    is_orm = _statement_touches_tenant_scoped(state)
    aggregate = None
    tenant_id = _tenant_id.get()

    if not is_orm:
        # Possibly an aggregate over a tenant-scoped table with no ORM entity.
        if tenant_id is None:
            return  # nothing tenant-related that we can detect; leave it alone
        aggregate = _augment_aggregate(state.statement, tenant_id)
        if aggregate is None:
            return
        state.statement = aggregate
        return

    if tenant_id is None:
        raise TenantContextMissing(
            "Tenant-scoped query executed with no tenant in context. "
            "Wrap it in tenant_scope(...) or, for deliberate cross-tenant access, platform_scope()."
        )

    state.statement = state.statement.options(
        with_loader_criteria(
            TenantScoped,
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _stamp_tenant_on_insert(session: Session, flush_context, instances) -> None:
    """Populate `tenant_id` on new tenant-scoped rows so routers never set it by hand."""
    if not session.new:
        return

    tenant_id = _tenant_id.get()
    bypassing = _bypass.get()

    for obj in session.new:
        if not isinstance(obj, TenantScoped):
            continue
        if getattr(obj, "tenant_id", None) is not None:
            continue  # explicitly set (provisioning, platform admin creating tenant data)
        if tenant_id is None:
            if bypassing:
                continue  # platform scope may legitimately create tenant-less rows
            raise TenantContextMissing(
                f"Cannot insert {type(obj).__name__} with no tenant in context."
            )
        obj.tenant_id = tenant_id


def tenant_predicate(model):
    """Explicit `model.tenant_id == <current>` for a hand-written aggregate.

    Prefer letting the automatic filter do its job. Reach for this only where a
    statement selects no ORM entity *and* no tenant-scoped table appears directly
    in its FROM — for example an aggregate over a subquery.
    """
    return model.tenant_id == require_tenant_id()
