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


def test_layer1_dkim_none_with_org_opens_llm_gate():
    meta = _Meta(
        sender="foo@example.com",
        sender_name="Serafe Team",
        auth_results="dkim=none; dmarc=none; spf=pass",
    )
    score, flags, suggest_llm = quick_header_flags(meta)
    assert suggest_llm
    assert any("DKIM" in f for f in flags)


def test_layer1_gmx_spam_flags_grauzone(monkeypatch):
    meta = _Meta(
        sender="store@g.shopifyemail.com",
        sender_name="Serafe CH",
        reply_to="sch@serafech.com",
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
            "reason": "Serafe behauptet, Reply-To serafech.com ist Typosquatting",
            "impersonated": "Serafe",
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
