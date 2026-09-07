"""Platform (Super Admin) API — creating and managing tenants.

Every endpoint here is guarded by `get_platform_admin` and runs in `platform_scope()`,
which is the *only* place tenant filtering is deliberately switched off. Actions are
recorded in `platform_audit_logs` against the real admin, including impersonation.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_platform_admin
from app.core.exceptions import AppError, NotFoundError
from app.core.schemas import Message
from app.core.security import create_impersonation_token
from app.core.config import settings
from app.core.tenancy import platform_scope, tenant_scope
from app.database.base import utcnow
from app.database.session import get_db
from app.platform import service
from app.platform.models import Tenant
from app.platform.schemas import (
    ImpersonateIn, ImpersonateOut, PlatformStatsOut, TenantCreate, TenantDetailOut, TenantOut, TenantUpdate,
)
from app.users.models import Role, User

router = APIRouter(prefix="/platform", tags=["platform"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    return service.list_tenants(db, include_deleted=include_deleted)


@router.post("/tenants", response_model=TenantDetailOut)
def create_tenant(
    payload: TenantCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    with platform_scope():
        clash = db.scalar(select(User).where(User.email == payload.owner_email))
    if clash:
        raise AppError("That owner email is already in use on the platform", 409)

    slug = service.unique_slug(db, payload.slug or service.slugify(payload.name))
    tenant = service.provision_tenant(
        db,
        payload.name,
        slug=slug,
        type=payload.type,
        template_key=payload.template_key,
        owner_email=payload.owner_email,
        owner_password=payload.owner_password,
        owner_first_name=payload.owner_first_name,
        owner_last_name=payload.owner_last_name,
    )

    with platform_scope():
        tenant.plan = payload.plan
        tenant.timezone = payload.timezone
        tenant.currency = payload.currency
        owner = db.scalar(select(User).where(User.email == payload.owner_email))
        if owner:
            tenant.owner_user_id = owner.id
        service.platform_audit(
            db, admin.id, "tenant.create", tenant.id,
            {"name": tenant.name, "template": tenant.template_key}, _client_ip(request),
        )
        db.commit()
    return _detail(db, tenant)


@router.get("/tenants/{tenant_id}", response_model=TenantDetailOut)
def get_tenant(tenant_id: str, db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    tenant = service.get_tenant(db, tenant_id)
    if not tenant or tenant.deleted_at:
        raise NotFoundError("Tenant")
    return _detail(db, tenant)


@router.patch("/tenants/{tenant_id}", response_model=TenantDetailOut)
def update_tenant(
    tenant_id: str,
    payload: TenantUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    tenant = service.get_tenant(db, tenant_id)
    if not tenant or tenant.deleted_at:
        raise NotFoundError("Tenant")
    with platform_scope():
        changes = {}
        for field, value in payload.model_dump(exclude_unset=True).items():
            if getattr(tenant, field) != value:
                changes[field] = [getattr(tenant, field), value]
                setattr(tenant, field, value)
        if changes:
            service.platform_audit(db, admin.id, "tenant.update", tenant.id, changes, _client_ip(request))
        db.commit()
    return _detail(db, tenant)


@router.post("/tenants/{tenant_id}/suspend", response_model=TenantOut)
def suspend_tenant(
    tenant_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)
):
    tenant = service.get_tenant(db, tenant_id)
    if not tenant or tenant.deleted_at:
        raise NotFoundError("Tenant")
    with platform_scope():
        tenant.status = "suspended"
        tenant.suspended_at = utcnow()
        service.platform_audit(db, admin.id, "tenant.suspend", tenant.id, {}, _client_ip(request))
        db.commit()
    return tenant


@router.post("/tenants/{tenant_id}/reactivate", response_model=TenantOut)
def reactivate_tenant(
    tenant_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)
):
    tenant = service.get_tenant(db, tenant_id)
    if not tenant or tenant.deleted_at:
        raise NotFoundError("Tenant")
    with platform_scope():
        tenant.status = "active"
        tenant.suspended_at = None
        service.platform_audit(db, admin.id, "tenant.reactivate", tenant.id, {}, _client_ip(request))
        db.commit()
    return tenant


@router.delete("/tenants/{tenant_id}", response_model=Message)
def delete_tenant(
    tenant_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)
):
    """Soft delete. A purge job removes the data after the retention window (Phase 7)."""
    tenant = service.get_tenant(db, tenant_id)
    if not tenant or tenant.deleted_at:
        raise NotFoundError("Tenant")
    if tenant.slug == settings.default_tenant_slug:
        raise AppError("The default workspace cannot be deleted", 400)
    with platform_scope():
        tenant.status = "deleted"
        tenant.deleted_at = utcnow()
        service.platform_audit(db, admin.id, "tenant.delete", tenant.id, {"name": tenant.name}, _client_ip(request))
        db.commit()
    return {"detail": "Tenant deleted"}


@router.post("/tenants/{tenant_id}/impersonate", response_model=ImpersonateOut)
def impersonate(
    tenant_id: str,
    payload: ImpersonateIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    """Mint a short-lived token to act as a tenant user, for support.

    The token carries an `imp` claim naming the real admin, and the start is
    audited. The frontend shows a persistent banner for the whole session.
    """
    tenant = service.get_tenant(db, tenant_id)
    if not tenant or tenant.deleted_at:
        raise NotFoundError("Tenant")

    with tenant_scope(tenant.id):
        if payload.user_id:
            target = db.get(User, payload.user_id)
        else:
            target = db.scalar(
                select(User).join(Role, User.role_id == Role.id)
                .where(Role.name == "Super Admin", User.is_active.is_(True))
                .order_by(User.created_at)
            ) or db.scalar(select(User).where(User.is_active.is_(True)).order_by(User.created_at))
        if not target:
            raise NotFoundError("Tenant user")
        target_email = target.email
        target_id = target.id

    with platform_scope():
        service.platform_audit(
            db, admin.id, "tenant.impersonate.start", tenant.id,
            {"acting_as": target_email, "user_id": target_id}, _client_ip(request),
        )
        db.commit()

    return {
        "access_token": create_impersonation_token(target_id, tenant.id, admin.id),
        "token_type": "bearer",
        "expires_in_minutes": settings.impersonation_token_expire_minutes,
        "tenant": tenant,
        "acting_as_email": target_email,
    }


@router.get("/stats", response_model=PlatformStatsOut)
def stats(db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    with platform_scope():
        tenants = list(db.scalars(select(Tenant).where(Tenant.deleted_at.is_(None))).all())
        users_total = db.scalar(select(func.count()).select_from(User).where(User.tenant_id.isnot(None))) or 0
    by_template: dict[str, int] = {}
    for t in tenants:
        by_template[t.template_key] = by_template.get(t.template_key, 0) + 1
    return {
        "tenants_total": len(tenants),
        "tenants_active": sum(1 for t in tenants if t.is_usable),
        "tenants_suspended": sum(1 for t in tenants if t.status == "suspended"),
        "users_total": users_total,
        "by_template": by_template,
    }


def _detail(db: Session, tenant: Tenant) -> dict:
    with platform_scope():
        count = db.scalar(select(func.count()).select_from(User).where(User.tenant_id == tenant.id)) or 0
    data = TenantOut.model_validate(tenant).model_dump()
    data["user_count"] = count
    data["settings"] = tenant.settings or {}
    return data
