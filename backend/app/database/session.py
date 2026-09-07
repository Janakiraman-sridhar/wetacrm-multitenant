from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Importing this registers the session-level events that enforce tenant
# isolation. It lives here so *any* code path that opens a session gets them,
# rather than depending on main.py import order.
from app.core import tenancy  # noqa: E402,F401  (import for side effects)

# Validates per-tenant custom field values on flush. Registered here for the
# same reason as the tenant filter: every session must get it.
from app.platform.schema_service import register_custom_field_validation  # noqa: E402

register_custom_field_validation()
