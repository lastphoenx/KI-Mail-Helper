"""Marken-Health RDAP-Zusammenfassung und kein Doppel-Lookup."""

import json

from src.services.brand_domain_health import (
    _rdap_summary_from_domains,
    health_report_to_json,
    run_health_report,
)


def test_health_report_to_json_roundtrip():
    health = {
        "domains": {"a.com": {"rdap_registered": "2000-01-01", "issues": []}},
        "rdap_followup_enqueued": True,
    }
    parsed = json.loads(health_report_to_json(health))
    assert parsed["rdap_followup_enqueued"] is True


def test_rdap_summary_counts():
    by_domain = {
        "a.com": {"rdap_status": "ok", "rdap_registered": "2000-01-01"},
        "b.de": {"rdap_status": "no_registration"},
        "c.ch": {"rdap_status": "query_failed", "severity": "warn"},
    }
    s = _rdap_summary_from_domains(by_domain)
    assert s["with_date"] == 1
    assert s["no_date"] == 1
    assert s["query_failed"] == 1


def test_validate_uses_precomputed_no_second_assess(monkeypatch):
    from src.services import brand_domain_health as bdh
    from src.services import domain_reputation as dr
    from src.services.domain_reputation import assess_domain_health as real_assess

    calls = {"n": 0}

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real_assess(*args, **kwargs)

    monkeypatch.setattr(bdh, "assess_domain_health", counting)
    brand_map = {"x": ["example.com"]}
    health = run_health_report(brand_map, include_rdap=False)
    dr.validate_official_domains_for_save(
        brand_map, include_rdap=False, precomputed=health["domains"]
    )
    assert calls["n"] == 1


def test_validate_precomputed_no_spurious_cap_warning():
    """225 Marken-Domains, Teillauf — kein «abgebrochen nach 100» nur wegen Listengrösse."""
    from src.services import domain_reputation as dr

    brand_map = {f"b{i}": [f"d{i}.com"] for i in range(225)}
    precomputed = {
        f"d{i}.com": {
            "severity": "ok",
            "dns_status": "ok",
            "verified_at": "2026-01-01T00:00:00+00:00",
        }
        for i in range(100)
    }
    _, warnings = dr.validate_official_domains_for_save(
        brand_map, include_rdap=False, precomputed=precomputed
    )
    assert not any("abgebrochen nach" in w for w in warnings)
