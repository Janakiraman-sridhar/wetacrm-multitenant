from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped


class Contact(TenantScoped, BaseModel):
    __tablename__ = "contacts"

    first_name: Mapped[str] = mapped_column(String(100), index=True)
    last_name: Mapped[str] = mapped_column(String(100), default="", index=True)
    position: Mapped[str | None] = mapped_column(String(150))
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    emails: Mapped[list] = mapped_column(JSON, default=list)   # ["a@x.com", ...]
    phones: Mapped[list] = mapped_column(JSON, default=list)   # ["+91...", ...]
    social_links: Mapped[dict] = mapped_column(JSON, default=dict)  # {"linkedin": "..."}
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    company = relationship("Company", lazy="joined")
    owner = relationship("User", lazy="joined")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
