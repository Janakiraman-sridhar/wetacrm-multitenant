# WeTa CRM

Enterprise-grade Customer Relationship Management platform — modular monolith **FastAPI** backend,
**React + TypeScript + Tailwind** frontend, deployed with **Docker Compose + Nginx** on a VPS.

Built from the specification in [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Features

- **Dashboard** — KPI cards, monthly revenue & lead-conversion charts, upcoming meetings, recent activity, top performers
- **Companies / Contacts / Leads / Deals** — full CRUD with search, sort, server-side pagination
- **Sales pipeline** — drag & drop Kanban across 7 stages; Won/Lost automatically close deals
- **Lead conversion** — one click turns a lead into a deal (+ company + contact records)
- **Tasks, Meetings & Calendar** — month calendar merging meetings, calls, follow-ups, reminders
- **Products, Quotations & Invoices** — line items with tax math, sequential numbering (QT-/INV-),
  PDF export, email sending, quote-to-invoice conversion, payment tracking
- **Projects** — milestones, team assignment; **Support** — prioritised tickets (TKT- numbers)
- **RBAC** — 9 seeded roles (Super Admin to Viewer) + custom roles with per-module read/write/delete
- **Real-time notifications** — Socket.IO pushes lead/task/ticket assignments, deal moves, meeting reminders
- **Global search** — Meilisearch (SQL fallback) across leads, companies, contacts, deals, tasks, projects
- **Activity timeline + audit log** on every entity; **email templates**; **light/dark theme**
- **Background jobs** — Celery + Redis: meeting reminders, overdue invoices, daily/weekly summaries, search reindex

## Repository layout

```
backend/    FastAPI modular monolith (app/<module>/{models,schemas,router}.py)
frontend/   React 18 + TypeScript + Tailwind (Vite)
docker/     Postgres init SQL, compose env template
nginx/      Edge reverse-proxy config (TLS notes included)
scripts/    Local dev launchers
docs/       Getting-started guide
```

## Quick start (local dev — zero external services)

The backend degrades gracefully: without Postgres/Redis/Meilisearch/MinIO/SMTP it uses
SQLite, inline jobs, SQL search, local-disk uploads, and console email. Nothing to install
beyond Python and Node.

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:asgi_app --port 8000 --reload
```

```bash
# frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in with the seeded Super Admin:
**admin@wetacrm.com / admin123** (change it immediately). API docs: http://localhost:8000/api/docs

## Production (VPS with Docker Compose)

```bash
cp docker/.env.example .env   # edit every "change-me" value
docker compose up -d --build
```

This starts Postgres (pgvector), Redis, Meilisearch, MinIO, the API, a Celery worker + beat,
the built frontend, and Nginx on port 80. For HTTPS, follow the Let's Encrypt notes at the top
of [nginx/nginx.conf](nginx/nginx.conf).

**Server already hosts another app on ports 80/443?** Use
[docs/DEPLOY_ALONGSIDE.md](docs/DEPLOY_ALONGSIDE.md) with `docker-compose.contabo.yml` —
the CRM runs with no host ports and the existing nginx routes a subdomain to it.

## Configuration

All backend settings are environment variables — see [backend/.env.example](backend/.env.example).
Optional integrations report their status in **Settings > System** inside the app.

| Service | When unset |
|---|---|
| `DATABASE_URL` | SQLite file (dev only) |
| `REDIS_URL` | Celery tasks run inline |
| `MEILI_URL` | SQL `ILIKE` search fallback |
| `MINIO_*` | Files stored under `backend/uploads/` |
| `SMTP_*` | Emails logged to console |

## Tests

`backend` has an end-to-end smoke suite exercised during development (auth, RBAC, CRM flows,
billing math, PDFs, reports, search, documents). Wire it into CI by running the API with
`fastapi.testclient.TestClient` against `app.main:app` (requires `httpx`) — see
`docs/GETTING_STARTED.md`.
