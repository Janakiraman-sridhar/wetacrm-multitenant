from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.config import settings as app_config
from app.core.crud import get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.schemas import Message
from app.database.session import get_db
from app.settings.models import EmailTemplate, Setting, Tag
from app.settings.schemas import (
    EmailTemplateOut, EmailTemplateUpdate, SettingOut, SettingUpdate, TagCreate, TagOut,
)
from app.users.models import User

router = APIRouter(prefix="/settings", tags=["settings"])

EDITABLE_KEYS = {"company_profile", "branding", "notification_settings"}


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


# --- Email templates ---

@router.get("/email-templates", response_model=list[EmailTemplateOut], dependencies=[Depends(require_perm("settings:read"))])
def list_email_templates(db: Session = Depends(get_db)):
    return db.scalars(select(EmailTemplate).order_by(EmailTemplate.name)).all()


@router.patch("/email-templates/{template_id}", response_model=EmailTemplateOut)
def update_email_template(template_id: str, payload: EmailTemplateUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    tpl = get_or_404(db, EmailTemplate, template_id, "Email template")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tpl, field, value)
    audit(db, user.id, "update", "email_template", tpl.id, {"name": tpl.name})
    db.commit()
    return tpl


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


@router.delete("/tags/{tag_id}", response_model=Message)
def delete_tag(tag_id: str, db: Session = Depends(get_db), _: User = Depends(require_perm("settings:write"))):
    tag = get_or_404(db, Tag, tag_id, "Tag")
    db.delete(tag)
    db.commit()
    return {"detail": "Tag deleted"}
