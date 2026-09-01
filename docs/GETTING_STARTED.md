# Getting Started — WeTa CRM

## 1. Local development

### Backend (FastAPI)

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux
.venv/Scripts/python -m uvicorn app.main:asgi_app --port 8000 --reload
```

- No `.env` needed for a first run: SQLite + seeded data + console email.
- Copy `backend/.env.example` to `backend/.env` to point at Postgres/Redis/etc.
- Swagger UI: http://localhost:8000/api/docs
- Tables are created automatically at startup (`Base.metadata.create_all`); Alembic is
  configured under `backend/migrations/` for versioned migrations once the schema stabilises:
  `alembic revision --autogenerate -m "..." && alembic upgrade head`
- `app.main:asgi_app` is the Socket.IO-wrapped entrypoint (realtime at `/ws/socket.io`);
  `app.main:app` is the bare FastAPI app, useful for `TestClient`.

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

`VITE_API_URL` defaults to `http://localhost:8000`. Set it in `frontend/.env` if the API runs
elsewhere; set it to an empty string when the API is same-origin behind a reverse proxy.

### First login

A Super Admin is seeded on first boot: `admin@wetacrm.com` / `admin123`
(overridable via `ADMIN_EMAIL` / `ADMIN_PASSWORD`). Change the password from the UI.

Windows shortcuts: `scripts\dev-backend.bat` and `scripts\dev-frontend.bat`.

## 2. Background jobs (optional in dev)

With `REDIS_URL` set:

```bash
cd backend
.venv/Scripts/celery -A app.automation.celery_app worker --loglevel=info
.venv/Scripts/celery -A app.automation.celery_app beat --loglevel=info
```

Without Redis, tasks execute inline so the app keeps working.

## 3. Seeded defaults

- **Roles:** Super Admin, Admin, Sales Manager, Sales Executive, Marketing, Support, Finance, HR, Viewer
- **Pipeline stages:** New, Contacted, Qualified, Proposal, Negotiation, Won, Lost
- **Lead sources:** Website, Referral, Exhibition, Cold Call, Social Media, Email Campaign, Advertisement, Other
- **Email templates:** welcome, password_reset, lead_assigned, quotation (editable in Settings)

## 4. Production deployment

```bash
cp docker/.env.example .env    # fill in secrets
docker compose up -d --build
```

Services: nginx (edge, :80/:443) fronting the static frontend and the API/WS backend, plus
Postgres (pgvector), Redis, Meilisearch, MinIO, Celery worker & beat. TLS via the certbot
profile — see the notes in `nginx/nginx.conf`.

## 5. Smoke testing

A TestClient-based end-to-end suite was used during development covering auth/refresh, RBAC,
CRM flows, lead-to-deal conversion, kanban moves, quotation totals & PDF, invoice payments,
projects, tickets, activities, audit logs, dashboards, search, documents and settings.
Recreate it against `app.main:app` with `fastapi.testclient` (requires `httpx`).
