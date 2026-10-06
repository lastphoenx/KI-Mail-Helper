#!/usr/bin/env python3
"""Verifikation nach Backfill (pre-f8). Masterpasswort wie backfill.

Vor f8: --require-full --sample 0
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
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="Stichprobe (0 = alle; bei --require-full immer alle)",
    )
    parser.add_argument("--require-full", action="store_true")
    parser.add_argument(
        "--expect-db",
        metavar="NAME",
        help="Abbruch wenn current_database() != NAME (Deploy/Drill)",
    )
    args = parser.parse_args()

    from src.helpers.database import get_session
    from src.services.audit_known_contacts_operator import (
        OperatorDekError,
        run_verify_encryption,
    )

    from scripts.kmh_expect_db import ExpectDbMismatch, check_expect_db, fail_exit_code_for_mismatch
    from scripts.kmh_operator_dek import resolve_dek_for_user_id

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
    models = importlib.import_module(".02_models", "src")
    try:
        master_key = resolve_dek_for_user_id(session, args.user_id)
    except OperatorDekError as exc:
        print(f"DEK: {exc}", file=sys.stderr)
        return 2

    try:
        stats, errors = run_verify_encryption(
            session,
            models,
            user_id=args.user_id,
            master_key=master_key,
            sample=args.sample,
            require_full=args.require_full,
        )
        print(
            f"user_id={args.user_id} total={stats.total} plain={stats.plain} "
            f"encrypted={stats.encrypted} both={stats.both} "
            f"plain_only={stats.plain_only} "
            f"name_plain_without_enc={stats.name_plain_without_enc}"
        )
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        print(f"  checked={stats.checked} failures={stats.failures}")
        if errors or stats.failures:
            return 1
        print("OK")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
