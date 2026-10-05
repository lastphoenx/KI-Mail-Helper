"""DEK at rest in service_tokens — AES-GCM mit app-spezifischem Key (nicht Zero-Knowledge)."""

from __future__ import annotations

import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

_PREFIX = "stenc1:"


def _dek_encryption_key() -> bytes:
    app_secret_key = (os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY") or "").strip()
    if not app_secret_key:
        raise ValueError("SECRET_KEY fehlt — Service-Token-DEK kann nicht verschlüsselt werden")
    return hashlib.sha256(b"ki-mail-helper:service-token-dek:v1:" + app_secret_key.encode()).digest()


def encrypt_service_token_dek(dek: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not dek:
        return dek
    nonce = os.urandom(12)
    ct = AESGCM(_dek_encryption_key()).encrypt(nonce, dek.encode("utf-8"), None)
    blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    return _PREFIX + blob


def decrypt_service_token_dek(stored: str) -> str:
    if not stored:
        return stored
    if not stored.startswith(_PREFIX):
        return stored
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.urlsafe_b64decode(stored[len(_PREFIX) :].encode("ascii"))
    nonce, ct = raw[:12], raw[12:]
    plain = AESGCM(_dek_encryption_key()).decrypt(nonce, ct, None)
    return plain.decode("utf-8")
