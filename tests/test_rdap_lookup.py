"""RDAP-Suffix-Auflösung und Override-URLs."""

from src.services.domain_reputation import (
    RDAP_TLD_OVERRIDES,
    _public_suffix_candidates,
    _rdap_base_url_for_registrable,
    _rdap_base_url_for_suffix,
)


def test_public_suffix_candidates_co_uk():
    assert _public_suffix_candidates("amazon.co.uk") == ["co.uk", "uk"]


def test_public_suffix_candidates_ch():
    assert _public_suffix_candidates("sbb.ch") == ["ch"]


def test_rdap_override_ch_when_iana_missing(monkeypatch):
    monkeypatch.setattr(
        "src.services.domain_reputation._load_iana_rdap_bootstrap",
        lambda: {"services": []},
    )
    base = _rdap_base_url_for_registrable("sbb.ch")
    assert base == "https://rdap.nic.ch"


def test_rdap_iana_preferred_over_override(monkeypatch):
    monkeypatch.setattr(
        "src.services.domain_reputation._load_iana_rdap_bootstrap",
        lambda: {
            "services": [[["fr"], ["https://rdap.nic.fr/rdap"]]],
        },
    )
    base = _rdap_base_url_for_registrable("amazon.fr")
    assert base == "https://rdap.nic.fr/rdap"


def test_rdap_bootstrap_uk_via_co_uk(monkeypatch):
    monkeypatch.setattr(
        "src.services.domain_reputation._load_iana_rdap_bootstrap",
        lambda: {"services": [[["uk"], ["https://rdap.example.test/rdap"]]]},
    )
    base = _rdap_base_url_for_registrable("amazon.co.uk")
    assert base == "https://rdap.example.test/rdap"


def test_rdap_override_urls_are_https(monkeypatch):
    monkeypatch.setattr(
        "src.services.domain_reputation._load_iana_rdap_bootstrap",
        lambda: {"services": []},
    )
    for suffix, url in RDAP_TLD_OVERRIDES.items():
        assert url.lower().startswith("https://"), suffix
        assert _rdap_base_url_for_suffix(suffix) == url.rstrip("/")
