import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import DEFAULT_ROLES
from app.core.security import hash_password
from app.deals.models import DEFAULT_STAGES, DealStage
from app.leads.models import LeadSource
from app.settings.models import EmailTemplate, Setting
from app.users.models import Role, User

log = logging.getLogger("weta.seed")

DEFAULT_LEAD_SOURCES = ["Website", "Referral", "Exhibition", "Cold Call", "Social Media", "Email Campaign", "Advertisement", "Other"]

DEFAULT_EMAIL_TEMPLATES = [
    {
        "name": "welcome",
        "subject": "Welcome to {app_name}",
        "body_html": "<p>Hi {first_name},</p><p>Your {app_name} account is ready. Sign in with <b>{email}</b>.</p>",
        "description": "Sent when a new user account is created",
    },
    {
        "name": "password_reset",
        "subject": "Reset your {app_name} password",
        "body_html": "<p>Hi {first_name},</p><p>Use this link to reset your password: <a href='{reset_link}'>Reset password</a>. It expires in 30 minutes.</p>",
        "description": "Password reset link",
    },
    {
        "name": "lead_assigned",
        "subject": "New lead assigned: {lead_title}",
        "body_html": "<p>Hi {first_name},</p><p>The lead <b>{lead_title}</b> has been assigned to you.</p>",
        "description": "Sent when a lead is assigned to a user",
    },
    {
        "name": "quotation",
        "subject": "Quotation {number} from {company_name}",
        "body_html": "<p>Dear {contact_name},</p><p>Please find attached quotation <b>{number}</b> totalling <b>{total}</b>.</p>",
        "description": "Sent with a quotation PDF",
    },
]

DEFAULT_SETTINGS = {
    "company_profile": {"name": "WeTa CRM", "website": "", "email": "", "phone": "", "address": "", "logo_url": ""},
    "branding": {"primary_color": "#4F46E5", "app_name": "WeTa CRM"},
    "counters": {"quotation": 0, "invoice": 0, "ticket": 0},
    "notification_settings": {"email_on_lead_assign": True, "email_on_task_assign": True},
    "quotation_template": {
        "title": "QUOTATION",
        "number_prefix": "QT",
        "accent_color": "#4F46E5",
        "footer_note": "Thank you for your business.",
        "default_terms": "This quotation is valid for 30 days from the issue date.",
    },
    "invoice_template": {
        "title": "INVOICE",
        "number_prefix": "INV",
        "accent_color": "#4F46E5",
        "footer_note": "Thank you for your business.",
        "default_notes": "",
    },
}


def run(db: Session) -> None:
    # Roles
    existing_roles = {r.name for r in db.scalars(select(Role)).all()}
    for name, spec in DEFAULT_ROLES.items():
        if name not in existing_roles:
            db.add(Role(name=name, description=spec["description"], permissions=spec["permissions"], is_system=True))
    db.flush()

    # First admin user
    if not db.scalar(select(User).limit(1)):
        super_admin = db.scalar(select(Role).where(Role.name == "Super Admin"))
        db.add(
            User(
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                first_name="Super",
                last_name="Admin",
                role_id=super_admin.id,
            )
        )
        log.warning("Seeded initial Super Admin user: %s (change the password!)", settings.admin_email)

    # Deal stages
    if not db.scalar(select(DealStage).limit(1)):
        for name, order, prob, is_won, is_lost in DEFAULT_STAGES:
            db.add(DealStage(name=name, order=order, probability=prob, is_won=is_won, is_lost=is_lost))

    # Lead sources
    existing_sources = {s.name for s in db.scalars(select(LeadSource)).all()}
    for name in DEFAULT_LEAD_SOURCES:
        if name not in existing_sources:
            db.add(LeadSource(name=name))

    # Settings
    existing_settings = {s.key for s in db.scalars(select(Setting)).all()}
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing_settings:
            db.add(Setting(key=key, value=value))

    # Email templates
    existing_templates = {t.name for t in db.scalars(select(EmailTemplate)).all()}
    for tpl in DEFAULT_EMAIL_TEMPLATES:
        if tpl["name"] not in existing_templates:
            db.add(EmailTemplate(**tpl))

    db.commit()
