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
custom-field (Phase 2), customer-PII (Phase 3), policy (Phase 4), poster/WhatsApp (Phase 5) and
loans/reports/insurance-quotation (Phase 6) and hardening (Phase 7: auth/RBAC, billing and
CSV I/O, signed downloads, purge, export, indexes, security review) and email-workflow suites — 557 tests. Install
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
  `/api/v1/platform/*` and **cannot reach tenant data at all** — see below.

Anything added to `app/*/models.py` almost certainly needs `TenantScoped`, and any new
global unique constraint needs to be composite with `tenant_id` instead.

### A platform admin has no way into a workspace

Impersonation was removed. There is no endpoint that mints a token for someone else's
tenant, `_create_token` cannot even express one, and `get_current_user` refuses any
token whose `tid` is not the user's own — no exceptions. Do not reintroduce a
"support session": the console manages a workspace from the outside, and everything
an admin needs (modules, template, status, owner, record counts) is on the tenant page.

Consequently a platform admin hitting a tenant endpoint must get a **refusal, not a
crash**. `require_perm` refuses them outright; for endpoints guarded only by
`get_current_user`, the tenant-scoped query raises `TenantContextMissing`, which has
its own handler rendering 403. A 500 there would read as a broken server when the
system is behaving exactly as designed.

### A disabled module is gone, not hidden

Switching a module off has to mean something at the API, or a workspace with Policies
disabled can still create policies over HTTP that its own UI will never show.

- `require_perm("policies:read")` refuses when the permission's prefix names a catalog
  module this tenant has switched off. Only prefixes that *are* catalog keys are gated —
  `users:read` and `activities:read` are cross-cutting and have no module to switch off.
- `require_module("poster")` is for the case the prefix cannot cover: the Poster Studio is
  permissioned on `contacts:read`, so its permission names the wrong module. Reach for it
  whenever an endpoint's permission does not name its own module.
- `/search` filters result groups the same way, so a general CRM gets no "Policies" heading
  for a module it does not have.
- `backfill_new_modules()` runs at startup and gives existing tenants a row for any module
  added to the catalog since they were provisioned — additive only, decided by that tenant's
  own template. Without it, shipping a module reaches only workspaces created afterwards.

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
- A template that names **any** modules is treated as naming **all** of them: anything
  it leaves out is disabled. Listing seven modules and silently getting the other ten
  is not what anyone means. A template with no module list gets everything.
  **The console must read the config the same way `_apply_modules` does** —
  `mergeWithCatalog()` in `platform/ModuleBoard.tsx` is the one place that does it, and
  both the template editor and the tenant page go through it. The editor used to
  default an unnamed module to *on*, which had two live consequences: it showed
  sixteen modules included for a template that grants five, and pressing Save wrote
  that back, silently switching on eleven modules the template deliberately withheld.
  If the backend rule ever changes, change it here too.
- Custom templates are editable (`PATCH /platform/templates/{key}`); system ones are
  refused, because they are refreshed from the bundled JSON and an edit would be
  overwritten. The edited config is re-validated before storing.
- Templates are **copied into a tenant at provisioning, never referenced live**, so
  editing one cannot change a running tenant. `POST /platform/tenants/{id}/apply-template`
  is the deliberate exception, and is additive only.
- `sync_system_templates()` refreshes a stored system template only when the file's
  `version` is higher. Bump it when you edit a file.
- Adding a vertical = a JSON file + its key in `SYSTEM_TEMPLATE_KEYS`. No code changes.
- Module keys come from `app/platform/catalog.py`; a template may only reference keys in
  it, and `locked` modules (dashboard, settings) stay on whatever a template says.

`app/database/seed.py` no longer exists — provisioning replaced it.

### The Super Admin console

Two screens decide the same thing at two moments — what a workspace can open — so
they share `platform/ModuleBoard.tsx` rather than being two lists to learn. The board
*is* the client's sidebar: the included modules in order, under the names that client
will read, draggable; everything switched off sits beside it under "Not included".
Counts and checkbox columns cannot show what a workspace will actually feel like.

`platform/TemplateEditor.tsx` is a **page** (`/platform/templates/:key`), not a modal:
it configures eighteen modules, a pipeline and a source list, and a scrolling dialog
gave no sense of scale, could not be linked to, and hid the save button as soon as you
scrolled. It holds the last-saved JSON and asks before discarding. A system template
opens read-only with the clone offered, because editing one would be overwritten by
the next `sync_system_templates()`.

