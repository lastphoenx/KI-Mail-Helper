"""Marken-RDAP pro Nutzer (Checkbox) und Batch-State."""

import time

from src.services.brand_domain_health import run_health_report
from src.services.domain_reputation import (
    brand_health_rdap_aborted,
    brand_health_rdap_admin_disabled,
    clear_brand_health_rdap_context,
    resolve_brand_health_rdap,
    reset_rdap_rate_limit_state_for_tests,
    set_brand_health_rdap_abort_policy,
    set_brand_health_rdap_context,
    set_brand_health_rdap_deadline,
)


def test_resolve_brand_health_rdap_respects_user_pref():
    assert resolve_brand_health_rdap(False) is False
    assert resolve_brand_health_rdap(True) is True


def test_resolve_brand_health_rdap_admin_override(monkeypatch):
    monkeypatch.setenv("BRAND_DOMAIN_HEALTH_RDAP", "false")
    assert brand_health_rdap_admin_disabled() is True
    assert resolve_brand_health_rdap(True) is False


def test_run_health_report_without_rdap_skips_lookup(monkeypatch):
    reset_rdap_rate_limit_state_for_tests()
    calls = {"n": 0}

    def _fake_lookup(domain, **kwargs):
        calls["n"] += 1
        return None, "ok"

    monkeypatch.setattr(
        "src.services.domain_reputation.lookup_rdap_registration_date",
        _fake_lookup,
    )
    run_health_report({"x": ["example.com"]}, include_rdap=False)
    assert calls["n"] == 0


def test_run_health_report_with_rdap_calls_lookup(monkeypatch):
    reset_rdap_rate_limit_state_for_tests()
    calls = {"n": 0}

    def _fake_lookup(domain, **kwargs):
        calls["n"] += 1
        return None, "no_registration"

    monkeypatch.setattr(
        "src.services.domain_reputation.lookup_rdap_registration_date",
        _fake_lookup,
    )
    set_brand_health_rdap_context(True)
    try:
        run_health_report({"x": ["example.com"]}, include_rdap=True)
    finally:
        clear_brand_health_rdap_context()
    assert calls["n"] >= 1


def test_rdap_batch_globals_cleared_after_health_report(monkeypatch):
    reset_rdap_rate_limit_state_for_tests()
    monkeypatch.setattr(
        "src.services.domain_reputation.lookup_rdap_registration_date",
        lambda *a, **k: (None, "no_registration"),
    )
    set_brand_health_rdap_abort_policy(True)
    set_brand_health_rdap_deadline(time.monotonic() + 60.0)
    run_health_report({"z": ["example.org"]}, include_rdap=False)
    assert brand_health_rdap_aborted() is False
