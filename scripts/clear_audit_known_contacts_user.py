#!/usr/bin/env python3
"""Kontakte eines Users leeren inkl. audit_contacts_import_state (Neuaufbau nach f7)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument(
        "--expect-db",
        metavar="NAME",
        help="Abbruch wenn current_database() != NAME",
    )
    args = parser.parse_args()

    from src.helpers.database import get_session
    from src.services.audit_contact_import import clear_known_contacts_for_user

    from scripts.kmh_expect_db import ExpectDbMismatch, check_expect_db, fail_exit_code_for_mismatch

    session = get_session()
    try:
        check_expect_db(session, args.expect_db)
    except ExpectDbMismatch as exc:
        print(
            f"FEHLER: verbunden mit '{exc.actual}', erwartet '{exc.expected}'",
            file=sys.stderr,
        )
        session.close()
        return fail_exit_code_for_mismatch()

    try:
        removed = clear_known_contacts_for_user(session, args.user_id)
        print(
            f"user_id={args.user_id} removed_contacts={removed} "
            f"import_state_reset=all_mail_accounts"
        )
        return 0
    except Exception:
        session.rollback()
        print("clear failed", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
