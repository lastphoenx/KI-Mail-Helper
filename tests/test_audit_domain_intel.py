"""Domain-Hinweis ohne Netz: DNS und RDAP sind injiziert."""

import secrets
from datetime import datetime, timedelta, timezone

from src.services.audit_domain_intel import (
    classify_dns_error,
    hard_brand_plus_intel_is_scam,
    lookup_sender_domain,
    query_dns_existence,
    reset_domain_intel_budget,
)
from src.services.audit_scam_detection import evaluate_scam_risk
from src.services.folder_audit_service import TrashEmailInfo


class _NX(Exception):
    pass


class _Timeout(Exception):
    pass


class _NoAnswer(Exception):
    pass


class _Session:
    def __init__(self):
        self.rows = {}

    def query(self, model):
        self._model = model
        return self

    def filter_by(self, domain):
        self._domain = domain
        return self

    def first(self):
        return self.rows.get(self._domain)

    def add(self, row):
        self.rows[row.domain] = row

    def flush(self):
        return None


def _token() -> str:
    return "zw" + secrets.token_hex(3)


def _mail(**kwargs) -> TrashEmailInfo:
    base = dict(
        uid=1,
        subject="Notiz",
        sender=f"news@{_token()}.example",
        sender_name="Qx",
        date=None,
        has_attachments=False,
        flags=[],
        size=20,
    )
    base.update(kwargs)
    return TrashEmailInfo(**base)


def test_timeout_is_unknown_not_missing():
    class Timeout(Exception):
        pass

    def resolve(domain, rtype):
        raise Timeout("timed out")

    assert classify_dns_error(Timeout()) == "unknown"
    assert query_dns_existence("shop.example", resolve=resolve) == "unknown"
    intel = lookup_sender_domain(
        "shop.example",
        dns_lookup=lambda domain: "unknown",
        rdap_lookup=lambda domain: 1,
        use_budget=False,
    )
    assert intel.badge is None
    assert not intel.missing


def test_nxdomain_badge_and_young_brand_is_scam_young_alone_is_not():
    def resolve(domain, rtype):
        raise _NX("nxdomain")

    assert query_dns_existence("gone.example", resolve=resolve) == "nxdomain"
    missing = lookup_sender_domain(
        "gone.example",
        dns_lookup=lambda domain: "nxdomain",
        use_budget=False,
    )
    assert missing.badge == "Domain existiert nicht"

    brand = _token()
    foreign = f"{_token()}.example"
    branded = _mail(
        sender=f"news@{brand}.{foreign}",
        sender_name="Qx",
        subject="Hallo",
    )
    branded.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    branded.domain_intel_enabled = True
    branded._dns_lookup = lambda domain: "exists"
    branded._rdap_lookup = lambda domain: 12
    ev = evaluate_scam_risk(
        branded,
        llm_enabled=False,
        brand_map={brand: [f"{brand}.example"]},
    )
    assert ev.is_scam
    assert ev.domain_badge == "Domain 12 Tage alt"

    plain = _mail(subject="Hallo")
    plain.auth_results = "dkim=none; spf=none; dmarc=none"
    plain.domain_intel_enabled = True
    plain._dns_lookup = lambda domain: "exists"
    plain._rdap_lookup = lambda domain: 12
    ev_plain = evaluate_scam_risk(plain, llm_enabled=False, brand_map={})
    assert not ev_plain.is_scam
    assert ev_plain.domain_badge == "Domain 12 Tage alt"
    assert not hard_brand_plus_intel_is_scam([], missing, 30)


def test_no_answer_means_domain_exists():
    class NoAnswer(Exception):
        pass

    def resolve(domain, rtype):
        raise NoAnswer("empty")

    assert query_dns_existence("parked.example", resolve=resolve) == "exists"


def test_cache_skips_second_lookup_and_budget_stops():
    reset_domain_intel_budget()
    calls = {"n": 0}
    session = _Session()

    def dns(domain):
        calls["n"] += 1
        return "exists"

    now = datetime.now(timezone.utc)
    first = lookup_sender_domain(
        "cache.example",
        db_session=session,
        dns_lookup=dns,
        rdap_lookup=lambda domain: 400,
        now=now,
        use_budget=False,
    )
    assert first.age_days == 400
    assert first.badge is None
    second = lookup_sender_domain(
        "cache.example",
        db_session=session,
        dns_lookup=dns,
        rdap_lookup=lambda domain: 1,
        now=now + timedelta(days=1),
        use_budget=False,
    )
    assert second.from_cache
    assert calls["n"] == 1

    reset_domain_intel_budget()
    from src.services.audit_domain_intel import MAX_LOOKUPS_PER_SCAN

    def counting(domain):
        calls["n"] += 1
        return "nxdomain"

    calls["n"] = 0
    for i in range(MAX_LOOKUPS_PER_SCAN + 2):
        lookup_sender_domain(
            f"b{i}.example",
            dns_lookup=counting,
            use_budget=True,
        )
    assert calls["n"] == MAX_LOOKUPS_PER_SCAN
