"""Tests für Zwei-Layer Scam-Erkennung (audit_scam_detection)."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pytest

from src.services.audit_scam_detection import (
    clear_audit_scam_caches,
    evaluate_scam_risk,
    quick_header_flags,
)
from src.services.folder_audit_service import (
    FolderAuditService,
    TrashCategory,
    TrashEmailInfo,
)


@dataclass
class _Meta:
    subject: str = ""
    sender: str = ""
    sender_name: str = ""
    auth_results: Optional[str] = None
    reply_to: Optional[str] = None
    x_mailer: Optional[str] = None
    server_spam_flag: bool = False
    provider_junk_score: Optional[int] = None
    is_auto_generated: bool = False
    to_header: Optional[str] = None


@pytest.fixture(autouse=True)
def _clear_caches():
    clear_audit_scam_caches()
    yield
    clear_audit_scam_caches()


def test_layer1_vip3rbox_auto_scam():
    meta = _Meta(
        sender="b55x6zkyrsmt3pda26xo@online.pro",
        sender_name="Rückerstattung in Serafe",
        x_mailer="V1P3RBOX v1.0-Ref96",
        auth_results="gmx.net; dkim=none; spf=pass; dmarc=none",
        is_auto_generated=True,
    )
    score, flags, suggest_llm = quick_header_flags(meta)
    assert score >= 80
    assert any("Scam-Software" in f for f in flags)

    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert ev.is_scam
    assert not ev.llm_used


def test_layer1_dkim_none_alone_is_weak():
    meta = _Meta(
        sender="info@kleine-firma.ch",
        sender_name="Kleine Firma",
        auth_results="dkim=none; dmarc=none; spf=pass",
    )
    score, _, _ = quick_header_flags(meta)
    assert score < 80


def test_layer1_dkim_none_with_org_sets_flag():
    meta = _Meta(
        sender="foo@example.com",
        sender_name="Rückerstattung Serafe AG",
        auth_results="dkim=none; dmarc=none; spf=pass",
    )
    score, flags, _suggest_llm = quick_header_flags(meta)
    assert any("DKIM" in f for f in flags)
    assert score < 80


def test_layer1_gmx_spam_flags_grauzone(monkeypatch):
    meta = _Meta(
        sender="store@g.shopifyemail.com",
        sender_name="Acme Shop",
        reply_to="help@other-domain.example",
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="dkim=pass; dmarc=pass; spf=pass",
    )
    score, _, suggest_llm = quick_header_flags(meta)
    assert 20 <= score < 80
    assert suggest_llm

    def fake_llm(_meta):
        return {
            "mismatch": True,
            "confidence": 90,
            "reason": "Anzeigename Acme, Versand Shopify, Reply-To andere Domain",
            "impersonated": "Acme",
        }

    monkeypatch.setattr(
        "src.services.audit_scam_detection.identity_llm_check",
        fake_llm,
    )
    ev = evaluate_scam_risk(meta, llm_enabled=True)
    assert ev.is_scam
    assert ev.llm_used


def test_integrated_folder_audit_vip3rbox():
    info = TrashEmailInfo(
        uid=1,
        subject="Team Serafe-AG",
        sender="b55x6zkyrsmt3pda26xo@online.pro",
        sender_name="Rückerstattung in Serafe",
        date=datetime.now(timezone.utc),
        has_attachments=False,
        flags=[],
        size=100,
        x_mailer="V1P3RBOX v1.0-Ref96",
        auth_results="gmx.net; dkim=none; spf=pass; dmarc=none",
        is_auto_generated=True,
        to_header="Undisclosed Recipients",
    )
    out = FolderAuditService.analyze_email(info)
    assert out.category == TrashCategory.SCAM


def test_trusted_domain_skips_scam():
    meta = _Meta(
        sender="info@serafe.ch",
        sender_name="Serafe",
        x_mailer="V1P3RBOX v1.0",
    )
    ev = evaluate_scam_risk(meta, trusted_domains={"serafe.ch"}, llm_enabled=False)
    assert not ev.is_scam


def test_gmx_junk2_pcloud_is_not_scam():
    """INBOX-Katastrophe: pCloud Login mit junk:2 darf kein SCAM/LLM sein."""
    meta = _Meta(
        sender="team@pcloud.com",
        sender_name="pCloud Team",
        subject="Neues Login auf Ihrem pCloud Konto",
        provider_junk_score=2,
        auth_results="dkim=pass; dmarc=pass; spf=pass",
    )
    score, flags, _ = quick_header_flags(meta)
    assert score < 40
    assert not any("Junk-Verdacht" in f for f in flags)
    ev = evaluate_scam_risk(meta, llm_enabled=True)
    assert not ev.is_scam
    assert not ev.llm_used


def test_person_name_tuwien_junk2_is_not_scam():
    meta = _Meta(
        sender="muster@gut.tuwien.ac.at",
        sender_name="Muster, Stephan",
        subject="AW: [Nuki] Re: Nuki Support",
        provider_junk_score=2,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, llm_enabled=True, trusted_domains=set())
    assert not ev.is_scam
    assert not ev.llm_used


def test_authenticated_mail_junk2_no_domain_allowlist():
    """Uni/Firma mit junk:2 + DKIM pass — ohne Domain-Whitelist, ohne Hardcode."""
    meta = _Meta(
        sender="sekretariat@gut.tuwien.ac.at",
        sender_name="GUT Sekretariat",
        provider_junk_score=2,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, llm_enabled=True, trusted_domains=set())
    assert not ev.is_scam
    assert not ev.llm_used


def test_placeholder_llm_reason_is_discarded(monkeypatch):
    meta = _Meta(
        sender="team@pcloud.com",
        sender_name="pCloud Team",
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="dkim=pass; dmarc=pass; spf=pass",
    )

    def fake_llm(_meta):
        return {
            "mismatch": True,
            "confidence": 90,
            "reason": "ein Satz auf Deutsch",
            "impersonated": "Org-Name oder null",
        }

    monkeypatch.setattr(
        "src.services.audit_scam_detection.identity_llm_check",
        fake_llm,
    )
    ev = evaluate_scam_risk(meta, llm_enabled=True)
    assert ev.llm_used
    assert not ev.is_scam
    assert not any("ein Satz auf Deutsch" in r for r in ev.reasons)
    assert not any("Org-Name oder null" in r for r in ev.reasons)


def test_llm_serafech_leak_on_unrelated_mail_is_discarded(monkeypatch):
    meta = _Meta(
        sender="muster@gut.tuwien.ac.at",
        sender_name="Muster, Stephan",
        subject="AW: [Nuki] Re: Nuki Support",
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )

    def fake_llm(_meta):
        return {
            "mismatch": True,
            "confidence": 90,
            "reason": "typisch für serafech.com (Typosquatting)",
            "impersonated": "serafe.ch",
        }

    monkeypatch.setattr(
        "src.services.audit_scam_detection.identity_llm_check",
        fake_llm,
    )
    ev = evaluate_scam_risk(meta, llm_enabled=True)
    assert not ev.is_scam
    assert not any("serafech" in r.lower() for r in ev.reasons)


def test_layer1_serafech_glued_cctld_is_scam_without_llm():
    """Beispiel c: Anzeigename Serafe CH, Reply-To serafech.com."""
    meta = _Meta(
        sender="store@g.shopifyemail.com",
        sender_name="Serafe CH",
        reply_to="sch@serafech.com",
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="dkim=pass; dmarc=pass; spf=pass",
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert ev.is_scam
    assert any("Typosquatting" in f for f in ev.layer1_flags)


def test_inbox_ham_pcloud_not_scam_via_folder_audit():
    info = TrashEmailInfo(
        uid=1,
        subject="Neues Login auf Ihrem pCloud Konto",
        sender="team@pcloud.com",
        sender_name="pCloud Team",
        date=datetime.now(timezone.utc),
        has_attachments=False,
        flags=[],
        size=100,
        provider_junk_score=2,
        auth_results="dkim=pass; dmarc=pass; spf=pass",
    )
    out = FolderAuditService.analyze_email(info)
    assert out.category != TrashCategory.SCAM
    assert not any("ein Satz auf Deutsch" in r for r in out.reasons)
