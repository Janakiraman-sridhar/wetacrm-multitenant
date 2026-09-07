#!/usr/bin/env bash
#
# Nightly backup: the database and the uploaded files.
#
# It deliberately does NOT back up PII_MASTER_KEY. That key wraps the encryption on
# every customer's PAN and Aadhaar, so a copy of it sitting beside a copy of the
# database is a copy of the plaintext — which is exactly what the encryption exists
# to prevent. The key is a 44-character string that changes approximately never;
# it belongs in a password manager and on paper, put there once by a person.
# See docs/DEPLOY.md section 1.
#
# Usage:
#   ./scripts/backup.sh                      # writes to ./backups
#   BACKUP_DIR=/mnt/backups ./scripts/backup.sh
#
# Nightly at 02:30, via crontab -e:
#   30 2 * * * cd /path/to/wetacrm-multitenant && ./scripts/backup.sh >> /var/log/weta-backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
STAMP="$(date +%Y-%m-%d_%H%M)"
DB_USER="${POSTGRES_USER:-weta}"
DB_NAME="${POSTGRES_DB:-weta_crm}"

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%F %T')] Backing up to $BACKUP_DIR"

# --- database -----------------------------------------------------------------
# Written to a .partial name first and renamed only on success, so an interrupted
# run cannot leave a truncated dump that looks like a good one. A backup you find
# out is broken while restoring is worse than no backup, because you stopped
# looking for another.
DB_FILE="$BACKUP_DIR/weta-db-$STAMP.sql.gz"
docker compose exec -T postgres pg_dump -U "$DB_USER" "$DB_NAME" \
  | gzip > "$DB_FILE.partial"

if ! gzip -t "$DB_FILE.partial"; then
  echo "ERROR: the dump is not a valid gzip file. Keeping it as $DB_FILE.partial" >&2
  exit 1
fi

# A dump of an empty database is also a valid gzip file. Check it has content.
LINES="$(gunzip -c "$DB_FILE.partial" | head -c 2000000 | grep -c 'CREATE TABLE' || true)"
if [ "$LINES" -lt 10 ]; then
  echo "ERROR: the dump contains only $LINES tables — refusing to call it a backup." >&2
  exit 1
fi

mv "$DB_FILE.partial" "$DB_FILE"
echo "  database: $(du -h "$DB_FILE" | cut -f1)  ($LINES tables)"

# --- uploaded files -----------------------------------------------------------
# Customer documents and generated posters. Posters regenerate; documents do not.
FILES_DIR="$BACKUP_DIR/files"
mkdir -p "$FILES_DIR"
if docker compose ps --status running --services 2>/dev/null | grep -q '^minio$'; then
  docker compose exec -T minio mc alias set local http://localhost:9000 \
    "${MINIO_ROOT_USER:-weta-minio}" "${MINIO_ROOT_PASSWORD:?set MINIO_ROOT_PASSWORD}" >/dev/null
  docker compose exec -T minio mc mirror --overwrite --quiet \
    "local/${MINIO_BUCKET:-weta-crm}" /tmp/backup >/dev/null
  docker compose cp minio:/tmp/backup/. "$FILES_DIR/"
  echo "  files:    $(du -sh "$FILES_DIR" | cut -f1)"
else
  echo "  files:    minio is not running — skipping (check this is intended)"
fi

# --- prune --------------------------------------------------------------------
find "$BACKUP_DIR" -name 'weta-db-*.sql.gz' -mtime "+$KEEP_DAYS" -print -delete

COUNT="$(find "$BACKUP_DIR" -name 'weta-db-*.sql.gz' | wc -l)"
echo "[$(date '+%F %T')] Done. $COUNT dumps retained (keeping $KEEP_DAYS days)."
echo
echo "Reminder: this backup cannot be restored without PII_MASTER_KEY, which is"
echo "not in it by design. Confirm you still have it somewhere off this machine."
