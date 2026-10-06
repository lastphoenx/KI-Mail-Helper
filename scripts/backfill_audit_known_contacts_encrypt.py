#!/usr/bin/env python3
"""Backfill: audit_known_contacts Klartext → encrypted_* + email_lookup_hmac.

Benötigt User-DEK (Argument oder interaktiv). Nur nach Alembic f7a8b9c0d1e2.
Vor Drop der Klartext-Spalten ausführen; DB-Backup zuerst (Operator).
"""

from __future__ import annotations

import argparse
import importlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument(
        "--dek-base64",
        help="Benutzer-DEK (Base64), sonst aus Umgebung KMH_BACKFILL_DEK",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    master_key = args.dek_base64 or __import__("os").environ.get("KMH_BACKFILL_DEK")
    if not master_key:
        print("DEK fehlt (--dek-base64 oder KMH_BACKFILL_DEK)", file=sys.stderr)
        return 2

    from src.helpers.database import get_session

    from src.services.audit_known_contacts_crypto import (
        encrypt_contact_fields,
        normalize_contact_email,
        row_requires_master_key,
    )

    session = get_session()
    models = importlib.import_module(".02_models", "src")
    try:
        rows = (
            session.query(models.AuditKnownContact)
            .filter(models.AuditKnownContact.user_id == args.user_id)
            .all()
        )
        updated = 0
        skipped = 0
        for row in rows:
            if row_requires_master_key(row):
                skipped += 1
                continue
            em_raw = row.email_normalized or ""
            em = normalize_contact_email(em_raw)
            if not em:
                continue
            hmac_val, enc_email, enc_name = encrypt_contact_fields(
                em, row.display_name, master_key
            )
            if args.dry_run:
                updated += 1
                continue
            row.email_lookup_hmac = hmac_val
            row.encrypted_email = enc_email
            row.encrypted_display_name = enc_name or None
            row.email_normalized = None
            row.display_name = None
            updated += 1
        if not args.dry_run:
            session.commit()
        print(f"user_id={args.user_id} updated={updated} already_encrypted={skipped}")
        return 0
    except Exception as exc:
        session.rollback()
        print(f"backfill failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
