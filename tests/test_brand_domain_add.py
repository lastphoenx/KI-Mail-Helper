"""Marken-Domain ergänzen (add, kein Full-Replace)."""

import secrets

import pytest

from src.services.brand_domain_policy import (
    add_domain_to_custom_brand_map,
    validate_brand_map,
)


def _token() -> str:
    return "zw" + secrets.token_hex(4)


def test_add_domain_preserves_other_brands():
    other = _token()
    dom_a = f"{_token()}.example"
    dom_b = f"{_token()}.example"
    dom_new = f"{_token()}.example"
    start = {other: [dom_a], "paypal": ["paypal.com"]}
    merged, added = add_domain_to_custom_brand_map(start, "paypal", dom_new)
    assert added is True
    assert set(merged[other]) == {dom_a}
    assert dom_new in merged["paypal"]
    assert "paypal.com" in merged["paypal"]


def test_add_domain_idempotent_duplicate():
    brand = "twint"
    dom = f"news.{_token()}.example"
    start = {brand: [dom]}
    merged, added = add_domain_to_custom_brand_map(start, brand, dom)
    assert added is False
    assert merged[brand] == [dom]


def test_add_domain_rejects_invalid():
    with pytest.raises(ValueError, match="Ungültige Domain"):
        add_domain_to_custom_brand_map({}, "paypal", "ch")


def test_add_domain_rejects_short_brand():
    with pytest.raises(ValueError, match="Ungültiger Markenname"):
        add_domain_to_custom_brand_map({}, "ab", "paypal.com")


def test_add_domain_normalizes_brand_key():
    dom = f"{_token()}.example"
    merged, _ = add_domain_to_custom_brand_map({}, "Swiss", dom)
    assert "swiss" in merged
    assert dom in merged["swiss"]


def test_prepare_save_surfaces_dbl_errors(monkeypatch):
    from src.services.brand_domain_health import prepare_save_brand_map

    def _fake_validate(cleaned, **kwargs):
        return (["Spamhaus DBL: evil.example"], [])

    monkeypatch.setattr(
        "src.services.brand_domain_health.validate_official_domains_for_save",
        _fake_validate,
    )
    proposed = {"paypal": ["evil.example"]}
    _, errors, _, _, _ = prepare_save_brand_map(
        proposed,
        [],
        run_live_checks=True,
        previous_map={},
    )
    assert any("Spamhaus" in e for e in errors)
