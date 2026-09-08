from fastapi import APIRouter, Depends, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.config import settings as app_config
from app.core.crud import get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.schemas import Message
from app.database.session import get_db
from app.services import storage
from app.services.pdf import document_pdf, sample_document
from app.settings import workflows
from app.settings.models import EmailTemplate, SentEmail, Setting, Tag
from app.settings.schemas import (
    EmailTemplateOut, EmailTemplateUpdate, SettingOut, SettingUpdate, TagCreate, TagOut,
    TagUpdate, WorkflowTriggerOut,
)
from app.users.models import User

router = APIRouter(prefix="/settings", tags=["settings"])

EDITABLE_KEYS = {"company_profile", "branding", "notification_settings", "quotation_template", "invoice_template"}


@router.get("", response_model=list[SettingOut], dependencies=[Depends(require_perm("settings:read"))])
def list_settings(db: Session = Depends(get_db)):
    return db.scalars(select(Setting).where(Setting.key != "counters")).all()


@router.put("/{key}", response_model=SettingOut)
def update_setting(key: str, payload: SettingUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    if key not in EDITABLE_KEYS:
        raise AppError(f"Setting '{key}' is not editable", 400)
    row = db.scalar(select(Setting).where(Setting.key == key))
    if row is None:
        row = Setting(key=key, value=payload.value)
        db.add(row)
    else:
        row.value = payload.value
    audit(db, user.id, "update", "setting", key)
    db.commit()
    return row


@router.get("/system-status", dependencies=[Depends(require_perm("settings:read"))])
def system_status():
    """Which optional integrations are configured (values themselves stay in env)."""
    return {
        "smtp_configured": bool(app_config.smtp_host),
        "redis_configured": bool(app_config.redis_url),
        "meilisearch_configured": bool(app_config.meili_url),
        "minio_configured": bool(app_config.minio_endpoint and app_config.minio_access_key),
        "database": "postgresql" if app_config.database_url.startswith("postgres") else "sqlite",
    }


# --- Company logo (used on quotation/invoice PDFs) ---

MAX_LOGO_BYTES = 2 * 1024 * 1024
LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}


def _profile_row(db: Session) -> Setting:
    row = db.scalar(select(Setting).where(Setting.key == "company_profile"))
    if row is None:
        row = Setting(key="company_profile", value={})
        db.add(row)
        db.flush()
    return row