A pipeline stage's outcome is **one** three-way choice (open / won / lost), not two
checkboxes that can both be clear or silently clear each other.

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

**A form shows what you need and hides the rest.** The customer form runs to
thirty-three fields; an agent holding a name and a number should not scroll past a
KYC block and a nominee editor to reach Save. `FormFields` collapses every
`section`, and the rule differs by intent: **creating** opens the first group only —
on a new record everything else is empty by definition, and a section that opens
because a dropdown has a default is open for no reason — while **editing** opens
whatever holds data, so nothing a colleague filled in hides behind a header nobody
thinks to click. A collapsed header shows how many of its fields are filled, so it
never conceals something silently. Sections group by **name**, not by adjacency:
custom fields are appended after the page's own, so a workspace with a custom KYC
field used to get two "KYC" headers with the whole form between them.

`_INTERNAL_COLUMNS` in `schema_registry.py` keeps storage out of the field list.
A blind index and a ciphertext are how a PAN is *stored* — the field is `pan`, and
the page supplies it. Offering them meant Settings → Fields listed six entries
nobody could act on, and every one was another line between an agent and the field
they wanted.

### Posters — one renderer, and layers that know what they need

`app/poster/render.py` renders a design from a layer spec, and **everything goes
through it** — the editor preview, batch output, whatever is sent. A separate
client-side preview would drift the first time a font fell back or a line wrapped,
and the agent would find out from the customer. The editor therefore previews by
POSTing the unsaved spec to `/poster/preview` and showing the PNG that comes back.

Two rules keep half-rendered output away from customers:

- `is_hollow()` drops a text layer whose merge placeholders **all** resolved empty —
  "Call {agent_mobile}" with no number would otherwise render a button reading "Call".
- `"requires": "agent_mobile"` on any layer skips it when that field is empty, which
  is how a button's *background* disappears along with its label rather than being
  left as an empty coloured pill.

Both were found by looking at a rendered poster, not by a test. Look at the output.

Fonts resolve through a candidate list (Linux paths first for Docker, then Windows).
`load_font(size, bold, family, italic)` falls back along **two** axes — an unavailable
italic drops to the upright of the same family, an unavailable family drops to `sans` —
before reaching Pillow's bitmap default, which looks like a ransom note next to real
type. `FONT_FAMILIES` is what `/poster/merge-fields` advertises, so the editor can only
offer a family the renderer can actually resolve. Add `fonts-dejavu-core` to the image.

**Alpha is the trap in this file.** Pillow's `putalpha` *replaces* the alpha channel and
`ImageDraw.text` *replaces* the pixel rather than blending it, and `render()` ends with
`convert("RGB")`, which throws alpha away. Both bugs that produced were the same shape: a
control the editor offered, that changed the spec, and changed nothing on the poster.
So: `_rounded` composites its mask against the layer's existing alpha, and a text layer
with `opacity < 1` is drawn onto its own transparent sheet and `alpha_composite`d.
`tests/test_poster_whatsapp.py` asserts these **in pixels** — a byte-length comparison
passes happily while the control does nothing.

The editor drags: `components/PosterCanvas.tsx` overlays one invisible box per layer on
the server-rendered image for click-to-select, drag-to-move and resize. It draws no
design of its own — a second, client-side copy is exactly the drift the server-rendered
preview exists to prevent. A **text** layer gets no height handle: the renderer derives
its height from the wrapped lines and never reads `h`.

**A design names its pictures; `load_assets` supplies the bytes.** `logo` is the
workspace logo and anything else in a layer's `source` (or `background.image`) is a
`poster_assets` id — the same shape the renderer already used, which is why adding
an image library changed no rendering code. Only the pictures a design actually
names are read, and one that cannot be read is left out of the map rather than
raised: the renderer skips an image layer it has no bytes for, so a picture someone
deleted costs that layer and not the whole poster.

Uploads are **raster images only**, decided from the bytes and then checked a second
way — Pillow must be able to open the file. The two are not the same check: a file
that sniffs as a PNG but will not decode would upload cleanly and then silently never
draw, and the agent would place a picture, see nothing, and have nothing to go on.
SVG is refused outright for the reason it is refused everywhere else here. An asset
is served back as the type it passed as, with `nosniff` — an allow-list at upload is
worth nothing if the file returns as something else.

