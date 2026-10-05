"""Marken-Domain-Policy für Audit/Scam."""

import pytest

from src.services.brand_domain_policy import (
    display_brand_authorized_sender,
    effective_brand_map,
    fetch_https_text_for_brand_import,
    find_brand_domain_mismatch,
    host_matches_official_domain,
    registrable_domain_from_host,
    validate_brand_map,
)


def test_registrable_domain_co_uk():
    assert registrable_domain_from_host("shop.amazon.co.uk") == "amazon.co.uk"


def test_sender_on_official_brand_domain_subdomain():
    bm = {"portalco": ["kundenportal-demo.example", "mail.kundenportal-demo.example"]}
    from src.services.brand_domain_policy import sender_on_official_brand_domain

    assert sender_on_official_brand_domain(
        "max.muster@mail.kundenportal-demo.example",
        bm,
    )
    assert not sender_on_official_brand_domain(
        "max.muster@phish-host-demo.example",
        bm,
    )


def test_wrong_tld_not_authorized():
    assert not display_brand_authorized_sender(
        "PayPal",
        "service@paypal.support",
        significant_tokens=["paypal"],
    )


def test_validate_rejects_public_suffix_as_domain():
    with pytest.raises(ValueError):
        validate_brand_map({"paypal": ["ch"]})


def test_validate_rejects_co_uk_only():
    with pytest.raises(ValueError):
        validate_brand_map({"amazon": ["co.uk"]})


def test_official_subdomain_authorized():
    assert display_brand_authorized_sender(
        "Insta360",
        "noreply@dm.insta360.com",
        significant_tokens=["insta360"],
    )


@pytest.mark.parametrize(
    "hosting_domain",
    [
        "herokuapp.com",
        "vercel.app",
        "netlify.app",
        "pages.dev",
        "blogspot.com",
        "web.app",
        "azurewebsites.net",
    ],
)
def test_validate_rejects_multi_tenant_hosting_suffix(hosting_domain):
    with pytest.raises(ValueError):
        validate_brand_map({"paypal": [hosting_domain]})


def test_kantonalbank_display_name_uses_umbrella_key_not_blkb():
    brand_map = effective_brand_map(None)
    assert "kantonalbank" in brand_map
    hit_blkb = find_brand_domain_mismatch(
        "Kantonalbank - Supportberatungshotline",
        "melanie.meyer67@socialfriends.at",
        brand_map,
    )
    assert hit_blkb is not None
    assert hit_blkb.brand_key == "kantonalbank"
    hit_zkb = find_brand_domain_mismatch(
        "ZKB - Zürcher Kantonalbank",
        "jan.muster@firma-beispiel.example",
        brand_map,
    )
    assert hit_zkb is not None
    assert hit_zkb.brand_key == "zkb"


def test_css_tricks_newsletter_not_css_krankenkasse_mismatch():
    hit = find_brand_domain_mismatch(
        "CSS-Tricks Newsletter",
        "newsletter@css-tricks.com",
        effective_brand_map(None),
    )
    assert hit is None


def test_h_and_m_brand_line_validates_and_matches_display_name():
    cleaned, _ = validate_brand_map({"h&m": ["hm.com"]})
    assert cleaned == {"handm": ["hm.com"]}
    hit = find_brand_domain_mismatch(
        "H&M Newsletter",
        "promo@phishing.example",
        cleaned,
    )
    assert hit is not None
    assert hit.brand_key == "handm"
    assert "H&M" in hit.message
    assert not find_brand_domain_mismatch(
        "H&M",
        "noreply@mail.hm.com",
        cleaned,
    )


def test_hm_subdomain_authorized():
    assert host_matches_official_domain("www2.hm.com", ["hm.com"])


def test_fetch_brand_import_rejects_http_redirect(monkeypatch):
    class FakeResp:
        status_code = 302
        headers = {"Location": "https://evil.example/list.json"}

        def close(self):
            pass

    def fake_get(*_a, **_kw):
        return FakeResp()

    monkeypatch.setattr(
        "requests.get",
        fake_get,
    )
    monkeypatch.setattr(
        "src.services.brand_domain_policy.assert_safe_brand_list_url",
        lambda u: u,
    )
    with pytest.raises(ValueError, match="Weiterleitung"):
        fetch_https_text_for_brand_import("https://example.com/brands.json")


def test_brand_display_token_prefix_and_typo():
    from src.services.brand_domain_policy import (
        _brand_key_matches_display_name,
        _damerau_levenshtein_at_most_one,
    )

    assert _damerau_levenshtein_at_most_one("ab", "ba")
    assert _damerau_levenshtein_at_most_one("xab", "xba")
    assert _damerau_levenshtein_at_most_one("plazner", "planzer")
    assert _brand_key_matches_display_name("planzer", "max von planzerft")
    assert _brand_key_matches_display_name("planzer", "planzerpv newsletter")
    assert _brand_key_matches_display_name("planzer", "rechnung plazner")
    assert _brand_key_matches_display_name("planzer", "plazner hr")
    assert not _brand_key_matches_display_name("planzer", "unrelated shop name")


@pytest.mark.parametrize(
    "brand_key,display",
    [
        ("coop", "Cooperative"),
        ("coop", "Coopers Pub"),
        ("apple", "Applewood Hotel"),
        ("ubs", "Ubstadt Gemeinde"),
        ("css", "Cssd"),
        ("google", "Googlefan"),
        ("amazon", "Amazonas Tours"),
    ],
)
def test_brand_prefix_no_false_positive_builtin(brand_key, display):
    from src.services.brand_domain_policy import _brand_key_matches_display_name

    assert not _brand_key_matches_display_name(brand_key, display.lower())
