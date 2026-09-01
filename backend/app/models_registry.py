"""Imports every model module so SQLAlchemy's metadata knows all tables.

Imported by main.py (create_all) and by Alembic's env.py (autogenerate).
"""

from app.activities import models as activities_models  # noqa: F401
from app.companies import models as companies_models  # noqa: F401
from app.contacts import models as contacts_models  # noqa: F401
from app.deals import models as deals_models  # noqa: F401
from app.documents import models as documents_models  # noqa: F401
from app.invoices import models as invoices_models  # noqa: F401
from app.leads import models as leads_models  # noqa: F401
from app.meetings import models as meetings_models  # noqa: F401
from app.notifications import models as notifications_models  # noqa: F401
from app.products import models as products_models  # noqa: F401
from app.projects import models as projects_models  # noqa: F401
from app.quotations import models as quotations_models  # noqa: F401
from app.settings import models as settings_models  # noqa: F401
from app.support import models as support_models  # noqa: F401
from app.tasks import models as tasks_models  # noqa: F401
from app.users import models as users_models  # noqa: F401
