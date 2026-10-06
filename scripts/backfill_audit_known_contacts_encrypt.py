#!/usr/bin/env python3
"""Backfill: audit_known_contacts Klartext → encrypted_* (pre-f8).

Masterpasswort interaktiv — DEK wird wie beim Login abgeleitet (kein Export, kein --dek).
Nur nach Alembic f7. Klartext-Spalten bleiben bis f8. Vorher pg_dump auf CT.
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

    from src.helpers.database import get_session
    from src.services.audit_known_contacts_operator import OperatorDekError, run_backfill_encrypt

    from scripts.kmh_operator_dek import resolve_dek_for_user_id

    session = get_session()
    models = importlib.import_module(".02_models", "src")
    try:
        master_key = resolve_dek_for_user_id(session, args.user_id)
    except OperatorDekError as exc:
        print(f"DEK: {exc}", file=sys.stderr)
        return 2

    try:
        stats = run_backfill_encrypt(
            session,
            models,
            user_id=args.user_id,
            master_key=master_key,
            dry_run=args.dry_run,
        )
        if stats.bad_rows:
            print(
                f"backfill: {stats.bad_rows} Zeile(n) ohne normalisierbare E-Mail",
                file=sys.stderr,
            )
            return 1
        print(
            f"user_id={args.user_id} updated={stats.updated} "
            f"already_encrypted={stats.skipped_encrypted} dry_run={args.dry_run}"
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
