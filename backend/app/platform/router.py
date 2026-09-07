"""Platform (Super Admin) API — creating and managing tenants.

Every endpoint here is guarded by `get_platform_admin` and runs in `platform_scope()`,
which is the *only* place tenant filtering is deliberately switched off. Actions are
recorded in `platform_audit_logs` against the admin who performed them.

A platform admin has no route into a tenant's own CRM: there is no impersonation, and
`get_current_user` refuses any token whose tenant is not the user's own. Everything an
admin can do to a workspace — its modules, its template, its status — is done from here.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_platform_admin
from app.core.exceptions import AppError, NotFoundError
from app.core.schemas import Message
from app.core.config import settings
from app.core.tenancy import platform_scope, tenant_scope
from app.database.base import utcnow
from app.database.session import get_db
from app.platform import provisioning, service
from app.platform.catalog import MODULES_BY_KEY
from app.platform.models import CrmTemplate, Tenant, TenantModule
from app.platform.modules_router import list_tenant_modules
from app.platform.template_schema import TemplateError, parse_template
from app.platform.schemas import (
    PlatformStatsOut, TemplateClone, TemplateCreate, TemplateDetailOut, TemplateOut,
    TemplateUpdate, TenantCreate, TenantDetailOut, TenantModuleUpdate, TenantOut,
    TenantUpdate,
)
from app.users.models import User

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
        # A deleted tenant's addresses are tombstoned on delete, so a clash here is
        # always with a live workspace — say which one, because "already in use" with
        # no idea where is a dead end for whoever is looking at the screen.
        with platform_scope():
            holder = db.get(Tenant, clash.tenant_id) if clash.tenant_id else None
        where = f" in {holder.name}" if holder else " by a platform administrator"
        raise AppError(f"That email already belongs to a user{where}", 409)

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
    # Free the addresses before marking the tenant gone: `users.email` is globally
    # unique, so leaving them in place would refuse this client's own email if they
    # were re-created — which is exactly what someone does after a mistaken delete.
    released = service.release_tenant_users(db, tenant.id)

    with platform_scope():
        tenant.status = "deleted"
        tenant.deleted_at = utcnow()
        service.platform_audit(
            db, admin.id, "tenant.delete", tenant.id,
            {"name": tenant.name, "users_released": released}, _client_ip(request),
        )
        db.commit()
    return {"detail": "Tenant deleted"}


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


#: What the console counts per workspace, and the module each count belongs to. Only
#: modules the tenant actually has are counted — a "0 policies" line for a general CRM
#: that has no Policies module is noise pretending to be information.
_RECORD_COUNTS = [
    ("contacts", "customers", "app.contacts.models", "Contact"),
    ("companies", "companies", "app.companies.models", "Company"),
    ("policies", "policies", "app.policies.models", "Policy"),
    ("loans", "loans", "app.loans.models", "Loan"),
    ("quotations", "quotations", "app.quotations.models", "Quotation"),
    ("deals", "deals", "app.deals.models", "Deal"),
    ("leads", "leads", "app.leads.models", "Lead"),
    ("tasks", "tasks", "app.tasks.models", "Task"),
]


def _detail(db: Session, tenant: Tenant) -> dict:
    """Everything the console shows about one workspace.

    Assembled here rather than left to a handful of separate calls, because the
    tenant page is the one screen where an admin asks "what *is* this client" and
    every answer should already be on it.
    """
    import importlib

    data = TenantOut.model_validate(tenant).model_dump()
    data["settings"] = tenant.settings or {}

    with tenant_scope(tenant.id):
        users = list(db.scalars(select(User).order_by(User.created_at)).all())
        modules = list(db.scalars(select(TenantModule)).all())
        enabled_keys = {m.module_key for m in modules if m.enabled}

        counts = {}
        for module_key, label, module_path, class_name in _RECORD_COUNTS:
            if module_key not in enabled_keys:
                continue
            model = getattr(importlib.import_module(module_path), class_name)
            counts[label] = db.scalar(select(func.count()).select_from(model)) or 0

    owner = next((u for u in users if u.id == tenant.owner_user_id), None) or (
        users[0] if users else None
    )
    data["user_count"] = len(users)
    data["owner_email"] = owner.email if owner else None
    data["owner_name"] = owner.full_name if owner else None
    data["module_count"] = len(modules)
    data["enabled_module_count"] = len(enabled_keys)
    data["record_counts"] = counts
    data["users"] = [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.name if u.role else None,
            "is_active": u.is_active,
            "last_login_at": u.last_login_at,
            "is_owner": bool(owner and u.id == owner.id),
        }
        for u in users
    ]
    return data


# --- templates ----------------------------------------------------------------

def _template_summary(row: CrmTemplate) -> dict:
    config = row.config or {}
    modules = config.get("modules", [])
    return {
        "id": row.id,
        "key": row.key,
        "name": row.name,
        "description": row.description,
        "version": row.version,
        "is_system": row.is_system,
        "module_count": len(modules),
        "enabled_module_count": sum(1 for m in modules if m.get("enabled", True)),
        "role_count": len(config.get("roles", [])),
        "stage_count": len(config.get("stages", [])),
    }


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    with platform_scope():
        rows = db.scalars(
            select(CrmTemplate).order_by(CrmTemplate.is_system.desc(), CrmTemplate.name)
        ).all()
    return [_template_summary(row) for row in rows]


@router.get("/templates/{key}", response_model=TemplateDetailOut)
def get_template_detail(
    key: str, db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)
):
    with platform_scope():
        row = db.scalar(select(CrmTemplate).where(CrmTemplate.key == key))
    if row is None:
        raise NotFoundError("Template")
    data = _template_summary(row)
    data["config"] = row.config or {}
    return data


def _copy_template(
    db: Session, admin: User, source_key: str, payload: TemplateClone, action: str, ip: str | None
) -> dict:
    """Create a custom template from an existing one.

    Both "clone" and "new" land here, because they are the same operation seen from
    two angles: a new template must start from a working one or it provisions a
    workspace with no roles and no stages, which nobody notices until the owner
    cannot sign in.
    """
    with platform_scope():
        source = db.scalar(select(CrmTemplate).where(CrmTemplate.key == source_key))
        if source is None:
            raise NotFoundError("Template")
        if db.scalar(select(CrmTemplate).where(CrmTemplate.key == payload.key)):
            raise AppError("A template with that key already exists", 409)

        config = dict(source.config or {})
        config["key"] = payload.key
        config["name"] = payload.name
        if payload.description is not None:
            config["description"] = payload.description

        created = CrmTemplate(
            key=payload.key,
            name=payload.name,
            description=payload.description or source.description,
            version=1,
            is_system=False,
            config=config,
        )
        db.add(created)
        service.platform_audit(
            db, admin.id, action, None, {"from": source.key, "to": payload.key}, ip
        )
        db.commit()

    data = _template_summary(created)
    data["config"] = created.config
    return data


@router.post("/templates", response_model=TemplateDetailOut)
def create_template(
    payload: TemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    """Create a new custom template, starting from `base_key`."""
    return _copy_template(
        db, admin, payload.base_key, payload, "template.create", _client_ip(request)
    )


@router.post("/templates/{key}/clone", response_model=TemplateDetailOut)
def clone_template(
    key: str,
    payload: TemplateClone,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    """Copy a template so it can be customised without touching the system one.

    System templates stay read-only: they are refreshed from the bundled JSON files
    whenever their version increases, so edits to them would be overwritten.
    """
    return _copy_template(db, admin, key, payload, "template.clone", _client_ip(request))


@router.delete("/templates/{key}", response_model=Message)
def delete_template(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    with platform_scope():
        row = db.scalar(select(CrmTemplate).where(CrmTemplate.key == key))
        if row is None:
            raise NotFoundError("Template")
        if row.is_system:
            raise AppError("System templates cannot be deleted", 400)
        in_use = db.scalar(
            select(func.count()).select_from(Tenant).where(
                Tenant.template_key == key, Tenant.deleted_at.is_(None)
            )
        ) or 0
        if in_use:
            raise AppError(f"{in_use} tenant(s) still use this template", 409)
        db.delete(row)
        service.platform_audit(
            db, admin.id, "template.delete", None, {"key": key}, _client_ip(request)
        )
        db.commit()
    return {"detail": "Template deleted"}


# --- a tenant's modules, from the platform side --------------------------------

@router.get("/tenants/{tenant_id}/modules")
def tenant_modules(
    tenant_id: str, db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)
):
    tenant = service.get_tenant(db, tenant_id)
    if not tenant or tenant.deleted_at:
        raise NotFoundError("Tenant")
    with tenant_scope(tenant_id):
        return list_tenant_modules(db, enabled_only=False)


@router.patch("/tenants/{tenant_id}/modules")
def update_tenant_modules(
    tenant_id: str,
    payload: list[TenantModuleUpdate],
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    """Rename, reorder or switch a tenant's modules on and off."""
    tenant = service.get_tenant(db, tenant_id)
    if not tenant or tenant.deleted_at:
        raise NotFoundError("Tenant")

    changed: dict[str, dict] = {}
    with tenant_scope(tenant_id):
        rows = {m.module_key: m for m in db.scalars(select(TenantModule)).all()}
        for update in payload:
            row = rows.get(update.module_key)
            if row is None:
                continue
            definition = MODULES_BY_KEY.get(row.module_key)
            data = update.model_dump(exclude_unset=True, exclude={"module_key"})
            if definition and definition.locked and data.get("enabled") is False:
                raise AppError(f"{definition.label} cannot be switched off", 400)
            for field, value in data.items():
                if value is not None and getattr(row, field) != value:
                    changed.setdefault(row.module_key, {})[field] = [getattr(row, field), value]
                    setattr(row, field, value)
        db.flush()
        result = list_tenant_modules(db, enabled_only=False)

    with platform_scope():
        if changed:
            service.platform_audit(
                db, admin.id, "tenant.modules.update", tenant_id, changed, _client_ip(request)
            )
        db.commit()
    return result


