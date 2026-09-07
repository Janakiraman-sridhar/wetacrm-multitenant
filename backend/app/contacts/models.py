from datetime import date

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.contacts.customer_fields import CustomerFieldsMixin
from app.database.base import BaseModel, TenantScoped


class Contact(CustomerFieldsMixin, TenantScoped, BaseModel):
    """A person the tenant deals with.

    An insurance tenant calls this a Customer and uses the fields from
    `CustomerFieldsMixin`; a general CRM tenant sees a plain contact and those
    columns stay null. Same table either way — a separate customer table would fork
    every relationship, filter, export and search path for no gain.
    """

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
    #: Values for this tenant's custom fields, keyed by field definition key.
    #: JSON rather than real columns so adding a field never touches the schema
    #: and one tenant's fields stay invisible to every other.
    custom: Mapped[dict] = mapped_column(JSON, default=dict)

    company = relationship("Company", lazy="joined")
    owner = relationship("User", lazy="joined")
    referred_by = relationship(
        "Contact", remote_side="Contact.id", foreign_keys="Contact.referred_by_contact_id", lazy="joined"
    )
    nominees: Mapped[list["Nominee"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan", lazy="selectin",
        order_by="Nominee.position",
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def primary_phone(self) -> str | None:
        """The number to call or message — the customer mobile, else the first phone."""
        if self.mobile:
            return self.mobile
        return (self.phones or [None])[0]

    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class Nominee(TenantScoped, BaseModel):
    """Who receives the benefit. Held per customer and copied onto a policy.

    Shares are validated to total 100 across a customer's nominees, and a minor
    nominee needs an appointee — both things an insurer rejects a proposal over.
    """

    __tablename__ = "nominees"

    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    #: Set when a policy carries its own nominee rather than the customer default.
    policy_id: Mapped[str | None] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    relation: Mapped[str | None] = mapped_column(String(50))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    age: Mapped[int | None] = mapped_column(Integer)
    share_percent: Mapped[int] = mapped_column(Integer, default=100)
    appointee_name: Mapped[str | None] = mapped_column(String(200))
    appointee_relation: Mapped[str | None] = mapped_column(String(50))
    position: Mapped[int] = mapped_column(Integer, default=0)

    contact: Mapped[Contact] = relationship(back_populates="nominees")

    @property
    def is_minor(self) -> bool:
        return self.age is not None and self.age < 18


class CustomerNote(TenantScoped, BaseModel):
    """A dated note on a customer.

    Separate from `Contact.notes` (a single free-text box) because an agent
    accumulates many over years and needs to know who wrote each one and when.
    """

    __tablename__ = "customer_notes"

    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    author = relationship("User", lazy="joined")
