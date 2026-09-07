from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped

TICKET_PRIORITIES = ["low", "medium", "high", "urgent"]
TICKET_STATUSES = ["open", "in_progress", "resolved", "closed"]


class Ticket(TenantScoped, BaseModel):
    __tablename__ = "tickets"

    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_tickets_tenant_number"),)

    number: Mapped[str] = mapped_column(String(50), index=True)
    subject: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    priority: Mapped[str] = mapped_column(String(10), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolution: Mapped[str | None] = mapped_column(Text)

    company = relationship("Company", lazy="joined")
    contact = relationship("Contact", lazy="joined")
    assigned_to = relationship("User", lazy="joined")
