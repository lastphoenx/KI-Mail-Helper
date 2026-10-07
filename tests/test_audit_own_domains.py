"""Tests: Meine Domains parsen/validieren."""

from src.services.audit_own_domains import clean_own_domains_for_save, expand_own_domain_tokens


def test_expand_splits_comma_semicolon_whitespace():
    raw = ["a.example.test, b.example.test", "c.example.test; d.example.test\ne.example.test"]
    assert expand_own_domain_tokens(raw) == [
        "a.example.test",
        "b.example.test",
        "c.example.test",
        "d.example.test",
        "e.example.test",
    ]


def test_clean_accepts_valid_domains():
    cleaned, errors = clean_own_domains_for_save(
        ["shop.example.test, mail.example.test", "cloud.example.test"]
    )
    assert not errors
    assert cleaned == ["shop.example.test", "mail.example.test", "cloud.example.test"]


def test_clean_rejects_comma_only_single_invalid():
    cleaned, errors = clean_own_domains_for_save(["a.example.test, b.example.test, nodot"])
    assert not cleaned or "nodot" not in cleaned
    assert errors
    assert any("nodot" in e for e in errors)


def test_clean_rejects_whitespace_in_token():
    _, errors = clean_own_domains_for_save(["bad space.example.test"])
    assert errors
