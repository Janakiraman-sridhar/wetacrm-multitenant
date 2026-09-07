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
from app.services import crypto
from app.core.tenancy import platform_scope, tenant_scope
from app.platform import provisioning
from app.platform.catalog import MODULE_CATALOG
from app.platform.models import PlatformAuditLog, Tenant, TenantModule
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
        # Its own data-encryption key, wrapped with the platform master key. Minted
        # here so PII can never be written before a key exists to protect it.
        dek_encrypted=crypto.wrap_dek(crypto.generate_dek()),
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


def ensure_tenant_keys(db: Session) -> None:
    """Give any tenant created before encryption existed its own data key."""
    with platform_scope():
        for tenant in db.scalars(select(Tenant).where(Tenant.dek_encrypted.is_(None))).all():
            tenant.dek_encrypted = crypto.wrap_dek(crypto.generate_dek())
            log.info("Generated a data-encryption key for tenant %s", tenant.slug)
        db.commit()


#: Prefix marking an address freed by a tenant deletion. It keeps the original
#: address readable inside it, so a restore during the retention window can put it
#: back without a second place to look it up.
TOMBSTONE_PREFIX = "deleted."


def tombstone_email(tenant_id: str, email: str) -> str:
    return f"{TOMBSTONE_PREFIX}{tenant_id[:8]}.{email}"


def original_email(tombstoned: str) -> str:
    """Reverse `tombstone_email`. Returns the input unchanged if it is not one."""
    if not tombstoned.startswith(TOMBSTONE_PREFIX):
        return tombstoned
    return tombstoned.split(".", 2)[-1]


def release_tenant_users(db: Session, tenant_id: str) -> int:
    """Deactivate a deleted tenant's users and free their email addresses.

    `users.email` is globally unique — that is what lets the sign-in screen work
    without a workspace picker. So a deleted tenant would otherwise hold its owner's
    address hostage for the whole retention window, and re-creating that client with
    the same address would be refused. The row stays (the data is retained), but the
    address is released by tombstoning it.

    Deactivating matters as much as renaming: a user whose tenant is gone must not be
    able to sign in, whatever their token or password says.
    """
    with tenant_scope(tenant_id):
        users = list(db.scalars(select(User)).all())
        for user in users:
            user.is_active = False
            if not user.email.startswith(TOMBSTONE_PREFIX):
                user.email = tombstone_email(tenant_id, user.email)
    return len(users)


def backfill_new_modules(db: Session) -> None:
    """Give existing tenants a row for any module added to the catalog since they were made.

    Without this, shipping a module reaches only workspaces created afterwards: the
    sidebar is built from `tenant_modules`, so an older tenant would never see it no
    matter what its template says.

    It is additive by construction — `_apply_modules` writes rows that are *missing*
    and never touches one that exists — so this cannot overwrite a choice the tenant
    made. Whether the new module arrives switched on is decided by the tenant's own
    template, which is the same answer it would have got at provisioning time.
    """
    with platform_scope():
        tenants = list(db.scalars(select(Tenant).where(Tenant.deleted_at.is_(None))).all())

    touched = False
    for tenant in tenants:
        with tenant_scope(tenant.id):
            present = {key for key in db.scalars(select(TenantModule.module_key)).all()}
            missing = [d.key for d in MODULE_CATALOG if d.key not in present]
            if not missing:
                continue
            try:
                config = provisioning.get_template(db, tenant.template_key or "general_crm")
            except Exception:
                config = provisioning.get_template(db, "general_crm")
            provisioning._apply_modules(db, config)
            touched = True
            log.info("Added modules %s to tenant %s", ", ".join(missing), tenant.slug)
    # One commit for every tenant. Startup writes hold a SQLite write lock, and a
    # reload can briefly leave two processes competing for it — a single short
    # transaction is far less likely to sit behind the other one.
    if touched:
        db.commit()


def bootstrap(db: Session) -> None:
    """Startup: load system templates, then ensure the platform admin and Default tenant."""
    provisioning.sync_system_templates(db)
    ensure_platform_admin(db)
    ensure_default_tenant(db)
    ensure_tenant_keys(db)
    backfill_new_modules(db)
