"""Poster Studio and WhatsApp sending."""

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.contacts.models import Contact
from app.core.crud import apply_updates, get_or_404
from app.core.deps import get_current_user, require_module, require_perm
from app.core.exceptions import AppError
from app.core.schemas import Message, ORMModel
from app.database.session import get_db
from app.poster import render as poster_render
from app.poster import service
from app.poster.models import POSTER_CATEGORIES, POSTER_SIZES, PosterBatch, PosterTemplate, WhatsAppMessage
from app.poster.presets import MERGE_FIELDS
from app.services import storage, whatsapp
from app.users.models import User

router = APIRouter(tags=["poster"], dependencies=[Depends(require_module("poster"))])


# --- schemas ------------------------------------------------------------------

class PosterTemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category: str = "general"
    size: str = "square"
    layers: list[dict] = []
    background: dict = {}
    order: int = 0


class PosterTemplateUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    size: str | None = None
    layers: list[dict] | None = None
    background: dict | None = None
    is_active: bool | None = None
    order: int | None = None


class PosterTemplateOut(ORMModel):
    id: str
    name: str
    category: str
    size: str
    layers: list[dict] = []
    background: dict = {}
    is_active: bool = True
    order: int = 0


class PreviewIn(BaseModel):
    """Render an unsaved design, so the editor shows exactly what will be sent."""

    size: str = "square"
    layers: list[dict] = []
    background: dict = {}
    contact_id: str | None = None


class BatchIn(BaseModel):
    template_id: str
    audience: str = Field(pattern="^(birthdays|renewals|selection)$")
    within_days: int = 7
    contact_ids: list[str] = []
    name: str | None = None


class SendIn(BaseModel):
    contact_id: str
    message: str = Field(min_length=1, max_length=4000)
    poster_key: str | None = None
    policy_id: str | None = None


class LogClickIn(BaseModel):
    """Record that an agent opened a click-to-chat link.

    Nothing left the server, but the workspace still needs to know a customer was
    already messaged today — otherwise three agents wish the same person a happy
    birthday.
    """

    contact_id: str
    message: str | None = None
    policy_id: str | None = None


# --- templates ----------------------------------------------------------------

@router.get("/poster/templates", response_model=list[PosterTemplateOut],
            dependencies=[Depends(require_perm("contacts:read"))])
def list_templates(category: str | None = None, db: Session = Depends(get_db)):
    stmt = select(PosterTemplate).where(PosterTemplate.is_active.is_(True)).order_by(
        PosterTemplate.order, PosterTemplate.name
    )
    if category:
        stmt = stmt.where(PosterTemplate.category == category)
    return db.scalars(stmt).all()


