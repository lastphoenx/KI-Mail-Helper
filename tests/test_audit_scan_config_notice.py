"""Scan-Hinweis: Konfigurations-Zusammenfassung."""

from src.services.audit_scan_config_notice import build_audit_scan_config_notice


def test_build_notice_without_db_reports_error():
    notice, err = build_audit_scan_config_notice(None, user_id=1, account_id=1)
    assert err
    assert "Konfiguration im Scan:" in notice


def test_build_notice_from_scan_config_snapshot():
    cfg = {
        "audit_config_load_ok": True,
        "brand_official_domains_custom": {"example": ["example.com"]},
        "brand_official_domains_effective": {"example": ["example.com"], "builtin": ["builtin.example"]},
        "own_domains": {"mine.example"},
        "trusted_domains": {"trusted.example"},
        "vip_senders": {"vip@example.com"},
        "safe_subject_patterns": {"newsletter"},
        "safe_sender_patterns": set(),
        "known_contacts_count": 2,
        "exclude_folder_count": 1,
    }
    notice, err = build_audit_scan_config_notice(
        None,
        user_id=1,
        account_id=1,
        audit_config=cfg,
        config_load_ok=True,
    )
    assert not err
    assert "Konfiguration im Scan:" in notice
    assert "Meine Domains: 1" in notice
    assert "Marketing-Pattern: 1" in notice


def test_build_notice_load_failed_no_fake_counts():
    notice, err = build_audit_scan_config_notice(
        None,
        user_id=1,
        account_id=1,
        audit_config={},
        config_load_ok=False,
    )
    assert err
    assert "nicht vollständig geladen" in notice
    assert "222 Marken" not in notice
