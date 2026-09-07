# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository location

The git repository root is the **nested** `WeTa CRM/WeTa CRM/` directory (the outer folder is just a
download wrapper). All paths below are relative to that repo root.

## Commands

```bash
# Backend (FastAPI) — no .env needed for a first run
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt      # Windows
.venv/Scripts/python -m uvicorn app.main:asgi_app --port 8000 --reload
```

```bash
# Frontend (Vite)
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc -b && vite build — this is also the only typecheck/lint gate
```

Other commands:

- Celery (only with `REDIS_URL` set; otherwise tasks run eagerly in-process):
  `celery -A app.automation.celery_app worker --loglevel=info` and `... beat --loglevel=info`
- Alembic: see **Schema changes** below — migrations run automatically at startup
- Full stack: `cp docker/.env.example .env && docker compose up -d --build`
- Coexisting with another app on the VPS: `docker-compose.contabo.yml` (see `docs/DEPLOY_ALONGSIDE.md`)

Entrypoints: `app.main:asgi_app` is the Socket.IO-wrapped ASGI app (realtime at `/ws/socket.io`);
`app.main:app` is the bare FastAPI app — use it for `fastapi.testclient.TestClient`.

Seeded on first boot: `admin@wetacrm.com` / `admin123`. Swagger at `/api/docs`.

### Tests

```bash
cd backend && .venv/Scripts/python.exe -m pytest          # all
.venv/Scripts/python.exe -m pytest tests/test_tenant_isolation.py -k search   # one test
```

`backend/tests/` holds the tenant-isolation (Phase 0), template/provisioning (Phase 1)
custom-field (Phase 2), customer-PII (Phase 3) and policy (Phase 4) suites — 180 tests. Install
test deps with `pip install -r requirements-dev.txt`. There is no frontend test suite;
`npm run build` (which runs `tsc -b`) is the only typecheck gate.

## Architecture

### Graceful degradation is the core design constraint

Every external service is optional and the app must keep working without it. Preserve this when
touching integrations:

| Unset env | Fallback |
|---|---|
| `DATABASE_URL` | SQLite (`backend/weta_crm_dev.db`) |
| `REDIS_URL` | Celery `task_always_eager` — jobs run inline |
| `MEILI_URL` | `/search` falls back to SQL `ILIKE`; indexing becomes a no-op |
| `MINIO_*` | Files written under `backend/uploads/` |
| `SMTP_HOST` | Emails logged to the console, `send_email` returns `False` |

This is why UUID PKs are `String(32)` hex (portable Postgres↔SQLite) and why `search_client`,
`storage` and `email` all probe lazily and swallow failures.

### Backend: modular monolith

Each business module is `app/<module>/{models,schemas,router}.py` (plus `service.py` where shared
logic exists: `activities`, `notifications`). Despite the wording in `PROJECT_PLAN.md`, there is
**no repository layer** — routers hold the business logic and talk to SQLAlchemy directly.

Cross-cutting pieces live in `app/core/` (config, security, deps, permissions, pagination,
exceptions, rate_limit, crud helpers, shared schemas), `app/database/`, `app/services/` (billing,
email, numbering, pdf, storage, search_client, search_sync), plus two top-level registries:
`app/filtering.py` and `app/io/`.

Wiring a new module requires **three** touch points: create the package, `include_router(...,
prefix="/api/v1")` in `app/main.py`, and import its models in `app/models_registry.py` — that
import is what puts tables on `Base.metadata` for Alembic autogenerate.

### Multi-tenancy — read this before touching any query

Every business row belongs to a tenant, and isolation is enforced **centrally** in
`app/core/tenancy.py`. Routers must never filter by `tenant_id` themselves.

- A model becomes tenant-owned by inheriting `TenantScoped` (`app/database/base.py`), which adds an
  indexed `tenant_id`.
- A `do_orm_execute` event injects `with_loader_criteria` into every SELECT touching such a model,
  including relationship loads. A `before_flush` hook stamps `tenant_id` on insert.
- **`with_loader_criteria` only reaches ORM entities.** `select(func.count()).select_from(Model)`
  selects no entity, so `_augment_aggregate` catches those by inspecting the statement's FROM
  tables. Aggregates over an *anonymous subquery* are reachable by neither — which is why
  `paginate()` calls `scope_to_tenant()` on the statement before turning it into a subquery. If you
  write a new aggregate that goes through a subquery, filter it explicitly with `tenant_predicate()`.
- Three scopes: `tenant_scope(tid)` (requests, per-tenant jobs), `platform_scope()` (Super Admin,
  provisioning, and the auth lookups that must find a user before their tenant is known), and no
  scope at all — which raises `TenantContextMissing` rather than returning everyone's rows.
