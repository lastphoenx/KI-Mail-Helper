"""Qualitätsregeln A–K mit Zufallswerten, ohne Kontodaten."""

import secrets
from datetime import datetime, timedelta, timezone

from src.services.audit_quality_rules import (
    BRAND_COMPOUND_SUFFIXES,
    OPERATIONAL_ALARM_TOKENS,
    SENSITIVE_SUBJECT_TOKENS,
    curated_marks,
    folder_is_curated,
    is_success_status_subject,
    subject_has_operational_alarm,
    subject_is_sensitive,
)
from src.services.audit_safe_delete_veto import safe_delete_veto_reason
from src.services.audit_scam_detection import (
    _merge_hybrid_llm_identity,
    _sanitize_llm_identity_reason,
    evaluate_scam_risk,
    should_never_scam,
)
from src.services.audit_scan_config_notice import build_audit_scan_config_notice
from src.services.brand_domain_policy import (
    _brand_key_matches_display_name,
    find_brand_in_local_part,
)
from src.services.folder_audit_service import (
    FolderAuditService,
    TrashCategory,
    TrashEmailInfo,
)
from src.services.shared_mail_infrastructure import FREEMAIL_REGISTRABLE


def _token(n: int = 4) -> str:
    return "zw" + secrets.token_hex(n)


def _mail(**kwargs) -> TrashEmailInfo:
    base = dict(
        uid=1,
        subject="Notiz",
        sender=f"news@{_token()}.example",
        sender_name="Qx",
        date=None,
        has_attachments=False,
        flags=[],
        size=20,
    )
    base.update(kwargs)
    return TrashEmailInfo(**base)


def _cfg(**extra):
    cfg = {
        "trusted_domains": set(),
        "own_domains": set(),
        "important_keywords": set(),
        "safe_subject_patterns": set(),
        "safe_sender_patterns": set(),
        "vip_senders": set(),
        "vip_pattern_types": {},
        "success_safe_after_days": 30,
        "transaction_safe_after_days": 30,
        "curated_folder_patterns": [],
    }
    cfg.update(extra)
    return cfg


def test_compound_brand_and_random_suffix_not_official():
    brand = _token()
    suffix = secrets.choice(tuple(BRAND_COMPOUND_SUFFIXES))
    assert _brand_key_matches_display_name(brand, f"{brand}{suffix} news")
    assert _brand_key_matches_display_name(brand, f"hello {brand}")
    assert not _brand_key_matches_display_name(brand, f"{brand}xyz")


def test_account_word_lists_extend_and_disable_system_words():
    extra = _token()
    lists = {
        "alarm": {"added": [extra], "disabled": ["alert"]},
        "sensitive": {"added": ["bolletta"], "disabled": ["konto"]},
        "success": {"added": ["fertig"], "disabled": ["erfolgreich"]},
    }
    assert "alert" in OPERATIONAL_ALARM_TOKENS
    assert "konto" in SENSITIVE_SUBJECT_TOKENS
    assert not subject_has_operational_alarm(f"Alert: {_token()}", lists)
    assert subject_has_operational_alarm(f"Disk failed {_token()}", lists)
    assert subject_has_operational_alarm(f"Hinweis {extra}", lists)
    assert not subject_is_sensitive(f"Konto {_token()}", lists)
    assert subject_is_sensitive(f"Bolletta {_token()}", lists)
    assert subject_is_sensitive(f"Facture {_token()}", lists)
    assert not is_success_status_subject(f"Vorgang erfolgreich {_token()}", lists)
    assert is_success_status_subject(f"Backup fertig {_token()}", lists)
    assert "." not in "".join(lists["alarm"]["added"])


def test_sensitive_subject_includes_fr_it_tokens():
    assert subject_is_sensitive(f"Vérification {_token()} compte")
    assert subject_is_sensitive(f"sécurité paiement {_token()}")
    assert subject_is_sensitive(f"Facture commande {_token()}")
    assert subject_is_sensitive(f"Verifica sicurezza {_token()}")
    assert subject_is_sensitive(f"Fattura {_token()} pagamento")
    assert subject_is_sensitive(f"Ordine conto {_token()}")
    assert not subject_is_sensitive(f"Wochennotiz {_token()}")


