# Deploying WeTa CRM

A VPS with Docker, a domain, and about twenty minutes.

Everything below assumes the full stack in `docker-compose.yml`. If the box already
runs another app on port 80, use `docker-compose.contabo.yml` instead and read
[DEPLOY_ALONGSIDE.md](DEPLOY_ALONGSIDE.md) first.

---

## 1. The one thing to get right before anything else

`PII_MASTER_KEY` wraps every tenant's data-encryption key, which in turn encrypts
customers' PAN and Aadhaar numbers.

- **Lose it and that data is permanently unreadable.** There is no recovery path,
  no reset link, and no support ticket that gets it back. Every other field
  survives; those do not.
- **Leak it and the encryption is undone.** Someone holding the key and a copy of
  the database has the plaintext.

Which means: **back the key up somewhere your database backups are not.** A nightly
database dump and the key sitting together in the same bucket is a nightly dump of
the plaintext. A password manager, a sealed envelope, your cloud provider's secret
store — anywhere separate.

Generate it, and every other secret, with:

```bash
python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Compose refuses to start without `PII_MASTER_KEY`, `JWT_SECRET` or `ADMIN_PASSWORD`.
That is deliberate — a deployment quietly running on a placeholder secret is worse
than one that will not come up.

---

## 2. First deploy

```bash
git clone https://github.com/Janakiraman-sridhar/wetacrm-multitenant.git
cd wetacrm-multitenant
cp docker/.env.example .env
```

Fill in `.env`. At minimum:

| Variable | What it is |
|---|---|
| `PII_MASTER_KEY` | Section 1. Generate it, back it up separately. |
| `JWT_SECRET` | Signs sessions. Changing it signs everyone out. |
| `POSTGRES_PASSWORD` | Database password. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | The first platform Super Admin. Change the password at first sign-in. |
| `CORS_ORIGINS` | Your real frontend origin, e.g. `https://crm.example.com`. |
| `APP_URL` | Public URL used in email links. |
| `MEILI_MASTER_KEY`, `MINIO_ROOT_PASSWORD` | Search and file storage. |
| `SMTP_*` | Optional. Without it, email is logged to the console and `send_email` returns `False` — the app runs, it just cannot send. |

Then:

```bash
docker compose up -d --build
docker compose logs -f backend
```

Migrations run automatically at startup (`AUTO_MIGRATE=true`), so there is no
separate migrate step. Wait for the log line saying the application has started,
then open your domain.

Sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` — that account lands in the **platform
console**, not the CRM. Create your first client workspace from there.

### TLS

```bash
docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d crm.example.com
```

Then uncomment the 443 block in `nginx/nginx.conf` and `docker compose restart nginx`.

---

## 3. Releasing a change

```bash
git pull
docker compose up -d --build
```

Migrations apply on boot. There is a short window during the rebuild where the API
is unavailable; for a single-agency deployment that is fine, and for anything larger
put the release behind a second backend container and switch nginx over.

**Before pulling a release that adds a migration, take a database backup** (below).
Alembic migrations are not reversible in practice on SQLite and only sometimes on
Postgres; the backup is the rollback.

---

## 4. Deleting a workspace

Deleting a tenant from the console is a **soft** delete: its users lose access
immediately and their email addresses are released, but the data stays for
`TENANT_RETENTION_DAYS` (30 by default) so a mis-click can be undone.

Platform console → **Deleted workspaces** shows what is in the window and how long
each has left. A weekly job purges anything past it, permanently: every row across
every table, every uploaded file, every search index entry.

To honour a "delete my data now" request without waiting out the window, purge from
the console — it requires typing the workspace slug, because there is no undo.

```bash
# What would go, without removing anything:
docker compose exec backend python -c "
from app.database.session import SessionLocal
from app.platform import purge
db = SessionLocal()
for t in purge.tenants_due_for_purge(db):
    print(t.slug, purge.purge_tenant(db, t, dry_run=True)['rows'])"
```

A purged workspace is not in the backups taken after the purge. If you may need it,
take a dump first.

## 5. Backups

Two things must be backed up, and **not to the same place**:

```bash
# 1. The database
docker compose exec -T postgres pg_dump -U weta weta_crm | gzip > weta-$(date +%F).sql.gz

# 2. Uploaded files
docker compose exec -T minio mc mirror --overwrite /data/weta-crm ./backup-files/
```

And separately, in your password manager or secret store: `PII_MASTER_KEY`.

### Restoring

```bash
gunzip -c weta-2026-09-08.sql.gz | docker compose exec -T postgres psql -U weta weta_crm
```

Restore with **the same `PII_MASTER_KEY`** the dump was taken under. With a different
key, every PAN and Aadhaar fails to decrypt — loudly, because AES-GCM authenticates,
so you get an error rather than garbage silently written back over real values. That
is the failure mode to expect if the key was lost; there is no way to read those
fields again.

---

## 6. What runs where

| Container | What it does | Safe to lose? |
|---|---|---|
| `backend` | FastAPI + Socket.IO. Runs migrations at boot. | Restart freely. |
| `worker` / `beat` | Celery. Renewal status refresh, reminders, the weekly tenant purge. | Yes — jobs resume, but nightly status refresh and the purge stop while down. |
| `postgres` | Everything. | **No.** This is the product. |
| `redis` | Celery queue and rate limiting. | Yes — queued jobs are lost, nothing else. |
| `meilisearch` | Search index. | Yes — `/search` falls back to SQL `ILIKE` automatically. |
| `minio` | Uploaded files and generated posters. | **No** for attachments; posters regenerate. |
| `nginx` | TLS and routing. | Restart freely. |

The degradation column is not aspirational — every one of those fallbacks is
exercised by the local development setup, which runs with none of these services.

---

## 7. When something is wrong

**The backend will not start.**
`docker compose logs backend`. If it mentions `PII_MASTER_KEY`, the variable is
missing from `.env` — that check exists precisely so this fails at boot rather than
after someone has typed in a hundred customers.

**Everyone is signed out after a deploy.**
`JWT_SECRET` changed. Restore the old value if you have it; otherwise everyone signs
in again.

**A customer's PAN or Aadhaar shows an error where the value should be.**
`PII_MASTER_KEY` does not match the one the data was written under. Restore the
correct key. Do not "fix" the record by overwriting it — that discards the ciphertext
you would need if the right key turns up.

**Search returns nothing but the records exist.**
Meilisearch is down or its index is empty. The app falls back to SQL automatically,
so this usually means Meili is *up* but unindexed: restart the backend to re-sync, or
just leave it — the SQL path is correct, only slower.

**A tenant reports their sidebar is missing a module.**
The module is switched off for that workspace. Platform console → the tenant →
Modules. Modules added to the product after a workspace was created arrive switched
off unless its template says otherwise.

---

## 8. What is not done yet

Honest list, so nothing here is a surprise in production:

- **Rate limiting is in-memory**, so it resets on restart and does not hold across
  multiple backend containers. Fine for one container. (Plan 7.2.)
- **Attachment URLs are not signed or expiring.** (Plan 7.3.)
- **Not load-tested** beyond small data. Indexes for renewal windows and custom-field
  queries are still to come. (Plan 7.4.)

None of these block a first deployment with a small number of workspaces. All of them
matter before this holds many clients' data.
