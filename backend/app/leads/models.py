from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel

LEAD_STATUSES = ["new", "contacted", "qualified", "unqualified", "converted"]


class LeadSource(BaseModel):
    __tablename__ = "lead_sources"

    name: Mapped[str] = mapped_column(String(100), unique=True)


class Lead(BaseModel):
    __tablename__ = "leads"

    title: Mapped[str] = mapped_column(String(255), index=True)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    company_name: Mapped[str | None] = mapped_column(String(255))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("lead_sources.id"))
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime)
    converted_deal_id: Mapped[str | None] = mapped_column(String(32))
    tags: Mapped[list] = mapped_column(JSON, default=list)

    source = relationship("LeadSource", lazy="joined")
    assigned_to = relationship("User", lazy="joined")
