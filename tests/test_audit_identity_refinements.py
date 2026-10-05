"""Rollen-Local-Parts, INBOX-Kontext, E9, Löschschutz-Erweiterungen."""

from dataclasses import dataclass
from typing import Optional

from src.services.audit_identity_helpers import (
    fold_identity_ascii,
    is_functional_role_local,
    is_curated_inbox_context,
    local_reflects_person_name,
    normalize_display_name_for_identity,
)
from src.services.audit_known_contacts import KnownContactContext, find_name_impersonation
from src.services.audit_scam_detection import evaluate_scam_risk, identity_rule_e9
from src.services.audit_safe_delete_veto import safe_delete_veto_reason
from src.services.folder_audit_service import TrashCategory, TrashEmailInfo


@dataclass
class _Meta:
    subject: str = ""
    sender: str = ""
    sender_name: str = ""
    folder: str = ""
    has_attachments: bool = False
    has_list_unsubscribe: bool = False
    provider_junk_score: int | None = None
    server_spam_flag: bool = False
    auth_results: str | None = "dkim=pass; spf=pass; dmarc=pass"
    reply_to: Optional[str] = None
    x_mailer: Optional[str] = None


def test_no_reply_not_private_mailbox_e3():
    from src.services.audit_scam_detection import identity_rule_e3

    assert not identity_rule_e3(
        "Sprüngli Newsletter",
        "no-reply@newsletter-beispiel.example",
    )


def test_person_surname_local_not_e6():
    from src.services.audit_scam_detection import identity_rule_e6

    assert not identity_rule_e6(
        "Max Muster",
        "muster@firma-beispiel.example",
    )


def test_fold_umlaut_local_match():
    assert local_reflects_person_name(
        "Andreas Keller",
        "andreas@keller-beispiel.example",
    )


def test_quoted_comma_display_name():
    n = normalize_display_name_for_identity('"Muster, Max"')
    assert n == "Muster, Max"