def test_e10_subject_alone_is_not_scam_subdomain_subject_is_scam():
    brand = _token()
    brand_map = {brand: [f"{brand}.example"]}
    foreign = f"{_token()}.example"
    local_sender = f"no_reply_login.{brand}@{foreign}"

    subject_only = _mail(
        sender=local_sender,
        sender_name="Qx",
        subject="Rechnung",
    )
    subject_only.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    ev_subject = evaluate_scam_risk(subject_only, llm_enabled=False, brand_map=brand_map)
    assert "E10" in ev_subject.identity_rules
    assert ev_subject.identity_suspicion
    assert not ev_subject.is_scam

    spam = _mail(sender=local_sender, sender_name="Qx", subject="Rechnung")
    spam.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    spam.spam_score = 6.0
    ev_spam = evaluate_scam_risk(spam, llm_enabled=False, brand_map=brand_map)
    assert ev_spam.is_scam

    auth_fail = _mail(sender=local_sender, sender_name="Qx", subject="Wochennotiz")
    auth_fail.auth_results = "spf=fail"
    ev_auth = evaluate_scam_risk(auth_fail, llm_enabled=False, brand_map=brand_map)
    assert ev_auth.is_scam

    sub_sender = f"news@{brand}.{foreign}"
    sub = _mail(sender=sub_sender, sender_name="Qx", subject="Rechnung")
    sub.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    ev_sub = evaluate_scam_risk(sub, llm_enabled=False, brand_map=brand_map)
    assert ev_sub.is_scam


def test_hard_brand_plus_warning_is_scam_local_part_without_warning_is_suspicion():
    brand = _token()
    brand_map = {brand: [f"{brand}.example"]}
    foreign = f"{_token()}.example"
    local_sender = f"no_reply_login.{brand}@{foreign}"
    hit = find_brand_in_local_part(local_sender, brand_map)
    assert hit is not None

    soft = _mail(sender=local_sender, sender_name="Qx", subject="Wochennotiz")
    soft.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    ev_soft = evaluate_scam_risk(soft, llm_enabled=False, brand_map=brand_map)
    assert ev_soft.identity_suspicion
    assert not ev_soft.is_scam

    hard = _mail(
        sender=local_sender,
        sender_name=f"{brand}bank",
        subject="Sicherheitsmitteilung zum Konto",
    )
    hard.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    ev_hard = evaluate_scam_risk(hard, llm_enabled=False, brand_map=brand_map)
    assert ev_hard.is_scam


def test_provider_spam_bulk_without_brand_is_safe():
    info = _mail(
        subject=f"Wochennotiz {_token()}",
        has_list_unsubscribe=True,
        server_spam_flag=True,
        spam_score=6.0,
    )
    out = FolderAuditService.analyze_email(info, audit_config=_cfg(), llm_enabled=False)
    assert out.category == TrashCategory.SAFE
    assert safe_delete_veto_reason(out, is_marketing=True) is None


def test_alarm_not_safe_via_repeat_sender():
    domain = f"{_token()}.example"
    emails = []
    for i in range(5):
        item = _mail(
            uid=i,
            subject=f"Offline device {_token()}",
            sender=f"noreply{i}@{domain}",
            has_list_unsubscribe=True,
        )
        item.category = TrashCategory.REVIEW
        emails.append(item)
    FolderAuditService._harmonize_repeat_marketing_senders(emails)
    assert all(item.category == TrashCategory.SAFE for item in emails)

    plain_domain = f"{_token()}.example"
    plains = []
    for i in range(5):
        item = _mail(
            uid=10 + i,
            subject=f"Offline device {_token()}",
            sender=f"monitor{i}@{plain_domain}",
        )
        item.category = TrashCategory.REVIEW
        plains.append(item)
    FolderAuditService._harmonize_repeat_marketing_senders(plains)
    assert all(item.category == TrashCategory.REVIEW for item in plains)

    alert = _mail(
        subject=f"Alert: {_token()} scan",
        has_list_unsubscribe=True,
    )
    out = FolderAuditService.analyze_email(alert, audit_config=_cfg(), llm_enabled=False)
    assert out.category != TrashCategory.IMPORTANT

    own_domain = f"{_token()}.example"
    own_alert = _mail(
        subject=f"Disk failed {_token()}",
        sender=f"root@{own_domain}",
        sender_name="root",
    )
    own_out = FolderAuditService.analyze_email(
        own_alert,
        account_email=f"root@{own_domain}",
        audit_config=_cfg(own_domains={own_domain}),
        llm_enabled=False,
    )
    assert own_out.category == TrashCategory.IMPORTANT


