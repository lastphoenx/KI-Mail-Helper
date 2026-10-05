"""Synthetische Identitäts-/Marken-Tests (B1, E3, E6, Verdacht vs. Scam)."""
from dataclasses import dataclass
from typing import Optional

import pytest

from src.services.audit_scam_detection import (
    _e3e6_reputation_exempt,
    evaluate_scam_risk,
    identity_rule_e3,
    identity_rule_e6,
    identity_rule_e8,
)
from src.services.brand_domain_policy import effective_brand_map
from src.services.folder_audit_service import FolderAuditService, TrashCategory, TrashEmailInfo


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
    list_unsubscribe: Optional[str] = None
    has_list_unsubscribe: bool = False


def _brand_map():
    base = dict(effective_brand_map(None))
    base["raiffeisen"] = ["raiffeisen.ch"]
    base["swissid"] = ["swissid.ch"]
    base["telekom"] = ["telekom.de", "t-online.de"]
    base["streamplus"] = ["streamplus-beispiel.example", "email.streamplus-beispiel.example"]
    base["aew"] = ["aew.ch"]
    base["swisspass"] = ["swisspass.ch", "notifications.swisspass.ch"]
    return base


def test_e3_n_dot_surname_without_digits():
    assert identity_rule_e3(
        "SwissID Kundenbetreuung",
        "n.muster@example-fake.test",
    )


def test_swissid_b1_e3_suspect_with_reasons():
    meta = _Meta(
        sender_name="SwissID Kundenbetreuung",
        sender="n.muster@example-fake.test",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=_brand_map(), llm_enabled=False)
    assert ev.identity_suspicion
    assert not ev.is_scam
    assert "B1" in ev.identity_rules
    assert "E3" in ev.identity_rules
    assert any(r.startswith("Identität:") for r in ev.reasons)


def test_raiffeisen_short_local_b1_e3_suspect():
    meta = _Meta(
        sender_name="Raiffeisen Kundenservice",
        sender="x@example-fake.test",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=_brand_map(), llm_enabled=False)
    assert ev.identity_suspicion
    assert not ev.is_scam
    assert "B1" in ev.identity_rules and "E3" in ev.identity_rules


def test_deutsche_telekom_e6():
    assert identity_rule_e6(
        "Deutsche Telekom",
        "deutsche-telekom@fake.test",
    )
    meta = _Meta(
        sender_name="Deutsche Telekom",
        sender="deutsche-telekom@fake.test",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=_brand_map(), llm_enabled=False)
    assert "E6" in ev.identity_rules


def test_raiffeisen_official_subdomain_no_hit():
    meta = _Meta(
        sender_name="Raiffeisen",
        sender="noreply@mail.raiffeisen.ch",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=_brand_map(), llm_enabled=False)
    assert not ev.identity_suspicion
    assert "B1" not in ev.identity_rules


def test_auth_pass_does_not_clear_suspect():
    meta = _Meta(
        sender_name="Raiffeisen Kundenservice",
        sender="vorname.nachname@example-fake.test",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=_brand_map(), llm_enabled=False)
    assert ev.identity_suspicion
    assert any("Auth bestanden" in r for r in ev.reasons)


@pytest.mark.parametrize(
    "sender_name,sender",
    [
        ("Michael von StreamPlus", "noreply@email.streamplus-beispiel.example"),
        ("AEW-Mitarbeiter", "vorname.nachname@aew.ch"),
        ("SwissPass", "mailings@notifications.swisspass.ch"),
        ("Apple", "no_reply@email.apple.com"),
    ],
)
def test_legitimate_senders_no_suspicion(sender_name, sender):
    ev = evaluate_scam_risk(
        _Meta(
            sender_name=sender_name,
            sender=sender,
            auth_results="dkim=pass; spf=pass; dmarc=pass",
        ),
        brand_map=_brand_map(),
        llm_enabled=False,
    )
    assert not ev.identity_suspicion
    assert not ev.is_scam


