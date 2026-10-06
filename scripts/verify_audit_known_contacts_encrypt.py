#!/usr/bin/env python3
"""Verifikation nach Backfill (f7): Counts, HMAC, Stichproben decrypt vs. Klartext.

DEK erforderlich. Vor Alembic f8 ausführen. Exit 0 = ok, 1 = Fehler, 2 = kein DEK.
"""

from __future__ import annotations

import argparse
import importlib
import random
import sys
from typing import List, Tuple


def _compare_row(row, master_key: str) -> Tuple[bool, str]:
    from src.services.audit_known_contacts_crypto import (
        contact_email_lookup_hmac,
        decrypt_contact_row,
        normalize_contact_email,
    )

    enc = getattr(row, "encrypted_email", None)
    plain_em = getattr(row, "email_normalized", None) or ""
    if not enc:
        return False, "encrypted_email fehlt"
    if not plain_em:
        return False, "email_normalized fehlt (Backfill/Transition: beides erwartet vor f8)"

    norm_plain = normalize_contact_email(plain_em)
    if not norm_plain:
        return False, "email_normalized nicht normalisierbar"

    hmac_expected = contact_email_lookup_hmac(norm_plain, master_key)
    hmac_stored = (getattr(row, "email_lookup_hmac", None) or "").strip()
    if not hmac_stored or hmac_stored != hmac_expected:
        return False, "email_lookup_hmac stimmt nicht (Normalisierung/DEK?)"

    dec_em, dec_name = decrypt_contact_row(row, master_key)
    dec_em = normalize_contact_email(dec_em)
    if dec_em != norm_plain:
        return False, "entschlüsselte E-Mail weicht von Klartext ab"

    plain_name = (getattr(row, "display_name", None) or "").strip()
    enc_name = getattr(row, "encrypted_display_name", None)
    if enc_name and plain_name and dec_name.strip() != plain_name:
        return False, "entschlüsselter Anzeigename weicht von Klartext ab"
    if enc_name and not plain_name and dec_name.strip():
        pass
    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument(
        "--dek-base64",
        help="Benutzer-DEK (Base64), sonst KMH_BACKFILL_DEK",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="Zufalls-Stichproben (0 = alle Zeilen prüfen)",
    )
    parser.add_argument(
        "--require-full",
        action="store_true",
        help="Jede Zeile mit Klartext muss encrypted_* + HMAC haben",
    )
    args = parser.parse_args()

    master_key = args.dek_base64 or __import__("os").environ.get("KMH_BACKFILL_DEK")
    if not master_key:
        print("DEK fehlt (--dek-base64 oder KMH_BACKFILL_DEK)", file=sys.stderr)
        return 2

    from src.helpers.database import get_session

    session = get_session()
    models = importlib.import_module(".02_models", "src")
    try:
        rows: List = (
            session.query(models.AuditKnownContact)
            .filter(models.AuditKnownContact.user_id == args.user_id)
            .all()
        )
        n_total = len(rows)
        n_plain = sum(1 for r in rows if getattr(r, "email_normalized", None))
        n_enc = sum(1 for r in rows if getattr(r, "encrypted_email", None))
        n_both = sum(
            1
            for r in rows
            if getattr(r, "email_normalized", None)
            and getattr(r, "encrypted_email", None)
        )
        n_plain_only = sum(
            1
            for r in rows
            if getattr(r, "email_normalized", None)
            and not getattr(r, "encrypted_email", None)
        )
        n_enc_only = sum(
            1
            for r in rows
            if getattr(r, "encrypted_email", None)
            and not getattr(r, "email_normalized", None)
        )

        print(f"user_id={args.user_id} total={n_total}")
        print(
            f"  plain={n_plain} encrypted={n_enc} both={n_both} "
            f"plain_only={n_plain_only} enc_only={n_enc_only}"
        )

        if args.require_full and n_plain_only:
            print(
                f"FAIL: {n_plain_only} Zeile(n) mit Klartext ohne Verschlüsselung",
                file=sys.stderr,
            )
            return 1
        if n_plain and n_enc and n_both != n_plain:
            print(
                "WARN: nicht jede Klartext-Zeile hat encrypted_* (both != plain)",
                file=sys.stderr,
            )

        candidates = [
            r
            for r in rows
            if getattr(r, "email_normalized", None)
            and getattr(r, "encrypted_email", None)
        ]
        if not candidates and n_total:
            print("FAIL: keine Zeilen mit Klartext+Verschlüsselung zum Prüfen", file=sys.stderr)
            return 1

        if args.sample and args.sample < len(candidates):
            rng = random.SystemRandom()
            check_rows = rng.sample(candidates, args.sample)
        else:
            check_rows = candidates

        failures = 0
        for row in check_rows:
            ok, msg = _compare_row(row, master_key)
            if not ok:
                failures += 1
                print(f"  id={row.id}: {msg}", file=sys.stderr)

        print(f"  checked={len(check_rows)} failures={failures}")
        if failures:
            return 1

        if args.require_full and n_plain != n_enc:
            print("FAIL: Anzahl Klartext != Anzahl verschlüsselt", file=sys.stderr)
            return 1

        print("OK")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
