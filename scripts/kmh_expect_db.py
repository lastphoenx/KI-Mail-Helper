#!/usr/bin/env python3
"""Prüft die tatsächlich verbundene PostgreSQL-Datenbank (current_database()).

Für Deploy/Drill: --expect-db NAME — bricht ab, wenn die Verbindung woanders hängt.
Lädt keine .env neu; nutzt DATABASE_URL aus der Umgebung wie get_session().
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class ExpectDbMismatch(Exception):
    def __init__(self, actual: str, expected: str) -> None:
        self.actual = actual
        self.expected = expected
        super().__init__(f"{actual}!={expected}")


def current_database_name(session) -> str:
    from sqlalchemy import text

    bind = session.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == "postgresql":
        return str(session.execute(text("SELECT current_database()")).scalar())
    if dialect_name == "sqlite":
        database = bind.url.database
        return database if database else ":memory:"
    raise ExpectDbMismatch(dialect_name, "postgresql")


def check_expect_db(session, expected: str | None) -> None:
    if not (expected or "").strip():
        return
    actual = current_database_name(session)
    if actual != expected:
        raise ExpectDbMismatch(actual, expected)


def fail_exit_code_for_mismatch() -> int:
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-db",
        required=True,
        metavar="NAME",
        help="Abbruch wenn current_database() != NAME",
    )
    args = parser.parse_args()

    from src.helpers.database import get_session

    session = get_session()
    try:
        check_expect_db(session, args.expect_db)
        print(f"OK: current_database() = {args.expect_db}")
        return 0
    except ExpectDbMismatch as exc:
        print(
            f"FEHLER: verbunden mit '{exc.actual}', erwartet '{exc.expected}'",
            file=sys.stderr,
        )
        return fail_exit_code_for_mismatch()
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