@router.post("/company-logo", response_model=Message)
async def upload_company_logo(file: UploadFile, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    if file.content_type not in LOGO_TYPES:
        raise AppError("Logo must be a PNG, JPEG or WebP image", 400)
    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise AppError("Logo exceeds the 2 MB limit", 413)
    row = _profile_row(db)
    old_key = (row.value or {}).get("logo_key")
    key = storage.save_file(data, file.filename or "logo", file.content_type)
    row.value = {**(row.value or {}), "logo_key": key}
    if old_key:
        storage.delete_file(old_key)
    audit(db, user.id, "update", "setting", "company_logo")
    db.commit()
    return {"detail": "Logo uploaded"}


@router.get("/company-logo")
def get_company_logo(db: Session = Depends(get_db), _: User = Depends(require_perm("settings:read"))):
    row = db.scalar(select(Setting).where(Setting.key == "company_profile"))
    key = (row.value if row else {}).get("logo_key")
    if not key:
        raise AppError("No logo uploaded", 404)
    try:
        data = storage.read_file(key)
    except Exception:
        raise AppError("No logo uploaded", 404)
    return Response(content=data, media_type="image/png")


@router.delete("/company-logo", response_model=Message)
def delete_company_logo(db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    row = _profile_row(db)
    key = (row.value or {}).get("logo_key")
    if key:
        storage.delete_file(key)
        row.value = {k: v for k, v in (row.value or {}).items() if k != "logo_key"}
        audit(db, user.id, "update", "setting", "company_logo")
        db.commit()
    return {"detail": "Logo removed"}


# --- Live PDF preview for the document template editors ---

@router.post("/document-preview/{kind}")
def document_template_preview(
    kind: str,
    payload: SettingUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_perm("settings:read")),
):
    if kind not in ("quotation", "invoice"):
        raise AppError("kind must be 'quotation' or 'invoice'", 400)
    profile_row = db.scalar(select(Setting).where(Setting.key == "company_profile"))
    profile = profile_row.value if profile_row else {}
    logo_bytes = None
    if profile.get("logo_key"):
        try:
            logo_bytes = storage.read_file(profile["logo_key"])
        except Exception:
            logo_bytes = None
    pdf = document_pdf(kind, sample_document(kind), profile, payload.value, logo_bytes)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{kind}-preview.pdf"'})


# --- Email templates ---

# Merge fields available per template, Zoho-style: users insert these into the
# subject or body and they are filled from the record when the email is sent.
COMMON_TEMPLATE_VARIABLES = [
    {"key": "app_name", "label": "Application name", "sample": "WeTa CRM"},
]

TEMPLATE_VARIABLES: dict[str, list[dict]] = {
    "welcome": [
        {"key": "first_name", "label": "User · First name", "sample": "Priya"},
        {"key": "email", "label": "User · Email address", "sample": "priya@company.com"},
        {"key": "app_url", "label": "Application URL", "sample": app_config.public_app_url},
        {"key": "logo_html", "label": "Application logo (image)", "sample": ""},
    ],
    "password_reset": [
        {"key": "first_name", "label": "User · First name", "sample": "Priya"},
        {"key": "reset_link", "label": "Password reset link", "sample": f"{app_config.public_app_url}/reset-password?token=…"},
    ],
    "lead_assigned": [
        {"key": "first_name", "label": "Assignee · First name", "sample": "Ravi"},
        {"key": "lead_title", "label": "Lead · Title", "sample": "Acme ERP rollout"},
    ],
    "quotation": [
        {"key": "contact_name", "label": "Contact · Name", "sample": "Priya"},
        {"key": "number", "label": "Quotation · Number", "sample": "QT-2026-0042"},
        {"key": "total", "label": "Quotation · Total", "sample": "INR 1,18,000.00"},
        {"key": "company_name", "label": "Your company name", "sample": "WeTa Technologies"},
    ],
}


def _template_out(tpl: EmailTemplate, db: Session | None = None) -> dict:
    definition = workflows.trigger_or_none(tpl.trigger)

    # Merge fields come from the trigger when it has them: the trigger is what
    # decides which values exist at the moment the email is built, so a template
    # bound to one should offer that trigger's fields rather than a list keyed on
    # the template's name.
    if definition:
        variables = [
            {"key": f, "label": f.replace("_", " ").capitalize(), "sample": ""}
            for f in definition.merge_fields
        ]
    else:
        variables = TEMPLATE_VARIABLES.get(tpl.name, [])

    sent_count, last_sent_at = 0, None
    if db is not None and tpl.trigger:
        sent_count = db.scalar(
            select(func.count()).select_from(SentEmail).where(SentEmail.trigger == tpl.trigger)
        ) or 0
        last_sent_at = db.scalar(
            select(SentEmail.sent_at).where(SentEmail.trigger == tpl.trigger)
            .order_by(SentEmail.sent_at.desc()).limit(1)
        )

    return {
        "id": tpl.id,
        "name": tpl.name,
        "subject": tpl.subject,
        "body_html": tpl.body_html,
        "description": tpl.description,
        "updated_at": tpl.updated_at,
        "variables": variables + COMMON_TEMPLATE_VARIABLES,
        "trigger": tpl.trigger,
        "enabled": tpl.enabled,
        "config": tpl.config or {},
        "trigger_label": definition.label if definition else None,
        "trigger_description": definition.description if definition else None,
        "trigger_kind": definition.kind if definition else None,
        "audience": definition.audience if definition else None,
        "locked": definition.locked if definition else False,
        "locked_reason": definition.locked_reason if definition else "",
        "customer_facing": bool(definition and definition.key in workflows.CUSTOMER_FACING),
        "config_schema": definition.config_schema if definition else {},
        "sent_count": sent_count,
        "last_sent_at": last_sent_at,
    }


@router.get("/email-templates", response_model=list[EmailTemplateOut], dependencies=[Depends(require_perm("settings:read"))])
def list_email_templates(db: Session = Depends(get_db)):
    return [
        _template_out(t, db)
        for t in db.scalars(select(EmailTemplate).order_by(EmailTemplate.name)).all()
    ]


@router.get("/email-workflows", response_model=list[WorkflowTriggerOut],
            dependencies=[Depends(require_perm("settings:read"))])
def list_email_workflows(db: Session = Depends(get_db)):
    """Every moment an email can fire, and what is bound to it.

    Listed from the catalog rather than from the templates, so a trigger with no
    template is visible as a gap instead of being invisible — which is exactly how
    the renewal and birthday emails sat unsent.
    """
    bound = {t.trigger: t for t in db.scalars(select(EmailTemplate)).all() if t.trigger}
    return [
        {
            "key": d.key,
            "label": d.label,
            "description": d.description,
            "kind": d.kind,
            "audience": d.audience,
            "merge_fields": d.merge_fields,
            "locked": d.locked,
            "locked_reason": d.locked_reason,
            "customer_facing": d.key in workflows.CUSTOMER_FACING,
            "config_schema": d.config_schema,
            "template_id": bound[d.key].id if d.key in bound else None,
            "template_name": bound[d.key].name if d.key in bound else None,
            "enabled": bool(d.key in bound and bound[d.key].enabled),
        }
        for d in workflows.TRIGGERS
    ]


@router.patch("/email-templates/{template_id}", response_model=EmailTemplateOut)
def update_email_template(template_id: str, payload: EmailTemplateUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    tpl = get_or_404(db, EmailTemplate, template_id, "Email template")
    data = payload.model_dump(exclude_unset=True)

    if "trigger" in data and data["trigger"]:
        if data["trigger"] not in workflows.TRIGGERS_BY_KEY:
            raise AppError(f"Unknown trigger '{data['trigger']}'", 400)
        clash = db.scalar(
            select(EmailTemplate).where(
                EmailTemplate.trigger == data["trigger"], EmailTemplate.id != tpl.id
            )
        )
        if clash:
            # Two templates on one trigger means the email a customer receives
            # depends on which row the query reached first.
            raise AppError(
                f"'{clash.name}' is already the template for that trigger. "
                "Move it off first, or edit that one instead.",
                409,
            )

    definition = workflows.trigger_or_none(data.get("trigger", tpl.trigger))
    if definition and definition.locked and data.get("enabled") is False:
        raise AppError(definition.locked_reason, 400)

    if "config" in data:
        data["config"] = workflows.coerce_config(
            data.get("trigger", tpl.trigger) or "", data["config"]
        )

    for field, value in data.items():
        setattr(tpl, field, value)

    audit(db, user.id, "update", "email_template", tpl.id,
          {"name": tpl.name, "trigger": tpl.trigger, "enabled": tpl.enabled})
    db.commit()
    return _template_out(tpl, db)


# --- Tags ---

@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db), _: User = Depends(require_perm("settings:read"))):
    return db.scalars(select(Tag).order_by(Tag.name)).all()


