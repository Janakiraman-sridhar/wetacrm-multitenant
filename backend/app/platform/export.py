"""Exporting everything one tenant owns, as a zip of CSVs.

Two jobs, and they pull in opposite directions.

**Portability.** A client asking for their data — because they are leaving, or
because someone asked them for it — should get something they can open, not a
database dump they need us to read back. So: one CSV per table, plus a manifest.

**Not handing out the plaintext by accident.** The export runs as an admin operation
over a whole workspace, which makes it the single easiest way to walk off with every
customer's PAN and Aadhaar at once. Encrypted columns are therefore exported
*encrypted*, and the masked forms are exported alongside. A client who genuinely
needs the plaintext gets it through the reveal endpoint, one record at a time, which
is permissioned and audited — as opposed to a zip file that is neither once it
leaves the building.
"""

import csv
import io
import json
import logging
import zipfile
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import tenant_scope
from app.database.base import Base

log = logging.getLogger("weta.export")

#: Columns holding ciphertext or a key-derived index. Exported as-is: without the
#: tenant's data key they are inert, and with it they are recoverable — which is the
#: right trade for a file that has to leave the building.
_OPAQUE_SUFFIXES = ("_encrypted", "_index", "_hash")

#: Never exported at all. A password hash is not the client's data to take, and
#: exporting one hands an offline cracking target to whoever receives the zip.
_NEVER_EXPORT = {"password_hash", "reset_token", "reset_token_expires"}


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _tenant_tables():
    return [t for t in Base.metadata.sorted_tables if "tenant_id" in t.c]


#: Readable forms derived at export time, because they are not stored. Without
#: these a client's export carries a PAN column they cannot read at all — the point
#: is to withhold the plaintext, not to hand over something meaningless.
_DERIVED = {
    "contacts": ["pan_masked", "aadhaar_masked"],
}


def _derived_values(table_name: str, row: dict, tenant_id: str) -> list[str]:
    if table_name != "contacts":
        return []

    from app.core.validators import mask_aadhaar, mask_pan
    from app.services import crypto

    def unmask(column: str, masker):
        blob = row.get(column)
        if not blob:
            return ""
        try:
            return masker(crypto.decrypt_for_tenant(tenant_id, blob)) or ""
        except Exception:
            # A value encrypted under a key we no longer hold. Say so rather than
            # emitting a blank that reads as "this customer had no PAN".
            return "<unreadable>"

    return [unmask("pan_encrypted", mask_pan), unmask("aadhaar_encrypted", mask_aadhaar)]


def table_to_csv(db: Session, table, tenant_id: str) -> tuple[str, int]:
    """One table's rows for the tenant in scope, as CSV text."""
    columns = [c.name for c in table.c if c.name not in _NEVER_EXPORT]
    derived = _DERIVED.get(table.name, [])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns + derived)

    rows = db.execute(select(*[table.c[name] for name in columns])).all()
    for row in rows:
        values = [_cell(value) for value in row]
        if derived:
            values += _derived_values(table.name, dict(zip(columns, row)), tenant_id)
        writer.writerow(values)
    return buffer.getvalue(), len(rows)


def build_export(db: Session, tenant, include_empty: bool = False) -> bytes:
    """A zip of one CSV per table, plus a README explaining what is inside."""
    manifest = {}
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        with tenant_scope(tenant.id):
            for table in _tenant_tables():
                content, count = table_to_csv(db, table, tenant.id)
                if count == 0 and not include_empty:
                    continue
                # BOM so Excel opens it as UTF-8 rather than mangling names.
                archive.writestr(f"data/{table.name}.csv", "﻿" + content)
                manifest[table.name] = count

        archive.writestr("manifest.json", json.dumps({
            "workspace": tenant.name,
            "slug": tenant.slug,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "tables": manifest,
            "total_rows": sum(manifest.values()),
        }, indent=2))
        archive.writestr("README.txt", _readme(tenant, manifest))

    return buffer.getvalue()


def _readme(tenant, manifest: dict) -> str:
    encrypted_note = (
        "PAN and Aadhaar numbers appear in two forms. The `*_encrypted` columns hold\n"
        "the ciphertext, which needs this workspace's data key to read. The `*_masked`\n"
        "and `*_last4` columns hold the safe-to-read forms. The plaintext is not in\n"
        "this export by design: a file that carries every customer's identity numbers\n"
        "is one lost laptop away from being a breach, and the same values are available\n"
        "individually through the application, where each access is recorded.\n"
    )
    lines = [
        f"Data export for {tenant.name} (/{tenant.slug})",
        "",
        "One CSV per table, under data/. Empty tables are omitted.",
        "JSON columns (custom fields, tags, policy details) are written as JSON text",
        "inside their cell.",
        "",
        encrypted_note,
        "Row counts:",
    ]
    for name, count in sorted(manifest.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {count:>8,}  {name}")
    lines.append("")
    lines.append(f"  {sum(manifest.values()):>8,}  total")
    return "\n".join(lines)