@router.get("/poster/merge-fields", dependencies=[Depends(require_perm("contacts:read"))])
def merge_fields(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Which `{placeholders}` a design can use, with the values a preview shows."""
    return {
        "fields": list(MERGE_FIELDS),
        "sample": service.sample_values(db, user),
        "sizes": {name: {"width": w, "height": h} for name, (w, h) in POSTER_SIZES.items()},
        "categories": POSTER_CATEGORIES,
    }


@router.post("/poster/templates", response_model=PosterTemplateOut)
def create_template(
    payload: PosterTemplateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("contacts:write")),
):
    if payload.size not in POSTER_SIZES:
        raise AppError(f"Size must be one of: {', '.join(POSTER_SIZES)}")
    template = PosterTemplate(**payload.model_dump())
    db.add(template)
    db.commit()
    return template


@router.patch("/poster/templates/{template_id}", response_model=PosterTemplateOut)
def update_template(
    template_id: str,
    payload: PosterTemplateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("contacts:write")),
):
    template = get_or_404(db, PosterTemplate, template_id, "Poster template")
    apply_updates(template, payload.model_dump(exclude_unset=True))
    db.commit()
    return template


@router.delete("/poster/templates/{template_id}", response_model=Message)
def delete_template(
    template_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("contacts:write"))
):
    template = get_or_404(db, PosterTemplate, template_id, "Poster template")
    db.delete(template)
    db.commit()
    return {"detail": "Template deleted"}


@router.post("/poster/seed-presets", response_model=Message)
def seed_presets(db: Session = Depends(get_db), user: User = Depends(require_perm("contacts:write"))):
    """Restore the starter designs, for a workspace that deleted them."""
    created = service.seed_presets(db)
    db.commit()
    return {"detail": f"{created} preset(s) added"}


# --- rendering ----------------------------------------------------------------

def _render(db: Session, spec: dict, values: dict) -> bytes:
    return poster_render.render(spec, values, service.load_assets(db, spec))


@router.post("/poster/preview", dependencies=[Depends(require_perm("contacts:read"))])
def preview(payload: PreviewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Render an unsaved design as PNG.

    The editor previews through the same renderer that produces the final file, so
    what an agent sees is what the customer receives — a separate client-side
    preview would drift the first time a font fell back or a line wrapped.
    """
    values = service.sample_values(db, user)
    if payload.contact_id:
        contact = db.get(Contact, payload.contact_id)
        if contact:
            values.update(service.customer_values(contact))

    spec = {"size": payload.size, "layers": payload.layers, "background": payload.background}
    return Response(content=_render(db, spec, values), media_type="image/png")


@router.get("/poster/templates/{template_id}/preview",
            dependencies=[Depends(require_perm("contacts:read"))])
def preview_template(
    template_id: str,
    contact_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    template = get_or_404(db, PosterTemplate, template_id, "Poster template")
    values = service.sample_values(db, user)
    if contact_id:
        contact = db.get(Contact, contact_id)
        if contact:
            values.update(service.customer_values(contact))
    spec = {"size": template.size, "layers": template.layers, "background": template.background}
    return Response(content=_render(db, spec, values), media_type="image/png")


# --- batches ------------------------------------------------------------------

@router.get("/poster/audience", dependencies=[Depends(require_perm("contacts:read"))])
def audience(
    kind: str = Query(pattern="^(birthdays|renewals)$"),
    within_days: int = Query(7, ge=0, le=365),
    db: Session = Depends(get_db),
):
    """Who a batch would go to, before generating anything."""
    people = service.resolve_audience(db, kind, {"within_days": within_days})
    return [
        {"contact_id": p["contact_id"], "name": p["name"], "phone": p["phone"]}
        for p in people
    ]


@router.post("/poster/batches")
def create_batch(
    payload: BatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("contacts:write")),
):
    """Render one personalised poster per recipient and store them.

    Done inline rather than queued: a realistic batch is tens of posters, and an
    agent watching the screen would rather wait three seconds than poll a job.
    """
    template = get_or_404(db, PosterTemplate, payload.template_id, "Poster template")
    people = service.resolve_audience(
        db, payload.audience,
        {"within_days": payload.within_days, "contact_ids": payload.contact_ids},
    )
    if not people:
        raise AppError("No one matches that audience", 400)
    if len(people) > 200:
        raise AppError(f"That is {len(people)} recipients — narrow the audience to 200 or fewer", 400)

    spec = {"size": template.size, "layers": template.layers, "background": template.background}
    assets = service.load_assets(db, spec)
    agency = service.agency_values(db, user)

    items = []
    for person in people:
        values = {**agency, **person["values"]}
        try:
            png = poster_render.render(spec, values, assets)
            key = storage.save_file(png, f"poster-{person['contact_id']}.png", "image/png")
            items.append({
                "contact_id": person["contact_id"],
                "policy_id": person.get("policy_id"),
                "name": person["name"],
                "phone": person["phone"],
                "file_key": key,
            })
        except Exception:
            items.append({
                "contact_id": person["contact_id"], "name": person["name"],
                "phone": person["phone"], "error": "Could not be rendered",
            })

    batch = PosterBatch(
        template_id=template.id,
        name=payload.name or f"{template.name} — {len(items)} recipients",
        audience=payload.audience,
        audience_params={"within_days": payload.within_days, "contact_ids": payload.contact_ids},
        items=items,
        created_by_id=user.id,
    )
    db.add(batch)
    audit(db, user.id, "create", "poster_batch", batch.id,
          {"template": template.name, "recipients": len(items)})
    db.commit()
    return {"id": batch.id, "name": batch.name, "items": items}


@router.get("/poster/batches", dependencies=[Depends(require_perm("contacts:read"))])
def list_batches(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(PosterBatch).order_by(PosterBatch.created_at.desc()).limit(50)
    ).all()
    return [
        {
            "id": b.id, "name": b.name, "audience": b.audience,
            "count": len(b.items or []), "created_at": b.created_at,
            "template": b.template.name if b.template else None,
            "created_by": b.created_by.full_name if b.created_by else None,
        }
        for b in rows
    ]


@router.get("/poster/batches/{batch_id}", dependencies=[Depends(require_perm("contacts:read"))])
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = get_or_404(db, PosterBatch, batch_id, "Batch")
    return {"id": batch.id, "name": batch.name, "audience": batch.audience,
            "items": batch.items, "created_at": batch.created_at}


@router.get("/poster/file", dependencies=[Depends(require_perm("contacts:read"))])
def poster_file(key: str):
    """Serve a generated poster.

    `storage.read_file` verifies the key belongs to the caller's tenant, so a
    guessed key from another workspace is refused rather than served.
    """
    try:
        data = storage.read_file(key)
    except storage.StorageAccessDenied:
        raise AppError("Not found", 404)
    except FileNotFoundError:
        raise AppError("Not found", 404)
    return Response(content=data, media_type="image/png")


# --- whatsapp -----------------------------------------------------------------

@router.get("/whatsapp/status", dependencies=[Depends(require_perm("contacts:read"))])
def whatsapp_status(db: Session = Depends(get_db)):
    """Which channel this workspace has: click-to-chat, or the API as well."""
    provider = whatsapp.provider_for(db)
    return {
        "provider": provider.name,
        "can_send_from_server": provider.can_send,
        "click_to_chat": True,
        "note": (
            "Messages are sent from the agent's own WhatsApp."
            if not provider.can_send
            else "Messages can be sent from the server."
        ),
    }


@router.post("/whatsapp/link", dependencies=[Depends(require_perm("contacts:read"))])
def build_link(payload: LogClickIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """A `wa.me` link, and a record that the agent opened it."""
    contact = get_or_404(db, Contact, payload.contact_id, "Customer")
    phone = contact.primary_phone
    link = whatsapp.click_to_chat_link(phone, payload.message)
    if not link:
        raise AppError("This customer has no usable mobile number", 400)

    db.add(WhatsAppMessage(
        contact_id=contact.id, policy_id=payload.policy_id,
        to_number=whatsapp.normalise_number(phone) or "",
        kind="text", channel="click_to_chat", body=payload.message,
        status="opened", sent_by_id=user.id,
    ))
    log_activity(db, "contact", contact.id, "note", "WhatsApp message opened",
                 body=(payload.message or "")[:400], user_id=user.id)
    db.commit()
    return {"link": link, "phone": phone}


@router.post("/whatsapp/send")
def send_message(
    payload: SendIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("contacts:write")),
):
    """Send from the server. Needs the Cloud API configured for this workspace.

    Refused rather than silently downgraded when it is not — a caller must never be
    told a message was sent when nothing left the building.
    """
    contact = get_or_404(db, Contact, payload.contact_id, "Customer")
    number = whatsapp.normalise_number(contact.primary_phone)
    if not number:
        raise AppError("This customer has no usable mobile number", 400)

    provider = whatsapp.provider_for(db)
    record = WhatsAppMessage(
        contact_id=contact.id, policy_id=payload.policy_id, to_number=number,
        kind="media" if payload.poster_key else "text", channel=provider.name,
        body=payload.message, media_key=payload.poster_key,
        status="queued", sent_by_id=user.id,
    )
    db.add(record)
    db.flush()

    if not provider.can_send:
        record.status = "failed"
        record.error = "WhatsApp API is not configured for this workspace"
        db.commit()
        raise AppError(
            "WhatsApp API is not set up for this workspace. Use the click-to-chat link, "
            "or configure it in Settings.",
            400,
        )

    if payload.poster_key:
        result = provider.send_media(number, storage.read_file(payload.poster_key),
                                     "poster.png", payload.message)
    else:
        result = provider.send_text(number, payload.message)

    record.status = "sent" if result.ok else "failed"
    record.provider_message_id = result.provider_message_id
    record.error = result.error
    if result.ok:
        log_activity(db, "contact", contact.id, "note", "WhatsApp message sent",
                     body=payload.message[:400], user_id=user.id)
    db.commit()

    if not result.ok:
        raise AppError(result.error or "The message could not be sent", 502)
    return {"status": record.status, "message_id": record.provider_message_id}


@router.get("/whatsapp/messages", dependencies=[Depends(require_perm("contacts:read"))])
def list_messages(contact_id: str | None = None, limit: int = Query(50, ge=1, le=200),
                  db: Session = Depends(get_db)):
    stmt = select(WhatsAppMessage).order_by(WhatsAppMessage.created_at.desc()).limit(limit)
    if contact_id:
        stmt = stmt.where(WhatsAppMessage.contact_id == contact_id)
    return [
        {
            "id": m.id, "to_number": m.to_number, "channel": m.channel, "status": m.status,
            "body": m.body, "error": m.error, "created_at": m.created_at,
            "contact": m.contact.full_name if m.contact else None,
            "sent_by": m.sent_by.full_name if m.sent_by else None,
        }
        for m in db.scalars(stmt).all()
    ]
