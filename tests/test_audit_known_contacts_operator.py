"""Tests: Operator Backfill/Verify + DEK aus Passwort."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from src.services.audit_known_contacts_crypto import encrypt_contact_fields
from src.services.audit_known_contacts_operator import (
    OperatorDekError,
    dek_from_master_unlock,
    run_backfill_encrypt,
    run_verify_encryption,
)


@pytest.fixture
def enc_mod():
    return importlib.import_module(".08_encryption", "src")


@pytest.fixture
def user_with_dek(enc_mod):
    unlock_phrase = "TestPhase2-Only-Example"
    salt = enc_mod.EncryptionManager.generate_salt()
    kek = enc_mod.EncryptionManager.generate_master_key(unlock_phrase, salt)
    dek = enc_mod.EncryptionManager.generate_dek()
    encrypted_dek = enc_mod.EncryptionManager.encrypt_dek(dek, kek)
    user = SimpleNamespace(
        id=1,
        salt=salt,
        encrypted_dek=encrypted_dek,
        encrypted_master_key=None,
    )
    return user, unlock_phrase, dek


def test_dek_from_master_unlock_roundtrip(user_with_dek):
    user, unlock, expected_dek = user_with_dek
    dek = dek_from_master_unlock(user, unlock)
    assert dek == expected_dek


def test_dek_from_master_unlock_wrong(user_with_dek):
    user, _, _ = user_with_dek
    with pytest.raises(OperatorDekError):
        dek_from_master_unlock(user, "wrong-unlock-example")


def test_backfill_encrypts_plaintext_row(monkeypatch, user_with_dek):
    from src.services.audit_known_contacts_operator import (
        _PlainContactRow,
        run_backfill_encrypt,
    )

    _, _, dek = user_with_dek
    plain = _PlainContactRow(
        id=1,
        email_normalized="friend@example.com",
        display_name="Example Friend",
        encrypted_email=None,
        encrypted_display_name=None,
        email_lookup_hmac=None,
    )
    monkeypatch.setattr(
        "src.services.audit_known_contacts_operator._fetch_plaintext_rows",
        lambda _s, _uid: [plain],
    )

    class FakeSession:
        def __init__(self):
            self.executed = False
            self.committed = False

        def execute(self, *args, **kwargs):
            self.executed = True

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

    session = FakeSession()
    stats = run_backfill_encrypt(
        session, None, user_id=1, master_key=dek, dry_run=False
    )
    assert stats.updated == 1
    assert stats.bad_rows == 0
    assert session.executed
    assert session.committed


def test_verify_detects_name_plain_without_encryption(monkeypatch, user_with_dek):
    from src.services.audit_known_contacts_operator import (
        _PlainContactRow,
        run_verify_encryption,
    )

    _, _, dek = user_with_dek
    hmac_val, enc_email, _enc_name = encrypt_contact_fields(
        "friend@example.com", "Example Friend", dek
    )
    monkeypatch.setattr(
        "src.services.audit_known_contacts_operator._fetch_plaintext_rows",
        lambda _s, _uid: [
            _PlainContactRow(
                id=2,
                email_normalized="friend@example.com",
                display_name="Example Friend",
                encrypted_email=enc_email,
                encrypted_display_name=None,
                email_lookup_hmac=hmac_val,
            )
        ],
    )

    stats, errors = run_verify_encryption(
        object(),
        None,
        user_id=1,
        master_key=dek,
        require_full=True,
        sample=0,
    )
    assert stats.name_plain_without_enc == 1
    assert errors


def test_verify_ok_when_fully_encrypted(monkeypatch, user_with_dek):
    from src.services.audit_known_contacts_operator import (
        _PlainContactRow,
        run_verify_encryption,
    )

    _, _, dek = user_with_dek
    hmac_val, enc_email, enc_name = encrypt_contact_fields(
        "friend@example.com", "Example Friend", dek
    )
    monkeypatch.setattr(
        "src.services.audit_known_contacts_operator._fetch_plaintext_rows",
        lambda _s, _uid: [
            _PlainContactRow(
                id=3,
                email_normalized="friend@example.com",
                display_name="Example Friend",
                encrypted_email=enc_email,
                encrypted_display_name=enc_name,
                email_lookup_hmac=hmac_val,
            )
        ],
    )

    stats, errors = run_verify_encryption(
        object(),
        None,
        user_id=1,
        master_key=dek,
        require_full=True,
        sample=0,
    )
    assert not errors
    assert stats.failures == 0
