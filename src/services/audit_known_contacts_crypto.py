"""Verschlüsselung + HMAC-Lookup für audit_known_contacts (User-DEK)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Optional, Tuple

from src.services.audit_scam_detection import normalize_sender_email

logger = logging.getLogger(__name__)

_HMAC_INFO = b"ki-mail-helper:audit-known-contact-hmac:v1"


class KnownContactsMasterKeyRequired(Exception):
    """Verschlüsselte Kontakte, aber kein DEK (Session/Service-Token)."""


def _import_encryption():
    from importlib import import_module

    return import_module(".08_encryption", "src")


def contact_email_lookup_hmac(normalized_email: str, master_key: str) -> str:
    """Keyed HMAC für DB-Lookup; Eingabe muss bereits normalize_sender_email sein."""
    em = (normalized_email or "").strip().lower()
    if not em or not master_key:
        return ""
    dek_bytes = base64.b64decode(master_key)
    mac_key = hmac.new(dek_bytes, _HMAC_INFO, hashlib.sha256).digest()
    return hmac.new(mac_key, em.encode("utf-8"), hashlib.sha256).hexdigest()


def normalize_contact_email(raw: str) -> str:
    return normalize_sender_email(raw or "")


def encrypt_contact_fields(
    email: str,
    display_name: Optional[str],
    master_key: str,
) -> Tuple[str, str, str]:
    """Returns (email_lookup_hmac, encrypted_email, encrypted_display_name)."""
    enc = _import_encryption()
    em = normalize_contact_email(email)
    if not em:
        raise ValueError("empty contact email")
    hmac_val = contact_email_lookup_hmac(em, master_key)
    encrypted_email = enc.CredentialManager.encrypt_email_address(em, master_key)
    name = (display_name or "").strip()
    encrypted_name = ""
    if name:
        encrypted_name = enc.EncryptionManager.encrypt_data(name, master_key)
    return hmac_val, encrypted_email, encrypted_name


def decrypt_contact_row(row, master_key: str) -> Tuple[str, str]:
    """(email, display_name) — legacy Klartext oder encrypted_*."""
    enc_mod = _import_encryption()
    enc_email = getattr(row, "encrypted_email", None)
    if enc_email:
        em = enc_mod.CredentialManager.decrypt_email_address(enc_email, master_key)
        enc_name = getattr(row, "encrypted_display_name", None)
        name = ""
        if enc_name:
            name = enc_mod.EncryptionManager.decrypt_data(enc_name, master_key)
        return em, name
    legacy_em = getattr(row, "email_normalized", None) or ""
    legacy_name = getattr(row, "display_name", None) or ""
    return legacy_em, legacy_name


def row_requires_master_key(row) -> bool:
    return bool(getattr(row, "encrypted_email", None))


def account_has_encrypted_known_contacts(db_session, models, user_id: int, account_id: int) -> bool:
    if not hasattr(models, "AuditKnownContact"):
        return False
    q = (
        db_session.query(models.AuditKnownContact.id)
        .filter(
            models.AuditKnownContact.user_id == user_id,
            models.AuditKnownContact.account_id == account_id,
            models.AuditKnownContact.is_active.is_(True),
            models.AuditKnownContact.encrypted_email.isnot(None),
        )
        .limit(1)
    )
    return q.first() is not None
