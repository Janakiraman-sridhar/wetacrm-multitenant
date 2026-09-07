from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped


class Company(TenantScoped, BaseModel):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), index=True)
    industry: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(255))
    gst_number: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    #: Values for this tenant's custom fields, keyed by field definition key.
    #: JSON rather than real columns so adding a field never touches the schema
    #: and one tenant's fields stay invisible to every other.
    custom: Mapped[dict] = mapped_column(JSON, default=dict)

    owner = relationship("User", lazy="joined")
