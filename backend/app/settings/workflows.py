"""What makes an email template actually send.

A template with no trigger is a draft nobody reads. Before this, the connection
between a template and the moment it fires was a string literal at a call site —
`send_templated(db, to, "lead_assigned", …)` — which had two consequences worth
naming, because both were live in this codebase:

- **`notification_settings` did nothing.** A tenant could switch "email on lead
  assign" off in Settings and still get the email, because nothing read the setting.
- **Two seeded templates never fired at all.** The insurance template ships a renewal
  reminder and a birthday email; both were editable, both were configured, and
  nothing anywhere sent either one.

So the trigger moves onto the template, and the catalog below is the list of moments
a template may hang off. Adding one is a `TriggerDef` plus the `fire()` call at the
moment it describes — the same shape as the module catalog, for the same reason: the
alternative is a growing chain of `if setting_enabled(...)` at scattered call sites,
which is where the two bugs above came from.

**Customer-facing scheduled triggers default to off.** A renewal reminder that starts
emailing a client's entire book because someone enabled a module is not a feature.
Switching one on has to be a decision somebody made.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

log = logging.getLogger("weta.workflows")


@dataclass(frozen=True)
class TriggerDef:
    key: str
    label: str
    #: What fires it, in the words of the person configuring it.
    description: str
    #: "event" fires inside a request; "scheduled" fires from a daily job.
    kind: str
    #: `{placeholders}` available to the subject and body.
    merge_fields: list[str]
    #: Recipient in plain language, so the settings screen can say who gets it.
    audience: str
    #: Locked triggers cannot be switched off — see `locked_reason`.
    locked: bool = False
    locked_reason: str = ""
    #: Whether a newly provisioned tenant has it on.
    default_enabled: bool = True
    #: Extra per-trigger settings, e.g. how many days before expiry to send.
    config_schema: dict = field(default_factory=dict)


TRIGGERS: list[TriggerDef] = [
    TriggerDef(
        key="welcome",
        label="Welcome email",
        description="A new user is added to the workspace.",
        kind="event",
        audience="The new user",
        merge_fields=["first_name", "email", "app_url", "app_name", "logo_html"],
    ),
    TriggerDef(
        key="password_reset",
        label="Password reset",
        description="Someone asks to reset their password.",
        kind="event",
        audience="The person resetting",
        merge_fields=["first_name", "reset_url", "app_name"],
        locked=True,
        locked_reason=(
            "Switching this off locks anyone who forgets their password out of the "
            "workspace, with no way back in that does not involve you."
        ),
    ),
    TriggerDef(
        key="lead_assigned",
        label="Enquiry assigned",
        description="An enquiry or lead is assigned to a team member.",
        kind="event",
        audience="The assignee",
        merge_fields=["assignee_name", "lead_title", "company_name", "app_url"],
    ),
    TriggerDef(
        key="task_assigned",
        label="Task assigned",
        description="A task is assigned to a team member.",
        kind="event",
        audience="The assignee",
        merge_fields=["assignee_name", "task_title", "due_date", "app_url"],
        default_enabled=False,
    ),
    TriggerDef(
        key="quotation",
        label="Quotation sent",
        description="An agent emails a quotation from the quotation screen.",
        kind="event",
        audience="The customer",
        merge_fields=["contact_name", "number", "total", "company_name"],
        locked=True,
        locked_reason=(
            "This one only fires when an agent presses Send on a specific quotation. "
            "Disabling it would make that button do nothing."
        ),
    ),
    TriggerDef(
        key="policy_renewal_due",
        label="Renewal reminder",
        description="A policy is approaching its expiry date.",
        kind="scheduled",
        audience="The customer",
        merge_fields=[
            "customer_name", "policy_number", "insurer", "expiry_date",
            "days_to_expiry", "premium", "agent_name", "company_name",
        ],
        default_enabled=False,
        config_schema={
            "days_before": {
                "label": "Days before expiry",
                "type": "multiselect",
                "options": [60, 30, 15, 7, 1],
                "default": [30, 7],
                "help": "One email per policy at each of these points. Pick sparingly — "
                        "five reminders for one renewal reads as pestering.",
            },
        },
    ),
    TriggerDef(
        key="customer_birthday",
        label="Birthday greeting",
        description="It is a customer's birthday.",
        kind="scheduled",
        audience="The customer",
        merge_fields=["customer_name", "agent_name", "company_name"],
        default_enabled=False,
        config_schema={
            "days_before": {
                "label": "When to send",
                "type": "multiselect",
                "options": [0, 1],
                "default": [0],
                "help": "0 sends on the day. 1 sends the day before.",
            },
        },
    ),
]

TRIGGERS_BY_KEY = {t.key: t for t in TRIGGERS}
TRIGGER_KEYS = [t.key for t in TRIGGERS]

#: Triggers whose recipient is a customer rather than a colleague. The settings
#: screen marks these, because the blast radius of switching one on is the client's
#: whole book rather than one inbox.
CUSTOMER_FACING = {t.key for t in TRIGGERS if t.audience == "The customer"}


def trigger_or_none(key: str | None) -> TriggerDef | None:
    return TRIGGERS_BY_KEY.get(key or "")


def default_config(key: str) -> dict:
    definition = TRIGGERS_BY_KEY.get(key)
    if not definition:
        return {}
    return {
        name: spec.get("default")
        for name, spec in definition.config_schema.items()
        if "default" in spec
    }


def coerce_config(key: str, raw: dict | None) -> dict:
    """Keep only declared keys, and only sensible values.

    Same reasoning as the policy `details` whitelist: a free-form JSON blob attached
    to something that sends email to customers is a place for a typo to live quietly.
    """
    definition = TRIGGERS_BY_KEY.get(key)
    if not definition:
        return {}

    clean = default_config(key)
    for name, spec in definition.config_schema.items():
        if raw is None or name not in raw:
            continue
        value = raw[name]
        if spec["type"] == "multiselect":
            allowed = set(spec["options"])
            chosen = [v for v in (value or []) if v in allowed]
            # An empty selection would mean "enabled but never sends", which reads on
            # screen as broken. Fall back to the default rather than storing it.
            clean[name] = sorted(set(chosen), reverse=True) or spec.get("default")
        else:
            clean[name] = value
    return clean


# --- dispatch -----------------------------------------------------------------

def template_for(db: Session, trigger: str):
    """The enabled template bound to this trigger, or None."""
    from app.settings.models import EmailTemplate

    return db.scalar(
        select(EmailTemplate).where(
            EmailTemplate.trigger == trigger, EmailTemplate.enabled.is_(True)
        )
    )


def is_enabled(db: Session, trigger: str) -> bool:
    return template_for(db, trigger) is not None


def fire(
    db: Session,
    trigger: str,
    to: str | list[str],
    context: dict,
    attachments=None,
    inline_images=None,
) -> bool:
    """Send the template bound to `trigger`, if one is bound and switched on.

    Returns False when nothing was sent — including when the trigger is switched
    off, which is a normal outcome and not an error. Callers that need to tell the
    user "no email went out" should check `is_enabled` first and say so, rather than
    reporting a failure.
    """
    from app.services.email import send_templated

    if trigger not in TRIGGERS_BY_KEY:
        log.error("Unknown email trigger %r — nothing sent", trigger)
        return False

    template = template_for(db, trigger)
    if template is None:
        return False
    return send_templated(
        db, to, template.name, context,
        attachments=attachments, inline_images=inline_images,
    )