def test_aged_success_on_own_domain_is_safe_recent_is_not_important():
    domain = f"{_token()}.example"
    sender = f"root@{domain}"
    old = _mail(
        subject=f"rsync erfolgreich {_token()}",
        sender=sender,
        sender_name="root",
        date=datetime.now(timezone.utc) - timedelta(days=40),
    )
    cfg = _cfg(own_domains={domain}, success_safe_after_days=30)
    out_old = FolderAuditService.analyze_email(
        old,
        account_email=sender,
        audit_config=cfg,
        llm_enabled=False,
    )
    assert out_old.category == TrashCategory.SAFE
    assert not any("Löschschutz" in r for r in out_old.reasons)

    recent = _mail(
        subject=f"rsync erfolgreich Datenbank {_token()}",
        sender=sender,
        sender_name="root",
        date=datetime.now(timezone.utc) - timedelta(days=2),
    )
    out_new = FolderAuditService.analyze_email(
        recent,
        account_email=sender,
        audit_config=cfg,
        llm_enabled=False,
    )
    assert out_new.category != TrashCategory.IMPORTANT
    assert out_new.category != TrashCategory.SAFE
    assert not any("Wichtiger Betreff" in r for r in out_new.reasons)


def test_routine_status_stays_review():
    domain = f"{_token()}.example"
    cfg = _cfg(trusted_domains={domain})
    package = _mail(
        subject=f"{_token()}: 4 package update(s)",
        sender=f"notice@{domain}",
        date=datetime.now(timezone.utc) - timedelta(days=1),
    )
    out_pkg = FolderAuditService.analyze_email(
        package, audit_config=cfg, llm_enabled=False
    )
    assert out_pkg.category == TrashCategory.REVIEW

    job = _mail(
        subject="Scan to E-mail Server Job",
        sender=f"scan@{domain}",
    )
    out_job = FolderAuditService.analyze_email(job, audit_config=cfg, llm_enabled=False)
    assert out_job.category != TrashCategory.IMPORTANT


def test_transaction_age_follows_ui_days():
    young = _mail(
        subject=f"Zugestellt {_token()}",
        date=datetime.now(timezone.utc) - timedelta(days=3),
    )
    out_young = FolderAuditService.analyze_email(
        young,
        audit_config=_cfg(transaction_safe_after_days=30),
        llm_enabled=False,
    )
    assert out_young.category != TrashCategory.SAFE

    old = _mail(
        subject=f"Zugestellt {_token()}",
        date=datetime.now(timezone.utc) - timedelta(days=40),
    )
    out_old = FolderAuditService.analyze_email(
        old,
        audit_config=_cfg(transaction_safe_after_days=30),
        llm_enabled=False,
    )
    assert out_old.category == TrashCategory.SAFE


def test_checked_folder_covers_children_not_a_sibling():
    leaf = _token()
    parent = f"X/{leaf}"
    assert folder_is_curated(parent, [parent])
    assert folder_is_curated(f"{parent}/Kind", [parent])
    assert folder_is_curated(parent.replace("/", "."), [parent])
    assert folder_is_curated(f"{parent}/Kind", [parent.replace("/", ".")])
    assert not folder_is_curated(f"{parent}-Archiv", [parent])
    assert not folder_is_curated(f"Archiv/{leaf}", [leaf])
    assert not folder_is_curated(f"Archiv.{leaf}", [leaf])
    assert not folder_is_curated("INBOX", [parent])
    marks = curated_marks(
        [parent, f"{parent}/Kind", f"{parent}-Archiv", f"Archiv/{leaf}", "INBOX"],
        [parent],
    )
    assert marks[parent] is True
    assert marks[f"{parent}/Kind"] is True
    assert marks[f"{parent}-Archiv"] is False
    assert marks[f"Archiv/{leaf}"] is False
    assert marks["INBOX"] is False


