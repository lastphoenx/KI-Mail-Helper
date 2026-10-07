"""Tests: Operator Backfill/Verify + DEK aus Passwort."""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
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
        account_id=10,
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
                account_id=10,
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
                account_id=10,
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


def test_verify_ok_encrypted_only_neuaufbau(monkeypatch, user_with_dek):
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
                id=10,
                account_id=10,
                email_normalized=None,
                display_name=None,
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
    assert stats.plain == 0
    assert stats.encrypted == 1


def test_verify_ok_mixed_plain_and_encrypted_only(monkeypatch, user_with_dek):
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
                id=11,
                account_id=10,
                email_normalized="friend@example.com",
                display_name="Example Friend",
                encrypted_email=enc_email,
                encrypted_display_name=enc_name,
                email_lookup_hmac=hmac_val,
            ),
            _PlainContactRow(
                id=12,
                account_id=10,
                email_normalized=None,
                display_name=None,
                encrypted_email=enc_email,
                encrypted_display_name=enc_name,
                email_lookup_hmac=hmac_val,
            ),
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
    assert stats.plain_only == 0


def test_verify_fails_plain_only(monkeypatch, user_with_dek):
    from src.services.audit_known_contacts_operator import (
        _PlainContactRow,
        run_verify_encryption,
    )

    _, _, dek = user_with_dek
    monkeypatch.setattr(
        "src.services.audit_known_contacts_operator._fetch_plaintext_rows",
        lambda _s, _uid: [
            _PlainContactRow(
                id=13,
                account_id=10,
                email_normalized="orphan@example.com",
                display_name="Orphan",
                encrypted_email=None,
                encrypted_display_name=None,
                email_lookup_hmac=None,
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
    assert stats.plain_only == 1
    assert errors
    assert any("Klartext ohne Verschlüsselung" in e for e in errors)


def test_backfill_merges_plaintext_with_encrypted_duplicate(monkeypatch, user_with_dek):
    from src.services.audit_known_contacts_operator import (
        _PlainContactRow,
        run_backfill_encrypt,
    )

    _, _, dek = user_with_dek
    hmac_val, enc_email, enc_name = encrypt_contact_fields(
        "friend@example.com", "Newer Name", dek
    )
    older = datetime(2020, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2024, 6, 1, tzinfo=timezone.utc)
    encrypted_row = _PlainContactRow(
        id=100,
        account_id=10,
        email_normalized=None,
        display_name=None,
        encrypted_email=enc_email,
        encrypted_display_name=enc_name,
        email_lookup_hmac=hmac_val,
        mail_count=2,
        last_seen_at=older,
    )
    plain_row = _PlainContactRow(
        id=101,
        account_id=10,
        email_normalized="friend@example.com",
        display_name="Legacy Plain",
        encrypted_email=None,
        encrypted_display_name=None,
        email_lookup_hmac=None,
        mail_count=5,
        last_seen_at=newer,
    )
    monkeypatch.setattr(
        "src.services.audit_known_contacts_operator._fetch_plaintext_rows",
        lambda _s, _uid: [encrypted_row, plain_row],
    )

    executed = []

    class FakeSession:
        def execute(self, stmt, params=None):
            executed.append((str(stmt), params))

        def commit(self):
            pass

        def rollback(self):
            pass

    session = FakeSession()
    stats = run_backfill_encrypt(
        session, None, user_id=1, master_key=dek, dry_run=False
    )
    assert stats.merged_duplicates == 1
    assert stats.updated == 0
    deletes = [p for s, p in executed if "DELETE" in s]
    assert any(p and p.get("id") == 101 for p in deletes)
    updates = [p for s, p in executed if "UPDATE" in s and p]
    assert any(p.get("id") == 100 and p.get("mail_count") == 7 for p in updates)
