"""Test fixtures: a throwaway database holding two fully-populated tenants.

Every isolation test works the same way — act as Tenant A, try to reach something
that belongs to Tenant B, and assert you cannot. For that to mean anything, both
tenants must hold data of *every* kind, which is what `seeded_world` builds.
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

# Point the app at a scratch database before anything imports settings.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="weta-tests-"))
_DB_PATH = _TMP_DIR / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["UPLOAD_DIR"] = str(_TMP_DIR / "uploads")
os.environ["AUTO_MIGRATE"] = "false"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["MEILI_URL"] = ""
os.environ["SMTP_HOST"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import models_registry  # noqa: E402,F401
from app.companies.models import Company  # noqa: E402
from app.contacts.models import Contact  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.tenancy import platform_scope, tenant_scope  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import SessionLocal, engine  # noqa: E402
from app.deals.models import Deal, DealStage  # noqa: E402
from app.documents.models import Document  # noqa: E402
from app.invoices.models import Invoice  # noqa: E402
from app.leads.models import Lead, LeadSource  # noqa: E402
from app.main import app  # noqa: E402
from app.meetings.models import CalendarEvent, Meeting  # noqa: E402
from app.notifications.models import Notification  # noqa: E402
from app.platform import provisioning  # noqa: E402
from app.platform.models import Tenant  # noqa: E402
from app.products.models import Product  # noqa: E402
from app.projects.models import Project  # noqa: E402
from app.quotations.models import Quotation  # noqa: E402
from app.services import crypto  # noqa: E402
from app.settings.models import EmailTemplate, Setting, Tag  # noqa: E402
from app.support.models import Ticket  # noqa: E402
from app.tasks.models import Task  # noqa: E402
from app.users.models import Role, User  # noqa: E402

PASSWORD = "test-password-123"


class TenantWorld:
    """Everything one tenant owns, so a test can name a row it should not be able to reach."""

    def __init__(self, key: str):
        self.key = key
        self.tenant_id: str = ""
        self.admin_email = f"admin-{key}@example.com"
        self.token: str = ""
        self.ids: dict[str, str] = {}

    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def _build_tenant(db, key: str) -> TenantWorld:
    world = TenantWorld(key)
    tenant = Tenant(
        id=uuid.uuid4().hex,
        name=f"Tenant {key.upper()}",
        slug=key,
        status="active",
        template_key="general_crm",
        # Its own data-encryption key, exactly as real provisioning mints one.
        dek_encrypted=crypto.wrap_dek(crypto.generate_dek()),
    )
    with platform_scope():
        db.add(tenant)
        db.flush()
    world.tenant_id = tenant.id

    with tenant_scope(tenant.id):
        # Build the workspace the way provisioning really does, so fixtures exercise
        # the template path rather than a hand-rolled approximation of it.
        provisioning.apply_template(db, tenant.id, provisioning.get_template(db, "general_crm"))
        db.flush()

        role = db.scalar(select(Role).where(Role.name == "Super Admin"))
        stage = db.scalar(select(DealStage).order_by(DealStage.order))
        source = db.scalar(select(LeadSource).order_by(LeadSource.name))

        admin = User(
            email=world.admin_email,
            password_hash=hash_password(PASSWORD),
            first_name=key.upper(),
            last_name="Admin",
            role_id=role.id,
        )
        db.add(admin)

        company = Company(name=f"{key}-corp", industry="Insurance", city="Chennai")
        db.add(company)
        db.flush()

        contact = Contact(first_name=key, last_name="Contact", company_id=company.id,
                          emails=[f"{key}@corp.test"], phones=["+919000000000"])
        product = Product(name=f"{key}-product", sku=f"SKU-{key.upper()}", unit_price=100)
        db.add_all([contact, product])
        db.flush()

        deal = Deal(title=f"{key}-deal", stage_id=stage.id, value=5000, company_id=company.id)
        lead = Lead(title=f"{key}-lead", source_id=source.id, contact_name=f"{key} lead")
        task = Task(title=f"{key}-task", assigned_to_id=admin.id)
        meeting = Meeting(title=f"{key}-meeting", starts_at=__import__("datetime").datetime(2026, 1, 1, 10, 0))
        event = CalendarEvent(title=f"{key}-event", starts_at=__import__("datetime").datetime(2026, 1, 2, 10, 0))
        project = Project(name=f"{key}-project", company_id=company.id)
        ticket = Ticket(number=f"TKT-{key.upper()}-0001", subject=f"{key}-ticket", company_id=company.id)
        quotation = Quotation(number=f"QT-{key.upper()}-0001", company_id=company.id, total=1000)
        invoice = Invoice(number=f"INV-{key.upper()}-0001", company_id=company.id, total=1000)
        document = Document(name=f"{key}-doc.pdf", file_key=f"tenants/{tenant.id}/abc/{key}-doc.pdf",
                            mime_type="application/pdf", size_bytes=10)
        notification = Notification(user_id=admin.id, type="system", title=f"{key}-notification")
        tag = Tag(name=f"{key}-tag")
        db.add_all([deal, lead, task, meeting, event, project, ticket, quotation,
                    invoice, document, notification, tag])
        db.flush()

        branding = db.scalar(select(Setting).where(Setting.key == "branding"))
        branding.value = {**(branding.value or {}), "app_name": f"{key.upper()} CRM"}

        world.ids = {
            "company": company.id, "contact": contact.id, "lead": lead.id, "deal": deal.id,
            "task": task.id, "meeting": meeting.id, "calendar_event": event.id,
            "project": project.id, "ticket": ticket.id, "quotation": quotation.id,
            "invoice": invoice.id, "document": document.id, "product": product.id,
            "user": admin.id, "role": role.id, "stage": stage.id, "source": source.id,
            "notification": notification.id, "tag": tag.id,
        }
        db.commit()
    return world


@pytest.fixture(scope="session")
def client() -> TestClient:
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def worlds(client) -> dict[str, TenantWorld]:
    """Two tenants, each with a row of every type, and a signed-in admin token."""
    Base.metadata.create_all(engine)
    built: dict[str, TenantWorld] = {}
    with SessionLocal() as db:
        for key in ("alpha", "bravo"):
            built[key] = _build_tenant(db, key)

    for world in built.values():
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": world.admin_email, "password": PASSWORD},
        )
        assert resp.status_code == 200, resp.text
        world.token = resp.json()["access_token"]
    return built


@pytest.fixture()
def alpha(worlds) -> TenantWorld:
    return worlds["alpha"]


@pytest.fixture()
def bravo(worlds) -> TenantWorld:
    return worlds["bravo"]


@pytest.fixture(scope="session")
def platform_admin_token(client) -> str:
    """Signed in once per session — the login endpoint is rate limited."""
    from app.core.config import settings
    from app.platform import service

    with SessionLocal() as db:
        service.ensure_platform_admin(db)
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.platform_admin_email,
            "password": settings.platform_admin_password,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]
