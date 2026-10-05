"""Löschschutz-Vetos und Person/E6-Regression."""
from dataclasses import dataclass
from typing import Optional

import pytest

from src.services.audit_scam_detection import identity_rule_e6
from src.services.audit_safe_delete_veto import (
    is_sent_or_drafts_folder,
    safe_delete_veto_reason,
)
from src.services.brand_domain_policy import find_brand_token_in_unofficial_host
from src.services.folder_audit_service import FolderAuditService, TrashCategory, TrashEmailInfo


@dataclass
class _Info:
    subject: str = ""
    sender: str = ""
    sender_name: str = ""
    folder: str = ""
    is_reply: bool = False
    has_attachments: bool = False
    has_list_unsubscribe: bool = False
    flags: Optional[list] = None
    reasons: Optional[list] = None


def _veto_subject(subject: str) -> bool:
    info = _Info(
        subject=subject,
        sender="news@marketing.example",
        has_list_unsubscribe=True,
    )
    return "geschütztes Muster" in (safe_delete_veto_reason(info, is_marketing=True) or "")


@pytest.mark.parametrize(
    "subject",
    [
        "Ihre Rechnungen",
        "Neue Anmeldung auf Ihrem Konto",
        "Bitte bestätigen Sie Ihre E-Mail-Adresse",
        "Ihr Code: 482913",
        "Zahlung ausstehend",
        "Bestellung wurde versendet",
        "Terminbestätigung",
    ],
)
def test_safe_veto_subject_patterns(subject):
    assert _veto_subject(subject)


def test_safe_veto_flagged_outside_inbox():
    info = _Info(
        subject="Newsletter",
        sender="news@marketing.example",
        folder="Archiv.2024",
        flags=["\\Flagged"],
        has_list_unsubscribe=True,
    )
    assert safe_delete_veto_reason(info, is_marketing=True) == "Als wichtig markiert (Flag)"


def test_sent_folder_gesendete_elemente():
    assert is_sent_or_drafts_folder("Gesendete Elemente")
    assert is_sent_or_drafts_folder("INBOX/Gesendete Elemente")


def test_safe_veto_conversation():
    info = _Info(
        subject="Newsletter",
        sender="news@marketing.example",
        is_reply=True,
        reasons=["💬 Teil einer Konversation"],
    )
    assert safe_delete_veto_reason(info) == "Teil einer Konversation"


def test_safe_veto_financial_without_newsletter():
    info = _Info(
        subject="Gebühreninformationen",
        sender="billing@beispiel.example",
        has_list_unsubscribe=False,
    )
    reason = safe_delete_veto_reason(info, is_marketing=False)
    assert reason == "Finanz-/Abrechnungsmail ohne Newsletter-Kontext"


def test_safe_veto_financial_not_feedback_subject():
    info = _Info(
        subject="Your Feedback matters",
        sender="news@beispiel.example",
        has_list_unsubscribe=False,
    )
    assert safe_delete_veto_reason(info, is_marketing=False) is None


def test_safe_veto_financial_sender_local_billing():
    info = _Info(
        subject="Monthly summary",
        sender="invoice@beispiel.example",
        sender_name="Accounts",
        has_list_unsubscribe=False,
    )
    reason = safe_delete_veto_reason(info, is_marketing=False)
    assert reason == "Finanz-/Abrechnungsmail ohne Newsletter-Kontext"


def test_safe_veto_ticket_subject():
    info = _Info(
        subject="[#101922024] Gehackt",
        sender="support@shop.example",
        has_list_unsubscribe=True,
    )
    assert "geschütztes Muster" in (safe_delete_veto_reason(info, is_marketing=True) or "")


def test_analyze_safe_veto_downgrades_to_review():
    info = TrashEmailInfo(
        uid=1,
        subject="Aw: Angebot für Arbeiten",
        sender="contact@corp-example.test",
        sender_name="Example Corp",
        date=None,
        has_attachments=False,
        flags=[],
        size=100,
        is_reply=True,
        has_list_unsubscribe=True,
    )
    out = FolderAuditService.analyze_email(info, llm_enabled=False)
    assert out.category != TrashCategory.SAFE
    assert any("Löschschutz" in r for r in out.reasons)


def test_person_name_no_e6_on_freemail():
    assert not identity_rule_e6(
        "PersonA Example",
        "persona.example@example-freemail.ch",
    )


def test_person_name_no_e6_person_local():
    assert not identity_rule_e6(
        "PersonA Example",
        "persona.example@corp-example.test",
    )


def test_b2_no_substring_ubs_in_hub():
    bm = {"ubs": ["ubs.com"]}
    assert find_brand_token_in_unofficial_host(
        "x@hub.selected-sales.de",
        bm,
    ) is None


def test_b2_glued_brand_label_in_sld():
    bm = {"hubspot": ["hubspot.com"]}
    hit = find_brand_token_in_unofficial_host(
        "noreply@hubspotprivacy-phish.example",
        bm,
    )
    assert hit is not None
    assert hit.brand_key == "hubspot"


def test_b2_no_relay_apple():
    bm = {"apple": ["apple.com"]}
    assert find_brand_token_in_unofficial_host(
        "abc@privaterelay.appleid.com",
        bm,
    ) is None


def test_sent_folder_mandatory_exclude():
    assert is_sent_or_drafts_folder("INBOX.Gesendet")
    assert is_sent_or_drafts_folder("Entwürfe")
    assert is_sent_or_drafts_folder("Gesendete Elemente")
