"""Spamhaus DBL Antwort-Codes (gemockt, kein Netz)."""

import pytest

from src.services.domain_reputation import classify_spamhaus_dbl_answer


@pytest.mark.parametrize(
    "code,listed,unavailable",
    [
        ("127.0.1.2", True, False),
        ("127.0.1.4", True, False),
        ("127.0.1.5", True, False),
        ("127.0.1.6", True, False),
        ("127.0.1.102", True, False),
        ("127.0.2.2", True, False),
        ("127.0.0.2", False, True),
        ("127.255.255.254", False, True),
        ("127.255.255.255", False, True),
        ("127.255.255.252", False, True),
    ],
)
def test_classify_spamhaus_dbl_answer_codes(code, listed, unavailable):
    r = classify_spamhaus_dbl_answer(code)
    assert r.listed is listed
    assert r.unavailable is unavailable
    if listed:
        assert "DBL" in r.detail


def test_dbl_abused_legit_not_hard_block():
    from src.services.domain_reputation import (
        assess_domain_health,
        dbl_is_abused_legit_code,
        dbl_is_hard_listing_code,
    )

    assert dbl_is_abused_legit_code("127.0.1.104")
    assert not dbl_is_hard_listing_code("127.0.1.104")
    assert dbl_is_hard_listing_code("127.0.1.4")


def test_lookup_spamhaus_dbl_uses_classifier(monkeypatch):
    from src.services import domain_reputation as dr

    class FakeAnswer:
        def __init__(self, val):
            self.val = val

        def __str__(self):
            return self.val

    class FakeResp:
        def __init__(self, codes):
            self.codes = codes

        def __iter__(self):
            return iter(self.codes)

    def fake_resolve(self, query, rtype):
        assert query.endswith(".dbl.spamhaus.org")
        return FakeResp([FakeAnswer("127.0.1.4")])

    monkeypatch.setattr("dns.resolver.Resolver.resolve", fake_resolve)
    dr._mem_dbl_cache.clear()
    r = dr.lookup_spamhaus_dbl("evil-example.com", db_session=None)
    assert r.listed is True
    assert r.unavailable is False