- The tenant comes from the JWT's signed `tid` claim, put into context by `TenantContextMiddleware`.
  It is a *pure ASGI* middleware on purpose: `BaseHTTPMiddleware` runs the app in a separate task and
  will not propagate a `ContextVar`.
- Outside the database: storage keys are prefixed `tenants/<id>/` and verified on read; Meilisearch
  documents carry `tenant_id` as a filterable attribute and every query filters on it; Socket.IO
  rooms are `tenant:<tid>:user:<uid>`; Celery beat jobs walk tenants via `for_each_tenant`.
- Platform Super Admins are the one user kind with `tenant_id` and `role_id` null. They use
  `/api/v1/platform/*` and reach tenant data only by impersonating (audited, ≤60 min).

Anything added to `app/*/models.py` almost certainly needs `TenantScoped`, and any new
global unique constraint needs to be composite with `tenant_id` instead.

### Templates — how a tenant gets its shape

A tenant is built from a **template**: `app/platform/templates/*.json`, validated by
`template_schema.py`, applied by `provisioning.apply_template()`. It decides which
modules exist, what each is *called* for that tenant, plus starting roles, pipeline
stages, lead sources, tags, settings and email templates.

- `general_crm.json` was **generated from the original seed constants**, so it
  reproduces the pre-template CRM exactly. It is the regression baseline — after any
  change, a tenant created from it must still behave like the old app.
- `insurance_agent.json` renames Contacts to Customers, Leads to Enquiries, swaps in an
  enquiry-to-policy pipeline, and switches off Companies/Invoices/Projects/Support.
- Templates are **copied into a tenant at provisioning, never referenced live**, so
  editing one cannot change a running tenant. `POST /platform/tenants/{id}/apply-template`
  is the deliberate exception, and is additive only.
- `sync_system_templates()` refreshes a stored system template only when the file's
  `version` is higher. Bump it when you edit a file.
- Adding a vertical = a JSON file + its key in `SYSTEM_TEMPLATE_KEYS`. No code changes.
- Module keys come from `app/platform/catalog.py`; a template may only reference keys in
  it, and `locked` modules (dashboard, settings) stay on whatever a template says.

`app/database/seed.py` no longer exists — provisioning replaced it.

### Custom fields — how a client gets their own fields

A tenant's field configuration lives in `field_defs`, and `GET /api/v1/schema/{module}`
serves the merged result. One table does two jobs:

- `is_custom = True` — a field this client invented. Values live in the entity's
  `custom` JSON column, so adding one never touches the schema and stays invisible to
  every other tenant. Postgres gets a GIN index on that column.
- `is_custom = False` — an override on a field the product ships (relabel, reorder,
  hide). The row holds only the difference from the default, created on first edit.

Base fields are **derived from the SQLAlchemy models** (`app/schema_registry.py`), not
listed by hand — a hand-written list is a second source of truth that drifts. Curate
`_LABEL_OVERRIDES` and `_LOCKED_COLUMNS` there when a column needs a nicer name or must
never be hidden.

Values are validated in a **session `before_flush` hook**, not in each router — same
reasoning as tenant isolation. Undeclared keys are dropped rather than rejected so a
stale form still saves. A module's Create/Update/Out schemas must declare `custom` or
Pydantic silently strips it.

**Filtering a JSON value needs `.as_string()` / `.as_float()`, never `cast(..., String)`.**
Casting leaves the JSON quoting in place, so `=` and `IN` never match while a substring
`ILIKE` matches straight through the quotes — a bug that passes a careless test.
Routers call `apply_filters_for(db, stmt, module, filters)`, which applies the static
whitelist and the tenant's filterable custom fields together.

