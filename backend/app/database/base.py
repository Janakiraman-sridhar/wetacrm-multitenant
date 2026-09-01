import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class BaseModel(Base):
    """Common columns for every business table.

    UUIDs are stored as 32-char hex strings so the schema is portable between
    PostgreSQL (production) and SQLite (zero-setup local dev).
    """

    __abstract__ = True

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
