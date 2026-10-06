#!/usr/bin/env python3
"""Verifikation nach Backfill (f7): Counts, HMAC, decrypt vs. Klartext.

DEK wie backfill (KMH_BACKFILL_DEK / getpass, kein CLI-Argument). Vor f8:
  --require-full --sample 0
"""

from __future__ import annotations

import argparse
import importlib
import random
import sys
from pathlib import Path
from typing import List, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _compare_row(row, master_key: str) -> Tuple[bool, str]:
    from src.services.audit_known_contacts_crypto import (
        contact_email_lookup_hmac,
        decrypt_contact_row,
        normalize_contact_email,
    )

    enc = getattr(row, "encrypted_email", None)
    plain_em = getattr(row, "email_normalized", None) or ""
    plain_name = (getattr(row, "display_name", None) or "").strip()
    enc_name = getattr(row, "encrypted_display_name", None)

    if plain_name and not enc_name:
        return False, "display_name Klartext ohne encrypted_display_name"

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

    if enc_name and plain_name and dec_name.strip() != plain_name:
        return False, "entschlüsselter Anzeigename weicht von Klartext ab"
    if plain_name and not enc_name:
        return False, "display_name Klartext ohne encrypted_display_name"
    return True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="Zufalls-Stichproben (0 = alle Zeilen mit Klartext+Verschlüsselung)",
    )
    parser.add_argument(
        "--require-full",
        action="store_true",
        help="Volle Abdeckung: alle Zeilen, Counts, Name-Verschlüsselung",
    )
    args = parser.parse_args()

    from scripts.kmh_operator_dek import resolve_operator_dek

    master_key = resolve_operator_dek()
    if not master_key:
        print("DEK fehlt (KMH_BACKFILL_DEK oder interaktive Eingabe)", file=sys.stderr)
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
        n_name_plain_no_enc = sum(
            1
            for r in rows
            if (getattr(r, "display_name", None) or "").strip()
            and not getattr(r, "encrypted_display_name", None)
        )

        print(f"user_id={args.user_id} total={n_total}")
        print(
            f"  plain={n_plain} encrypted={n_enc} both={n_both} "
            f"plain_only={n_plain_only} name_plain_without_enc={n_name_plain_no_enc}"
        )

        if n_name_plain_no_enc:
            print(
                f"FAIL: {n_name_plain_no_enc} Zeile(n) mit Klartext-Name ohne "
                "encrypted_display_name",
                file=sys.stderr,
            )
            return 1

        if args.require_full and n_plain_only:
            print(
                f"FAIL: {n_plain_only} Zeile(n) mit Klartext ohne Verschlüsselung",
                file=sys.stderr,
            )
            return 1

        candidates = [
            r
            for r in rows
            if getattr(r, "email_normalized", None)
            and getattr(r, "encrypted_email", None)
        ]
        if not candidates and n_total:
            print("FAIL: keine Zeilen mit Klartext+Verschlüsselung zum Prüfen", file=sys.stderr)
            return 1

        sample_n = args.sample
        if args.require_full:
            sample_n = 0

        if sample_n and sample_n < len(candidates):
            rng = random.SystemRandom()
            check_rows = rng.sample(candidates, sample_n)
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