Frontend: pages keep their hand-built field and column arrays as the base (they carry
render details the server cannot know, like which hook supplies a select's options), and
`useSchemaOverlay` in `CrudPage` layers the tenant's relabels, hides and custom fields on
top. Custom form values are named `custom.<key>`, which react-hook-form nests into
exactly the shape the API wants.

### Policies — status is derived, renewal is a new row

Two rules in `app/policies/service.py` shape the whole module:

- **Status is never typed.** `expiring` and `lapsed` come from the expiry date, set on
  create/update and by a nightly job. That is what makes "renewals due in 60 days" a
  number worth acting on — it cannot drift because someone forgot a dropdown. Terminal
  states (`renewed`, `cancelled`, `draft`) are left alone.
- **A renewal is a new policy row**, linked back via `renewal_of_id` with the old one
  marked `renewed` and pointed forward. Editing in place would destroy the record of
  what the customer was covered for last year. `renewal_chain()` reads the history.

Fields common to every line are columns; line-specific ones live in `details`, filtered
through `LINE_FIELDS` so it cannot become a dumping ground — a tenant needing more adds
a custom field. The exceptions promoted to columns (expiry, premium, insurer, bank,
product line, status, registration number) are the ones filtered and summed constantly.

`compute_premium()` derives whichever of net/GST/gross was omitted, so the premium
schema fields are `None`-defaulted rather than `0` — otherwise "not supplied" and
"free" are indistinguishable.

`masters` holds a tenant's insurers, banks and branches as rows, because policies point
at them; deleting one that is in use deactivates it so historical policies keep the
insurer they were actually written with.

### Personal data — encryption, masking, reveal

`app/services/crypto.py` does envelope encryption: a platform master key
(`PII_MASTER_KEY`) wraps a per-tenant data key stored on `tenants.dek_encrypted`;
that key encrypts the values with **AES-256-GCM**, so a tampered ciphertext fails to
decrypt rather than returning garbage. Without the env var a dev key is derived from
`JWT_SECRET` and loudly logged; in production the app refuses to start without one.

An encrypted column cannot be searched, so each searchable field has a **blind index**
— `HMAC-SHA256(tenant_key, normalised)` — supporting exact-match lookup with nothing
reversible stored. `GET /contacts/lookup?pan=…` uses it.

**Masked by default.** `contacts/router._out()` is the single serialisation point, so a
full PAN or Aadhaar cannot escape through an endpoint someone forgot to mask. The
plaintext comes only from `POST /contacts/{id}/reveal`, which needs the separate
`contacts:reveal_pii` permission, is rate limited, and writes an audit row every time.

**Aadhaar defaults to last-4 only.** Full capture sits behind the tenant setting
`features.aadhaar_full_capture`, off unless a workspace opts in — a private entity
storing full Aadhaar is restricted under the Aadhaar Act. See PRD 9.4.

Validation lives in `app/core/validators.py`: PAN format, Aadhaar **Verhoeff** check
digit (catches a typo or transposition), E.164 phone normalisation, pincode. Phone
normalisation is deliberately forgiving — refusing to save a customer over a phone
format would be worse than storing it imperfectly.

Birthdays query an indexed `birthday_key` (MMDD) rather than a date function over every
row, so "whose birthday is this week" stays a range scan.

### The sidebar is data, not code

`AppLayout` builds its nav from `GET /api/v1/modules`, which returns this tenant's
`tenant_modules` rows joined with the catalog's route/icon/permission. Two filters apply:
the tenant decides which modules exist, the user's role decides which they can see.
Never add a module to a hardcoded list in the frontend — add it to the catalog.

### Schema changes

Alembic is the only way the schema changes — `create_all()` and the old `ensure_schema.py` patcher
are gone. `alembic upgrade head` runs automatically at startup (`AUTO_MIGRATE=true`); turn it off
where a deploy pipeline applies migrations itself.

```bash
cd backend
.venv/Scripts/python.exe -m alembic revision --autogenerate -m "..."
.venv/Scripts/python.exe -m alembic upgrade head
```

`0001_baseline` is the pre-multi-tenant schema; a database created by the old `create_all` should be
`alembic stamp 0001_baseline`-ed rather than run through it. SQLite cannot ALTER constraints, so
migrations that change one need batch mode — and because SQLite renders `unique=True` as an
*unnamed* constraint that batch mode cannot drop, `0002_multitenant` reflects the table, discards the
constraint from the reflected definition, and passes it as `copy_from`. Reuse that pattern.

`app/database/seed.py` seeds **one tenant** (`seed.run(db, tenant_id)`) and is idempotent: roles,
pipeline stages, lead sources, email templates, settings keys. It deliberately upgrades only
*unmodified* default email templates (compared against the `*_V1` constants) so user edits survive.
It must never create a user — `users.email` is globally unique, so the owner is created by
`provision_tenant()` in `app/platform/service.py`, which knows that tenant's own owner email.
`platform_service.bootstrap()` runs at startup and ensures the platform admin and Default tenant.

### Permissions

Platform admins bypass tenant RBAC entirely (guarded by `get_platform_admin`) and are refused by
`require_perm` unless impersonating. Otherwise permissions are `"<module>:<action>"` strings (`app/core/permissions.py`; actions are
read/write/delete). A role's `permissions` column is a JSON list; `"*"` and `"<module>:*"` are
wildcards. Routes gate with `Depends(require_perm("leads:write"))` — either inside the decorator's
`dependencies=[...]` (read-only routes) or as the `user:` parameter when the handler needs the
actor. The frontend mirrors the same logic in `useAuth().hasPerm`, which drives both sidebar
visibility and per-row action buttons.

### Router conventions

Follow `app/leads/router.py` as the reference. Mutating handlers:

1. `get_or_404(db, Model, id, "Lead")` to load, `apply_updates(obj, data)` to write —
   `apply_updates` returns a `{field: [old, new]}` diff used for auditing.
2. `log_activity(...)` for the user-visible entity timeline, `audit(...)` for the admin audit log,
   `notify(...)` for a persisted + Socket.IO-pushed notification.
3. **Caller commits.** `log_activity`, `audit` and `notify` only `add`/`flush`; the router calls
   `db.commit()` once at the end.
4. `search_sync.sync_<entity>(obj)` / `search_sync.remove(index, id)` *after* the commit.

List endpoints compose: `select(Model)` → explicit query-param filters → `params.search` ILIKE →
`apply_sort(stmt, Model, params.sort)` → `apply_filters(stmt, FILTERS["<entity>"], filters)` →
`paginate(db, stmt, params)`, returning `Page[T]` (`items`/`total`/`page`/`page_size`).

Raise `AppError(detail, status)` (or `NotFoundError` / `PermissionDeniedError`) for domain errors —
the handlers in `app/core/exceptions.py` render them as `{"detail": ...}` and never leak stack
traces.

### Two shared registries (keep them in sync with the models)

- `app/filtering.py` — `FILTERS[entity] = {key: FF(column, type)}`. A whitelist: only declared keys
  are honoured and column objects are never built from user input. The *same* registry backs both
  the module list endpoints and `/io/<entity>/export`, so an export always matches the on-screen
  filter.
- `app/io/registry.py` — one `IOSpec` per entity driving `/io/<entity>/export`, `/template` and
  `/import` (generic CSV engine in `app/io/spec.py`). Imports defer notification emails into
  `ImportOptions.pending` and fire them only after the whole import commits.

### Realtime

`app/notifications/socket.py` holds an `AsyncServer`; `capture_loop()` stores the running loop at
startup so **sync** route/service code can emit via `emit_to_user` →
`asyncio.run_coroutine_threadsafe`. Clients authenticate with `{auth: {token}}` and join a
`user:<id>` room. Never call `sio.emit` directly from sync code.

### Money and document numbers

All quotation/invoice line-item math goes through `app/services/billing.py` (`Decimal`,
`ROUND_HALF_UP`) — never compute totals inline. Sequential numbers (`QT-2026-0042`, `INV-`, `TKT-`)
come from `next_number(db, kind)`, which increments a counter stored in the `settings` table under
key `counters` (`SELECT ... FOR UPDATE`), with the prefix overridable via the `<kind>_template`
setting. PDF rendering (`app/services/pdf.py`, ReportLab) is likewise driven by those
`quotation_template` / `invoice_template` settings rows, which the Settings "template studio" edits
with a live preview.

### Frontend

React 18 + TS (strict) + Vite + Tailwind, `@/*` → `src/*`. Provider order in `main.tsx`:
QueryClient → Theme → Toast → Router → Auth.

**`components/CrudPage.tsx` is the spine of the app.** Most list pages (`pages/Companies.tsx` is the
cleanest example) are pure configuration: a zod `schema`, `defaults`, a `FieldDef[]` describing the
modal form, `columns` (default view) plus `allColumns` (the full field catalog users can build views
from), `filterFields`, and `ioEntity` to switch on CSV import/export. `CrudPage` supplies the table,
search, pagination, sorting, create/edit modal, delete confirm, TanStack Query cache invalidation
and permission gating. Prefer extending it — or `useViewColumns` for custom pages like Quotations
and Invoices — over hand-rolling a list page.

Supporting conventions:

- `lib/zh.ts` — zod preprocessors (`optStr`, `optNum`, `optEmail`, `reqStr`, `numDefault`) that
  translate HTML input `""`/`NaN` into the `null` the API expects. Use these, not bare `z.string()`.
- `lib/options.ts` — cached `useXOptions()` hooks for select fields (users, companies, contacts,
  stages, sources, tags, products).
- `lib/api.ts` — axios instance with a bearer interceptor and a single-flight refresh-token retry on
  401; tokens live in `localStorage` (`weta_access` / `weta_refresh`). `errorMessage(err)` unwraps
  the FastAPI `detail`.
- Styling uses the `@layer components` classes in `index.css` (`btn-primary`, `btn-secondary`,
  `btn-ghost`, `input`, `label`, `card`, `badge`) — reach for those before writing new utility soup.
  Dark mode is class-based (`darkMode: "class"`), so every color needs a `dark:` variant.
- Saved table views are per-device `localStorage` (`weta_views_<module>`), not server state.

### Adding a module end to end

Backend: `models.py` → import it in `models_registry.py` → `schemas.py` → `router.py` →
`include_router` in `main.py` → add the module name to `MODULES` in `core/permissions.py` (and to
the relevant `DEFAULT_ROLES` grants) → optionally register `FILTERS[...]` and an `IOSpec`.
Frontend: a page under `src/pages/` built on `CrudPage`, a route in `App.tsx`, a `NAV` entry with
its `perm` in `layouts/AppLayout.tsx`, and types in `src/types/index.ts`.
