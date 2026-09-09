"""The shape of a CRM template, and validation for it.

A template is the recipe a tenant is built from: which modules exist and what they
are called, which roles and pipeline stages to create, what settings and email
templates to start with. `general_crm` reproduces today's CRM exactly;
`insurance_agent` reshapes it for an insurance agency.

Templates are **copied into a tenant at provisioning time**, never referenced live.
Editing a template afterwards therefore cannot silently change a running tenant —
that only happens through a deliberate re-apply.
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.permissions import ALL_PERMISSIONS
from app.platform.catalog import MODULE_KEYS


class TemplateError(ValueError):
    """A template document is malformed."""


@dataclass
class TemplateModule:
    key: str
    enabled: bool = True
    label: str | None = None   # None = use the catalog's default label
    order: int | None = None


@dataclass
class TemplateConfig:
    key: str
    name: str
    version: int = 1
    description: str = ""
    modules: list[TemplateModule] = field(default_factory=list)
    roles: list[dict] = field(default_factory=list)
    stages: list[dict] = field(default_factory=list)
    lead_sources: list[str] = field(default_factory=list)
    tags: list[dict] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    email_templates: list[dict] = field(default_factory=list)
    masters: dict[str, list] = field(default_factory=dict)
    #: [{key, enabled, order}] — which dashboard cards a workspace opens with.
    #: Read selectively, like `modules`: naming any names all.
    dashboard: list[dict] = field(default_factory=list)

    def module_map(self) -> dict[str, TemplateModule]:
        return {m.key: m for m in self.modules}


def parse_template(raw: dict) -> TemplateConfig:
    """Validate a template document and return it as a `TemplateConfig`.

    Fails loudly: a template with a typo'd module key or an unknown permission
    would otherwise produce a tenant that is subtly broken in ways only noticed
    much later, by the client.
    """
    if not isinstance(raw, dict):
        raise TemplateError("Template must be an object")

    for required in ("key", "name"):
        if not raw.get(required):
            raise TemplateError(f"Template is missing '{required}'")

    modules = []
    seen: set[str] = set()
    for entry in raw.get("modules", []):
        key = entry.get("key")
        if key not in MODULE_KEYS:
            raise TemplateError(f"Unknown module '{key}'. Known modules: {', '.join(MODULE_KEYS)}")
        if key in seen:
            raise TemplateError(f"Module '{key}' appears more than once")
        seen.add(key)
        modules.append(
            TemplateModule(
                key=key,
                enabled=bool(entry.get("enabled", True)),
                label=entry.get("label"),
                order=entry.get("order"),
            )
        )

    roles = raw.get("roles", [])
    for role in roles:
        if not role.get("name"):
            raise TemplateError("Every role needs a name")
        for permission in role.get("permissions", []):
            if permission != "*" and not permission.endswith(":*") and permission not in ALL_PERMISSIONS:
                raise TemplateError(f"Role '{role['name']}' has unknown permission '{permission}'")

    for stage in raw.get("stages", []):
        if not stage.get("name"):
            raise TemplateError("Every pipeline stage needs a name")

    seen_triggers = set()
    for template in raw.get("email_templates", []):
        for required in ("name", "subject", "body_html"):
            if required not in template:
                raise TemplateError(f"Email template is missing '{required}'")

        trigger = template.get("trigger")
        if trigger:
            from app.settings.workflows import TRIGGERS_BY_KEY

            if trigger not in TRIGGERS_BY_KEY:
                raise TemplateError(
                    f"Email template '{template['name']}' names an unknown trigger "
                    f"'{trigger}'"
                )
            if trigger in seen_triggers:
                # Two templates on one trigger means the email a customer receives
                # depends on which row a query reaches first.
                raise TemplateError(
                    f"Two email templates both claim the trigger '{trigger}'"
                )
            seen_triggers.add(trigger)

    return TemplateConfig(
        key=raw["key"],
        name=raw["name"],
        version=int(raw.get("version", 1)),
        description=raw.get("description", ""),
        modules=modules,
        roles=roles,
        stages=raw.get("stages", []),
        lead_sources=raw.get("lead_sources", []),
        tags=raw.get("tags", []),
        settings=raw.get("settings", {}),
        email_templates=raw.get("email_templates", []),
        masters=raw.get("masters", {}),
        dashboard=raw.get("dashboard", []),
    )
