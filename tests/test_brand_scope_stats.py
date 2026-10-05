"""brand_scope_stats — Custom vs. System vs. Health."""

from datetime import datetime, timezone

from src.services.brand_domain_health import (
    brand_scope_stats,
    domain_verified_for_list,
    iso_utc_for_api,
)


def test_brand_scope_stats_custom_and_system_split():
    custom = {"paypal": ["paypal.com"], "swiss": ["swiss.ch"]}
    health = {
        "domains": {
            "paypal.com": {
                "severity": "ok",
                "dns_status": "ok",
                "verified_at": "2026-01-01T00:00:00+00:00",
            },
        }
    }
    s = brand_scope_stats(custom, health)
    assert s["custom_brands"] == 2
    assert s["custom_domains"] == 2
    assert s["effective_domains"] >= s["custom_domains"]
    assert s["system_only_domains"] == s["effective_domains"] - s["custom_domains"]
    assert s["health_verified"] == 1
    assert s["health_pending"] == 1
    assert s["health_records"] == 1


def test_domain_verified_for_list_requires_verified_at():
    assert domain_verified_for_list({"verified_at": "x", "dns_status": "ok"})


def test_iso_utc_for_api_appends_z_for_naive_utc():
    dt = datetime(2026, 10, 4, 16, 44, 38)
    assert iso_utc_for_api(dt).endswith("Z")
    assert "16:44:38" in iso_utc_for_api(dt)
