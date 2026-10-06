"""Tests für audit_known_contacts Verschlüsselung (nur .example-Adressen)."""

from importlib import import_module

import pytest

from src.services.audit_known_contacts import (
    KnownContactContext,
    load_known_contact_context,
)
from src.services.audit_known_contacts_crypto import (
    KnownContactsMasterKeyRequired,
    contact_email_lookup_hmac,
    decrypt_contact_row,
    encrypt_contact_fields,
    normalize_contact_email,
    row_requires_master_key,
)
from src.services.audit_scam_detection import normalize_sender_email


@pytest.fixture
def dek():
    enc = import_module(".08_encryption", "src")
    return enc.EncryptionManager.generate_dek()


def test_hmac_uses_same_normalization_as_scam_detection(dek):
    raw = "  User.Name@Example.COM  "
    em = normalize_contact_email(raw)
    assert em == normalize_sender_email(raw)
    h1 = contact_email_lookup_hmac(em, dek)
    h2 = contact_email_lookup_hmac(normalize_sender_email(raw), dek)
    assert h1 == h2
    assert len(h1) == 64


def test_encrypt_roundtrip(dek):
    email = "friend@example.com"
    name = "Example Friend"
    hmac_val, enc_email, enc_name = encrypt_contact_fields(email, name, dek)
    assert hmac_val
    assert enc_email
    assert enc_name

    class Row:
        encrypted_email = enc_email
        encrypted_display_name = enc_name

    assert row_requires_master_key(Row())
    em_out, name_out = decrypt_contact_row(Row(), dek)
    assert em_out == normalize_sender_email(email)
    assert name_out == name


def test_load_context_encrypted_without_dek_raises():
    class EncRow:
        encrypted_email = "enc:stub"
        mail_count = 1
        source = "sent"
        is_active = True

    class FakeQuery:
        def filter(self, *a, **k):
            return self

        def all(self):
            return [EncRow()]

    class FakeSession:
        def query(self, model):
            return FakeQuery()

    with pytest.raises(KnownContactsMasterKeyRequired):
        load_known_contact_context(FakeSession(), user_id=1, account_id=2, master_key=None)


def test_load_context_decrypts_with_dek(dek):
    hmac_val, enc_email, enc_name = encrypt_contact_fields(
        "friend@example.com", "Example Friend", dek
    )

    class EncRow:
        encrypted_email = enc_email
        encrypted_display_name = enc_name
        mail_count = 2
        source = "sent"
        is_active = True

    class FakeQuery:
        def filter(self, *a, **k):
            return self

        def all(self):
            return [EncRow()]

    class FakeSession:
        def query(self, model):
            return FakeQuery()

    ctx = load_known_contact_context(
        FakeSession(), user_id=1, account_id=2, master_key=dek
    )
    assert isinstance(ctx, KnownContactContext)
    assert "friend@example.com" in ctx.trusted_emails
