from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped

#: What a poster is for. Drives which audience the batch screen offers and which
#: merge fields are available.
POSTER_CATEGORIES = ["birthday", "renewal", "issued", "festival", "promo", "claim", "general"]

#: 1080-square for a WhatsApp/feed post, 1080x1920 for a status/story.
POSTER_SIZES = {
    "square": (1080, 1080),
    "story": (1080, 1920),
    "landscape": (1200, 675),
}


class PosterTemplate(TenantScoped, BaseModel):
    """A poster design, held as an ordered list of layers.

    The layer spec is the single source of truth: the same JSON is rendered by
    `app.poster.render` for the editor preview, the batch output and anything sent
    over WhatsApp. One renderer means what an agent designs is exactly what a
    customer receives — a separate client-side preview would drift the first time a
    font fell back.
    """

    __tablename__ = "poster_templates"

    name: Mapped[str] = mapped_column(String(150), index=True)
    category: Mapped[str] = mapped_column(String(30), default="general", index=True)
    size: Mapped[str] = mapped_column(String(20), default="square")
    #: [{type: text|image|rect, ...}] — see `app.poster.render.LAYER_SPEC`.
    layers: Mapped[list] = mapped_column(JSON, default=list)
    background: Mapped[dict] = mapped_column(JSON, default=dict)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    order: Mapped[int] = mapped_column(Integer, default=0)


class PosterAsset(TenantScoped, BaseModel):
    """An image this workspace uploaded to put on its posters.

    Kept as a row rather than a bare storage key so an agent picks a picture from a
    library they recognise instead of pasting a path, and so a picture still in use
    can be found again. The layer spec refers to an asset by **id** in its `source`,
    which is why nothing about the renderer had to change to support it.

    Only raster images get in, and the type is decided by the bytes: `image/svg+xml`
    is a document that can run script, so it is refused rather than stored and later
    served back to the workspace.
    """

    __tablename__ = "poster_assets"

    name: Mapped[str] = mapped_column(String(200), index=True)
    file_key: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100), default="image/png")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    uploaded_by = relationship("User", lazy="joined")


class PosterBatch(TenantScoped, BaseModel):
    """One run of personalised posters — who they were for, and what came out.

    Kept so an agent can come back to a batch they generated this morning rather
    than regenerating it, and so a send can be traced to the design it used.
    """

    __tablename__ = "poster_batches"

    template_id: Mapped[str | None] = mapped_column(ForeignKey("poster_templates.id"))
    name: Mapped[str] = mapped_column(String(200))
    audience: Mapped[str] = mapped_column(String(40))  # birthdays|renewals|selection
    audience_params: Mapped[dict] = mapped_column(JSON, default=dict)
    #: [{contact_id, name, file_key, phone}] — one entry per recipient.
    items: Mapped[list] = mapped_column(JSON, default=list)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    template = relationship("PosterTemplate", lazy="joined")
    created_by = relationship("User", lazy="joined")


class WhatsAppMessage(TenantScoped, BaseModel):
    """A message this workspace sent, or tried to.

    Written for click-to-chat too, not only API sends: an agent needs to know a
    customer was already wished a happy birthday this morning, however it went out.
    """

    __tablename__ = "whatsapp_messages"

    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    policy_id: Mapped[str | None] = mapped_column(String(32), index=True)
    to_number: Mapped[str] = mapped_column(String(20), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="text")  # text|template|media
    #: click_to_chat when the agent sent it from their own WhatsApp; otherwise the
    #: provider that carried it.
    channel: Mapped[str] = mapped_column(String(30), default="click_to_chat", index=True)
    body: Mapped[str | None] = mapped_column(Text)
    media_key: Mapped[str | None] = mapped_column(String(500))
    template_name: Mapped[str | None] = mapped_column(String(100))
    provider_message_id: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    sent_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    contact = relationship("Contact", lazy="joined")
    sent_by = relationship("User", lazy="joined")
