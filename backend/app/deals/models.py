from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped

DEFAULT_STAGES = [
    # (name, order, probability, is_won, is_lost)
    ("New", 1, 10, False, False),
    ("Contacted", 2, 25, False, False),
    ("Qualified", 3, 45, False, False),
    ("Proposal", 4, 65, False, False),
    ("Negotiation", 5, 80, False, False),
    ("Won", 6, 100, True, False),
    ("Lost", 7, 0, False, True),
]


class DealStage(TenantScoped, BaseModel):
    __tablename__ = "deal_stages"

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_deal_stages_tenant_name"),)

    name: Mapped[str] = mapped_column(String(100), index=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    probability: Mapped[int] = mapped_column(Integer, default=0)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False)


class Deal(TenantScoped, BaseModel):
    __tablename__ = "deals"

    title: Mapped[str] = mapped_column(String(255), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    probability: Mapped[int] = mapped_column(Integer, default=10)
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    stage_id: Mapped[str] = mapped_column(ForeignKey("deal_stages.id"), index=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    competitors: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)  # open|won|lost
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    tags: Mapped[list] = mapped_column(JSON, default=list)

    stage = relationship("DealStage", lazy="joined")
    company = relationship("Company", lazy="joined")
    contact = relationship("Contact", lazy="joined")
    owner = relationship("User", lazy="joined")