Designs are created, duplicated and deleted from the studio, so switching away from
one is now a way to lose work: the editor holds the last-saved JSON and asks before
discarding. Deleting the last design leaves a workspace with none, which is a normal
state (it is where a new one starts) — hence the empty state offering a blank canvas
or `POST /poster/seed-presets` to bring the starters back.

### WhatsApp — two channels, one interface

**Click-to-chat** is a `wa.me` link: the agent's own WhatsApp opens with the message
prefilled and *they* press send. No approvals, no fees, no verification — the default,
and why an agency can use this on day one. `/whatsapp/link` returns the link *and*
records it, because the workspace still needs to know a customer was already messaged.

**The Cloud API** sends from the server and needs a verified Meta Business account,
a dedicated number, and pre-approved templates for anything outside a 24-hour reply
window. Configured per tenant; absent, `provider_for()` returns `NullProvider`, which
**always reports failure** rather than pretending — a caller must never be told a
message was sent when nothing left the building. Nothing provider-specific escapes
`WhatsAppProvider`, so a BSP swap is a subclass plus a settings change.

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
insurer they were actually written with. A workspace maintains these from
**Settings → Reference lists**; before that existed they were seeded once at
provisioning and the only way to add one was the API, so a dropdown went stale the
first time the market moved.

**`insurer_id` and `broker_id` are two different companies on the same policy.** One
underwrites the risk; the other is the intermediary the business was placed through
and carries the agency code the commission is paid against. An agency reconciles by
each separately, which is why they are not one field. `broker_id` is labelled
**"Insurance company"**, and that label lives in `schema_registry._LABEL_OVERRIDES`
rather than in the page — a page-level label is overridden by the served schema, so
the form would say one thing and the column picker another.

### Quotations come in two shapes

`Quotation.kind` is `"standard"` or `"insurance"`, and the difference is arithmetic:

- A **standard** quotation's items are things bought together, so the total is their sum —
  `billing.compute_items` as before, unchanged.
- An **insurance** quotation's options are *competing quotes for the same cover*, so the
  total is the **selected option** and never the sum. Three insurers at ₹12k, ₹14k and
  ₹16.5k is a ₹12k–₹16.5k decision, not a ₹42.5k sale. This is why the options live in an
  `insurance` JSON column rather than in `quotation_items`: the billing engine's whole job
  is to add items up, and these must not be added up.

`normalise_options()` settles the selection — one and only one, defaulting to the
recommendation and then to the cheapest — and runs premiums through the same
`compute_premium()` a policy does, so an option and the policy it becomes cannot disagree
about the gross. Option keys are whitelisted by `OPTION_FIELDS`, same reasoning as
`LINE_FIELDS` on a policy.

`comparison_pdf.py` is a *separate renderer*, not a mode of `document_pdf`: one prints line
items down a portrait page and totals them, the other puts insurers across a landscape page
and totals nothing.

`POST /quotations/{id}/convert-to-policy` books the selected option; `convert` (to an
invoice) refuses an insurance quotation and says why. Both check the policy number is free
first — a duplicate would otherwise surface as a 500 on a typo.

### Loans

Deliberately thinner than a policy: the lender does the underwriting, so what an agency
tracks is whose case it is, how far it has got, and what it earns. `expected_payout` is
derived from the **sanctioned** amount (never the requested one) and recomputed whenever
either input moves, so a payout report cannot quietly go stale. Stage changes stamp
`sanctioned_on` / `disbursed_on` — on create as well as on update, because agencies enter
existing cases at the stage they have already reached.

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

**Nominees are captured on the customer form** (`components/NomineeFields.tsx`). The
API had accepted them since the module was built and nothing ever asked, so every
customer had none. Two rules are the insurer's and are enforced server-side — shares
total 100, and a nominee under 18 needs an appointee — and the form mirrors both as
they are typed, because being told which of four rows is wrong beats being told the
set is. Adding a row takes the unallocated share, or splits evenly when there is
none: appending a 0% nominee looks reasonable, totals 100 with the others, and is
then refused by the API, which requires every share to be at least 1.

`FieldDef.render` on `CrudPage` is the escape hatch a repeating sub-record like this
needs. It is handed the form's `control` so it registers with react-hook-form like
any other field — validation, dirty state and reset keep working rather than needing
a second state tree beside them.

### The dashboard is data too

