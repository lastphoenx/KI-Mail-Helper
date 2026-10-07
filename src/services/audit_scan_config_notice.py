"""Scan-Hinweis: Zusammenfassung der beim Scan geladenen Audit-Konfiguration."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _counts_from_audit_config(
    audit_config: Dict[str, Any],
) -> Tuple[int, int, int, int, int, int, int, int, int, int, int, int]:
    from src.services.brand_domain_policy import BUILTIN_BRAND_OFFICIAL_DOMAINS

    custom_map = audit_config.get("brand_official_domains_custom") or {}
    effective_map = audit_config.get("brand_official_domains_effective") or {}
    custom_keys = set(custom_map)
    builtin_keys = set(BUILTIN_BRAND_OFFICIAL_DOMAINS)
    effective_keys = set(effective_map) or (custom_keys | builtin_keys)
    overlap = len(custom_keys & builtin_keys & effective_keys)
    custom_only = len((custom_keys & effective_keys) - builtin_keys)
    builtin_only = len(effective_keys - custom_keys)
    effective_brands = len(effective_keys)
    custom_brands = custom_only
    builtin_brands = builtin_only

    n_own = len(audit_config.get("own_domains") or [])
    n_trusted = len(audit_config.get("trusted_domains") or [])
    n_vip = len(audit_config.get("vip_senders") or [])
    n_safe_subject = len(audit_config.get("safe_subject_patterns") or [])
    n_safe_sender = len(audit_config.get("safe_sender_patterns") or [])
    n_known = int(audit_config.get("known_contacts_count") or 0)
    n_exclude = int(audit_config.get("exclude_folder_count") or 0)
    return (
        effective_brands,
        custom_brands,
        builtin_brands,
        n_own,
        n_trusted,
        n_vip,
        n_known,
        n_safe_subject,
        n_safe_sender,
        n_exclude,
        overlap,
        len(custom_keys),
    )


def build_audit_scan_config_notice(
    db_session,
    user_id: int,
    account_id: Optional[int] = None,
    *,
    audit_config: Optional[Dict[str, Any]] = None,
    config_load_ok: Optional[bool] = None,
) -> Tuple[str, bool]:
    """Returns (notice_text, load_error). Prefer audit_config from the scan run."""
    if audit_config is None:
        if db_session is None or user_id is None:
            return ("Konfiguration im Scan: nicht geladen (kein Benutzerkontext).", True)
        from src.services.folder_audit_service import AuditConfigCache

        audit_config = AuditConfigCache.get_config(db_session, user_id, account_id) or {}
        if config_load_ok is None:
            config_load_ok = bool(audit_config.get("audit_config_load_ok"))

    if config_load_ok is None:
        config_load_ok = bool(audit_config.get("audit_config_load_ok"))

    load_error = not config_load_ok

    if load_error:
        return (
            "⚠️ Konfiguration im Scan: nicht vollständig geladen — "
            "Analyse lief ggf. mit leeren Listen. Bitte Scan wiederholen oder Logs prüfen.",
            True,
        )

    (
        effective_brands,
        custom_brands,
        builtin_brands,
        n_own,
        n_trusted,
        n_vip,
        n_known,
        n_safe_subject,
        n_safe_sender,
        n_exclude,
        overlap,
        custom_entry_count,
    ) = _counts_from_audit_config(audit_config)

    brand_json_warn = False
    row_hint = audit_config.get("_brand_json_bytes")
    if row_hint and isinstance(row_hint, int) and row_hint > 10 and custom_entry_count == 0:
        brand_json_warn = True
        logger.warning(
            "Marken-JSON (%s Bytes) aber 0 Custom-Keys in Scan-Config (user_id=%s)",
            row_hint,
            user_id,
        )

    parts = [
        f"Konfiguration im Scan: {effective_brands} Marken aktiv "
        f"({custom_brands} nur eigene, {builtin_brands} nur System, {overlap} in beiden)",
        f"Meine Domains: {n_own}",
        f"Vertrauenswürdige Domains: {n_trusted}",
        f"VIP: {n_vip}",
        f"Bekannte Kontakte: {n_known}",
        f"Muster Betreff: {n_safe_subject}",
        f"Muster Absender: {n_safe_sender}",
        f"Ordner ausgenommen: {n_exclude}",
    ]
    prefix = "⚠️ Audit-Konfiguration unvollständig — " if brand_json_warn else ""
    return (prefix + " · ".join(parts) + ".", brand_json_warn or load_error)
