"""Operator-Hilfen: DEK aus Masterpasswort, Backfill, Verify (pre-f8)."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class OperatorDekError(Exception):
    """DEK konnte nicht abgeleitet werden."""


@dataclass
class BackfillStats:
    updated: int = 0
    skipped_encrypted: int = 0
    merged_duplicates: int = 0
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
    account_id: int
    email_normalized: Optional[str]
    display_name: Optional[str]
    encrypted_email: Optional[str]
    encrypted_display_name: Optional[str]
    email_lookup_hmac: Optional[str]
    mail_count: int = 1
    last_seen_at: Optional[datetime] = None


def _row_last_seen(row: _PlainContactRow) -> datetime:
    return row.last_seen_at or datetime.min


def _group_key_hmac(
    row: _PlainContactRow, master_key: str, normalize_contact_email, contact_email_lookup_hmac
) -> Optional[Tuple[int, str]]:
    hmac_stored = (row.email_lookup_hmac or "").strip()
    if hmac_stored:
        return row.account_id, hmac_stored
    em = normalize_contact_email(row.email_normalized or "")
    if not em:
        return None
    return row.account_id, contact_email_lookup_hmac(em, master_key)


def dek_from_master_unlock(user, unlock: str, session=None) -> str:
    """DEK wie beim Login — Eingabe nie persistieren."""
    import importlib

    if not (unlock or "").strip():
        raise OperatorDekError("empty_unlock")
    auth = importlib.import_module(".07_auth", "src")
    dek = auth.MasterKeyManager.decrypt_dek_from_password(user, unlock, session)
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
        SELECT id, account_id, email_normalized, display_name,
               encrypted_email, encrypted_display_name, email_lookup_hmac,
               mail_count, last_seen_at
        FROM audit_known_contacts
        WHERE user_id = :uid
        """
    )
    out: List[_PlainContactRow] = []
    for r in session.execute(sql, {"uid": user_id}).fetchall():
        out.append(
            _PlainContactRow(
                id=int(r[0]),
                account_id=int(r[1]),
                email_normalized=r[2],
                display_name=r[3],
                encrypted_email=r[4],
                encrypted_display_name=r[5],
                email_lookup_hmac=r[6],
                mail_count=int(r[7] or 1),
                last_seen_at=r[8],
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
        contact_email_lookup_hmac,
        encrypt_contact_fields,
        normalize_contact_email,
    )

    stats = BackfillStats()
    rows = _fetch_plaintext_rows(db_session, user_id)
    delete_sql = text("DELETE FROM audit_known_contacts WHERE id = :id")
    update_encrypt_sql = text(
        """
        UPDATE audit_known_contacts
        SET email_lookup_hmac = :hmac,
            encrypted_email = :enc_email,
            encrypted_display_name = :enc_name,
            mail_count = :mail_count
        WHERE id = :id
        """
    )
    update_merge_sql = text(
        """
        UPDATE audit_known_contacts
        SET mail_count = :mail_count,
            encrypted_display_name = :enc_name,
            last_seen_at = :last_seen_at
        WHERE id = :id
        """
    )

    groups: Dict[Tuple[int, str], List[_PlainContactRow]] = defaultdict(list)
    for row in rows:
        key = _group_key_hmac(
            row, master_key, normalize_contact_email, contact_email_lookup_hmac
        )
        if key is None:
            stats.bad_rows += 1
            continue
        groups[key].append(row)

    for _key, members in groups.items():
        if len(members) == 1 and members[0].encrypted_email:
            stats.skipped_encrypted += 1
            continue

        canonical = max(
            members,
            key=lambda r: (
                1 if r.encrypted_email else 0,
                _row_last_seen(r),
                r.id,
            ),
        )
        name_row = max(members, key=lambda r: (_row_last_seen(r), r.id))
        display_name = name_row.display_name
        total_mail = sum(int(m.mail_count or 1) for m in members)
        dup_ids = [m.id for m in members if m.id != canonical.id]

        if dup_ids:
            stats.merged_duplicates += len(dup_ids)
        if not canonical.encrypted_email:
            stats.updated += 1

        em = normalize_contact_email(canonical.email_normalized or "")
        if not em:
            for m in members:
                em = normalize_contact_email(m.email_normalized or "")
                if em:
                    break
        if not em and not canonical.encrypted_email:
            stats.bad_rows += 1
            continue

        if dry_run:
            continue

        if not canonical.encrypted_email:
            hmac_val, enc_email, enc_name = encrypt_contact_fields(
                em, display_name, master_key
            )
        else:
            hmac_val = (canonical.email_lookup_hmac or "").strip()
            enc_email = canonical.encrypted_email
            if em and (display_name or "").strip():
                _, _, enc_name = encrypt_contact_fields(em, display_name, master_key)
            else:
                enc_name = canonical.encrypted_display_name

        for dup_id in dup_ids:
            db_session.execute(delete_sql, {"id": dup_id})

        last_seen = max(_row_last_seen(m) for m in members)

        if not canonical.encrypted_email:
            db_session.execute(
                update_encrypt_sql,
                {
                    "id": canonical.id,
                    "hmac": hmac_val,
                    "enc_email": enc_email,
                    "enc_name": enc_name or None,
                    "mail_count": total_mail,
                },
            )
        else:
            db_session.execute(
                update_merge_sql,
                {
                    "id": canonical.id,
                    "mail_count": total_mail,
                    "enc_name": enc_name or canonical.encrypted_display_name,
                    "last_seen_at": last_seen,
                },
            )

    if not dry_run and (stats.updated or stats.merged_duplicates) and not stats.bad_rows:
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

    hmac_stored = (row.email_lookup_hmac or "").strip()
    if not hmac_stored:
        return False, "email_lookup_hmac fehlt"

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
    if not dec_em:
        return False, "entschlüsselte E-Mail leer"

    hmac_expected = contact_email_lookup_hmac(dec_em, master_key)
    if hmac_stored != hmac_expected:
        return False, "email_lookup_hmac stimmt nicht"

    plain_em = row.email_normalized or ""
    if plain_em:
        norm_plain = normalize_contact_email(plain_em)
        if not norm_plain:
            return False, "email_normalized nicht normalisierbar"
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
    expect_min: Optional[int] = None,
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
    if require_full and expect_min is not None and stats.total < expect_min:
        errors.append(
            f"keine oder zu wenige Kontakte (total={stats.total}, erwartet mindestens {expect_min})"
        )

    candidates = [r for r in rows if r.encrypted_email]
    if require_full and stats.total and not candidates:
        errors.append("keine verschlüsselten Zeilen")

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
