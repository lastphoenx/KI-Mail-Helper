"""DEK für Operator-Skripte (Backfill/Verify) — nicht in argv, nicht loggen."""

from __future__ import annotations

import os
import sys


def resolve_operator_dek() -> str:
    """KMH_BACKFILL_DEK oder getpass (TTY). Leer → Abbruch durch Aufrufer."""
    key = (os.environ.get("KMH_BACKFILL_DEK") or "").strip()
    if key:
        return key
    if sys.stdin.isatty():
        import getpass

        key = getpass.getpass(
            "User-DEK Base64 (wie Session master_key nach Login, Eingabe verborgen): "
        ).strip()
        if key:
            return key
    return ""
