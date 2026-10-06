"""Scan-Hinweis: Konfigurations-Zusammenfassung."""

from src.services.audit_scan_config_notice import build_audit_scan_config_notice


def test_build_notice_without_db_reports_error():
    notice, err = build_audit_scan_config_notice(None, user_id=1, account_id=1)
    assert err
    assert "Konfiguration im Scan:" in notice
