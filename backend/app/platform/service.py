"""Tenant lifecycle: bootstrap, provisioning and lookup.

Phase 0 keeps this deliberately small — enough to create the Default tenant that
existing single-tenant data migrates into, and the platform Super Admin who can
see across tenants. Phase 1 replaces `provision_tenant` with the template-driven
version described in the PRD.
"""

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.core.tenancy import platform_scope, tenant_scope
from app.platform import provisioning
from app.platform.models import PlatformAuditLog, Tenant
from app.users.models import User

log = logging.getLogger("weta.platform")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "tenant"


def unique_slug(db: Session, base: str) -> str:
    """A slug not yet taken. Runs in platform scope — slugs are unique platform-wide."""
    with platform_scope():
        taken = {s for s in db.scalars(select(Tenant.slug)).all()}
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def get_tenant(db: Session, tenant_id: str) -> Tenant | None:
    with platform_scope():
        return db.get(Tenant, tenant_id)


def list_tenants(db: Session, include_deleted: bool = False) -> list[Tenant]:
    with platform_scope():
        stmt = select(Tenant).order_by(Tenant.created_at.desc())
        if not include_deleted:
            stmt = stmt.where(Tenant.deleted_at.is_(None))
        return list(db.scalars(stmt).all())


def provision_tenant(
    db: Session,
    name: str,
    *,
    slug: str | None = None,
    type: str = "company",
    template_key: str = "general_crm",
    owner_email: str | None = None,
    owner_password: str | None = None,
    owner_first_name: str = "Admin",
    owner_last_name: str = "",
    status: str = "active",
) -> Tenant:
    """Create a tenant and seed its baseline data.

    Idempotent per slug: an existing tenant with the same slug is returned as-is,
    so a retried provision does not create duplicates.
    """
    base_slug = slug or slugify(name)
    with platform_scope():
        existing = db.scalar(select(Tenant).where(Tenant.slug == base_slug))
        if existing:
            return existing

    tenant = Tenant(
        name=name,
        slug=base_slug,
        type=type,
        template_key=template_key,
        status="provisioning",
    )
    with platform_scope():
        db.add(tenant)
        db.flush()

    # Everything below belongs to the new tenant.
    with tenant_scope(tenant.id):
        provisioning.apply_template(db, tenant.id, provisioning.get_template(db, template_key))

        if owner_email:
            with platform_scope():
                clash = db.scalar(select(User).where(User.email == owner_email))
            if not clash:
                from app.users.models import Role  # local import avoids a cycle at module load

                admin_role = db.scalar(
                    select(Role).where(Role.name == "Super Admin")
                ) or db.scalar(select(Role).order_by(Role.created_at))
                db.add(
                    User(
                        email=owner_email,
                        password_hash=hash_password(owner_password or settings.admin_password),
                        first_name=owner_first_name,
                        last_name=owner_last_name,
                        role_id=admin_role.id if admin_role else None,
                        tenant_id=tenant.id,
                    )
                )

    tenant.status = status
    db.commit()
    log.info("Provisioned tenant %s (%s) from template %s", tenant.name, tenant.slug, template_key)
    return tenant


def ensure_default_tenant(db: Session) -> Tenant:
    """The tenant that pre-multi-tenant data belongs to."""
    with platform_scope():
        tenant = db.scalar(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    if tenant:
        # Keep its baseline data current without touching customisations. This is
        # also what backfills module rows for a tenant provisioned before templates.
        with tenant_scope(tenant.id):
            provisioning.apply_template(
                db, tenant.id, provisioning.get_template(db, tenant.template_key)
            )
            db.commit()
        return tenant

    return provision_tenant(
        db,
        settings.default_tenant_name,
        slug=settings.default_tenant_slug,
        template_key="general_crm",
        owner_email=settings.admin_email,
        owner_password=settings.admin_password,
        owner_first_name="Super",
        owner_last_name="Admin",
    )


def ensure_platform_admin(db: Session) -> User:
    """The Super Admin who manages tenants. Has no tenant of their own."""
    with platform_scope():
        user = db.scalar(select(User).where(User.email == settings.platform_admin_email))
        if user:
            return user

        user = User(
            email=settings.platform_admin_email,
            password_hash=hash_password(settings.platform_admin_password),
            first_name="Platform",
            last_name="Admin",
            is_platform_admin=True,
            tenant_id=None,
            role_id=None,
        )
        db.add(user)
        db.commit()
    log.warning(
        "Seeded platform Super Admin: %s (change the password immediately)",
        settings.platform_admin_email,
    )
    return user


def platform_audit(
    db: Session,
    actor_user_id: str | None,
    action: str,
    tenant_id: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Record a platform-level action. Caller commits."""
    db.add(
        PlatformAuditLog(
            actor_user_id=actor_user_id,
            action=action,
            tenant_id_ref=tenant_id,
            detail=detail or {},
            ip_address=ip_address,
        )
    )


def bootstrap(db: Session) -> None:
    """Startup: load system templates, then ensure the platform admin and Default tenant."""
    provisioning.sync_system_templates(db)
    ensure_platform_admin(db)
    ensure_default_tenant(db)
