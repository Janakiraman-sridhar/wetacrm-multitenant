"""Building a tenant's CRM from a template.

This replaces the fixed `seed.run()` of Phase 0. Everything a new workspace starts
with — roles, modules and their labels, pipeline stages, lead sources, tags,
settings, email templates — comes from the template document, so adding a vertical
means adding a JSON file, not branching in code.

Templates are **copied**, never referenced: once a tenant exists it owns its
configuration outright, and editing the template afterwards cannot change it behind
the client's back.
"""

import json
import logging
import pathlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import platform_scope, tenant_scope
from app.deals.models import DealStage
from app.leads.models import LeadSource
from app.platform.catalog import MODULE_CATALOG, MODULES_BY_KEY
from app.platform.models import CrmTemplate, TenantModule
from app.platform.template_schema import TemplateConfig, parse_template
from app.settings.models import EmailTemplate, Setting, Tag
from app.users.models import Role

log = logging.getLogger("weta.provisioning")

TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"
SYSTEM_TEMPLATE_KEYS = ["general_crm", "insurance_agent"]

# The original default body of each seeded email template, so an upgrade can tell
# "still the default" from "the client edited this" and only replace the former.
_UNTOUCHED_MARKER = "__weta_original__"


def load_template_file(key: str) -> TemplateConfig:
    path = TEMPLATE_DIR / f"{key}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return parse_template(raw)


def sync_system_templates(db: Session) -> None:
    """Load the bundled templates into the database, refreshing on a version bump.

    Runs at startup. A custom template cloned by an admin is never touched here —
    only rows flagged `is_system`.
    """
    with platform_scope():
        for key in SYSTEM_TEMPLATE_KEYS:
            try:
                config = load_template_file(key)
            except Exception:
                log.exception("Could not load system template %s", key)
                continue

            raw = json.loads((TEMPLATE_DIR / f"{key}.json").read_text(encoding="utf-8"))
            row = db.scalar(select(CrmTemplate).where(CrmTemplate.key == key))
            if row is None:
                db.add(
                    CrmTemplate(
                        key=config.key,
                        name=config.name,
                        description=config.description,
                        version=config.version,
                        is_system=True,
                        config=raw,
                    )
                )
                log.info("Loaded system template %s v%s", key, config.version)
            elif row.is_system and row.version < config.version:
                row.name = config.name
                row.description = config.description
                row.version = config.version
                row.config = raw
                log.info("Updated system template %s to v%s", key, config.version)
        db.commit()


def get_template(db: Session, key: str) -> TemplateConfig:
    """The stored template, falling back to the bundled file if it is not in the DB yet."""
    with platform_scope():
        row = db.scalar(select(CrmTemplate).where(CrmTemplate.key == key))
    if row is not None:
        return parse_template(row.config)
    return load_template_file(key)


def apply_template(db: Session, tenant_id: str, config: TemplateConfig) -> None:
    """Create a tenant's configuration from a template. Idempotent.

    Called inside the tenant's scope, so every `select` below already sees only that
    tenant's rows and the `existing_*` checks are naturally per-tenant.
    """
    _apply_modules(db, config)
    _apply_roles(db, config)
    _apply_stages(db, config)
    _apply_lead_sources(db, config)
    _apply_tags(db, config)
    _apply_settings(db, config)
    _apply_masters(db, config)
    _apply_email_templates(db, config)
    db.flush()


def _apply_modules(db: Session, config: TemplateConfig) -> None:
    """Write one row per catalog module, using the template's overrides where given.

    Every module gets a row — including disabled ones — so a tenant admin can switch
    one on later without needing to know the catalog.
    """
    existing = {m.module_key: m for m in db.scalars(select(TenantModule)).all()}
    overrides = config.module_map()

    for definition in MODULE_CATALOG:
        override = overrides.get(definition.key)
        enabled = True if override is None else override.enabled
        if definition.locked:
            enabled = True  # dashboard and settings cannot be switched off
        label = (override.label if override and override.label else definition.label)
        order = (override.order if override and override.order is not None else definition.order)

        row = existing.get(definition.key)
        if row is None:
            db.add(TenantModule(module_key=definition.key, label=label, enabled=enabled, order=order))
        # An existing row is left alone: it may hold the tenant's own customisation.


def _apply_roles(db: Session, config: TemplateConfig) -> None:
    existing = {r.name for r in db.scalars(select(Role)).all()}
    for role in config.roles:
        if role["name"] in existing:
            continue
        db.add(
            Role(
                name=role["name"],
                description=role.get("description"),
                permissions=role.get("permissions", []),
                is_system=True,
            )
        )


def _apply_stages(db: Session, config: TemplateConfig) -> None:
    if db.scalar(select(DealStage).limit(1)):
        return  # the tenant already has a pipeline; never rewrite it
    for stage in config.stages:
        db.add(
            DealStage(
                name=stage["name"],
                order=stage.get("order", 0),
                probability=stage.get("probability", 0),
                is_won=bool(stage.get("is_won", False)),
                is_lost=bool(stage.get("is_lost", False)),
            )
        )


def _apply_lead_sources(db: Session, config: TemplateConfig) -> None:
    existing = {s.name for s in db.scalars(select(LeadSource)).all()}
    for name in config.lead_sources:
        if name not in existing:
            db.add(LeadSource(name=name))


def _apply_tags(db: Session, config: TemplateConfig) -> None:
    existing = {t.name for t in db.scalars(select(Tag)).all()}
    for tag in config.tags:
        if tag["name"] not in existing:
            db.add(Tag(name=tag["name"], color=tag.get("color", "#4F46E5")))


def _apply_settings(db: Session, config: TemplateConfig) -> None:
    existing = {s.key for s in db.scalars(select(Setting)).all()}
    for key, value in config.settings.items():
        if key not in existing:
            db.add(Setting(key=key, value=value))
    # Masters (insurers, banks, relations, …) live as one settings row so later
    # phases can read them without another table per list.
    if config.masters and "masters" not in existing:
        db.add(Setting(key="masters", value=config.masters))


def _apply_masters(db: Session, config: TemplateConfig) -> None:
    """Turn the template's reference lists into rows policies can point at.

    The template names them in the plural ("insurers"); the table stores the
    singular type ("insurer"), because a policy has one insurer.
    """
    from app.policies.models import MASTER_TYPES, Master

    if not config.masters:
        return

    existing = {(m.type, m.name) for m in db.scalars(select(Master)).all()}
    for plural, names in config.masters.items():
        singular = plural[:-1] if plural.endswith("s") else plural
        if singular not in MASTER_TYPES:
            continue
        for order, name in enumerate(names):
            if (singular, name) not in existing:
                db.add(Master(type=singular, name=name, order=order))


def _apply_email_templates(db: Session, config: TemplateConfig) -> None:
    existing = {t.name for t in db.scalars(select(EmailTemplate)).all()}
    for template in config.email_templates:
        if template["name"] in existing:
            continue
        db.add(
            EmailTemplate(
                name=template["name"],
                subject=template["subject"],
                body_html=template["body_html"],
                description=template.get("description"),
            )
        )


def provision_from_template(db: Session, tenant_id: str, template_key: str) -> TemplateConfig:
    """Apply a template to a tenant. The caller commits."""
    config = get_template(db, template_key)
    with tenant_scope(tenant_id):
        apply_template(db, tenant_id, config)
    return config
