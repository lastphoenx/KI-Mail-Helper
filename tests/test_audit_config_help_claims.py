"""Behauptungen aus Audit-Hilfe/Doku gegen analyze_email / evaluate_scam_risk prüfen."""

from src.services.audit_scam_detection import evaluate_scam_risk
from src.services.folder_audit_service import FolderAuditService, TrashCategory
from tests.test_audit_own_domain_floor import FORGED, _mail as _scam_mail
from tests.test_audit_quality_rules import _cfg, _mail, _token


def test_safe_sender_pattern_does_not_override_brand_scam():
    brand = _token()
    rogue_domain = f"{_token()}.example"
    sender = f"login.{brand}@{rogue_domain}"
    info = _mail(
        sender=sender,
        sender_name=f"{brand}bank",
        subject="Sicherheitsmitteilung zum Konto",
        has_list_unsubscribe=True,
    )
    info.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    brand_map = {brand: [f"{brand}.example"]}
    cfg = _cfg(safe_sender_patterns={rogue_domain})
    cfg["brand_official_domains_effective"] = brand_map
    out = FolderAuditService.analyze_email(info, audit_config=cfg, llm_enabled=False)
    assert out.category == TrashCategory.SCAM


def test_safe_sender_with_newsletter_can_classify_invoice_subject_as_safe():
    domain = f"{_token()}.example"
    sender = f"newsletter@{domain}"
    info = _mail(
        subject="Ihre Rechnung Oktober",
        sender=sender,
        has_list_unsubscribe=True,
    )
    info.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    cfg = _cfg(safe_sender_patterns={f"@{domain}"})
    out = FolderAuditService.analyze_email(info, audit_config=cfg, llm_enabled=False)
    assert out.category == TrashCategory.SAFE


def test_safe_sender_alone_does_not_make_invoice_subject_safe():
    domain = f"{_token()}.example"
    sender = f"promo@{domain}"
    info = _mail(
        subject="Ihre Rechnung Oktober",
        sender=sender,
        has_list_unsubscribe=False,
    )
    info.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    cfg = _cfg(safe_sender_patterns={f"@{domain}"})
    out = FolderAuditService.analyze_email(info, audit_config=cfg, llm_enabled=False)
    assert out.category != TrashCategory.SAFE


def test_trusted_domain_spamhaus_still_suspicious(monkeypatch):
    """Doku: Spamhaus bleibt aktiv bei vertrauenswürdiger Domain."""

    def _listed(domain, db_session=None):
        return True, "Spamhaus DBL"

    monkeypatch.setattr("src.services.audit_scam_detection.check_dbl", _listed)
    trusted = f"{_token()}.example"
    meta = _scam_mail(sender=f"news@{trusted}", auth_results=FORGED)
    ev = evaluate_scam_risk(meta, trusted_domains={trusted}, llm_enabled=True)
    assert ev.identity_suspicion
    assert any("Spamhaus" in line for line in ev.reasons)
    assert not any("SPF fail" in line for line in ev.reasons)