def test_e7_alone_not_verdacht():
    meta = _Meta(
        sender_name="Support-Team",
        sender="vorname.nachname@premium-beispiel.example",
        provider_junk_score=2,
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert "E7" in ev.identity_rules
    assert not ev.identity_suspicion


def test_e7_with_spam_flag_verdacht():
    meta = _Meta(
        sender_name="Support-Team",
        sender="vorname.nachname@premium-beispiel.example",
        server_spam_flag=True,
        provider_junk_score=10,
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert "E7" in ev.identity_rules
    assert ev.identity_suspicion


def test_e6_fake_org_display_spam_verdacht():
    meta = _Meta(
        sender_name="FakeShop AG",
        sender="fakeshop@phish-beispiel.example",
        server_spam_flag=True,
        provider_junk_score=10,
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert "E6" in ev.identity_rules
    assert ev.identity_suspicion


def test_e3_maria_von_beispiel_spam_verdacht():
    """Personen-Local auf fremder Domain: E3 (nicht E6 — Local spiegelt Namen)."""
    meta = _Meta(
        sender_name="Selina Von Randen",
        sender="selina.randen@host-unrelated-demo.example",
        server_spam_flag=True,
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert "E3" in ev.identity_rules
    assert ev.identity_suspicion


def test_curated_inbox_identity_only_not_verdacht():
    meta = _Meta(
        sender_name="ACME Kundenservice",
        sender="vorname.nachname@unrelated-beispiel.example",
        folder="INBOX/wichtig",
        provider_junk_score=2,
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert ev.identity_rules
    assert not ev.identity_suspicion


def test_e9_person_noreply_invoice():
    meta = _Meta(
        sender_name="Sara Beispiel",
        sender="no-reply@malware-beispiel.example",
        subject="Kopie Rechnung Nr. 12345",
        has_attachments=True,
    )
    meta._firstname_set = frozenset({"sara"})
    assert identity_rule_e9(meta.sender_name, meta.sender, meta)
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert ev.identity_suspicion
    assert "E9" in ev.identity_rules


def test_e9_not_firm_invoice():
    meta = _Meta(
        sender_name="Deutsche Bahn",
        sender="no-reply@bahn-beispiel.example",
        subject="Ihre Rechnung",
        has_attachments=True,
    )
    meta._firstname_set = frozenset({"sara", "max"})
    assert not identity_rule_e9(meta.sender_name, meta.sender, meta)


def test_e9_empty_firstnames_off():
    meta = _Meta(
        sender_name="Apple Store",
        sender="no-reply@apple-beispiel.example",
        subject="Rechnung",
    )
    meta._firstname_set = frozenset()
    assert not identity_rule_e9(meta.sender_name, meta.sender, meta)


def test_n1_name_impersonation():
    ctx = KnownContactContext(
        name_keys={fold_identity_ascii("Max Muster")},
    )
    msg = find_name_impersonation(
        ctx,
        "Max Muster",
        "fremd@betrug-beispiel.example",
        firstnames=frozenset({"max"}),
    )
    assert msg


def test_n1_not_hostpoint_billing_same_org():
    ctx = KnownContactContext(
        name_keys={fold_identity_ascii("Hostpoint Support")},
        name_domains={
            fold_identity_ascii("Hostpoint Support"): {"hostpoint-beispiel.example"},
        },
    )
    msg = find_name_impersonation(
        ctx,
        "Hostpoint Support",
        "billing@hostpoint-beispiel.example",
        firstnames=frozenset({"max"}),
    )
    assert msg is None


def test_n1_not_one_word_brand():
    ctx = KnownContactContext(name_keys={fold_identity_ascii("Hostpoint")})
    msg = find_name_impersonation(
        ctx,
        "Hostpoint",
        "news@fremd-beispiel.example",
        firstnames=frozenset({"hostpoint"}),
    )
    assert msg is None


def test_safe_delete_veto_attachment_despite_newsletter():
    info = TrashEmailInfo(
        uid=1,
        subject="Ihr Vertrag Prometeo",
        sender="news@shop-beispiel.example",
        sender_name="Shop",
        date=None,
        has_attachments=True,
        flags=[],
        size=1,
        has_list_unsubscribe=True,
    )
    reason = safe_delete_veto_reason(info, is_marketing=True)
    assert reason is not None


def test_review_default_reason_when_only_age_hint():
    from src.services.folder_audit_service import (
        FolderAuditService,
        REVIEW_DEFAULT_REASON,
    )

    info = TrashEmailInfo(
        uid=2,
        subject="Deals",
        sender="unknown@beispiel.example",
        sender_name="Shop",
        date=None,
        has_attachments=False,
        flags=[],
        size=1,
    )
    info.category = TrashCategory.REVIEW
    info.reasons = ["Kürzlich gelöscht"]
    FolderAuditService._ensure_review_reasons(info)
    assert info.reasons == [REVIEW_DEFAULT_REASON]


def test_review_default_reason():
    from src.services.folder_audit_service import FolderAuditService

    info = TrashEmailInfo(
        uid=2,
        subject="",
        sender="unknown@beispiel.example",
        sender_name="",
        date=None,
        has_attachments=False,
        flags=[],
        size=1,
    )
    info.category = TrashCategory.REVIEW
    FolderAuditService._ensure_review_reasons(info)
    assert info.reasons


def test_is_curated_inbox_context():
    assert is_curated_inbox_context(_Meta(folder="INBOX/Dringend"))
    assert not is_curated_inbox_context(
        _Meta(folder="INBOX/Spamverdacht", server_spam_flag=True)
    )


def test_functional_role_locals():
    assert is_functional_role_local("no-reply@amazon-beispiel.example")
    assert is_functional_role_local("event-mailings@ct-beispiel.example")


def test_safe_delete_no_false_positive_substrings():
    for subj in (
        "What we learned about birds",
        "Neue Laborjacke im Sale",
        "Kabo Sneaker",
        "Delivery Hero Angebot",
        "Zollfreie Preise",
    ):
        info = TrashEmailInfo(
            uid=10,
            subject=subj,
            sender="shop@beispiel.example",
            sender_name="Shop",
            date=None,
            has_attachments=False,
            flags=[],
            size=1,
            has_list_unsubscribe=True,
        )
        assert safe_delete_veto_reason(info, is_marketing=True) is None


def test_all_caps_display_normalized():
    n = normalize_display_name_for_identity("MARIA CRISTINA")
    assert n == "maria cristina"


def test_e3_not_all_caps_person_local():
    from src.services.audit_scam_detection import identity_rule_e3

    meta = _Meta(
        sender_name="MARIA CRISTINA",
        sender="c.maria@firma-beispiel.example",
    )
    meta._firstname_set = frozenset({"cristina"})
    assert not identity_rule_e3(meta.sender_name, meta.sender, meta=meta)


def test_harmonize_repeat_marketing_senders_by_domain():
    from src.services.folder_audit_service import (
        FolderAuditService,
        REVIEW_DEFAULT_REASON,
    )

    emails: list[TrashEmailInfo] = []
    safe_senders = (
        "promo@alibaba-beispiel.example",
        "deals@mail.alibaba-beispiel.example",
        "news@eu.alibaba-beispiel.example",
    )
    for i, sender in enumerate(safe_senders):
        emails.append(
            TrashEmailInfo(
                uid=i,
                subject="Deals",
                sender=sender,
                sender_name="Alibaba",
                date=None,
                has_attachments=False,
                flags=[],
                size=1,
                category=TrashCategory.SAFE,
            )
        )
    for i in range(3, 7):
        info = TrashEmailInfo(
            uid=i,
            subject="Deals",
            sender="other@alibaba-beispiel.example",
            sender_name="Alibaba",
            date=None,
            has_attachments=False,
            flags=[],
            size=1,
            category=TrashCategory.REVIEW,
            has_list_unsubscribe=True,
        )
        FolderAuditService._ensure_review_reasons(info)
        assert info.reasons == [REVIEW_DEFAULT_REASON]
        emails.append(info)
    FolderAuditService._harmonize_repeat_marketing_senders(emails)
    review = [e for e in emails if e.uid >= 3]
    assert all(e.category == TrashCategory.SAFE for e in review)


def test_harmonize_repeat_marketing_senders():
    from src.services.folder_audit_service import (
        FolderAuditService,
        REVIEW_DEFAULT_REASON,
    )

    sender = "promo@alibaba-beispiel.example"
    emails: list[TrashEmailInfo] = []
    for i in range(3):
        emails.append(
            TrashEmailInfo(
                uid=i,
                subject="Deals",
                sender=sender,
                sender_name="Alibaba",
                date=None,
                has_attachments=False,
                flags=[],
                size=1,
                category=TrashCategory.SAFE,
            )
        )
    for i in range(3, 7):
        info = TrashEmailInfo(
            uid=i,
            subject="Deals",
            sender=sender,
            sender_name="Alibaba",
            date=None,
            has_attachments=False,
            flags=[],
            size=1,
            category=TrashCategory.REVIEW,
            has_list_unsubscribe=True,
        )
        FolderAuditService._ensure_review_reasons(info)
        assert info.reasons == [REVIEW_DEFAULT_REASON]
        emails.append(info)
    FolderAuditService._harmonize_repeat_marketing_senders(emails)
    review = [e for e in emails if e.uid >= 3]
    assert all(e.category == TrashCategory.SAFE for e in review)