@router.post("/tenants/{tenant_id}/apply-template", response_model=Message)
def apply_template_to_tenant(
    tenant_id: str,
    template_key: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    """Re-apply a template to an existing tenant.

    Additive only: it fills in roles, stages, sources, settings and modules the
    tenant does not have yet, and never overwrites something already customised.
    This is the deliberate action referred to in the PRD — templates are otherwise
    copied once at provisioning and never touch a live tenant again.
    """
    tenant = service.get_tenant(db, tenant_id)
    if not tenant or tenant.deleted_at:
        raise NotFoundError("Tenant")

    config = provisioning.get_template(db, template_key)
    with tenant_scope(tenant_id):
        provisioning.apply_template(db, tenant_id, config)
    with platform_scope():
        tenant.template_key = template_key
        service.platform_audit(
            db, admin.id, "tenant.template.apply", tenant_id,
            {"template": template_key}, _client_ip(request),
        )
        db.commit()
    return {"detail": f"Template '{config.name}' applied"}


@router.patch("/templates/{key}", response_model=TemplateDetailOut)
def update_template(
    key: str,
    payload: TemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    """Customise a template.

    System templates are refreshed from the bundled JSON whenever their version
    increases, so an edit to one would be silently overwritten. Cloning first is
    therefore required rather than merely advised, and the error says so.

    The edited config is re-validated before it is stored: a template with a typo'd
    module key or an unknown permission would otherwise produce a subtly broken
    workspace that nobody notices until the client does.
    """
    with platform_scope():
        row = db.scalar(select(CrmTemplate).where(CrmTemplate.key == key))
        if row is None:
            raise NotFoundError("Template")
        if row.is_system:
            raise AppError(
                "System templates cannot be edited — they are refreshed from the product "
                "and your changes would be overwritten. Clone this one first.",
                400,
            )

        config = dict(row.config or {})
        data = payload.model_dump(exclude_unset=True)
        for field in ("modules", "stages", "lead_sources", "tags", "settings"):
            if field in data and data[field] is not None:
                config[field] = data[field]
        if data.get("name"):
            config["name"] = data["name"]
            row.name = data["name"]
        if "description" in data:
            config["description"] = data["description"]
            row.description = data["description"]

        try:
            parse_template(config)
        except TemplateError as exc:
            raise AppError(f"That template would not be valid: {exc}", 400)

        row.config = config
        row.version = (row.version or 1) + 1
        service.platform_audit(
            db, admin.id, "template.update", None,
            {"key": key, "changed": sorted(data)}, _client_ip(request),
        )
        db.commit()

    result = _template_summary(row)
    result["config"] = row.config
    return result


@router.get("/module-catalog")
def module_catalog(admin: User = Depends(get_platform_admin)):
    """Every module a template may enable, with its default label.

    Served rather than duplicated in the frontend so the template editor cannot
    offer a module key the backend would reject.
    """
    from app.platform.catalog import MODULE_CATALOG

    return [
        {"key": m.key, "label": m.label, "order": m.order,
         "icon": m.icon, "locked": m.locked, "permission": m.permission}
        for m in MODULE_CATALOG
    ]