`app/reports/widgets.py` is the mirror of `platform/catalog.py`, for the same
reason. The dashboard was a fixed sequence in `Dashboard.tsx`, so an insurance
workspace opened on six deal figures reading zero and a new vertical could only be
served by another `if` in that file. `GET /api/v1/dashboard-widgets` now returns the
cards in order and the page renders the list it is given.

- A `WidgetDef` names the module it reports on. A card whose module is off is never
  served — the module gating does the work, no second rule for the dashboard.
- **`resolve()` is read at two moments and they do not mean the same thing.** A
  *template* is hand-written and may name four cards: naming any names all, so the
  rest are off (`selective=True`). A *workspace's stored layout* is written by the
  editor and always names every card, so a key it omits is one shipped afterwards
  and gets the catalog default (`selective=False`) — the equivalent of
  `backfill_new_modules()`, without which a new card would arrive switched off
  everywhere and nobody would ever see it. Naming *nothing* is unconfigured either
  way, and still gets everything.
- Provisioning calls `materialise()` and writes the whole picture into the
  `dashboard_widgets` setting. A settings row rather than a table because nothing
  points at a widget, unlike `tenant_modules` which permissions and routes join to.
  It is stored under a `widgets` key inside that row: `SettingOut.value` is typed
  `dict`, so a bare list breaks `GET /settings` for every other row.
- Edited in two places, both the same two-column board: **Settings → Dashboard** for
  one workspace, and the **Dashboard tab** of a template in the console for every
  workspace made from it afterwards.

Adding a card is a `WidgetDef` plus an entry in the `WIDGETS` map in `Dashboard.tsx`.
A key the server sends and this build does not know is skipped rather than crashing,
so a rolling deploy is survivable.

### The sidebar is data, not code

`AppLayout` builds its nav from `GET /api/v1/modules`, which returns this tenant's
`tenant_modules` rows joined with the catalog's route/icon/permission. Two filters apply:
the tenant decides which modules exist, the user's role decides which they can see.
Never add a module to a hardcoded list in the frontend — add it to the catalog.

### Emails fire because a trigger says so

`EmailTemplate.trigger` names the moment a template sends, and
`app/settings/workflows.py` is the catalog of those moments. Before this the link
was a string literal at a call site, which had two consequences that were both live:
`notification_settings` was stored and never read (so switching an email off did
nothing), and the insurance template's renewal and birthday emails were editable,
configured, and sent by nothing at all.

- Call sites use `workflows.fire(db, "lead_assigned", to, ctx)`, never
  `send_templated` directly. `fire` returns False when the trigger is switched off —
  a normal outcome, not an error.
- One template per trigger, enforced on write: two would mean the email a customer
  receives depends on which row a query reached first.
- `locked` triggers cannot be switched off, with the reason in the refusal — turning
  off password reset locks people out with no way back in.
- **Customer-facing triggers default to off.** Provisioning a workspace must never
  start emailing that client's customers.

Scheduled triggers (renewal, birthday) run from daily Celery jobs through
`app/settings/dispatch.py`, and every send writes a `sent_emails` row **before** the
send, with a unique `(tenant_id, dedupe_key)`. Without it a daily job over a
two-month renewal window emails every customer every morning for two months. Writing
the row first means a crash mid-send fails towards *not* sending again, which is the
right way round: a missed reminder is recoverable, a customer harassed by software is
not. The table doubles as the answer to "did we email this customer?".

Adding a trigger is a `TriggerDef` plus the `fire()` call at the moment it names —
the alternative is a chain of `if setting_enabled(...)` at scattered call sites,
which is where both original bugs came from.

### One record's notes, files and history

`components/RecordPanel.tsx` is the drawer behind the paperclip on a contact,
policy or loan row. Notes, attachments and the activity timeline had all been
written to the database since their modules were built and none of them had a
screen — a customer accumulated dated notes nobody could read, and a policy could
not carry the PDF it was issued as.

- A drawer, not the edit modal: these are read far more often than they are
  changed, and you should not enter edit mode to look at them.
- The **Notes** tab appears only for contacts, because `customer_notes` is the only
  dated-note table there is. Inventing one for other records would mean two things
  called notes behaving differently.
- **Files** pass `entity_type`/`entity_id` to `/documents` and open through
  `/documents/{id}/link` — a signed URL, because a new tab cannot send a bearer
  token. See below for why the signature is the credential.
