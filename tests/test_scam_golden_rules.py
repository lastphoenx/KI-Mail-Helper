"""Golden-Set + Akzeptanztests Phase 1 Scam-Regeln."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pytest

from src.services.audit_scam_detection import (
    assess_transport,
    evaluate_scam_risk,
    should_never_scam,
    TRANSPORT_SCORE_CAP,
)
from src.services.folder_audit_service import FolderAuditService, TrashCategory, TrashEmailInfo
from tests.scam_golden_set import OWN_DOMAINS, ROWS


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


def _meta(**kw) -> _Meta:
    return _Meta(**kw)


def test_wordfence_pattern_transport_only_not_scam():
    """Spam-Flag + Junk + kein DKIM/DMARC, ohne Identität → höchstens REVIEW."""
    meta = _meta(
        sender="wordpress@kleine-firma.example",
        sender_name="WordPress",
        subject="[Wordfence Alert] Problems found",
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="mailprovider.example; dkim=none; spf=pass; dmarc=none",
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert not ev.is_scam
    assert ev.needs_review_boost
    assert any(r.startswith("Transport:") for r in ev.reasons)
    assert not any(r.startswith("Identität:") for r in ev.reasons)


def test_e1_slash_with_provider_is_scam():
    meta = _meta(
        sender="Swisscom-kundenbetreuung.ch/feedback/6und0@sendhost-demo.net",
        sender_name="Swisscom Kundenbetreuung",
        subject="Ihr WLAN-Verstärker ist abrufbereit",
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="dkim=pass; spf=pass; dmarc=pass",
    )
    ev = evaluate_scam_risk(meta, llm_enabled=False)
    assert ev.is_scam
    assert "E1" in ev.identity_rules
    assert any(r.startswith("Identität:") for r in ev.reasons)


def test_transport_score_capped():
    meta = _meta(
        sender="x@example.com",
        sender_name="Shop",
        server_spam_flag=True,
        provider_junk_score=10,
    )
    score, line = assess_transport(meta)
    assert score <= TRANSPORT_SCORE_CAP
    assert line.startswith("Provider-Verdikt")
    assert line.count("Junk") == 1
    assert line.count("Spam") == 1 or "Spam-Flag" in line


def test_own_domain_never_scam_wordfence():
    meta = _meta(
        sender="wordpress@meine-seite.example",
        sender_name="WordPress",
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="dkim=none; dmarc=none; spf=pass",
    )
    assert should_never_scam(meta, own_domains=OWN_DOMAINS)
    ev = evaluate_scam_risk(
        meta,
        never_scam=should_never_scam(meta, own_domains=OWN_DOMAINS),
        llm_enabled=False,
    )
    assert not ev.is_scam


def test_noreply_local_not_never_scam():
    meta = _meta(sender="noreply@raiffeisen.ch", sender_name="Raiffeisen")
    assert not should_never_scam(meta, own_domains=set())


def test_freemail_account_email_only_never_scam():
    meta_own = _meta(sender="anna.muster@example-freemail.ch", sender_name="Anna")
    meta_other = _meta(sender="scam@evil-demo.net", sender_name="Scam")
    assert should_never_scam(meta_own, account_email="anna.muster@example-freemail.ch")
    assert not should_never_scam(meta_other, account_email="anna.muster@example-freemail.ch")


def test_golden_rules_fifteen_scam_zero_false_positives():
    """Regeln allein: Golden-S als Scam (S) oder Verdacht (U), 0 Falschalarme auf N/H/A.

    B1+E3 ohne Provider → U (Verdacht), nicht S; mit Junk/Auth-Schwäche → S.
    """
    from scripts.eval_scam import rule_eval

    scam_tp = suspect_tp = fp = 0
    for row in ROWS:
        label = row[0]
        pred = rule_eval(row)[0]
        if pred == "S" and label != "S":
            fp += 1
        elif label == "S":
            if pred == "S":
                scam_tp += 1
            elif pred == "U":
                suspect_tp += 1
    assert fp == 0
    assert scam_tp + suspect_tp >= 20


def test_golden_e1_rows_scam_without_llm():
    for row in ROWS:
        if row[0] != "S" or "/" not in row[2].split("@")[0]:
            continue
        _, name, addr, subj, p, auth, lu = row
        auth_results = (
            "dkim=none; dmarc=none; spf=pass"
            if auth == "none"
            else "dkim=pass; spf=pass; dmarc=pass"
        )
        meta = _Meta(
            subject=subj,
            sender=addr,
            sender_name=name,
            auth_results=auth_results,
            server_spam_flag=bool(p),
            provider_junk_score=10 if p else None,
        )
        ev = evaluate_scam_risk(meta, llm_enabled=False)
        assert ev.is_scam, addr


def test_integrated_wordfence_on_own_domain_not_scam():
    info = TrashEmailInfo(
        uid=1,
        subject="[Wordfence Alert] Problems found on meine-seite.example",
        sender="wordpress@meine-seite.example",
        sender_name="WordPress",
        date=datetime.now(timezone.utc),
        has_attachments=False,
        flags=[],
        size=100,
        server_spam_flag=True,
        provider_junk_score=10,
        auth_results="mailprovider.example; dkim=none; spf=pass; dmarc=none",
    )
    out = FolderAuditService.analyze_email(
        info,
        audit_config={"trusted_domains": set(), "own_domains": OWN_DOMAINS},
    )
    assert out.category != TrashCategory.SCAM
