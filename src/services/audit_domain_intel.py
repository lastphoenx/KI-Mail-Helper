"""DNS- und RDAP-Hinweis nur für Zweifel-Kandidaten.

Keine Abfrage für jede Mail. Timeout ist nicht «Domain existiert nicht».
Alter und «existiert nicht» sind Zusatzsignale: mit hartem Markentreffer Scam,
allein nur ein Badge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

DEFAULT_YOUNG_DAYS = 30
DEFAULT_CAUTION_DAYS = 90
POSITIVE_CACHE_DAYS = 30
NEGATIVE_CACHE_DAYS = 7
DNS_TIMEOUT_SECONDS = 2.0
MAX_LOOKUPS_PER_SCAN = 20

_lookups_this_scan = 0


def reset_domain_intel_budget() -> None:
    global _lookups_this_scan
    _lookups_this_scan = 0


@dataclass
class DomainIntel:
    domain: str
    dns_status: str = "unknown"  # exists | nxdomain | unknown
    age_days: Optional[int] = None
    badge: Optional[str] = None
    from_cache: bool = False

    @property
    def missing(self) -> bool:
        return self.dns_status == "nxdomain"

    def young(self, young_days: int) -> bool:
        return self.age_days is not None and self.age_days < young_days

    def notable(self, young_days: int, caution_days: int) -> bool:
        if self.missing:
            return True
        if self.age_days is None:
            return False
        return self.age_days < caution_days


def is_domain_intel_candidate(meta, rule_ids) -> bool:
    """Harter Markentreffer, Verdacht oder explizit fehlende/fehlgeschlagene Auth."""
    from src.services.audit_quality_rules import HARD_BRAND_RULES

    rules = set(rule_ids or [])
    if rules & HARD_BRAND_RULES:
        return True
    if getattr(meta, "identity_suspicion", False):
        return True
    auth = (getattr(meta, "auth_results", None) or "").lower()
    if not auth:
        return False
    if "fail" in auth:
        return True
    if "none" in auth and "pass" not in auth:
        return True
    return False


def classify_dns_error(exc: BaseException) -> str:
    """nxdomain | no_answer | unknown. Timeout und SERVFAIL sind unknown."""
    name = type(exc).__name__
    text = str(exc).lower()
    if name == "NXDOMAIN" or "nxdomain" in text:
        return "nxdomain"
    if name in ("NoAnswer", "NoNameservers"):
        return "no_answer"
    return "unknown"


def query_dns_existence(domain: str, *, resolve: Optional[Callable] = None) -> str:
    """NS, dann A, dann MX. exists | nxdomain | unknown."""
    domain = (domain or "").lower().strip(".")
    if not domain:
        return "unknown"
    if resolve is None:
        resolve = _live_resolve
    saw_nx = False
    saw_no_answer = False
    for rtype in ("NS", "A", "MX"):
        try:
            resolve(domain, rtype)
            return "exists"
        except Exception as exc:
            kind = classify_dns_error(exc)
            if kind == "unknown":
                return "unknown"
            if kind == "nxdomain":
                saw_nx = True
            else:
                saw_no_answer = True
    if saw_nx and not saw_no_answer:
        return "nxdomain"
    if saw_no_answer:
        return "exists"
    return "unknown"


def _live_resolve(domain: str, rtype: str):
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.lifetime = DNS_TIMEOUT_SECONDS
    resolver.timeout = DNS_TIMEOUT_SECONDS
    return resolver.resolve(domain, rtype)


def notable_kind(dns_status: str, age_days: Optional[int], young_days: int, caution_days: int) -> Optional[str]:
    if dns_status == "nxdomain":
        return "missing"
    if age_days is None:
        return None
    if age_days < young_days:
        return "young"
    if age_days < caution_days:
        return "caution"
    return None


def badge_for(intel: DomainIntel, *, young_days: int, caution_days: int) -> Optional[str]:
    if intel.dns_status == "nxdomain":
        return "Domain existiert nicht"
    if intel.dns_status != "exists" or intel.age_days is None:
        return None
    if intel.age_days < caution_days:
        return f"Domain {intel.age_days} Tage alt"
    return None


def _cache_fresh(checked_at: datetime, dns_status: str, now: datetime) -> bool:
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    age = now - checked_at
    if dns_status == "nxdomain":
        return age <= timedelta(days=NEGATIVE_CACHE_DAYS)
    if dns_status == "exists":
        return age <= timedelta(days=POSITIVE_CACHE_DAYS)
    return False


def _read_cache(db_session, domain: str, now: datetime) -> Optional[DomainIntel]:
    if db_session is None:
        return None
    try:
        import importlib

        models = importlib.import_module(".02_models", "src")
        row = (
            db_session.query(models.AuditDomainIntelCache)
            .filter_by(domain=domain)
            .first()
        )
    except Exception:
        return None
    if row is None or not _cache_fresh(row.checked_at, row.dns_status or "", now):
        return None
    intel = DomainIntel(
        domain=domain,
        dns_status=row.dns_status or "unknown",
        age_days=row.age_days,
        from_cache=True,
    )
    return intel


def _write_cache(db_session, intel: DomainIntel, now: datetime) -> None:
    if db_session is None or intel.dns_status == "unknown":
        return
    try:
        import importlib

        models = importlib.import_module(".02_models", "src")
        row = (
            db_session.query(models.AuditDomainIntelCache)
            .filter_by(domain=intel.domain)
            .first()
        )
        if row is None:
            row = models.AuditDomainIntelCache(domain=intel.domain)
            db_session.add(row)
        row.dns_status = intel.dns_status
        row.age_days = intel.age_days
        row.checked_at = now
        db_session.flush()
    except Exception:
        return


def lookup_sender_domain(
    domain: str,
    *,
    young_days: int = DEFAULT_YOUNG_DAYS,
    caution_days: int = DEFAULT_CAUTION_DAYS,
    db_session=None,
    dns_lookup: Optional[Callable[[str], str]] = None,
    rdap_lookup: Optional[Callable[[str], Optional[int]]] = None,
    now: Optional[datetime] = None,
    use_budget: bool = True,
) -> DomainIntel:
    """Eine registrierbare Domain. Kein Netz, wenn dns_lookup/rdap_lookup gesetzt sind."""
    global _lookups_this_scan
    from src.services.brand_domain_policy import registrable_domain_from_host

    now = now or datetime.now(timezone.utc)
    reg = (registrable_domain_from_host(domain) or domain or "").lower().strip(".")
    intel = DomainIntel(domain=reg)
    if not reg:
        return intel
    cached = _read_cache(db_session, reg, now)
    if cached is not None:
        cached.badge = badge_for(cached, young_days=young_days, caution_days=caution_days)
        return cached
    if use_budget and _lookups_this_scan >= MAX_LOOKUPS_PER_SCAN:
        intel.dns_status = "unknown"
        return intel
    if use_budget:
        _lookups_this_scan += 1
    dns_lookup = dns_lookup or query_dns_existence
    intel.dns_status = dns_lookup(reg)
    if intel.dns_status == "exists":
        if rdap_lookup is None:
            rdap_lookup = _default_rdap_age
        try:
            intel.age_days = rdap_lookup(reg)
        except Exception:
            intel.age_days = None
    intel.badge = badge_for(intel, young_days=young_days, caution_days=caution_days)
    _write_cache(db_session, intel, now)
    return intel


def _default_rdap_age(domain: str) -> Optional[int]:
    from src.services.domain_reputation import lookup_rdap_registration_date

    reg_dt, status = lookup_rdap_registration_date(domain)
    if status != "ok" or reg_dt is None:
        return None
    if reg_dt.tzinfo is None:
        reg_dt = reg_dt.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - reg_dt).days)


def hard_brand_plus_intel_is_scam(rule_ids, intel: DomainIntel, young_days: int) -> bool:
    from src.services.audit_quality_rules import HARD_BRAND_RULES

    if not (set(rule_ids or []) & HARD_BRAND_RULES):
        return False
    if intel.missing or intel.young(young_days):
        return True
    return False


def apply_domain_intel(meta, evaluation, *, db_session=None) -> None:
    """Setzt Badge. Hebt einen harten Markentreffer auf Scam, wenn die Domain fehlt oder jung ist."""
    if not getattr(meta, "domain_intel_enabled", False):
        return
    rules = list(getattr(evaluation, "identity_rules", None) or [])
    if not is_domain_intel_candidate(meta, rules) and not getattr(
        evaluation, "identity_suspicion", False
    ):
        return
    from src.services.audit_scam_detection import extract_domain

    host = extract_domain(getattr(meta, "sender", "") or "")
    young_days = int(getattr(meta, "domain_young_days", None) or DEFAULT_YOUNG_DAYS)
    caution_days = int(getattr(meta, "domain_caution_days", None) or DEFAULT_CAUTION_DAYS)
    intel = lookup_sender_domain(
        host,
        young_days=young_days,
        caution_days=caution_days,
        db_session=db_session,
        dns_lookup=getattr(meta, "_dns_lookup", None),
        rdap_lookup=getattr(meta, "_rdap_lookup", None),
    )
    if intel.badge:
        evaluation.domain_badge = intel.badge
        reasons = list(getattr(evaluation, "reasons", None) or [])
        if intel.badge not in reasons:
            reasons.append(intel.badge)
        evaluation.reasons = reasons
    if not getattr(evaluation, "is_scam", False) and hard_brand_plus_intel_is_scam(
        rules, intel, young_days
    ):
        evaluation.is_scam = True
        evaluation.confidence = max(getattr(evaluation, "confidence", 0) or 0, 0.8)
