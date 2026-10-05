"""Tests für Zwei-Layer Scam-Erkennung (audit_scam_detection)."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pytest

from src.services.audit_scam_detection import (
    clear_audit_scam_caches,
    evaluate_scam_risk,
    hybrid_second_evidence,
    quick_header_flags,
    ScamEvaluation,
    _merge_hybrid_llm_identity,
)
from src.services.audit_scam_llm_config import AuditScamLlmConfig
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
    folder: Optional[str] = None
    has_list_unsubscribe: bool = False


def _llm_cfg_enabled() -> AuditScamLlmConfig:
    return AuditScamLlmConfig(
        enabled=True,
        provider="ollama",
        model="test-model",
        think=False,
        base_url="http://127.0.0.1:11434",
        prompt_version=1,
        timeout=90,
        configured_via="user",
    )


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
    score, flags, suggest_llm = quick_header_flags(meta)
    assert score < 80
    assert any(r.startswith("Transport:") for r in flags)
    assert not any(f.startswith("Identität:") for f in flags if "Slash" in f)

    meta2 = _Meta(
        sender="Swisscom-kundenbetreuung.ch/x@sendhost-demo.net",
        sender_name="Swisscom",
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="dkim=pass; dmarc=pass; spf=pass",
    )
    ev2 = evaluate_scam_risk(meta2, llm_enabled=False)
    assert ev2.is_scam
    assert "E1" in ev2.identity_rules


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

    def fake_llm(*_a, **_kw):
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
    ev = evaluate_scam_risk(
        meta,
        llm_enabled=True,
        audit_llm_config=_llm_cfg_enabled(),
    )
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

    def fake_llm(*_a, **_kw):
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
    ev = evaluate_scam_risk(
        meta,
        llm_enabled=True,
        audit_llm_config=_llm_cfg_enabled(),
    )
    assert not ev.is_scam
    assert not any("serafech" in r.lower() for r in ev.reasons)


def test_hybrid_merge_s_without_second_evidence_not_auto_scam():
    meta = _Meta(
        sender="team@pcloud.com",
        sender_name="pCloud Team",
        subject="Quartalsinfo",
    )
    out = ScamEvaluation()
    _merge_hybrid_llm_identity(out, meta, {"verdict": "S", "reason": "Marke passt nicht"})
    assert not out.is_scam
    assert out.identity_suspicion
    assert not out.needs_review_boost
    assert not hybrid_second_evidence(out, meta)


def test_spam_empty_name_subject_is_verdacht():
    meta = _Meta(
        sender="local-leer@beispiel.example",
        sender_name="",
        subject="(Kein Betreff)",
        server_spam_flag=True,
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert ev.identity_suspicion
    assert not ev.needs_review_boost


def test_llm_unclear_in_curated_inbox_no_review_boost():
    meta = _Meta(
        sender="benutzer1@beispiel.example",
        sender_name="Example Org",
        subject="Info",
        folder="INBOX/wichtig",
    )
    out = ScamEvaluation(needs_review_boost=False)
    _merge_hybrid_llm_identity(
        out,
        meta,
        {"verdict": "U", "reason": "unklar"},
    )
    assert not out.needs_review_boost


def test_llm_unclear_outside_curated_inbox_boosts_review():
    meta = _Meta(
        sender="news@beispiel.example",
        sender_name="Example Org",
        subject="Info",
        folder="Trash",
    )
    out = ScamEvaluation()
    _merge_hybrid_llm_identity(
        out,
        meta,
        {"verdict": "U", "reason": "unklar"},
    )
    assert out.needs_review_boost


def test_hybrid_merge_s_with_transport_is_scam():
    meta = _Meta(
        sender="kv02@devs-demo-template.com",
        sender_name="Raiffeisen Kundenservice",
        subject="Ein wichtiger Hinweis",
        server_spam_flag=True,
        provider_junk_score=10,
    )
    out = ScamEvaluation(
        transport_score=28,
        identity_rules=["E3"],
        identity_score=55,
    )
    assert hybrid_second_evidence(out, meta)
    _merge_hybrid_llm_identity(
        out,
        meta,
        {"verdict": "S", "reason": "Behauptete Bank, fremde Domain"},
    )
    assert out.is_scam


def test_hybrid_llm_integration_with_provider_and_verdict_s(monkeypatch):
    meta = _Meta(
        sender="kv02@devs-demo-template.com",
        sender_name="Raiffeisen Kundenservice",
        subject="Ein wichtiger Hinweis zu Ihrem Konto",
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )

    def fake_llm(*_a, **_kw):
        return {"verdict": "S", "reason": "Behauptete Bank, fremde Domain"}

    monkeypatch.setattr(
        "src.services.audit_scam_detection.identity_llm_check",
        fake_llm,
    )
    ev = evaluate_scam_risk(
        meta,
        llm_enabled=True,
        audit_llm_config=_llm_cfg_enabled(),
    )
    assert ev.is_scam
    assert {"B1", "E3"} <= set(ev.identity_rules)
    assert any(r.startswith("Identität:") for r in ev.reasons)
    if ev.llm_used:
        assert any("Identität (KI)" in r for r in ev.reasons)


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
    assert any("Lookalike" in f for f in ev.layer1_flags)


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


def test_apple_privaterelay_skips_e4_not_scam():
    """Newsletter über Hide My Email: Relay-Local-Part ist kein E4-Signal."""
    meta = _Meta(
        sender=(
            "no-reply_at_news_termius_com_trncpxkqch_3e11dd0e"
            "@privaterelay.appleid.com"
        ),
        sender_name="Termius News",
        subject="Termius News: Android updates",
        provider_junk_score=2,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert "E4" not in ev.identity_rules
    assert not ev.is_scam


def test_insta360_strong_auth_calibrates_llm_s():
    from src.services.audit_scam_detection import calibrate_llm_identity_result

    meta = _Meta(
        sender="noreply@dm.insta360.com",
        sender_name="Insta360",
        subject="Email Verification Code",
        auth_results=(
            "dkim=pass header.i=@dm.insta360.com; spf=pass; dmarc=pass"
        ),
    )
    raw_llm = {
        "verdict": "S",
        "reason": "Subdomain dm. ist verdächtig",
    }
    llm = calibrate_llm_identity_result(meta, raw_llm)
    out = ScamEvaluation()
    _merge_hybrid_llm_identity(out, meta, llm)
    assert not out.is_scam
    assert not out.needs_review_boost


@pytest.mark.parametrize(
    "sender,sender_name",
    [
        ("service@paypal-secure-login.com", "PayPal Support"),
        ("info@swisscom-kundendienst-ch.com", "Swisscom Kundendienst"),
        ("no-reply@ubs-sicherheitscenter.net", "UBS Sicherheit"),
        ("info@postfinance.evil-domain.com", "PostFinance"),
    ],
)
def test_llm_calibration_rejects_lookalike_registrable_domain(
    sender, sender_name
):
    from src.services.audit_scam_detection import (
        _llm_identity_verdict,
        calibrate_llm_identity_result,
    )

    meta = _Meta(
        sender=sender,
        sender_name=sender_name,
        subject="Wichtiger Hinweis",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    raw_llm = {"verdict": "S", "reason": "Marken-Domain passt nicht"}
    llm = calibrate_llm_identity_result(meta, raw_llm)
    assert _llm_identity_verdict(llm) == "S"


@pytest.mark.parametrize(
    "sender,sender_name",
    [
        ("service@paypal.support", "PayPal"),
        ("info@swisscom.top", "Swisscom"),
        ("security@microsoft.cc", "Microsoft"),
        ("noreply@amazon.com.evil.com", "Amazon"),
    ],
)
def test_llm_calibration_rejects_wrong_tld_known_brand(sender, sender_name):
    from src.services.audit_scam_detection import (
        _llm_identity_verdict,
        calibrate_llm_identity_result,
    )

    meta = _Meta(
        sender=sender,
        sender_name=sender_name,
        subject="Account notice",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    raw_llm = {"verdict": "S", "reason": "Domain passt nicht zur Marke"}
    llm = calibrate_llm_identity_result(meta, raw_llm)
    assert _llm_identity_verdict(llm) == "S"


def test_amazon_co_uk_strong_auth_calibrates_llm_s():
    from src.services.audit_scam_detection import calibrate_llm_identity_result

    meta = _Meta(
        sender="orders@amazon.co.uk",
        sender_name="Amazon",
        subject="Your order",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    raw_llm = {"verdict": "S", "reason": "co.uk wirkt ungewohnt"}
    llm = calibrate_llm_identity_result(meta, raw_llm)
    assert llm.get("verdict") == "O"


def test_llm_calibration_skipped_when_layer1_e3():
    from src.services.audit_scam_detection import (
        _llm_identity_verdict,
        calibrate_llm_identity_result,
    )

    meta = _Meta(
        sender="jan.muster@firma-beispiel.example",
        sender_name="ZKB - Zürcher Kantonalbank - Unterstutzungskontakt",
        subject="Bitte kurz prüfen",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    raw_llm = {"verdict": "S", "reason": "Bank mismatch"}
    llm = calibrate_llm_identity_result(meta, raw_llm)
    assert _llm_identity_verdict(llm) == "S"


def test_check_dbl_reputation_cache_skips_live_quota(monkeypatch):
    from src.services import audit_scam_detection as asd
    from src.services import domain_reputation as dr

    live_calls = []

    monkeypatch.setattr(
        dr,
        "read_spamhaus_dbl_cache",
        lambda domain, db_session=None: dr.DblLookupResult(
            True, "Spamhaus DBL (127.0.1.4)", False
        ),
    )
    monkeypatch.setattr(
        dr,
        "lookup_spamhaus_dbl",
        lambda domain, db_session=None: live_calls.append(domain)
        or dr.DblLookupResult(False, "", False),
    )
    listed, detail = asd.check_dbl("evil-example.com")
    assert listed is True
    assert "127.0.1.4" in detail
    assert live_calls == []
    assert asd._dbl_lookups_this_scan == 0


def _llm_cfg_prompt(version: int) -> AuditScamLlmConfig:
    return AuditScamLlmConfig(
        enabled=True,
        provider="ollama",
        model="test-model",
        think=False,
        base_url="http://127.0.0.1:11434",
        prompt_version=version,
        timeout=90,
        configured_via="user",
    )


def test_identity_llm_check_prompt_v2_stubbed(monkeypatch):
    from src.services.audit_scam_detection import (
        _identity_llm_cache,
        identity_llm_check,
    )

    _identity_llm_cache.clear()
    meta = _Meta(
        sender="noreply@shop-beispiel.example",
        sender_name="Shop Beispiel",
        subject="Ihre Rechnung v2-stub",
        reply_to="other@betrug-beispiel.example",
    )
    seen = {}

    def fake_json(prompt, cfg=None):
        seen["prompt"] = prompt
        return {
            "verdict": "O",
            "mismatch": False,
            "confidence": 0,
            "reason": None,
            "impersonated": None,
        }

    monkeypatch.setattr(
        "src.services.audit_scam_detection._load_identity_llm_db",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "src.services.audit_scam_detection._store_identity_llm_db",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "src.services.audit_scam_detection._audit_identity_llm_json",
        fake_json,
    )
    result = identity_llm_check(meta, cfg=_llm_cfg_prompt(2))
    assert result is not None
    assert result["verdict"] == "O"
    assert "prompt" in seen
    assert "replyto_domain" not in seen["prompt"]


def test_identity_llm_check_prompt_v1_stubbed(monkeypatch):
    from src.services.audit_scam_detection import (
        _identity_llm_cache,
        identity_llm_check,
    )

    _identity_llm_cache.clear()
    meta = _Meta(
        sender="noreply@shop-beispiel.example",
        sender_name="Shop Beispiel",
        subject="Ihre Rechnung v1-stub",
        reply_to="other@betrug-beispiel.example",
        server_spam_flag=True,
        provider_junk_score=8,
        auth_results="dkim=pass",
    )
    seen = {}

    def fake_json(prompt, cfg=None):
        seen["prompt"] = prompt
        return {
            "verdict": "S",
            "mismatch": True,
            "confidence": 80,
            "reason": "Test",
            "impersonated": "Shop",
        }

    monkeypatch.setattr(
        "src.services.audit_scam_detection._load_identity_llm_db",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "src.services.audit_scam_detection._store_identity_llm_db",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "src.services.audit_scam_detection._audit_identity_llm_json",
        fake_json,
    )
    result = identity_llm_check(meta, cfg=_llm_cfg_prompt(1))
    assert result is not None
    assert "prompt" in seen
    assert "betrug-beispiel.example" in seen["prompt"]