def test_plain_inbox_never_curated_pattern_list_is():
    assert not folder_is_curated("INBOX", ["inbox", "Dringend"])
    token = _token()
    assert not folder_is_curated(f"INBOX/{token}/Newsletter", [])
    assert not folder_is_curated(f"INBOX/{token}/Newsletter", [token])
    assert folder_is_curated(f"INBOX/{token}/Newsletter", [f"INBOX/{token}"])
    assert folder_is_curated(f"INBOX.{token}.Newsletter", [f"INBOX/{token}"])


def test_bulk_verification_subject_is_not_important():
    bulk = _mail(
        subject="Verification code",
        sender=f"news@{_token()}.example",
        sender_name="Qx",
        has_list_unsubscribe=True,
    )
    out = FolderAuditService.analyze_email(bulk, audit_config=_cfg(), llm_enabled=False)
    assert out.category != TrashCategory.IMPORTANT
    assert not any("Wichtiger Betreff" in r for r in out.reasons)

    plain = _mail(
        subject="Verification code",
        sender=f"person@{_token()}.example",
        sender_name="Qx",
        has_list_unsubscribe=False,
    )
    plain_out = FolderAuditService.analyze_email(
        plain, audit_config=_cfg(), llm_enabled=False
    )
    assert plain_out.category == TrashCategory.IMPORTANT
    assert plain_out.reasons == ["Wichtiger Betreff"]


def test_suspicion_reason_comes_from_the_identity_rule():
    brand = _token()
    foreign = f"{_token()}.example"
    mail = _mail(
        sender=f"no_reply_login.{brand}@{foreign}",
        sender_name="Qx",
        subject="Verification code",
        has_list_unsubscribe=False,
    )
    mail.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    out = FolderAuditService.analyze_email(
        mail,
        audit_config=_cfg(
            brand_official_domains_effective={brand: [f"{brand}.example"]},
        ),
        llm_enabled=False,
    )
    assert out.category == TrashCategory.SUSPICION
    assert out.reasons
    assert not any("Wichtiger Betreff" in r for r in out.reasons)
    assert any(r.startswith("Identität:") for r in out.reasons)


def test_own_address_does_not_free_the_domain():
    from src.services.audit_own_domains import (
        clean_own_addresses_for_save,
        sender_on_own_domains,
    )

    freemail = sorted(FREEMAIL_REGISTRABLE)[0]
    mine = f"{_token()}@{freemail}"
    other = f"{_token()}@{freemail}"
    assert should_never_scam(_mail(sender=mine), own_addresses={mine})
    assert not should_never_scam(_mail(sender=other), own_addresses={mine})
    cleaned, errors = clean_own_addresses_for_save([mine, freemail])
    assert cleaned == [mine]
    assert errors
    assert not sender_on_own_domains(other, set())
    assert freemail not in cleaned

    brand = _token()
    owned = _mail(sender=mine, sender_name=brand, subject="Verification code")
    owned_out = FolderAuditService.analyze_email(
        owned,
        audit_config=_cfg(
            own_addresses={mine},
            brand_official_domains_effective={brand: [f"{brand}.example"]},
        ),
        llm_enabled=False,
    )
    assert owned_out.category not in (TrashCategory.SCAM, TrashCategory.SUSPICION)


def test_freemail_login_domain_is_not_own_domain():
    freemail = sorted(FREEMAIL_REGISTRABLE)[0]
    account = f"a@{freemail}"
    other = f"b@{freemail}"
    meta = _mail(sender=other)
    assert not should_never_scam(meta, account_email=account)
    assert should_never_scam(_mail(sender=account), account_email=account)
    own = f"{_token()}.example"
    assert should_never_scam(
        _mail(sender=f"other@{own}"),
        account_email=f"me@{own}",
    )


