import logging
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models_registry  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.database import seed
from app.database.base import Base
from app.database.session import SessionLocal, engine
from app.notifications.socket import capture_loop, sio

from app.activities.router import router as activities_router
from app.auth.router import router as auth_router
from app.companies.router import router as companies_router
from app.contacts.router import router as contacts_router
from app.deals.router import router as deals_router
from app.documents.router import router as documents_router
from app.invoices.router import router as invoices_router
from app.leads.router import router as leads_router
from app.meetings.router import router as meetings_router
from app.notifications.router import router as notifications_router
from app.products.router import router as products_router
from app.projects.router import router as projects_router
from app.quotations.router import router as quotations_router
from app.reports.router import router as reports_router
from app.search.router import router as search_router
from app.settings.router import router as settings_router
from app.support.router import router as support_router
from app.tasks.router import router as tasks_router
from app.users.router import router as users_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    capture_loop()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed.run(db)
    yield


app = FastAPI(
    title="WeTa CRM API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

API_V1 = "/api/v1"

app.include_router(auth_router, prefix=API_V1)
app.include_router(users_router, prefix=API_V1)
app.include_router(companies_router, prefix=API_V1)
app.include_router(contacts_router, prefix=API_V1)
app.include_router(leads_router, prefix=API_V1)
app.include_router(deals_router, prefix=API_V1)
app.include_router(activities_router, prefix=API_V1)
app.include_router(tasks_router, prefix=API_V1)
app.include_router(meetings_router, prefix=API_V1)
app.include_router(products_router, prefix=API_V1)
app.include_router(quotations_router, prefix=API_V1)
app.include_router(invoices_router, prefix=API_V1)
app.include_router(projects_router, prefix=API_V1)
app.include_router(support_router, prefix=API_V1)
app.include_router(documents_router, prefix=API_V1)
app.include_router(notifications_router, prefix=API_V1)
app.include_router(reports_router, prefix=API_V1)
app.include_router(search_router, prefix=API_V1)
app.include_router(settings_router, prefix=API_V1)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}


# Socket.IO wraps the FastAPI app: requests to /ws/socket.io are handled by the
# realtime server, everything else falls through to FastAPI. Run with
# `uvicorn app.main:asgi_app`.
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/ws/socket.io")
