"""brand_settings_api_payload — Celery-sicher ohne Blueprint."""

from datetime import datetime

from src.services.brand_domain_health import brand_settings_api_payload


class _FakeRow:
    brand_official_domains_json = "paypal: paypal.com"
    brand_import_pending_json = None
    brand_domains_health_json = '{"domains": {}, "brands": {}}'
    brand_domains_health_checked_at = datetime(2026, 10, 4, 12, 0, 0)
    brand_dbl_blocked_domains_json = None
    brand_health_rdap = False


def test_brand_settings_api_payload_from_row():
    payload = brand_settings_api_payload(_FakeRow(), user_id=42)
    assert payload["custom_count"] >= 1
    assert payload["brand_health_rdap"] is False
    assert payload["brand_health_rdap_enabled"] is False
    assert payload["health"] is not None
    assert payload["health_checked_at"].startswith("2026-10-04")
    assert "brand_health_rdap_enabled" in payload
    assert "scope" in payload
    assert payload["scope"]["custom_brands"] >= 1


def test_brand_settings_api_payload_empty_row():
    payload = brand_settings_api_payload(None, user_id=1)
    assert payload["custom_count"] == 0
    assert payload["health"] is None
