"""RDAP 429 / Retry-After / Circuit-Breaker."""

from unittest.mock import MagicMock

import pytest

from src.services.domain_reputation import (
    _rdap_retry_after_seconds,
    lookup_rdap_registration_date,
    rdap_retry_after_max_seconds,
    reset_rdap_rate_limit_state_for_tests,
)


def test_retry_after_capped():
    resp = MagicMock()
    resp.headers = {"Retry-After": "3600"}
    assert _rdap_retry_after_seconds(resp) == rdap_retry_after_max_seconds()


def test_retry_after_default_when_missing():
    resp = MagicMock()
    resp.headers = {}
    assert _rdap_retry_after_seconds(resp) == rdap_retry_after_max_seconds()


def test_rdap_429_trips_server_circuit(monkeypatch):
    reset_rdap_rate_limit_state_for_tests()
    monkeypatch.setattr(
        "src.services.domain_reputation._load_iana_rdap_bootstrap",
        lambda: {"services": []},
    )
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        r = MagicMock()
        r.status_code = 429
        r.headers = {"Retry-After": "120"}
        return r

    monkeypatch.setattr("src.services.domain_reputation.requests.get", fake_get)
    monkeypatch.setattr("src.services.domain_reputation.time.sleep", lambda _: None)

    _, st1 = lookup_rdap_registration_date("first-example.ch", bypass_cache=True)
    assert st1 == "query_failed"
    assert calls["n"] == 2

    _, st2 = lookup_rdap_registration_date("second-example.ch", bypass_cache=True)
    assert st2 == "query_failed"
    assert calls["n"] == 4


def test_rdap_429_trips_server_circuit_when_enabled(monkeypatch):
    reset_rdap_rate_limit_state_for_tests()
    monkeypatch.setenv("RDAP_USE_CIRCUIT_BREAKER", "true")
    monkeypatch.setattr(
        "src.services.domain_reputation._load_iana_rdap_bootstrap",
        lambda: {"services": []},
    )
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        r = MagicMock()
        r.status_code = 429
        r.headers = {"Retry-After": "120"}
        return r

    monkeypatch.setattr("src.services.domain_reputation.requests.get", fake_get)
    monkeypatch.setattr("src.services.domain_reputation.time.sleep", lambda _: None)

    lookup_rdap_registration_date("first-example.ch", bypass_cache=True)
    assert calls["n"] == 2
    lookup_rdap_registration_date("second-example.ch", bypass_cache=True)
    assert calls["n"] == 2


def test_prepare_brand_health_rdap_batch_reopens_circuit(monkeypatch):
    reset_rdap_rate_limit_state_for_tests()
    monkeypatch.setattr(
        "src.services.domain_reputation._load_iana_rdap_bootstrap",
        lambda: {"services": []},
    )
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        r = MagicMock()
        r.status_code = 429
        r.headers = {"Retry-After": "120"}
        return r

    monkeypatch.setattr("src.services.domain_reputation.requests.get", fake_get)
    monkeypatch.setattr("src.services.domain_reputation.time.sleep", lambda _: None)

    lookup_rdap_registration_date("first-example.ch", bypass_cache=True)
    assert calls["n"] == 2

    from src.services.domain_reputation import prepare_brand_health_rdap_batch

    prepare_brand_health_rdap_batch(["second-example.ch"])
    lookup_rdap_registration_date("second-example.ch", bypass_cache=True)
    assert calls["n"] == 4
