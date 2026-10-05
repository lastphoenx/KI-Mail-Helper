"""Marken-Domain-Health-Check (lange Laufzeit — Celery, nicht Gunicorn-Request)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional

from src.helpers.database import get_db_session
from src.services.brand_domain_health import (
    brand_health_rdap_user_pref,
    brand_settings_api_payload,
    clear_domain_verification_state,
    domains_in_brand_map,
    persist_brand_health_row,
    run_health_report,
)
from src.services.brand_domain_policy import validate_brand_map
from src.services.domain_reputation import (
    audit_scam_rdap_sender_enabled,
    clear_brand_health_rdap_context,
    resolve_brand_health_rdap,
    set_brand_health_rdap_context,
    validate_official_domains_for_save,
)
from src.services.folder_audit_service import AuditConfigCache

logger = logging.getLogger(__name__)


def _brand_settings_row(db, user_id: int):
    from src.helpers.database import _get_models

    models = _get_models()
    if not hasattr(models, "AuditClusterSettings"):
        return None
    return (
        db.query(models.AuditClusterSettings)
        .filter(
            models.AuditClusterSettings.user_id == user_id,
            models.AuditClusterSettings.account_id == None,
        )
        .first()
    )


def run_brand_health_check_for_user(
    user_id: int,
    brand_map: Mapping[str, List[str]],
    *,
    force_recheck: bool = False,
    recheck_domains: Optional[List[str]] = None,
    include_rdap: Optional[bool] = None,
) -> Dict[str, Any]:
    """DNS/DBL/RDAP prüfen, Health JSON speichern."""
    from src.helpers.database import _get_models

    models = _get_models()
    with get_db_session() as db:
        row = _brand_settings_row(db, user_id)
        if not row:
            row = models.AuditClusterSettings(user_id=user_id, account_id=None)
            db.add(row)
            db.flush()

        try:
            existing_health = json.loads(row.brand_domains_health_json or "{}")
        except json.JSONDecodeError:
            existing_health = {}
        cleaned, _ = validate_brand_map(brand_map)
        by_domain = dict(existing_health.get("domains") or {})
        only_domains: Optional[List[str]] = None
        if force_recheck:
            clear_domain_verification_state(by_domain, domains_in_brand_map(cleaned))
            existing_health["domains"] = by_domain
        elif recheck_domains:
            wanted = sorted(
                {
                    str(d).lower().strip(".")
                    for d in recheck_domains
                    if str(d).strip()
                }
            )
            allowed = set(domains_in_brand_map(cleaned))
            only_domains = [d for d in wanted if d in allowed]
            clear_domain_verification_state(by_domain, only_domains)
            existing_health["domains"] = by_domain
        if include_rdap is None:
            include_rdap = resolve_brand_health_rdap(brand_health_rdap_user_pref(row))
        else:
            include_rdap = bool(include_rdap)
        set_brand_health_rdap_context(include_rdap)
        try:
            health = run_health_report(
                cleaned,
                db_session=db,
                existing_health=existing_health,
                only_domains=only_domains,
                include_rdap=include_rdap,
            )
        finally:
            clear_brand_health_rdap_context()
        errors, warnings = validate_official_domains_for_save(
            cleaned,
            db_session=db,
            precomputed=health.get("domains"),
        )
        if health.get("aborted") == "rdap_429":
            warnings = list(warnings) + [
                "RDAP 429 (nic.ch o.ä.) — Lauf gestoppt. Bereits verifizierte Domains "
                "bleiben gespeichert. Nach Cooldown erneut «Domains prüfen» (nur Offene)."
            ]
        elif health.get("truncated"):
            n = len(health.get("pending_verification") or [])
            warnings = list(warnings) + [
                f"Teil-Lauf (max. {health.get('max_domains')} pro Start) — "
                f"{n} Domain(s) noch offen; erneut «Domains prüfen»."
            ]
        pending = list(health.get("pending_verification") or [])

        persist_brand_health_row(row, health)
        db.commit()
        db.refresh(row)
        AuditConfigCache.clear_cache(user_id)

        settings = brand_settings_api_payload(row, user_id)
        return {
            "ok": True,
            "success": True,
            "errors": errors,
            "warnings": warnings,
            "removed_domains": [],
            "list_unchanged": True,
            "rdap_pending": pending,
            "checks_performed": {
                "dns": True,
                "spamhaus_dbl": True,
                "rdap_brand_health": include_rdap,
                "rdap_mail_scan": audit_scam_rdap_sender_enabled(),
            },
            "settings": settings,
        }
