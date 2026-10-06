"""Operator-Hilfen: DEK aus Masterpasswort, Backfill, Verify (pre-f8)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple


class OperatorDekError(Exception):
    """DEK konnte nicht abgeleitet werden."""


@dataclass
class BackfillStats:
    updated: int = 0
    skipped_encrypted: int = 0
    bad_rows: int = 0


@dataclass
class VerifyStats:
    total: int = 0
    plain: int = 0
    encrypted: int = 0
    both: int = 0
    plain_only: int = 0
    name_plain_without_enc: int = 0
    checked: int = 0
    failures: int = 0


@dataclass
class _PlainContactRow:
    id: int
    email_normalized: Optional[str]
    display_name: Optional[str]
    encrypted_email: Optional[str]
    encrypted_display_name: Optional[str]
    email_lookup_hmac: Optional[str]


def dek_from_master_unlock(user, unlock: str) -> str:
    """DEK wie beim Login — Eingabe nie persistieren."""
    import importlib

    if not (unlock or "").strip():
        raise OperatorDekError("empty_unlock")
    auth = importlib.import_module(".07_auth", "src")
    dek = auth.MasterKeyManager.decrypt_dek_from_password(user, unlock)
    if not dek:
        raise OperatorDekError("decrypt_failed")
    return dek


def _plaintext_columns_present(session) -> bool:
    from sqlalchemy import inspect

    engine = session.get_bind()
    insp = inspect(engine)
    if not insp.has_table("audit_known_contacts"):
        return False
    cols = {c["name"] for c in insp.get_columns("audit_known_contacts")}
    return "email_normalized" in cols


def _fetch_plaintext_rows(session, user_id: int) -> List[_PlainContactRow]:
    from sqlalchemy import text

    if not _plaintext_columns_present(session):
        raise OperatorDekError("plaintext_columns_missing_run_before_f8")
    sql = text(
        """
        SELECT id, email_normalized, display_name,
               encrypted_email, encrypted_display_name, email_lookup_hmac
        FROM audit_known_contacts
        WHERE user_id = :uid
        """
    )
    out: List[_PlainContactRow] = []
    for r in session.execute(sql, {"uid": user_id}).fetchall():
        out.append(
            _PlainContactRow(
                id=int(r[0]),
                email_normalized=r[1],
                display_name=r[2],
                encrypted_email=r[3],
                encrypted_display_name=r[4],
                email_lookup_hmac=r[5],
            )
        )
    return out


def run_backfill_encrypt(
    db_session,
    models,
    *,
    user_id: int,
    master_key: str,
    dry_run: bool = False,
) -> BackfillStats:
    from sqlalchemy import text

    from src.services.audit_known_contacts_crypto import (
        encrypt_contact_fields,
        normalize_contact_email,
    )

    stats = BackfillStats()
    rows = _fetch_plaintext_rows(db_session, user_id)
    update_sql = text(
        """
        UPDATE audit_known_contacts
        SET email_lookup_hmac = :hmac,
            encrypted_email = :enc_email,
            encrypted_display_name = :enc_name
        WHERE id = :id
        """
    )
    for row in rows:
        if row.encrypted_email:
            stats.skipped_encrypted += 1
            continue
        em = normalize_contact_email(row.email_normalized or "")
        if not em:
            stats.bad_rows += 1
            continue
        hmac_val, enc_email, enc_name = encrypt_contact_fields(
            em, row.display_name, master_key
        )
        stats.updated += 1
        if dry_run:
            continue
        db_session.execute(
            update_sql,
            {
                "id": row.id,
                "hmac": hmac_val,
                "enc_email": enc_email,
                "enc_name": enc_name or None,
            },
        )
    if not dry_run and stats.updated and not stats.bad_rows:
        db_session.commit()
    elif stats.bad_rows:
        db_session.rollback()
    return stats


def _verify_compare_row(row: _PlainContactRow, master_key: str) -> Tuple[bool, str]:
    from src.services.audit_known_contacts_crypto import (
        contact_email_lookup_hmac,
        decrypt_contact_row,
        normalize_contact_email,
    )

    plain_name = (row.display_name or "").strip()
    if plain_name and not row.encrypted_display_name:
        return False, "display_name Klartext ohne encrypted_display_name"
    if not row.encrypted_email:
        return False, "encrypted_email fehlt"
    plain_em = row.email_normalized or ""
    if not plain_em:
        return False, "email_normalized fehlt (pre-f8 Transition)"

    norm_plain = normalize_contact_email(plain_em)
    if not norm_plain:
        return False, "email_normalized nicht normalisierbar"

    hmac_expected = contact_email_lookup_hmac(norm_plain, master_key)
    hmac_stored = (row.email_lookup_hmac or "").strip()
    if not hmac_stored or hmac_stored != hmac_expected:
        return False, "email_lookup_hmac stimmt nicht"

    wrapper = type(
        "Row",
        (),
        {
            "encrypted_email": row.encrypted_email,
            "encrypted_display_name": row.encrypted_display_name,
        },
    )()
    dec_em, dec_name = decrypt_contact_row(wrapper, master_key)
    dec_em = normalize_contact_email(dec_em)
    if dec_em != norm_plain:
        return False, "entschlüsselte E-Mail weicht ab"
    if row.encrypted_display_name and plain_name and dec_name.strip() != plain_name:
        return False, "Anzeigename weicht ab"
    return True, "ok"


def run_verify_encryption(
    db_session,
    models,
    *,
    user_id: int,
    master_key: str,
    sample: int = 10,
    require_full: bool = False,
) -> Tuple[VerifyStats, List[str]]:
    stats = VerifyStats()
    errors: List[str] = []
    try:
        rows = _fetch_plaintext_rows(db_session, user_id)
    except OperatorDekError as exc:
        errors.append(str(exc))
        return stats, errors

    stats.total = len(rows)
    stats.plain = sum(1 for r in rows if r.email_normalized)
    stats.encrypted = sum(1 for r in rows if r.encrypted_email)
    stats.both = sum(1 for r in rows if r.email_normalized and r.encrypted_email)
    stats.plain_only = sum(
        1 for r in rows if r.email_normalized and not r.encrypted_email
    )
    stats.name_plain_without_enc = sum(
        1
        for r in rows
        if (r.display_name or "").strip() and not r.encrypted_display_name
    )

    if stats.name_plain_without_enc:
        errors.append(
            f"{stats.name_plain_without_enc} Zeile(n) Klartext-Name ohne Verschlüsselung"
        )
    if require_full and stats.plain_only:
        errors.append(f"{stats.plain_only} Zeile(n) Klartext ohne Verschlüsselung")
    if require_full and stats.plain != stats.encrypted:
        errors.append("Anzahl Klartext != Anzahl verschlüsselt")

    candidates = [r for r in rows if r.email_normalized and r.encrypted_email]
    if not candidates and stats.total:
        errors.append("keine Zeilen mit Klartext+Verschlüsselung")

    sample_n = 0 if require_full else sample
    if sample_n and sample_n < len(candidates):
        check_rows = random.SystemRandom().sample(candidates, sample_n)
    else:
        check_rows = candidates

    for row in check_rows:
        ok, msg = _verify_compare_row(row, master_key)
        if not ok:
            stats.failures += 1
            errors.append(f"id={row.id}: {msg}")
    stats.checked = len(check_rows)
    return stats, errors
