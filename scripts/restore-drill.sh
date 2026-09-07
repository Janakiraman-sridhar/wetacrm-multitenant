#!/usr/bin/env bash
#
# Prove a backup can actually be restored — before you need it to be.
#
# Restores a dump into a scratch database alongside the live one, counts what came
# back, and decrypts one customer's PAN with the key currently in the environment.
# That last step is the one that matters: it proves the dump and the key you hold
# belong together. A dump that restores cleanly but whose encrypted columns cannot
# be read is not a backup of a CRM, it is a backup of some names and addresses.
#
# The live database is never touched. The scratch database is dropped at the end.
#
# Usage:
#   ./scripts/restore-drill.sh backups/weta-db-2026-09-08_0230.sql.gz
#
# Run it after the first deployment, and again whenever PII_MASTER_KEY changes or
# anyone touches the backup setup.

set -euo pipefail

DUMP="${1:?usage: restore-drill.sh <dump.sql.gz>}"
DB_USER="${POSTGRES_USER:-weta}"
SCRATCH="weta_restore_drill"

if [ ! -f "$DUMP" ]; then
  echo "No such dump: $DUMP" >&2
  exit 1
fi

cleanup() {
  docker compose exec -T postgres psql -U "$DB_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $SCRATCH" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Restoring $DUMP into a scratch database (the live one is untouched)…"
cleanup
docker compose exec -T postgres psql -U "$DB_USER" -d postgres \
  -c "CREATE DATABASE $SCRATCH" >/dev/null

gunzip -c "$DUMP" | docker compose exec -T postgres psql -q -U "$DB_USER" -d "$SCRATCH" >/dev/null

echo
echo "What came back:"
docker compose exec -T postgres psql -U "$DB_USER" -d "$SCRATCH" -t -A -F' ' -c "
  SELECT 'tenants', COUNT(*) FROM tenants
  UNION ALL SELECT 'users', COUNT(*) FROM users
  UNION ALL SELECT 'contacts', COUNT(*) FROM contacts
  UNION ALL SELECT 'policies', COUNT(*) FROM policies
  UNION ALL SELECT 'loans', COUNT(*) FROM loans
  UNION ALL SELECT 'documents', COUNT(*) FROM documents;" \
  | while read -r name count; do printf '  %-12s %s\n' "$name" "$count"; done

echo
echo "Decrypting a stored PAN with the key this deployment is running on…"

# Run inside the backend container so it uses the same PII_MASTER_KEY the live app
# does, but pointed at the scratch database.
docker compose exec -T \
  -e DATABASE_URL="postgresql://$DB_USER@postgres:5432/$SCRATCH" \
  backend python - <<'PYTHON'
import sys

from sqlalchemy import create_engine, text

# Import the registry first: `decrypt_for_tenant` loads the Tenant model to find the
# workspace's data key, and SQLAlchemy cannot configure that mapper until every model
# it relates to has been imported. Without this the drill dies on a mapper error that
# looks nothing like a backup problem.
from app import models_registry  # noqa: F401
from app.core.config import settings
from app.services import crypto

engine = create_engine(settings.database_url)
with engine.connect() as conn:
    row = conn.execute(text(
        "SELECT tenant_id, pan_encrypted FROM contacts "
        "WHERE pan_encrypted IS NOT NULL LIMIT 1"
    )).first()

if row is None:
    print("  No encrypted PAN in this dump — nothing to check.")
    print("  Store one on a test customer and run the drill again, or this proves nothing.")
    sys.exit(0)

tenant_id, blob = row
try:
    value = crypto.decrypt_for_tenant(tenant_id, blob)
except Exception as exc:
    print(f"  FAILED: {exc}")
    print("  The dump and PII_MASTER_KEY do not match. Do not overwrite anything;")
    print("  find the key this data was written under.")
    sys.exit(1)

if not value:
    print("  FAILED: the value did not decrypt.")
    print("  PII_MASTER_KEY does not match the key this dump was written under.")
    sys.exit(1)

masked = f"{value[:2]}{'*' * (len(value) - 3)}{value[-1]}"
print(f"  OK — decrypted to {masked} ({len(value)} characters).")
PYTHON

echo
echo "Drill passed. This dump plus the key you currently hold is a working restore."