def test_vip_suppresses_soft_identity_not_hard_brand():
    brand = _token()
    first = _token()
    last = _token()
    sender = f"no-reply@{_token()}.example"
    soft = _mail(
        sender=sender,
        sender_name=f"{first} {last}",
        subject=f"Rechnung {_token()}",
        has_attachments=True,
    )
    soft._firstname_set = {first}
    soft.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    soft.vip_matched = True
    ev = evaluate_scam_risk(soft, llm_enabled=False, brand_map={brand: [f"{brand}.example"]})
    assert not ev.identity_suspicion
    assert not ev.is_scam

    soft.vip_matched = False
    ev_open = evaluate_scam_risk(soft, llm_enabled=False, brand_map={brand: [f"{brand}.example"]})
    assert ev_open.identity_suspicion

    soft.vip_matched = True
    soft.auth_results = "dmarc=fail"
    ev_auth = evaluate_scam_risk(soft, llm_enabled=False, brand_map={brand: [f"{brand}.example"]})
    assert ev_auth.identity_suspicion or ev_auth.is_scam

    hard = _mail(
        sender=f"login.{brand}@{_token()}.example",
        sender_name=f"{brand}bank",
        subject="Sicherheitsmitteilung zum Konto",
    )
    hard.vip_matched = True
    hard.auth_results = "dkim=pass; spf=pass; dmarc=pass"
    ev_hard = evaluate_scam_risk(
        hard, llm_enabled=False, brand_map={brand: [f"{brand}.example"]}
    )
    assert ev_hard.is_scam


def test_subject_protection_skipped_when_list_unsubscribe():
    info = _mail(subject=f"Garantie {_token()}", has_list_unsubscribe=True)
    assert safe_delete_veto_reason(info, is_marketing=True) is None
    bare = _mail(subject=f"Garantie {_token()}")
    assert safe_delete_veto_reason(bare, is_marketing=False)


def test_llm_reason_only_one_sentence_and_unclear_hidden():
    assert _sanitize_llm_identity_reason("ich muss das prüfen") is None
    assert _sanitize_llm_identity_reason("also sollte man warten") is None
    long_reason = "Domain passt nicht. " + ("Weiterer Satz. " * 8)
    one = _sanitize_llm_identity_reason(long_reason)
    assert one is not None
    assert "Weiterer" not in one

    meta = _mail()
    out_u = type("E", (), {"reasons": [], "needs_review_boost": False, "is_scam": False, "identity_suspicion": False})()
    _merge_hybrid_llm_identity(
        out_u,
        meta,
        {"verdict": "U", "reason": "This is unclear because the domain might be unrelated and the name is generic."},
    )
    assert not any("Identität (KI)" in r for r in out_u.reasons)
    assert out_u.needs_review_boost

    from src.services.audit_scam_detection import ScamEvaluation

    out_s = ScamEvaluation()
    _merge_hybrid_llm_identity(
        out_s,
        meta,
        {"verdict": "S", "reason": "Domain passt nicht. Zweiter Satz bleibt weg."},
    )
    ki = [r for r in out_s.reasons if r.startswith("Identität (KI)")]
    assert len(ki) == 1
    assert "Zweiter" not in ki[0]


def test_brand_count_parts_sum_to_active():
    custom = {"alphaexample": ["alpha.example"], "sharedexample": ["shared.example"]}
    builtin_key = "sharedexample"
    effective = {
        "alphaexample": ["alpha.example"],
        builtin_key: ["shared.example"],
        "onlysystemexample": ["system.example"],
    }
    notice, err = build_audit_scan_config_notice(
        None,
        user_id=1,
        account_id=1,
        audit_config={
            "audit_config_load_ok": True,
            "brand_official_domains_custom": custom,
            "brand_official_domains_effective": effective,
            "own_domains": [],
            "trusted_domains": [],
            "vip_senders": [],
            "safe_subject_patterns": [],
            "safe_sender_patterns": [],
        },
        config_load_ok=True,
    )
    assert not err
    import re

    match = re.search(
        r"(\d+) Marken aktiv \((\d+) nur eigene, (\d+) nur System, (\d+) in beiden\)",
        notice,
    )
    assert match
    total, own_only, system_only, both = (int(x) for x in match.groups())
    assert own_only + system_only + both == total
    assert total == len(effective)
