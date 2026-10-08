"""Feste Ebene für eigene Domain und Vertrauens-Domain. Kein Netz."""

import secrets

from src.services.audit_scam_detection import evaluate_scam_risk
from src.services.folder_audit_service import (
    REVIEW_DEFAULT_REASON,
    FolderAuditService,
    TrashCategory,
    TrashEmailInfo,
)


def _token() -> str:
    return "zw" + secrets.token_hex(4)


def _mail(**kwargs) -> TrashEmailInfo:
    base = dict(
        uid=1,
        subject="Notiz",
        sender=f"news@{_token()}.example",
        sender_name="Qx",
        date=None,
        has_attachments=False,
        flags=[],
        size=100,
    )
    base.update(kwargs)
    return TrashEmailInfo(**base)


def _cfg(**extra):
    cfg = {
        "trusted_domains": set(),
        "own_domains": set(),
        "own_addresses": set(),
        "important_keywords": set(),
        "safe_subject_patterns": set(),
        "safe_sender_patterns": set(),
        "vip_senders": set(),
        "vip_pattern_types": {},
    }
    cfg.update(extra)
    return cfg


FORGED = "spf=fail; dkim=fail; dmarc=fail"
OK = "spf=pass; dkim=pass; dmarc=pass"


def test_own_domain_all_auth_fail_is_suspicion():
    dom = f"{_token()}.example"
    meta = _mail(sender=f"alert@{dom}", auth_results=FORGED)
    ev = evaluate_scam_risk(meta, never_scam=True, llm_enabled=False)
    assert ev.identity_suspicion
    assert not ev.is_scam
    text = " ".join(ev.reasons)
    assert "SPF fail" in text and "DKIM fail" in text and "DMARC fail" in text

    out = FolderAuditService.analyze_email(
        meta, audit_config=_cfg(own_domains={dom}), llm_enabled=False
    )
    assert out.category == TrashCategory.SUSPICION
    assert "SPF fail" in (out.decision_reason or "")


def test_own_domain_auth_ok_stays_clear():
    dom = f"{_token()}.example"
    brand = _token()
    meta = _mail(
        sender=f"news@{dom}",
        sender_name=brand,
        subject="Hinweis",
        auth_results=OK,
    )
    ev = evaluate_scam_risk(
        meta,
        never_scam=True,
        llm_enabled=False,
        brand_map={brand: [f"{brand}.example"]},
    )
    assert not ev.identity_suspicion
    assert not ev.is_scam

    out = FolderAuditService.analyze_email(
        meta, audit_config=_cfg(own_domains={dom}), llm_enabled=False
    )
    assert out.category not in (TrashCategory.SCAM, TrashCategory.SUSPICION)


def test_own_domain_single_auth_fail_is_not_suspicion():
    dom = f"{_token()}.example"
    meta = _mail(
        sender=f"news@{dom}",
        auth_results="spf=fail; dkim=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, never_scam=True, llm_enabled=False)
    assert not ev.identity_suspicion
    assert not ev.is_scam


def test_trusted_domain_auth_fail_is_not_suspicion():
    dom = f"{_token()}.example"
    meta = _mail(sender=f"list@{dom}", auth_results=FORGED)
    ev = evaluate_scam_risk(
        meta, trusted_domains={dom}, llm_enabled=False
    )
    assert not ev.identity_suspicion
    assert not ev.is_scam


def test_spamhaus_hits_own_and_trusted_domains(monkeypatch):
    def _listed(domain, db_session=None):
        return True, "Spamhaus DBL"

    monkeypatch.setattr(
        "src.services.audit_scam_detection.check_dbl", _listed
    )
    own = f"{_token()}.example"
    trusted = f"{_token()}.example"
    own_meta = _mail(sender=f"news@{own}", auth_results=OK)
    own_ev = evaluate_scam_risk(own_meta, never_scam=True, llm_enabled=True)
    assert own_ev.identity_suspicion
    assert any("Spamhaus" in line for line in own_ev.reasons)

    trusted_meta = _mail(sender=f"news@{trusted}", auth_results=FORGED)
    trusted_ev = evaluate_scam_risk(
        trusted_meta, trusted_domains={trusted}, llm_enabled=True
    )
    assert trusted_ev.identity_suspicion
    assert any("Spamhaus" in line for line in trusted_ev.reasons)
    assert not any("SPF fail" in line for line in trusted_ev.reasons)


def test_rule_preview_names_the_fallback_and_the_alarm():
    sender = f"ada-{_token()}@{_token()}.example"
    cfg = _cfg()
    plain = FolderAuditService.preview_rule_decision(sender, _token(), cfg)
    assert plain["category"] == TrashCategory.REVIEW.value
    assert plain["decision"] == REVIEW_DEFAULT_REASON

    alarm = FolderAuditService.preview_rule_decision(sender, "disk failed", cfg)
    assert alarm["category"] == TrashCategory.IMPORTANT.value
    assert "nicht löschbar" in alarm["decision"]
