"""Tests: Meine Domains parsen/validieren."""

from src.services.audit_own_domains import (
    clean_own_domains_for_save,
    expand_own_domain_tokens,
    own_domains_set_from_items,
)


def test_expand_splits_comma_semicolon_whitespace():
    raw = ["a.example.com, b.example.org", "c.example.com; d.example.com\ne.example.com"]
    assert expand_own_domain_tokens(raw) == [
        "a.example.com",
        "b.example.org",
        "c.example.com",
        "d.example.com",
        "e.example.com",
    ]


def test_clean_accepts_valid_public_domains():
    cleaned, errors = clean_own_domains_for_save(
        ["shop.example.com, mail.example.org", "cloud.example.com"]
    )
    assert not errors
    assert cleaned == ["shop.example.com", "mail.example.org", "cloud.example.com"]


def test_clean_accepts_homelab_suffixes():
    cleaned, errors = clean_own_domains_for_save(
        ["pve2.localdomain", "nas.lan", "host.local", "gw.home.arpa"]
    )
    assert not errors
    assert cleaned == ["pve2.localdomain", "nas.lan", "host.local", "gw.home.arpa"]


def test_set_from_items_splits_legacy_comma_json():
    assert own_domains_set_from_items(["shop.example.com, mail.example.org"]) == {
        "shop.example.com",
        "mail.example.org",
    }


def test_clean_rejects_comma_only_single_invalid():
    cleaned, errors = clean_own_domains_for_save(["a.example.com, b.example.com, nodot"])
    assert not cleaned or "nodot" not in cleaned
    assert errors
    assert any("nodot" in e for e in errors)


def test_clean_rejects_whitespace_in_token():
    _, errors = clean_own_domains_for_save(["bad space.example.com"])
    assert errors
