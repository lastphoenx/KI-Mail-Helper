"""Scan-Hinweis: geladene Audit-Konfiguration (unabhängig vom AuditConfigCache-Zustand)."""

from __future__ import annotations

import json
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _brand_settings_row(db_session, user_id: int):
    models = __import__("src.02_models", fromlist=["AuditClusterSettings"])
    if not hasattr(models, "AuditClusterSettings"):
        return None
    return (
        db_session.query(models.AuditClusterSettings)
        .filter(
            models.AuditClusterSettings.user_id == user_id,
            models.AuditClusterSettings.account_id == None,
            models.AuditClusterSettings.is_active == True,
        )
        .first()
    )


def _count_model_entries(db_session, user_id: int, account_id: Optional[int], model_name: str) -> int:
    models = __import__("src.02_models", fromlist=[model_name])
    model = getattr(models, model_name, None)
    if model is None:
        return 0
    q = db_session.query(model).filter(
        model.user_id == user_id,
        model.is_active == True,
    )
    if account_id is not None and hasattr(model, "account_id"):
        q = q.filter((model.account_id == account_id) | (model.account_id == None))
    return q.count()


def _own_domains_count(db_session, user_id: int, account_id: Optional[int]) -> int:
    if not account_id:
        return 0
    models = __import__("src.02_models", fromlist=["MailAccount"])
    acc = (
        db_session.query(models.MailAccount)
        .filter(models.MailAccount.id == account_id, models.MailAccount.user_id == user_id)
        .first()
    )
    if not acc:
        return 0
    raw = getattr(acc, "audit_own_domains", None)
    if not raw:
        return 0
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return sum(1 for d in parsed if d and str(d).strip())
    except (TypeError, json.JSONDecodeError):
        logger.debug("audit_own_domains für Scan-Hinweis unparsebar")
    return 0


def _exclude_folder_count(db_session, user_id: int, account_id: Optional[int]) -> int:
    if not account_id:
        return 0
    models = __import__("src.02_models", fromlist=["MailAccount"])
    acc = (
        db_session.query(models.MailAccount)
        .filter(models.MailAccount.id == account_id, models.MailAccount.user_id == user_id)
        .first()
    )
    if not acc:
        return 0
    raw = getattr(acc, "audit_exclude_folders", None)
    if not raw:
        return 0
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return len([x for x in data if x])
    except (TypeError, json.JSONDecodeError):
        pass
    return 0


def _known_contacts_count(db_session, user_id: int, account_id: Optional[int]) -> int:
    if not account_id:
        return 0
    return _count_model_entries(
        db_session, user_id, account_id, "AuditKnownContact"
    )


def build_audit_scan_config_notice(
    db_session,
    user_id: int,
    account_id: Optional[int] = None,
) -> Tuple[str, bool]:
    """Returns (notice_text, load_error). load_error=True → UI soll warnen."""
    if db_session is None or user_id is None:
        return ("Konfiguration im Scan: nicht geladen (kein Benutzerkontext).", True)

    from src.services.brand_domain_health import brand_settings_api_payload

    load_error = False
    row = _brand_settings_row(db_session, user_id)
    brand_payload = brand_settings_api_payload(row, user_id)
    scope = brand_payload.get("scope") or {}
    effective_brands = scope.get("effective_brands") or brand_payload.get("effective_count") or 0
    custom_brands = scope.get("custom_brands") or brand_payload.get("custom_count") or 0
    builtin_brands = scope.get("builtin_brands") or brand_payload.get("builtin_count") or 0

    if row and row.brand_official_domains_json and custom_brands == 0:
        raw_len = len((row.brand_official_domains_json or "").strip())
        if raw_len > 10:
            load_error = True
            logger.warning(
                "Marken-JSON in DB (%s Bytes) aber 0 Custom-Keys nach Parse (user_id=%s)",
                raw_len,
                user_id,
            )

    n_own = _own_domains_count(db_session, user_id, account_id)
    n_trusted = _count_model_entries(db_session, user_id, account_id, "AuditTrustedDomain")
    n_vip = _count_model_entries(db_session, user_id, account_id, "AuditVIPSender")
    n_safe = _count_model_entries(db_session, user_id, account_id, "AuditSafePattern")
    n_known = _known_contacts_count(db_session, user_id, account_id)
    n_exclude = _exclude_folder_count(db_session, user_id, account_id)

    parts = [
        f"Konfiguration im Scan: {effective_brands} Marken aktiv "
        f"(davon {custom_brands} von dir eingetragen, {builtin_brands} System)",
        f"Meine Domains: {n_own}",
        f"Vertrauenswürdige Domains: {n_trusted}",
        f"VIP: {n_vip}",
        f"Bekannte Kontakte: {n_known}",
        f"Marketing-Pattern: {n_safe}",
        f"Ordner ausgenommen: {n_exclude}",
    ]
    prefix = "⚠️ Audit-Konfiguration unvollständig — " if load_error else ""
    return (prefix + " · ".join(parts) + ".", load_error)