@router.post("/tags", response_model=TagOut)
def create_tag(payload: TagCreate, db: Session = Depends(get_db), _: User = Depends(require_perm("settings:write"))):
    if db.scalar(select(Tag).where(Tag.name == payload.name)):
        raise AppError("Tag already exists", 409)
    tag = Tag(name=payload.name, color=payload.color)
    db.add(tag)
    db.commit()
    return tag


@router.patch("/tags/{tag_id}", response_model=TagOut)
def update_tag(tag_id: str, payload: TagUpdate, db: Session = Depends(get_db), _: User = Depends(require_perm("settings:write"))):
    tag = get_or_404(db, Tag, tag_id, "Tag")
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") and data["name"] != tag.name:
        if db.scalar(select(Tag).where(Tag.name == data["name"], Tag.id != tag.id)):
            raise AppError("Tag already exists", 409)
    for field, value in data.items():
        if value is not None:
            setattr(tag, field, value)
    db.commit()
    return tag


@router.delete("/tags/{tag_id}", response_model=Message)
def delete_tag(tag_id: str, db: Session = Depends(get_db), _: User = Depends(require_perm("settings:write"))):
    tag = get_or_404(db, Tag, tag_id, "Tag")
    db.delete(tag)
    db.commit()
    return {"detail": "Tag deleted"}
