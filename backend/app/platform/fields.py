"""Per-tenant field configuration — the model and the rules around it.

One table covers both jobs a client needs:

* **Custom fields** (`is_custom = True`) — a field this client invented. Its values
  live in the entity's `custom` JSON column, so adding one never changes the schema
  and one tenant's fields are invisible to every other.
* **Base field overrides** (`is_custom = False`) — relabelling, reordering or hiding
  a field the product already ships. The row carries only the difference from the default.

Keeping both in one table means the merged schema is a single query, and the field
editor is one list rather than two.
"""

from sqlalchemy import JSON, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel, TenantScoped


class FieldDef(TenantScoped, BaseModel):
    __tablename__ = "field_defs"

    __table_args__ = (
        UniqueConstraint("tenant_id", "module", "key", name="uq_field_defs_tenant_module_key"),
    )

    module: Mapped[str] = mapped_column(String(50), index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(120))
    field_type: Mapped[str] = mapped_column(String(30), default="text")
    options: Mapped[list] = mapped_column(JSON, default=list)  # [{value,label}] for select types
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    section: Mapped[str | None] = mapped_column(String(80))
    order: Mapped[int] = mapped_column(Integer, default=0)
    help_text: Mapped[str | None] = mapped_column(String(300))
    placeholder: Mapped[str | None] = mapped_column(String(150))
    default_value: Mapped[str | None] = mapped_column(Text)

    #: False = an override for a field the product ships; True = a field this tenant added.
    is_custom: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    #: Hiding is soft: `is_active = False` keeps the definition and any stored values
    #: so switching a field back on does not lose data.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    show_in_table: Mapped[bool] = mapped_column(Boolean, default=False)
    filterable: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Marks a field as holding personal data, so Phase 3 can encrypt and mask it.
    is_pii: Mapped[bool] = mapped_column(Boolean, default=False)