- **Settings → Audit log** finally reads `audit_logs`. Every mutating route has
  written one since the audit helper landed and nothing ever read them; a workspace
  had a complete record of every premium edited and every PAN revealed, and no way
  to look at it. Read-only on purpose — a log a user can prune is not evidence.

**The API serialises naive UTC** ("2026-09-09T15:28:24", no zone), and JavaScript
reads a zone-less ISO string with a time in it as *local*. Every relative time in
the app was out by the viewer's offset — in IST a note written seconds ago read
"5h ago". `lib/format.ts` parses through one helper that appends `Z` when there is
no zone; date-only values are already UTC and are left alone. Fix it there, not at
each call site.

### Serving files: signed links, and not trusting the uploader

`/api/v1/files/{token}` is the one route that serves stored bytes without a bearer
token, so a document can go in an `<img src>` or open in a tab. The signature is the
credential: an HMAC over `{key, tenant, expiry}`, signed with a key
**domain-separated from `JWT_SECRET`** so a download token can never be replayed as a
session. Reading it re-enters the token's tenant scope — the key alone is not enough,
because `tenants/<id>/…` is guessable in shape.

`app/services/mime.py` decides what a file *is* from its bytes. `UploadFile.content_type`
is whatever the client typed, and storing it means the uploader chooses the
`Content-Type` their file is later served with — one browser quirk from stored XSS.
HTML and SVG are refused outright (an SVG is a document that can run script wearing an
image's clothes); everything else is served with `nosniff`, a sandbox CSP, and
`attachment` disposition unless it is on a short inline-safe list.

### Indexes lead with tenant_id

Every query in a shared-schema multi-tenant app starts with `tenant_id = ?`, so a
single-column index on the filtered column cannot serve one. `TENANT_COMPOSITE_INDEXES`
in `app/models_registry.py` holds the list; migration `0010` holds the same list,
deliberately duplicated because a migration that imports live app code stops describing
the schema it produced. `tests/test_indexes.py` stops the two drifting.

Measured at 12,000 policies before adding them: dashboard KPIs 32x and 45x faster,
renewals 3.1x. Two candidates measured at ~1.0x were left out — an index that does not
earn its place still costs write throughput.

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

**Deleting a tenant is reversible for `TENANT_RETENTION_DAYS` (30), then it is not.**
`app/platform/purge.py` empties every tenant-scoped table in reverse dependency
order, removes the tenant's storage prefix and its search documents, and deletes the
tenant row. It deliberately does *not* lean on `ON DELETE CASCADE` from `tenants.id`:
that works on Postgres and silently does nothing on SQLite unless foreign keys are
enabled, and a purge that reports success while leaving everything behind is the
worst available outcome. A weekly Celery job runs it; the console lists what is in
the window and can purge one immediately (slug typed to confirm) for a
"delete my data now" request.

**Deleting a tenant releases its email addresses.** `users.email` is globally unique —
that is what lets the sign-in screen work without a workspace picker — so a soft-deleted
tenant would otherwise hold its owner's address for the whole retention window, and
re-creating that client under the same address would be refused. `release_tenant_users()`
deactivates the users and tombstones their addresses (`deleted.<tid8>.<original>`), which
keeps the row for the retention window and the original address readable inside the
tombstone. `original_email()` reverses it.

`app/database/seed.py` seeds **one tenant** (`seed.run(db, tenant_id)`) and is idempotent: roles,
pipeline stages, lead sources, email templates, settings keys. It deliberately upgrades only
*unmodified* default email templates (compared against the `*_V1` constants) so user edits survive.
It must never create a user — `users.email` is globally unique, so the owner is created by
`provision_tenant()` in `app/platform/service.py`, which knows that tenant's own owner email.
`platform_service.bootstrap()` runs at startup and ensures the platform admin and Default tenant.

### Permissions

Platform admins bypass tenant RBAC entirely (guarded by `get_platform_admin`) and are refused by
`require_perm`. Otherwise permissions are `"<module>:<action>"` strings (`app/core/permissions.py`; actions are
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
the relevant `DEFAULT_ROLES` grants) → add a `ModuleDef` to `platform/catalog.py` → name it in the
templates that should have it (and bump their `version`) → optionally register `FILTERS[...]` and
an `IOSpec`. Existing tenants pick the module up at next startup via `backfill_new_modules()`.
Frontend: a page under `src/pages/`, a route in `App.tsx`, and types in `src/types/index.ts` — the
sidebar entry comes from the catalog, not from a list in the frontend.
