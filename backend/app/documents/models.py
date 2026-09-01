from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel


class Document(BaseModel):
    __tablename__ = "documents"

    name: Mapped[str] = mapped_column(String(255), index=True)
    file_key: Mapped[str] = mapped_column(String(500))  # object key in MinIO / relative path locally
    mime_type: Mapped[str | None] = mapped_column(String(150))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    entity_type: Mapped[str | None] = mapped_column(String(50), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(32), index=True)
    uploaded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    uploaded_by = relationship("User", lazy="joined")
