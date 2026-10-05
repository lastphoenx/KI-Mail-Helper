"""Security hardening helpers (audit fixes)."""

import pytest


def test_sanitize_log_field_strips_newlines():
    from src.helpers.security_log import sanitize_log_field

    assert "\n" not in sanitize_log_field("admin\nSECURITY[LOGIN_FAILED]")
    assert sanitize_log_field("  user  ") == "user"


def test_service_token_dek_roundtrip(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key-for-dek-storage")
    from src.helpers.service_token_storage import (
        decrypt_service_token_dek,
        encrypt_service_token_dek,
    )

    plain = "0" * 64
    enc = encrypt_service_token_dek(plain)
    assert enc.startswith("stenc1:")
    assert decrypt_service_token_dek(enc) == plain
    assert decrypt_service_token_dek(plain) == plain  # legacy plaintext


def test_assert_safe_mail_host_blocks_loopback():
    from src.helpers.network_safety import UnsafeMailHostError, assert_safe_mail_host

    with pytest.raises(UnsafeMailHostError):
        assert_safe_mail_host("127.0.0.1")
