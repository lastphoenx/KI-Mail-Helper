"""Qualitäts-Fixes: Löschschutz, never_scam, Harmonize, LLM-Reason."""

from dataclasses import dataclass

from src.services.audit_scam_detection import (
    EmailMeta,
    _sanitize_llm_identity_reason,
    should_never_scam,
)
from src.services.audit_safe_delete_veto import safe_delete_veto_reason
from src.services.folder_audit_service import (
    FolderAuditService,
    REVIEW_DEFAULT_REASON,
    TrashCategory,
    TrashEmailInfo,
)


@dataclass
class _Meta:
    sender: str = ""
    sender_name: str = ""
    subject: str = ""
    folder: str = "INBOX.Spam"
    auth_results: str = ""
    reply_to: str = ""
    x_mailer: str = ""
    server_spam_flag: bool = False
    provider_junk_score: int = 0
    is_auto_generated: bool = False
    to_header: str = ""
    list_unsubscribe: str = ""


def test_postmaster_foreign_not_never_scam():
    meta = _Meta(sender="postmaster@cc-demo-academy.example")
    assert not should_never_scam(meta, own_domains={"shop.example.com"})


def test_postmaster_on_own_domain_still_never_scam():
    meta = _Meta(sender="postmaster@shop.example.com")
    assert should_never_scam(meta, own_domains={"shop.example.com"})


def test_safe_veto_provider_spam_with_newsletter():
    info = TrashEmailInfo(
        uid=1,
        subject="Weekly deals",
        sender="promo@marketing.example",
        sender_name="Shop",
        date=None,
        has_attachments=False,
        flags=[],
        size=1,
        has_list_unsubscribe=True,
        server_spam_flag=True,
    )
    reason = safe_delete_veto_reason(info, is_marketing=True)
    assert reason is None


def test_safe_veto_curated_inbox_folder():
    info = TrashEmailInfo(
        uid=2,
        subject="News",
        sender="news@marketing.example",
        sender_name="",
        date=None,
        has_attachments=False,
        flags=[],
        size=1,
        folder="INBOX.Wichtig",
        has_list_unsubscribe=True,
    )
    assert safe_delete_veto_reason(info, is_marketing=True) is None
    info.curated_folder_patterns = ["INBOX.Wichtig"]
    assert safe_delete_veto_reason(info, is_marketing=True) == (
        "Wichtiger Ordner (Konfiguration): INBOX.Wichtig"
    )


def test_llm_reason_rejects_hallucinated_version():
    assert _sanitize_llm_identity_reason(
        "Windows 12.5 gibt es nicht und ist erfunden"
    ) is None
    assert _sanitize_llm_identity_reason("Marke passt nicht zur Domain.") is not None


def test_harmonize_repeat_domain_without_list_unsubscribe():
    sender = "promo@alibaba-beispiel.example"
    emails: list[TrashEmailInfo] = []
    for i in range(4):
        emails.append(
            TrashEmailInfo(
                uid=i,
                subject="Flash sale 50% off",
                sender=sender,
                sender_name="Deals",
                date=None,
                has_attachments=False,
                flags=[],
                size=1,
                category=TrashCategory.SAFE,
            )
        )
    for i in range(4, 8):
        info = TrashEmailInfo(
            uid=i,
            subject="Flash sale 50% off",
            sender=sender,
            sender_name="Deals",
            date=None,
            has_attachments=False,
            flags=[],
            size=1,
            category=TrashCategory.REVIEW,
            has_list_unsubscribe=False,
        )
        FolderAuditService._ensure_review_reasons(info)
        assert info.reasons == [REVIEW_DEFAULT_REASON]
        emails.append(info)
    FolderAuditService._harmonize_repeat_marketing_senders(emails)
    review = [e for e in emails if e.uid >= 4]
    assert all(e.category == TrashCategory.SAFE for e in review)


def test_analyze_db_safe_subject_without_unsub_not_marketing_safe():
    info = TrashEmailInfo(
        uid=10,
        subject="Unser xyzspezial kw12 nur für sie",
        sender="ads@retail.example",
        sender_name="Retail",
        date=None,
        has_attachments=False,
        flags=[],
        size=1,
        has_list_unsubscribe=False,
    )
    audit_config = {
        "trusted_domains": set(),
        "own_domains": set(),
        "safe_subject_patterns": {"xyzspezial"},
        "safe_sender_patterns": set(),
        "important_keywords": set(),
        "auto_delete_rules": [],
        "brand_official_domains_effective": {},
    }
    out = FolderAuditService.analyze_email(
        info,
        audit_config=audit_config,
        llm_enabled=False,
    )
    assert out.category == TrashCategory.REVIEW
    assert any("kein List-Unsubscribe" in r for r in (out.reasons or []))
