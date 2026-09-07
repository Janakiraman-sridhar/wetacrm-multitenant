"""Imports every model module so SQLAlchemy's metadata knows all tables.

Imported by main.py (create_all) and by Alembic's env.py (autogenerate).
"""

from app.activities import models as activities_models  # noqa: F401
from app.companies import models as companies_models  # noqa: F401
from app.contacts import models as contacts_models  # noqa: F401  (Contact, Nominee, CustomerNote)
from app.deals import models as deals_models  # noqa: F401
from app.documents import models as documents_models  # noqa: F401
from app.invoices import models as invoices_models  # noqa: F401
from app.leads import models as leads_models  # noqa: F401
from app.loans import models as loans_models  # noqa: F401
from app.meetings import models as meetings_models  # noqa: F401
from app.notifications import models as notifications_models  # noqa: F401
from app.platform import fields as platform_fields  # noqa: F401
from app.policies import models as policies_models  # noqa: F401
from app.poster import models as poster_models  # noqa: F401
from app.platform import models as platform_models  # noqa: F401
from app.products import models as products_models  # noqa: F401
from app.projects import models as projects_models  # noqa: F401
from app.quotations import models as quotations_models  # noqa: F401
from app.settings import models as settings_models  # noqa: F401
from app.support import models as support_models  # noqa: F401
from app.tasks import models as tasks_models  # noqa: F401
from app.users import models as users_models  # noqa: F401


# --- composite indexes --------------------------------------------------------
#
# Declared here rather than in each model because they share one reason: in a
# shared-schema multi-tenant app every query starts with `tenant_id = ?`, so an
# index that does not lead with it cannot serve one. Keeping the list in a single
# place makes that reasoning visible, and makes it obvious when a new hot query
# has no index behind it.
#
# `migrations/versions/0010_tenant_composite_indexes.py` carries the same list —
# deliberately duplicated, because a migration that imports live app code stops
# describing the schema it actually produced. `test_indexes.py` asserts the two
# never drift.

from sqlalchemy import Index  # noqa: E402

from app.database.base import Base  # noqa: E402

TENANT_COMPOSITE_INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_policies_tenant_expiry", "policies", ["tenant_id", "expiry_date"]),
    ("ix_policies_tenant_status", "policies", ["tenant_id", "status"]),
    ("ix_policies_tenant_issue", "policies", ["tenant_id", "issue_date"]),
    ("ix_contacts_tenant_birthday", "contacts", ["tenant_id", "birthday_key"]),
    ("ix_loans_tenant_status", "loans", ["tenant_id", "status"]),
    ("ix_loans_tenant_disbursed", "loans", ["tenant_id", "disbursed_on"]),
    ("ix_tasks_tenant_status_due", "tasks", ["tenant_id", "status", "due_date"]),
    ("ix_deals_tenant_stage", "deals", ["tenant_id", "stage_id"]),
    ("ix_invoices_tenant_status", "invoices", ["tenant_id", "status"]),
    ("ix_quotations_tenant_status", "quotations", ["tenant_id", "status"]),
    ("ix_activities_tenant_entity", "activities", ["tenant_id", "entity_type", "entity_id"]),
    ("ix_documents_tenant_entity", "documents", ["tenant_id", "entity_type", "entity_id"]),
]

for _name, _table_name, _columns in TENANT_COMPOSITE_INDEXES:
    _table = Base.metadata.tables[_table_name]
    if not any(ix.name == _name for ix in _table.indexes):
        Index(_name, *[_table.c[c] for c in _columns])