def test_integrated_category_suspicion():
    info = TrashEmailInfo(
        uid=1,
        subject="Konto",
        sender="n.muster@example-fake.test",
        sender_name="SwissID Kundenbetreuung",
        date=None,
        has_attachments=False,
        flags=[],
        size=100,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    out = FolderAuditService.analyze_email(
        info,
        audit_config={
            "trusted_domains": set(),
            "brand_official_domains_effective": _brand_map(),
        },
        llm_enabled=False,
    )
    assert out.category == TrashCategory.SUSPICION
    assert any(r.startswith("Identität:") for r in out.reasons)


def test_scam_with_junk_second_evidence():
    meta = _Meta(
        sender_name="SwissID Kundenbetreuung",
        sender="n.muster@example-fake.test",
        provider_junk_score=2,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=_brand_map(), llm_enabled=False)
    assert ev.identity_suspicion
    assert not ev.is_scam


def test_scam_with_junk5_and_b1_e3():
    meta = _Meta(
        sender_name="SwissID Kundenbetreuung",
        sender="n.muster@example-fake.test",
        provider_junk_score=8,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=_brand_map(), llm_enabled=False)
    assert ev.is_scam
    assert not ev.identity_suspicion


def test_ubs_mailing_not_scam_with_junk2():
    bm = _brand_map()
    bm["ubs"] = ["ubs.com", "mailing.ubs.com"]
    meta = _Meta(
        sender_name="UBS Switzerland",
        sender="ubs_switzerland@mailing.ubs.com",
        provider_junk_score=2,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=bm, llm_enabled=False)
    assert not ev.is_scam
    assert not ev.identity_suspicion


def test_person_on_official_brand_domain_not_e3_e6():
    """Mitarbeiter-Adresse auf offizieller Marken-Domain — kein B2/E3."""
    bm = {
        "portalco": [
            "kundenportal-demo.example",
            "mail.kundenportal-demo.example",
        ],
    }
    meta = _Meta(
        sender_name="Max Muster",
        sender="max.muster@mail.kundenportal-demo.example",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=bm, llm_enabled=False)
    assert "E3" not in ev.identity_rules
    assert "E6" not in ev.identity_rules
    assert "B2" not in ev.identity_rules
    assert not ev.is_scam


def test_b1_alone_is_suspicion_not_scam():
    bm = _brand_map()
    bm["bcv"] = ["bcv.ch"]
    meta = _Meta(
        sender_name="BCV",
        sender="news@unrelated-fake.test",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=bm, llm_enabled=False)
    assert ev.identity_suspicion
    assert not ev.is_scam
    assert "B1" in ev.identity_rules


def test_support_team_private_local_e7():
    meta = _Meta(
        sender_name="Support-Team",
        sender="vorname.nachname@premium-beispiel.example",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert "E7" in ev.identity_rules
    assert not ev.identity_suspicion


def test_e3_send_local_without_org_display():
    assert not identity_rule_e3("Michael Miller", "send@unrelated-fake.test")


def test_e3_short_local_with_org_kundenservice():
    # «send» in E3_LOCAL_STOP; Domain ohne Anzeigenamen-Token (sonst kein E3)
    assert identity_rule_e3("ACME Kundenservice", "druck@unrelated-fake.test")


def test_b2_lookalike_host_without_display_brand():
    bm = _brand_map()
    bm["hubspot"] = ["hubspot.com"]
    meta = _Meta(
        sender_name="Data Privacy Team",
        sender="noreply@hubspotprivacy-phish.example",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=bm, llm_enabled=False)
    assert "B2" in ev.identity_rules
    assert ev.identity_suspicion
    assert not ev.is_scam


def test_i1_shared_infra_brand_in_local():
    bm = _brand_map()
    bm["migros"] = ["migros.ch"]
    meta = _Meta(
        sender_name="Migros",
        sender="migros-news@ccsend.com",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, brand_map=bm, llm_enabled=False)
    assert "I1" in ev.identity_rules
    assert ev.identity_suspicion


def test_e8_noreply_code_local():
    assert identity_rule_e8("Noreply", "23c_demo@example-fake.test")
    meta = _Meta(
        sender_name="Noreply",
        sender="23c_demo@example-fake.test",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert "E8" in ev.identity_rules
    assert ev.identity_suspicion


def test_tranco_auth_without_list_unsub_not_exempt(tmp_path, monkeypatch):
    from src.services.tranco_popularity import build_sqlite_from_rank_pairs, get_tranco_store

    db = tmp_path / "tranco.db"
    build_sqlite_from_rank_pairs([(10, "corp-example.test")], db, list_id="T")
    monkeypatch.setenv("TRANCO_DB_PATH", str(db))
    monkeypatch.setenv("TRANCO_TOP_N", "100000")
    get_tranco_store(force_reload=True)

    meta = _Meta(
        sender_name="Behörde Kundenservice",
        sender="vorname.nachname@corp-example.test",
        auth_results="dkim=pass; spf=pass; dmarc=pass",
        has_list_unsubscribe=False,
    )
    assert identity_rule_e3(meta.sender_name, meta.sender)
    assert not _e3e6_reputation_exempt(meta)
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert "E3" in ev.identity_rules
    assert ev.identity_suspicion
