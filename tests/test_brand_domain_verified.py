"""Inkrementelle Marken-Domain-Verifikation."""

from src.services.brand_domain_health import (
    clear_domain_verification_state,
    domain_verified_for_list,
    new_domains_from_maps,
    pending_verification_domains,
    stamp_domain_health_checked,
)


def test_new_domains_from_maps_added_only():
    old = {"paypal": ["paypal.com"]}
    new = {"paypal": ["paypal.com", "paypal.ch"], "sbb": ["sbb.ch"]}
    assert new_domains_from_maps(old, new) == ["paypal.ch", "sbb.ch"]


def test_pending_skips_verified():
    brand_map = {"a": ["x.ch", "y.ch"]}
    by_domain = {
        "x.ch": {"verified_at": "2026-01-01T00:00:00", "dns_status": "ok", "rdap_status": "ok"},
    }
    assert pending_verification_domains(brand_map, by_domain) == ["y.ch"]


def test_stamp_sets_verified_when_dns_ok():
    h = stamp_domain_health_checked(
        {"dns_status": "ok", "dbl_hard_listed": False, "rdap_status": "ok"}
    )
    assert h.get("verified_at")
    assert domain_verified_for_list(h)


def test_query_failed_not_verified(monkeypatch):
    monkeypatch.setattr(
        "src.services.brand_domain_health.brand_health_rdap_enabled",
        lambda: True,
    )
    h = stamp_domain_health_checked(
        {"dns_status": "ok", "rdap_status": "query_failed", "dbl_hard_listed": False}
    )
    assert not h.get("verified_at")
    assert not domain_verified_for_list(h)


def test_clear_verification_for_recheck():
    by_domain = {
        "a.ch": {"verified_at": "2026-01-01", "checked_at": "2026-01-01", "dns_status": "ok"},
        "b.ch": {"verified_at": "2026-01-02", "dns_status": "ok"},
    }
    clear_domain_verification_state(by_domain, ["a.ch"])
    assert "verified_at" not in by_domain["a.ch"]
    assert "checked_at" not in by_domain["a.ch"]
    assert by_domain["b.ch"].get("verified_at")
