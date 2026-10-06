#!/usr/bin/env python3
"""Backfill: audit_known_contacts Klartext → encrypted_* + email_lookup_hmac.

DEK: Umgebungsvariable KMH_BACKFILL_DEK oder versteckte Eingabe (kein CLI-Argument).
Der Wert entspricht dem Session-DEK (master_key) nach Login — nur in der Shell setzen,
nicht in .env committen. Alternative: Kontakt-Import über UI + Service-Token (Celery).

Nur nach Alembic f7a8b9c0d1e2. Klartext-Spalten bleiben bis f8. Vor Backfill: pg_dump.
Nach Backfill: verify mit --require-full --sample 0
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from scripts.kmh_operator_dek import resolve_operator_dek

    master_key = resolve_operator_dek()
    if not master_key:
        print(
            "DEK fehlt: export KMH_BACKFILL_DEK=… (nur diese Shell) "
            "oder interaktiv getpass",
            file=sys.stderr,
        )
        return 2

    from src.helpers.database import get_session

    from src.services.audit_known_contacts_crypto import (
        encrypt_contact_fields,
        normalize_contact_email,
        row_requires_master_key,
    )

    session = get_session()
    models = importlib.import_module(".02_models", "src")
    bad_rows = 0
    updated = 0
    skipped = 0
    try:
        rows = (
            session.query(models.AuditKnownContact)
            .filter(models.AuditKnownContact.user_id == args.user_id)
            .all()
        )
        for row in rows:
            if row_requires_master_key(row):
                skipped += 1
                continue
            em_raw = row.email_normalized or ""
            em = normalize_contact_email(em_raw)
            if not em:
                print(
                    f"backfill: Zeile id={row.id} ohne normalisierbare E-Mail — Abbruch",
                    file=sys.stderr,
                )
                bad_rows += 1
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
            updated += 1
        if bad_rows:
            session.rollback()
            return 1
        if not args.dry_run and updated:
            session.commit()
        print(
            f"user_id={args.user_id} updated={updated} already_encrypted={skipped} "
            f"dry_run={args.dry_run}"
        )
        return 0
    except Exception as exc:
        session.rollback()
        print(f"backfill failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
