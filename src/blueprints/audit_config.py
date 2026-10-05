"""
Audit Config Blueprint - Konfiguration für Ordner-Audit

Endpoints:
    GET  /api/audit-config/trusted-domains     - Trusted Domains laden
    POST /api/audit-config/trusted-domains     - Trusted Domains speichern (Bulk)
    GET  /api/audit-config/important-keywords  - Important Keywords laden
    POST /api/audit-config/important-keywords  - Important Keywords speichern (Bulk)
    GET  /api/audit-config/safe-patterns       - Safe Patterns laden
    POST /api/audit-config/safe-patterns       - Safe Patterns speichern (Bulk)
    GET  /api/audit-config/vip-senders         - VIP Senders laden
    POST /api/audit-config/vip-senders         - VIP Senders speichern (Bulk)
    POST /api/audit-config/load-defaults       - System-Defaults laden
    GET  /api/audit-config/cluster-settings    - Clustering (Delta) laden
    POST /api/audit-config/cluster-settings    - Clustering speichern
    GET  /api/audit-config/brand-official-domains  - Marken → offizielle Domains
    POST /api/audit-config/brand-official-domains  - Speichern (JSON/Zeilen)
    POST /api/audit-config/brand-official-domains/fetch-preview - HTTPS-Import Preview
"""

import logging
import re
import json
from pathlib import Path
from flask import Blueprint, request, jsonify
from flask_login import login_required
import importlib

from src.helpers import get_db_session, get_current_user_model
from src.services.folder_audit_service import (
    AuditConfigCache,
    get_system_cluster_defaults_for_api,
    resolve_effective_cluster_settings,
    resolve_mode_cluster_config,
    SUGGESTED_STRICT_BULK_MERGE_BLOCK_DOMAINS,
    CLUSTER_MODE_DEFAULTS,
    CLUSTER_MODE_SETTING_KEYS,
)
from src.services.brand_domain_health import (
    brand_health_rdap_user_pref,
    brand_settings_api_payload,
    health_report_to_json,
    merge_dbl_blocked,
    parse_dbl_blocked_json,
    persist_brand_health_row,
    prepare_save_brand_map,
    run_health_report,
)
from src.services.brand_domain_policy import (
    BUILTIN_BRAND_OFFICIAL_DOMAINS,
    MAX_CUSTOM_JSON_BYTES,
    fetch_https_text_for_brand_import,
    brand_map_to_lines,
    diff_brand_maps,
    effective_brand_map,
    parse_brand_domains_text,
    validate_brand_map,
)
from src.services.domain_reputation import (
    audit_scam_rdap_sender_enabled,
    clear_brand_health_rdap_context,
    resolve_brand_health_rdap,
    set_brand_health_rdap_context,
    validate_official_domains_for_save,
)

logger = logging.getLogger(__name__)

audit_config_bp = Blueprint("audit_config", __name__)


# =============================================================================
# Lazy Imports
# =============================================================================

_models = None


def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


# =============================================================================
# Helper Functions
# =============================================================================

def parse_comma_separated(text: str) -> list[str]:
    """Parst komma-getrennten Text zu Liste.
    
    Unterstützt auch Newlines als Trennzeichen.
    Entfernt Leerzeichen und leere Einträge.
    """
    if not text:
        return []
    
    # Ersetze Newlines durch Kommas
    text = text.replace('\n', ',').replace('\r', '')
    
    # Split und cleanup
    items = [item.strip().lower() for item in text.split(',')]
    
    # Leere und doppelte entfernen
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    
    return result


def detect_pattern_type(pattern: str) -> str:
    """Erkennt Pattern-Typ automatisch.
    
    Returns:
        'exact': chef@firma.de
        'email_domain': @firma.de
        'domain': firma.de
    """
    if '@' in pattern:
        if pattern.startswith('@'):
            return 'email_domain'
        return 'exact'
    return 'domain'


# =============================================================================
# System Default Listen
# =============================================================================

# Diese werden bei "Load Defaults" eingefügt
DEFAULT_TRUSTED_DOMAINS = {
    # Banks CH
    ("ubs.com", "bank"): "system",
    ("credit-suisse.com", "bank"): "system",
    ("postfinance.ch", "bank"): "system",
    ("raiffeisen.ch", "bank"): "system",
    ("zkb.ch", "bank"): "system",
    ("yuh.com", "bank"): "system",
    ("neon-free.ch", "bank"): "system",
    # Banks IT
    ("credit-agricole.it", "bank"): "system",
    ("intesasanpaolo.com", "bank"): "system",
    ("unicredit.it", "bank"): "system",
    # Government CH
    ("admin.ch", "government"): "system",
    ("estv.admin.ch", "government"): "system",
    ("ahv-iv.ch", "government"): "system",
    # Government IT
    ("agenziaentrate.gov.it", "government"): "system",
    ("inps.it", "government"): "system",
    ("stanzadelcittadino.it", "government"): "system",
    # Telco CH
    ("swisscom.com", "telco"): "system",
    ("swisscom.ch", "telco"): "system",
    ("sunrise.ch", "telco"): "system",
    ("salt.ch", "telco"): "system",
    ("wingo.ch", "telco"): "system",
    # Telco IT
    ("iliad.it", "telco"): "system",
    ("tim.it", "telco"): "system",
    ("vodafone.it", "telco"): "system",
    ("windtre.it", "telco"): "system",
    # Transport
    ("sbb.ch", "transport"): "system",
    ("post.ch", "transport"): "system",
    ("swiss.com", "transport"): "system",
    ("trenitalia.it", "transport"): "system",
    # Utilities IT
    ("estraprometeo.it", "utility"): "system",
    ("enel.it", "utility"): "system",
    ("eni.it", "utility"): "system",
    ("a2a.eu", "utility"): "system",
    # Retail CH
    ("migros.ch", "retail"): "system",
    ("coop.ch", "retail"): "system",
    ("digitec.ch", "retail"): "system",
    ("galaxus.ch", "retail"): "system",
    # Insurance CH
    ("swisslife.ch", "insurance"): "system",
    ("axa.ch", "insurance"): "system",
    ("mobiliar.ch", "insurance"): "system",
    # Media CH
    ("nzz.ch", "media"): "system",
    ("srf.ch", "media"): "system",
}

DEFAULT_IMPORTANT_KEYWORDS = {
    # German
    ("rechnung", "de", "invoice"): "system",
    ("mahnung", "de", "invoice"): "system",
    ("zahlungserinnerung", "de", "invoice"): "system",
    ("kündigung", "de", "legal"): "system",
    ("vertrag", "de", "legal"): "system",
    ("termin", "de", "appointment"): "system",
    ("arzt", "de", "medical"): "system",
    ("anwalt", "de", "legal"): "system",
    ("steuer", "de", "financial"): "system",
    ("versicherung", "de", "insurance"): "system",
    ("gehalt", "de", "financial"): "system",
    ("lohn", "de", "financial"): "system",
    ("passwort", "de", "security"): "system",
    ("bestätigung", "de", "confirmation"): "system",
    # English
    ("invoice", "en", "invoice"): "system",
    ("payment", "en", "invoice"): "system",
    ("contract", "en", "legal"): "system",
    ("appointment", "en", "appointment"): "system",
    ("password", "en", "security"): "system",
    ("verification", "en", "security"): "system",
    ("confirmation", "en", "confirmation"): "system",
    ("shipping", "en", "shipping"): "system",
    ("tracking", "en", "shipping"): "system",
    # Italian
    ("fattura", "it", "invoice"): "system",
    ("bolletta", "it", "invoice"): "system",
    ("avviso di pagamento", "it", "invoice"): "system",
    ("scadenza", "it", "invoice"): "system",
    ("contratto", "it", "legal"): "system",
    ("disdetta", "it", "legal"): "system",
    ("appuntamento", "it", "appointment"): "system",
    ("medico", "it", "medical"): "system",
    ("avvocato", "it", "legal"): "system",
    ("password", "it", "security"): "system",
    ("conferma", "it", "confirmation"): "system",
    # French
    ("facture", "fr", "invoice"): "system",
    ("paiement", "fr", "invoice"): "system",
    ("contrat", "fr", "legal"): "system",
    ("rendez-vous", "fr", "appointment"): "system",
    ("mot de passe", "fr", "security"): "system",
}

DEFAULT_SAFE_PATTERNS = {
    # Subject patterns
    ("newsletter", "subject"): "system",
    ("weekly digest", "subject"): "system",
    ("daily digest", "subject"): "system",
    ("unsubscribe", "subject"): "system",
    ("rabatt", "subject"): "system",
    ("discount", "subject"): "system",
    ("sale", "subject"): "system",
    ("angebot", "subject"): "system",
    ("gutschein", "subject"): "system",
    ("coupon", "subject"): "system",
    # Sender patterns
    ("newsletter@", "sender"): "system",
    ("noreply@", "sender"): "system",
    ("no-reply@", "sender"): "system",
    ("marketing@", "sender"): "system",
    ("promo@", "sender"): "system",
    ("news@", "sender"): "system",
    ("@mailchimp.", "sender"): "system",
    ("@sendgrid.", "sender"): "system",
    ("@hubspot.", "sender"): "system",
}


# =============================================================================
# API Endpoints
# =============================================================================

@audit_config_bp.route("/api/audit-config/trusted-domains", methods=["GET"])
@login_required
def get_trusted_domains():
    """Lädt Trusted Domains für User (optional Account-spezifisch)"""
    account_id = request.args.get("account_id", type=int)
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        query = db.query(models.AuditTrustedDomain).filter(
            models.AuditTrustedDomain.user_id == user.id,
            models.AuditTrustedDomain.is_active == True,
        )
        
        if account_id:
            # Account-spezifisch + global (NULL)
            query = query.filter(
                (models.AuditTrustedDomain.account_id == account_id) |
                (models.AuditTrustedDomain.account_id == None)
            )
        else:
            # Nur globale
            query = query.filter(models.AuditTrustedDomain.account_id == None)
        
        domains = query.order_by(models.AuditTrustedDomain.category, models.AuditTrustedDomain.domain).all()
        
        return jsonify({
            "domains": [
                {
                    "id": d.id,
                    "domain": d.domain,
                    "category": d.category,
                    "source": d.source,
                    "account_id": d.account_id,
                }
                for d in domains
            ],
            "comma_separated": ", ".join(d.domain for d in domains),
        })


@audit_config_bp.route("/api/audit-config/trusted-domains", methods=["POST"])
@login_required
def save_trusted_domains():
    """Speichert Trusted Domains (Bulk-Update via Komma-String)"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Keine Daten"}), 400
    
    domains_text = data.get("domains", "")
    account_id = data.get("account_id")  # Optional
    category = data.get("category")  # Optional
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        # Parse Eingabe
        new_domains = parse_comma_separated(domains_text)
        
        # Bestehende User-Einträge laden (nur 'user' source, nicht system/import)
        existing = db.query(models.AuditTrustedDomain).filter(
            models.AuditTrustedDomain.user_id == user.id,
            models.AuditTrustedDomain.account_id == account_id,
            models.AuditTrustedDomain.source == "user",
        ).all()
        
        existing_domains = {d.domain for d in existing}
        
        # Neue hinzufügen
        added = 0
        for domain in new_domains:
            if domain not in existing_domains:
                db.add(models.AuditTrustedDomain(
                    user_id=user.id,
                    account_id=account_id,
                    domain=domain,
                    category=category,
                    source="user",
                ))
                added += 1
        
        # Entfernte deaktivieren (soft delete)
        removed = 0
        for entry in existing:
            if entry.domain not in new_domains:
                entry.is_active = False
                removed += 1
        
        db.commit()
        
        # Cache invalidieren
        AuditConfigCache.clear_cache(user.id)
        
        return jsonify({
            "success": True,
            "added": added,
            "removed": removed,
            "total": len(new_domains),
        })


@audit_config_bp.route("/api/audit-config/important-keywords", methods=["GET"])
@login_required
def get_important_keywords():
    """Lädt Important Keywords"""
    account_id = request.args.get("account_id", type=int)
    language = request.args.get("language")  # Optional: 'de', 'en', 'it', 'fr'
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        query = db.query(models.AuditImportantKeyword).filter(
            models.AuditImportantKeyword.user_id == user.id,
            models.AuditImportantKeyword.is_active == True,
        )
        
        if account_id:
            query = query.filter(
                (models.AuditImportantKeyword.account_id == account_id) |
                (models.AuditImportantKeyword.account_id == None)
            )
        
        if language:
            query = query.filter(
                (models.AuditImportantKeyword.language == language) |
                (models.AuditImportantKeyword.language == None)
            )
        
        keywords = query.order_by(
            models.AuditImportantKeyword.language,
            models.AuditImportantKeyword.category,
            models.AuditImportantKeyword.keyword
        ).all()
        
        # Gruppiert nach Sprache
        by_language = {}
        for kw in keywords:
            lang = kw.language or "all"
            if lang not in by_language:
                by_language[lang] = []
            by_language[lang].append({
                "id": kw.id,
                "keyword": kw.keyword,
                "category": kw.category,
                "source": kw.source,
            })
        
        return jsonify({
            "keywords": [
                {
                    "id": kw.id,
                    "keyword": kw.keyword,
                    "language": kw.language,
                    "category": kw.category,
                    "source": kw.source,
                }
                for kw in keywords
            ],
            "by_language": by_language,
            "comma_separated": ", ".join(kw.keyword for kw in keywords),
        })


@audit_config_bp.route("/api/audit-config/important-keywords", methods=["POST"])
@login_required
def save_important_keywords():
    """Speichert Important Keywords (Bulk)"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Keine Daten"}), 400
    
    keywords_text = data.get("keywords", "")
    account_id = data.get("account_id")
    language = data.get("language")  # Optional
    category = data.get("category")  # Optional
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        new_keywords = parse_comma_separated(keywords_text)
        
        existing = db.query(models.AuditImportantKeyword).filter(
            models.AuditImportantKeyword.user_id == user.id,
            models.AuditImportantKeyword.account_id == account_id,
            models.AuditImportantKeyword.source == "user",
        ).all()
        
        existing_keywords = {kw.keyword for kw in existing}
        
        added = 0
        for keyword in new_keywords:
            if keyword not in existing_keywords:
                db.add(models.AuditImportantKeyword(
                    user_id=user.id,
                    account_id=account_id,
                    keyword=keyword,
                    language=language,
                    category=category,
                    source="user",
                ))
                added += 1
        
        removed = 0
        for entry in existing:
            if entry.keyword not in new_keywords:
                entry.is_active = False
                removed += 1
        
        db.commit()
        
        # Cache invalidieren
        AuditConfigCache.clear_cache(user.id)
        
        return jsonify({
            "success": True,
            "added": added,
            "removed": removed,
            "total": len(new_keywords),
        })


@audit_config_bp.route("/api/audit-config/safe-patterns", methods=["GET"])
@login_required
def get_safe_patterns():
    """Lädt Safe Patterns (Newsletter, Marketing, etc.)"""
    account_id = request.args.get("account_id", type=int)
    pattern_type = request.args.get("pattern_type")  # 'subject', 'sender', 'domain'
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        query = db.query(models.AuditSafePattern).filter(
            models.AuditSafePattern.user_id == user.id,
            models.AuditSafePattern.is_active == True,
        )
        
        if account_id:
            query = query.filter(
                (models.AuditSafePattern.account_id == account_id) |
                (models.AuditSafePattern.account_id == None)
            )
        
        if pattern_type:
            query = query.filter(models.AuditSafePattern.pattern_type == pattern_type)
        
        patterns = query.order_by(
            models.AuditSafePattern.pattern_type,
            models.AuditSafePattern.pattern
        ).all()
        
        # Gruppiert nach Typ
        by_type = {"subject": [], "sender": [], "domain": []}
        for p in patterns:
            if p.pattern_type in by_type:
                by_type[p.pattern_type].append({
                    "id": p.id,
                    "pattern": p.pattern,
                    "source": p.source,
                })
        
        return jsonify({
            "patterns": [
                {
                    "id": p.id,
                    "pattern": p.pattern,
                    "pattern_type": p.pattern_type,
                    "source": p.source,
                }
                for p in patterns
            ],
            "by_type": by_type,
        })


@audit_config_bp.route("/api/audit-config/safe-patterns", methods=["POST"])
@login_required
def save_safe_patterns():
    """Speichert Safe Patterns"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Keine Daten"}), 400
    
    patterns_text = data.get("patterns", "")
    pattern_type = data.get("pattern_type", "subject")
    account_id = data.get("account_id")
    
    if pattern_type not in ("subject", "sender", "domain"):
        return jsonify({"error": "Ungültiger pattern_type"}), 400
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        new_patterns = parse_comma_separated(patterns_text)
        
        existing = db.query(models.AuditSafePattern).filter(
            models.AuditSafePattern.user_id == user.id,
            models.AuditSafePattern.account_id == account_id,
            models.AuditSafePattern.pattern_type == pattern_type,
            models.AuditSafePattern.source == "user",
        ).all()
        
        existing_patterns = {p.pattern for p in existing}
        
        added = 0
        for pattern in new_patterns:
            if pattern not in existing_patterns:
                db.add(models.AuditSafePattern(
                    user_id=user.id,
                    account_id=account_id,
                    pattern=pattern,
                    pattern_type=pattern_type,
                    source="user",
                ))
                added += 1
        
        removed = 0
        for entry in existing:
            if entry.pattern not in new_patterns:
                entry.is_active = False
                removed += 1
        
        db.commit()
        
        # Cache invalidieren
        AuditConfigCache.clear_cache(user.id)
        
        return jsonify({
            "success": True,
            "added": added,
            "removed": removed,
            "total": len(new_patterns),
        })


@audit_config_bp.route("/api/audit-config/vip-senders", methods=["GET"])
@login_required
def get_vip_senders():
    """Lädt VIP Senders"""
    account_id = request.args.get("account_id", type=int)
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        query = db.query(models.AuditVIPSender).filter(
            models.AuditVIPSender.user_id == user.id,
            models.AuditVIPSender.is_active == True,
        )
        
        if account_id:
            query = query.filter(
                (models.AuditVIPSender.account_id == account_id) |
                (models.AuditVIPSender.account_id == None)
            )
        
        vips = query.order_by(models.AuditVIPSender.label, models.AuditVIPSender.sender_pattern).all()
        
        return jsonify({
            "vip_senders": [
                {
                    "id": v.id,
                    "sender_pattern": v.sender_pattern,
                    "pattern_type": v.pattern_type,
                    "label": v.label,
                    "source": v.source,
                }
                for v in vips
            ],
            "comma_separated": ", ".join(v.sender_pattern for v in vips),
        })


@audit_config_bp.route("/api/audit-config/vip-senders", methods=["POST"])
@login_required
def save_vip_senders():
    """Speichert VIP Senders (Bulk)"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Keine Daten"}), 400
    
    senders_text = data.get("senders", "")
    account_id = data.get("account_id")
    label = data.get("label")  # Optional
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        new_senders = parse_comma_separated(senders_text)
        
        existing = db.query(models.AuditVIPSender).filter(
            models.AuditVIPSender.user_id == user.id,
            models.AuditVIPSender.account_id == account_id,
            models.AuditVIPSender.source == "user",
        ).all()
        
        existing_patterns = {v.sender_pattern for v in existing}
        
        added = 0
        for sender in new_senders:
            if sender not in existing_patterns:
                pattern_type = detect_pattern_type(sender)
                db.add(models.AuditVIPSender(
                    user_id=user.id,
                    account_id=account_id,
                    sender_pattern=sender,
                    pattern_type=pattern_type,
                    label=label,
                    source="user",
                ))
                added += 1
        
        removed = 0
        for entry in existing:
            if entry.sender_pattern not in new_senders:
                entry.is_active = False
                removed += 1
        
        db.commit()
        
        # Cache invalidieren
        AuditConfigCache.clear_cache(user.id)
        
        return jsonify({
            "success": True,
            "added": added,
            "removed": removed,
            "total": len(new_senders),
        })


# =============================================================================
# Auto-Delete Rules API
# =============================================================================

@audit_config_bp.route("/api/audit-config/auto-delete-rules", methods=["GET"])
@login_required
def get_auto_delete_rules():
    """Lädt Auto-Delete Rules"""
    account_id = request.args.get("account_id", type=int)
    disposition = request.args.get("disposition")  # SAFE, IMPORTANT, SCAM, REVIEW
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        query = db.query(models.AuditAutoDeleteRule).filter(
            models.AuditAutoDeleteRule.user_id == user.id,
            models.AuditAutoDeleteRule.is_active == True,
        )
        
        if account_id:
            query = query.filter(
                (models.AuditAutoDeleteRule.account_id == account_id) |
                (models.AuditAutoDeleteRule.account_id == None)
            )
        
        if disposition:
            query = query.filter(models.AuditAutoDeleteRule.disposition == disposition)
        
        rules = query.order_by(
            models.AuditAutoDeleteRule.disposition,
            models.AuditAutoDeleteRule.sender_pattern,
            models.AuditAutoDeleteRule.subject_pattern
        ).all()
        
        # Gruppiert nach Disposition
        by_disposition = {"SAFE": [], "IMPORTANT": [], "SCAM": [], "REVIEW": []}
        for r in rules:
            if r.disposition in by_disposition:
                by_disposition[r.disposition].append({
                    "id": r.id,
                    "sender_pattern": r.sender_pattern,
                    "subject_pattern": r.subject_pattern,
                    "max_age_days": r.max_age_days,
                    "description": r.description,
                    "source": r.source,
                })
        
        return jsonify({
            "rules": [
                {
                    "id": r.id,
                    "sender_pattern": r.sender_pattern,
                    "subject_pattern": r.subject_pattern,
                    "disposition": r.disposition,
                    "max_age_days": r.max_age_days,
                    "description": r.description,
                    "source": r.source,
                    "account_id": r.account_id,
                }
                for r in rules
            ],
            "by_disposition": by_disposition,
            "count": len(rules),
        })


@audit_config_bp.route("/api/audit-config/auto-delete-rules", methods=["POST"])
@login_required
def save_auto_delete_rule():
    """Speichert eine einzelne Auto-Delete Rule"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Keine Daten"}), 400
    
    sender_pattern = data.get("sender_pattern")
    subject_pattern = data.get("subject_pattern")
    disposition = data.get("disposition")
    max_age_days = data.get("max_age_days")
    description = data.get("description")
    account_id = data.get("account_id")
    
    # Validierung
    if not disposition or disposition not in ("SAFE", "IMPORTANT", "SCAM", "REVIEW"):
        return jsonify({"error": "Ungültige disposition (SAFE, IMPORTANT, SCAM, REVIEW)"}), 400
    
    if not sender_pattern and not subject_pattern:
        return jsonify({"error": "Mindestens sender_pattern oder subject_pattern erforderlich"}), 400
    
    # SAFE braucht max_age_days
    if disposition == "SAFE" and max_age_days is None:
        return jsonify({"error": "SAFE benötigt max_age_days"}), 400
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        # Prüfen ob Regel existiert
        existing = db.query(models.AuditAutoDeleteRule).filter(
            models.AuditAutoDeleteRule.user_id == user.id,
            models.AuditAutoDeleteRule.account_id == account_id,
            models.AuditAutoDeleteRule.sender_pattern == sender_pattern,
            models.AuditAutoDeleteRule.subject_pattern == subject_pattern,
        ).first()
        
        if existing:
            # Update
            existing.disposition = disposition
            existing.max_age_days = max_age_days
            existing.description = description
            existing.is_active = True
            action = "updated"
        else:
            # Insert
            db.add(models.AuditAutoDeleteRule(
                user_id=user.id,
                account_id=account_id,
                sender_pattern=sender_pattern,
                subject_pattern=subject_pattern,
                disposition=disposition,
                max_age_days=max_age_days,
                description=description,
                source="user",
            ))
            action = "created"
        
        db.commit()
        
        # Cache invalidieren
        AuditConfigCache.clear_cache(user.id)
        
        return jsonify({
            "success": True,
            "action": action,
        })


@audit_config_bp.route("/api/audit-config/auto-delete-rules/<int:rule_id>", methods=["DELETE"])
@login_required
def delete_auto_delete_rule(rule_id):
    """Löscht eine Auto-Delete Rule (soft delete)"""
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        rule = db.query(models.AuditAutoDeleteRule).filter(
            models.AuditAutoDeleteRule.id == rule_id,
            models.AuditAutoDeleteRule.user_id == user.id,
        ).first()
        
        if not rule:
            return jsonify({"error": "Regel nicht gefunden"}), 404
        
        rule.is_active = False
        db.commit()
        
        # Cache invalidieren
        AuditConfigCache.clear_cache(user.id)
        
        return jsonify({
            "success": True,
            "deleted": rule_id,
        })


@audit_config_bp.route("/api/audit-config/auto-delete-rules/bulk", methods=["POST"])
@login_required
def save_auto_delete_rules_bulk():
    """Speichert mehrere Auto-Delete Rules auf einmal"""
    data = request.get_json()
    if not data or "rules" not in data:
        return jsonify({"error": "Keine Regeln angegeben"}), 400
    
    rules_data = data.get("rules", [])
    account_id = data.get("account_id")
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        added = 0
        updated = 0
        errors = []
        
        for rule in rules_data:
            sender_pattern = rule.get("sender_pattern")
            subject_pattern = rule.get("subject_pattern")
            disposition = rule.get("disposition")
            max_age_days = rule.get("max_age_days")
            description = rule.get("description")
            
            # Validierung
            if not disposition or disposition not in ("SAFE", "IMPORTANT", "SCAM", "REVIEW"):
                errors.append(f"Ungültige disposition: {disposition}")
                continue
            
            if not sender_pattern and not subject_pattern:
                errors.append("Regel ohne Pattern übersprungen")
                continue
            
            if disposition == "SAFE" and max_age_days is None:
                errors.append(f"SAFE ohne max_age_days: {sender_pattern}/{subject_pattern}")
                continue
            
            # Prüfen ob existiert
            existing = db.query(models.AuditAutoDeleteRule).filter(
                models.AuditAutoDeleteRule.user_id == user.id,
                models.AuditAutoDeleteRule.account_id == account_id,
                models.AuditAutoDeleteRule.sender_pattern == sender_pattern,
                models.AuditAutoDeleteRule.subject_pattern == subject_pattern,
            ).first()
            
            if existing:
                existing.disposition = disposition
                existing.max_age_days = max_age_days
                existing.description = description
                existing.is_active = True
                updated += 1
            else:
                db.add(models.AuditAutoDeleteRule(
                    user_id=user.id,
                    account_id=account_id,
                    sender_pattern=sender_pattern,
                    subject_pattern=subject_pattern,
                    disposition=disposition,
                    max_age_days=max_age_days,
                    description=description,
                    source="user",
                ))
                added += 1
        
        db.commit()
        
        # Cache invalidieren
        AuditConfigCache.clear_cache(user.id)
        
        return jsonify({
            "success": True,
            "added": added,
            "updated": updated,
            "errors": errors,
        })


def _get_cluster_settings_row(db, user_id, account_id):
    models = _get_models()
    if not hasattr(models, "AuditClusterSettings"):
        return None
    if account_id is not None:
        row = db.query(models.AuditClusterSettings).filter(
            models.AuditClusterSettings.user_id == user_id,
            models.AuditClusterSettings.account_id == account_id,
            models.AuditClusterSettings.is_active == True,
        ).first()
        if row:
            return row
    return db.query(models.AuditClusterSettings).filter(
        models.AuditClusterSettings.user_id == user_id,
        models.AuditClusterSettings.account_id == None,
        models.AuditClusterSettings.is_active == True,
    ).first()


def _parse_mode_overrides_row(row) -> dict:
    if not row:
        return {}
    try:
        data = json.loads(getattr(row, "mode_overrides_json", None) or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _sanitize_mode_overrides(incoming: dict) -> dict:
    """Speichert nur Abweichungen vom Modus-Default."""
    if not isinstance(incoming, dict):
        return {}
    cleaned = {}
    for mode in ("cleanup", "maintenance"):
        if mode not in incoming or not isinstance(incoming[mode], dict):
            continue
        defaults = CLUSTER_MODE_DEFAULTS.get(mode, {})
        diff = {}
        for key in CLUSTER_MODE_SETTING_KEYS:
            if key not in incoming[mode]:
                continue
            val = incoming[mode][key]
            if val is None:
                continue
            if key in ("min_count", "absorb_max", "same_sender_min_count", "campaign_review_min_independent_domains"):
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    continue
                if key == "min_count":
                    val = max(2, val)
                elif key == "same_sender_min_count":
                    val = max(3, val)
                elif key == "campaign_review_min_independent_domains":
                    val = max(2, val)
                elif key == "absorb_max":
                    val = max(1, val)
            elif key in (
                "domain_stage",
                "plain_bulk_db_safe_patterns",
                "same_sender_volume_merge",
                "campaign_review_multidomain",
            ):
                val = bool(val)
            if val != defaults.get(key):
                diff[key] = val
        if diff:
            cleaned[mode] = diff
    return cleaned


def _cluster_settings_response(row) -> dict:
    system = get_system_cluster_defaults_for_api()
    raw = {}
    if row:
        try:
            domains = json.loads(row.bulk_merge_block_domains or "[]")
        except (TypeError, json.JSONDecodeError):
            domains = []
        try:
            norm = json.loads(row.normalization_json or "{}")
        except (TypeError, json.JSONDecodeError):
            norm = {}
        raw = {
            "use_custom_bulk_merge_block": bool(row.use_custom_bulk_merge_block),
            "bulk_merge_block_domains": domains if isinstance(domains, list) else [],
            "normalization": norm if isinstance(norm, dict) else {},
            "mode_overrides": _parse_mode_overrides_row(row),
        }
    effective = resolve_effective_cluster_settings(raw)
    user_domains_text = ", ".join(raw.get("bulk_merge_block_domains") or [])
    mode_effective = {
        mode: resolve_mode_cluster_config(mode, raw)
        for mode in ("cleanup", "maintenance")
    }
    mode_customized = {
        mode: bool((raw.get("mode_overrides") or {}).get(mode))
        for mode in ("cleanup", "maintenance")
    }
    return {
        "system_defaults": system,
        "strict_bulk_merge_suggestion": ", ".join(sorted(SUGGESTED_STRICT_BULK_MERGE_BLOCK_DOMAINS)),
        "use_custom_bulk_merge_block": raw.get("use_custom_bulk_merge_block", False),
        "bulk_merge_block_domains": user_domains_text,
        "normalization": effective.get("normalization") or system["normalization"],
        "normalization_overrides": raw.get("normalization") or {},
        "mode_overrides": raw.get("mode_overrides") or {},
        "mode_effective": mode_effective,
        "mode_customized": mode_customized,
        "effective_bulk_merge_block_count": len(effective.get("bulk_merge_block") or []),
        "using_system_bulk_merge_block": not raw.get("use_custom_bulk_merge_block", False),
    }


@audit_config_bp.route("/api/audit-config/cluster-settings", methods=["GET"])
@login_required
def get_cluster_settings():
    """Clustering-Parameter (Delta): Defaults + User-Overrides."""
    account_id = request.args.get("account_id", type=int)

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        row = _get_cluster_settings_row(db, user.id, account_id)
        return jsonify(_cluster_settings_response(row))


@audit_config_bp.route("/api/audit-config/cluster-settings", methods=["POST"])
@login_required
def save_cluster_settings():
    """Speichert Clustering-Parameter."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Keine Daten"}), 400

    account_id = data.get("account_id")
    reset_mode = data.get("reset_mode")
    use_custom = bool(data.get("use_custom_bulk_merge_block", False)) if "use_custom_bulk_merge_block" in data else None
    domains_text = data.get("bulk_merge_block_domains", "")
    normalization = data.get("normalization") or {}
    mode_overrides_in = data.get("mode_overrides")

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        models = _get_models()
        if not hasattr(models, "AuditClusterSettings"):
            return jsonify({"error": "Migration audit_cluster_settings fehlt"}), 503

        row = db.query(models.AuditClusterSettings).filter(
            models.AuditClusterSettings.user_id == user.id,
            models.AuditClusterSettings.account_id == account_id,
        ).first()

        if not row:
            row = models.AuditClusterSettings(
                user_id=user.id,
                account_id=account_id,
            )
            db.add(row)

        if reset_mode in ("cleanup", "maintenance"):
            existing_mode = _parse_mode_overrides_row(row)
            existing_mode.pop(reset_mode, None)
            row.mode_overrides_json = json.dumps(existing_mode) if existing_mode else None
            row.is_active = True
            db.commit()
            AuditConfigCache.clear_cache(user.id)
            return jsonify({"success": True, "settings": _cluster_settings_response(row)})

        if use_custom is None:
            use_custom = bool(row.use_custom_bulk_merge_block)

        domain_list = parse_comma_separated(domains_text) if use_custom else []
        norm_clean = {}
        defaults = get_system_cluster_defaults_for_api()["normalization"]
        for key in defaults:
            if key not in normalization:
                continue
            val = bool(normalization[key])
            if val != defaults[key]:
                norm_clean[key] = val

        row.use_custom_bulk_merge_block = use_custom
        row.bulk_merge_block_domains = json.dumps(domain_list)
        row.normalization_json = json.dumps(norm_clean) if norm_clean else None

        existing_mode = _parse_mode_overrides_row(row)
        if mode_overrides_in is not None:
            existing_mode = _sanitize_mode_overrides(mode_overrides_in)
        row.mode_overrides_json = json.dumps(existing_mode) if existing_mode else None

        row.is_active = True
        db.commit()

        AuditConfigCache.clear_cache(user.id)

        return jsonify({
            "success": True,
            "settings": _cluster_settings_response(row),
        })


def _user_brand_settings_row(db, user_id):
    models = _get_models()
    if not hasattr(models, "AuditClusterSettings"):
        return None
    return db.query(models.AuditClusterSettings).filter(
        models.AuditClusterSettings.user_id == user_id,
        models.AuditClusterSettings.account_id == None,
    ).first()


def _apply_brand_health_rdap_pref(row, data: dict) -> None:
    if row is None or "brand_health_rdap" not in data:
        return
    row.brand_health_rdap = bool(data.get("brand_health_rdap"))


def _brand_settings_response(row, user_id: int) -> dict:
    return brand_settings_api_payload(row, user_id)


def _custom_map_from_request(data: dict) -> dict:
    raw_map = data.get("custom_map")
    if isinstance(raw_map, dict) and raw_map:
        cleaned, _ = validate_brand_map(raw_map)
        return cleaned
    text = (data.get("text") or data.get("custom_text") or "").strip()
    if not text:
        return {}
    return parse_brand_domains_text(text)


def _commit_brand_save(row, cleaned: dict, health: dict, dbl_blocked: list) -> None:
    from datetime import datetime, timezone

    row.brand_official_domains_json = (
        json.dumps(cleaned, ensure_ascii=False) if cleaned else None
    )
    row.brand_import_pending_json = None
    row.brand_domains_health_json = health_report_to_json(health) if health else None
    row.brand_domains_health_checked_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) if health else None
    )
    row.brand_dbl_blocked_domains_json = json.dumps(dbl_blocked)


def _persist_brand_health_only(row, health: dict) -> None:
    persist_brand_health_row(row, health)


@audit_config_bp.route("/api/audit-config/brand-official-domains", methods=["GET"])
@login_required
def get_brand_official_domains():
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        row = _user_brand_settings_row(db, user.id)
        return jsonify(_brand_settings_response(row, user.id))


@audit_config_bp.route("/api/audit-config/brand-official-domains", methods=["POST"])
@login_required
def save_brand_official_domains():
    data = request.get_json(silent=True) or {}
    apply_pending = bool(data.get("apply_pending"))
    discard_pending = bool(data.get("discard_pending"))
    skip_live_checks = bool(data.get("skip_live_checks"))

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        models = _get_models()
        if not hasattr(models, "AuditClusterSettings"):
            return jsonify({"error": "Migration fehlt"}), 503

        row = _user_brand_settings_row(db, user.id)
        if not row:
            row = models.AuditClusterSettings(user_id=user.id, account_id=None)
            db.add(row)

        _apply_brand_health_rdap_pref(row, data)

        if discard_pending:
            row.brand_import_pending_json = None

        if apply_pending and row.brand_import_pending_json:
            try:
                pending = json.loads(row.brand_import_pending_json)
                proposed = pending.get("proposed_map") or {}
                data = {"custom_map": proposed}
            except (TypeError, json.JSONDecodeError) as exc:
                return jsonify({"error": str(exc)}), 400

        try:
            proposed_map = _custom_map_from_request(data)
        except (ValueError, json.JSONDecodeError) as exc:
            return jsonify({"error": str(exc)}), 400

        payload_size = len(json.dumps(proposed_map).encode("utf-8"))
        if payload_size > MAX_CUSTOM_JSON_BYTES:
            return jsonify({"error": "Liste zu gross (max. 64 KB)"}), 400

        dbl_blocked = parse_dbl_blocked_json(
            getattr(row, "brand_dbl_blocked_domains_json", None)
        )
        try:
            prior_health = json.loads(row.brand_domains_health_json or "{}")
        except json.JSONDecodeError:
            prior_health = {}
        old_map: dict = {}
        if row.brand_official_domains_json:
            try:
                old_map = parse_brand_domains_text(row.brand_official_domains_json)
            except ValueError:
                old_map = {}
        include_rdap = resolve_brand_health_rdap(brand_health_rdap_user_pref(row))
        set_brand_health_rdap_context(include_rdap)
        try:
            cleaned, errors, warnings, health, new_dbl = prepare_save_brand_map(
                proposed_map,
                dbl_blocked,
                run_live_checks=not skip_live_checks,
                db_session=db,
                existing_health=prior_health,
                previous_map=old_map,
                include_rdap=include_rdap,
            )
        finally:
            clear_brand_health_rdap_context()
        if errors:
            return jsonify(
                {"error": "; ".join(errors[:10]), "errors": errors, "warnings": warnings}
            ), 400

        confirm_strip = bool(data.get("confirm_dbl_strip"))
        removed: list = []
        if confirm_strip and new_dbl:
            from src.services.brand_domain_health import strip_dbl_domains_from_map

            cleaned, removed = strip_dbl_domains_from_map(cleaned, merge_dbl_blocked(dbl_blocked, new_dbl))
            dbl_blocked = merge_dbl_blocked(dbl_blocked, new_dbl)
            if removed:
                warnings = list(warnings) + [
                    f"Aus Liste entfernt (Spamhaus DBL): {', '.join(sorted(set(removed))[:10])}"
                ]
        elif new_dbl:
            warnings = list(warnings) + [
                "DBL-Harttreffer in der Liste — nicht entfernt. "
                "Erneut speichern mit Bestätigung oder Domains manuell prüfen."
            ]

        _commit_brand_save(row, cleaned, health, dbl_blocked)
        db.commit()
        AuditConfigCache.clear_cache(user.id)
        return jsonify(
            {
                "success": True,
                "warnings": warnings,
                "settings": _brand_settings_response(row, user.id),
            }
        )


@audit_config_bp.route(
    "/api/audit-config/brand-official-domains/health-check", methods=["POST"]
)
@login_required
def brand_official_domains_health_check():
    from src.helpers.task_ownership import track_celery_task
    from src.services.brand_health_check_lock import (
        release_brand_health_check_lock,
        try_acquire_brand_health_check_lock,
    )
    from src.tasks.brand_health_tasks import run_brand_health_check_task

    data = request.get_json(silent=True) or {}
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        if not try_acquire_brand_health_check_lock(user.id):
            return jsonify({"error": "Domain-Prüfung läuft bereits — bitte warten."}), 409

        task_queued = False
        try:
            try:
                if data.get("custom_map") is not None or data.get("text"):
                    brand_map = _custom_map_from_request(data)
                else:
                    row = _user_brand_settings_row(db, user.id)
                    if row and row.brand_official_domains_json:
                        brand_map = parse_brand_domains_text(row.brand_official_domains_json)
                    else:
                        brand_map = {}
            except (ValueError, json.JSONDecodeError) as exc:
                return jsonify({"error": str(exc)}), 400

            models = _get_models()
            row = _user_brand_settings_row(db, user.id)
            if not row:
                row = models.AuditClusterSettings(user_id=user.id, account_id=None)
                db.add(row)
            _apply_brand_health_rdap_pref(row, data)
            include_rdap = resolve_brand_health_rdap(brand_health_rdap_user_pref(row))

            cleaned, _ = validate_brand_map(brand_map)
            check_options = {"brand_health_rdap": include_rdap}
            if data.get("force_recheck"):
                check_options["force_recheck"] = True
            raw_recheck = data.get("recheck_domains")
            if isinstance(raw_recheck, list) and raw_recheck:
                check_options["recheck_domains"] = [
                    str(x).lower().strip(".") for x in raw_recheck if str(x).strip()
                ]
            async_result = run_brand_health_check_task.delay(
                user.id, cleaned, check_options
            )
            track_celery_task(async_result, user.id)
            task_queued = True
            return jsonify({"status": "queued", "task_id": async_result.id}), 202
        except Exception as exc:
            logger.exception("brand health check enqueue failed: %s", exc)
            return jsonify({"error": "Domain-Prüfung konnte nicht gestartet werden."}), 500
        finally:
            if not task_queued:
                release_brand_health_check_lock(user.id)


@audit_config_bp.route("/api/audit-config/tranco-status", methods=["GET"])
@login_required
def tranco_status_api():
    from src.services.tranco_popularity import get_tranco_status

    st = get_tranco_status()
    return jsonify(
        {
            "available": st.available,
            "list_id": st.list_id,
            "updated_at": st.updated_at,
            "domain_count": st.domain_count,
            "top_n": st.top_n,
            "message": st.message,
            "source_note": st.source_note,
        }
    )


@audit_config_bp.route("/api/audit-config/tranco-update", methods=["POST"])
@login_required
def tranco_update_api():
    from src.helpers.app_admin import user_is_app_admin
    from src.helpers.task_ownership import track_celery_task
    from src.tasks.tranco_tasks import update_tranco_popularity_list

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht angemeldet"}), 401
        if not user_is_app_admin(user):
            return jsonify({"error": "Nur für App-Administratoren."}), 403
        user_id = user.id

    try:
        task = track_celery_task(
            update_tranco_popularity_list.delay(force=True),
            user_id,
        )
        return jsonify({"status": "queued", "task_id": task.id}), 202
    except Exception as exc:
        logger.error("tranco_update_api: %s", exc)
        return jsonify(
            {"error": "Tranco-Aktualisierung konnte nicht gestartet werden."}
        ), 500


@audit_config_bp.route("/api/audit-config/brand-official-domains/fetch-preview", methods=["POST"])
@login_required
def preview_brand_official_domains_url():
    import requests as http_requests

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    try:
        body = fetch_https_text_for_brand_import(url)
        proposed = parse_brand_domains_text(body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except http_requests.RequestException as exc:
        return jsonify({"error": f"Download fehlgeschlagen: {type(exc).__name__}"}), 502

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        models = _get_models()
        row = _user_brand_settings_row(db, user.id)
        if not row:
            row = models.AuditClusterSettings(user_id=user.id, account_id=None)
            db.add(row)

        current_custom = {}
        if row.brand_official_domains_json:
            try:
                current_custom = parse_brand_domains_text(row.brand_official_domains_json)
            except ValueError:
                current_custom = {}
        current_effective = effective_brand_map(current_custom)
        proposed_effective = effective_brand_map(proposed)
        diff = diff_brand_maps(current_effective, proposed_effective)
        pending = {
            "proposed_map": proposed,
            "diff": diff,
            "url": url,
        }
        row.brand_source_url = url
        row.brand_import_pending_json = json.dumps(pending, ensure_ascii=False)
        db.commit()
        return jsonify(
            {
                "success": True,
                "pending_import": pending,
                "preview_lines": brand_map_to_lines(proposed),
            }
        )


@audit_config_bp.route("/api/audit-config/load-defaults", methods=["POST"])
@login_required
def load_defaults():
    """Lädt System-Default-Listen in die User-Tabellen"""
    data = request.get_json() or {}
    account_id = data.get("account_id")
    reset_existing = data.get("reset_existing", False)  # Optional: Bestehende löschen
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        stats = {
            "trusted_domains": 0,
            "important_keywords": 0,
            "safe_patterns": 0,
        }
        
        if reset_existing:
            # System-Einträge entfernen
            db.query(models.AuditTrustedDomain).filter(
                models.AuditTrustedDomain.user_id == user.id,
                models.AuditTrustedDomain.source == "system",
            ).delete()
            db.query(models.AuditImportantKeyword).filter(
                models.AuditImportantKeyword.user_id == user.id,
                models.AuditImportantKeyword.source == "system",
            ).delete()
            db.query(models.AuditSafePattern).filter(
                models.AuditSafePattern.user_id == user.id,
                models.AuditSafePattern.source == "system",
            ).delete()
        
        # Trusted Domains
        existing_domains = {
            d.domain for d in db.query(models.AuditTrustedDomain).filter(
                models.AuditTrustedDomain.user_id == user.id,
            ).all()
        }
        
        for (domain, category), source in DEFAULT_TRUSTED_DOMAINS.items():
            if domain not in existing_domains:
                db.add(models.AuditTrustedDomain(
                    user_id=user.id,
                    account_id=account_id,
                    domain=domain,
                    category=category,
                    source=source,
                ))
                stats["trusted_domains"] += 1
        
        # Important Keywords
        existing_keywords = {
            kw.keyword for kw in db.query(models.AuditImportantKeyword).filter(
                models.AuditImportantKeyword.user_id == user.id,
            ).all()
        }
        
        for (keyword, language, category), source in DEFAULT_IMPORTANT_KEYWORDS.items():
            if keyword not in existing_keywords:
                db.add(models.AuditImportantKeyword(
                    user_id=user.id,
                    account_id=account_id,
                    keyword=keyword,
                    language=language,
                    category=category,
                    source=source,
                ))
                stats["important_keywords"] += 1
        
        # Safe Patterns
        existing_patterns = {
            (p.pattern, p.pattern_type) for p in db.query(models.AuditSafePattern).filter(
                models.AuditSafePattern.user_id == user.id,
            ).all()
        }
        
        for (pattern, pattern_type), source in DEFAULT_SAFE_PATTERNS.items():
            if (pattern, pattern_type) not in existing_patterns:
                db.add(models.AuditSafePattern(
                    user_id=user.id,
                    account_id=account_id,
                    pattern=pattern,
                    pattern_type=pattern_type,
                    source=source,
                ))
                stats["safe_patterns"] += 1
        
        db.commit()
        
        # Cache invalidieren
        AuditConfigCache.clear_cache(user.id)
        
        logger.info(f"Loaded defaults for user {user.id}: {stats}")
        
        return jsonify({
            "success": True,
            "loaded": stats,
            "message": f"Geladen: {stats['trusted_domains']} Domains, {stats['important_keywords']} Keywords, {stats['safe_patterns']} Patterns",
        })


@audit_config_bp.route("/api/audit-config/stats", methods=["GET"])
@login_required
def get_stats():
    """Statistiken über gespeicherte Konfiguration"""
    account_id = request.args.get("account_id", type=int)
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        models = _get_models()
        
        # Zähle pro Tabelle
        def count_entries(model):
            query = db.query(model).filter(
                model.user_id == user.id,
                model.is_active == True,
            )
            if account_id and hasattr(model, 'account_id'):
                query = query.filter(
                    (model.account_id == account_id) | (model.account_id == None)
                )
            return query.count()
        
        cluster_custom = False
        if hasattr(models, "AuditClusterSettings"):
            cs_row = _get_cluster_settings_row(db, user.id, account_id)
            if cs_row:
                cluster_custom = bool(
                    cs_row.use_custom_bulk_merge_block or cs_row.normalization_json
                )
        
        return jsonify({
            "trusted_domains": count_entries(models.AuditTrustedDomain),
            "important_keywords": count_entries(models.AuditImportantKeyword),
            "safe_patterns": count_entries(models.AuditSafePattern),
            "vip_senders": count_entries(models.AuditVIPSender),
            "auto_delete_rules": count_entries(models.AuditAutoDeleteRule) if hasattr(models, 'AuditAutoDeleteRule') else 0,
            "cluster_settings_customized": cluster_custom,
        })


@audit_config_bp.route("/api/audit-config/firstnames/stats", methods=["GET"])
@login_required
def audit_firstnames_stats():
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        models = _get_models()
        if not hasattr(models, "AuditFirstname"):
            return jsonify({"count": 0, "source": None})
        cnt = db.query(models.AuditFirstname).count()
        row = (
            db.query(models.AuditFirstname.source)
            .order_by(models.AuditFirstname.id.desc())
            .first()
        )
        source = row[0] if row else None
        notice_path = Path(__file__).resolve().parents[2] / "NOTICE-firstnames.txt"
        notice_hint = None
        if notice_path.is_file():
            try:
                for line in notice_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("Stand Import:"):
                        notice_hint = line.strip()
                        break
            except OSError:
                pass
        return jsonify(
            {
                "count": cnt,
                "source": source,
                "notice_line": notice_hint,
            }
        )


@audit_config_bp.route("/api/audit-config/known-contacts/settings", methods=["GET", "POST"])
@login_required
def audit_known_contacts_settings():
    data = request.get_json(silent=True) or {}
    account_id = request.args.get("account_id", type=int)
    if request.method == "POST":
        account_id = data.get("account_id", account_id)
    if not account_id:
        return jsonify({"error": "account_id erforderlich"}), 400

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )
        if not account:
            return jsonify({"error": "Konto nicht gefunden"}), 404

        from src.services.audit_contact_import import _last_import_from_state

        if request.method == "GET":
            cnt = 0
            if hasattr(models, "AuditKnownContact"):
                cnt = (
                    db.query(models.AuditKnownContact)
                    .filter_by(user_id=user.id, account_id=account_id, is_active=True)
                    .count()
                )
            return jsonify(
                {
                    "account_id": account_id,
                    "import_enabled": bool(
                        getattr(account, "audit_contacts_import_enabled", False)
                    ),
                    "contact_count": cnt,
                    "last_import": _last_import_from_state(
                        getattr(account, "audit_contacts_import_state", None)
                    ),
                }
            )

        enabled = bool(data.get("import_enabled"))
        account.audit_contacts_import_enabled = enabled
        db.commit()
        return jsonify({"success": True, "import_enabled": enabled})


@audit_config_bp.route("/api/audit-config/known-contacts", methods=["GET"])
@login_required
def audit_known_contacts_list():
    account_id = request.args.get("account_id", type=int)
    if not account_id:
        return jsonify({"error": "account_id erforderlich"}), 400
    limit = min(request.args.get("limit", 500, type=int) or 500, 2000)
    offset = max(request.args.get("offset", 0, type=int) or 0, 0)

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )
        if not account:
            return jsonify({"error": "Konto nicht gefunden"}), 404
        from src.services.audit_contact_import import _last_import_from_state

        if not hasattr(models, "AuditKnownContact"):
            return jsonify({"contacts": [], "total": 0, "account_id": account_id})

        base = db.query(models.AuditKnownContact).filter_by(
            user_id=user.id,
            account_id=account_id,
            is_active=True,
        )
        total = base.count()
        rows = (
            base.order_by(
                models.AuditKnownContact.display_name.asc(),
                models.AuditKnownContact.email_normalized.asc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        contacts = [
            {
                "id": r.id,
                "display_name": r.display_name or "",
                "email": r.email_normalized,
                "source": r.source,
                "mail_count": int(r.mail_count or 0),
            }
            for r in rows
        ]
        return jsonify(
            {
                "account_id": account_id,
                "contacts": contacts,
                "total": total,
                "limit": limit,
                "offset": offset,
                "import_enabled": bool(
                    getattr(account, "audit_contacts_import_enabled", False)
                ),
                "last_import": _last_import_from_state(
                    getattr(account, "audit_contacts_import_state", None)
                ),
            }
        )


@audit_config_bp.route("/api/audit-config/known-contacts/import", methods=["POST"])
@login_required
def audit_known_contacts_import():
    from flask import session as flask_session

    from src.helpers.task_ownership import track_celery_task
    from src.tasks.audit_contacts_tasks import import_audit_known_contacts_task

    auth_mod = importlib.import_module(".07_auth", "src")
    ServiceTokenManager = auth_mod.ServiceTokenManager

    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    if not account_id:
        return jsonify({"error": "account_id erforderlich"}), 400

    master_key = flask_session.get("master_key")
    if not master_key:
        return jsonify({"error": "Master-Key erforderlich. Bitte neu einloggen."}), 401

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )
        if not account:
            return jsonify({"error": "Konto nicht gefunden"}), 404

        _, service_token = ServiceTokenManager.create_token(
            user_id=user.id,
            master_key=master_key,
            session=db,
            days=1,
        )
        async_result = import_audit_known_contacts_task.delay(
            user.id,
            account_id,
            service_token.id,
        )
        track_celery_task(async_result, user.id)
        return jsonify({"status": "queued", "task_id": async_result.id}), 202


@audit_config_bp.route("/api/audit-config/known-contacts", methods=["DELETE"])
@login_required
def audit_known_contacts_clear():
    from src.services.audit_contact_import import clear_known_contacts

    account_id = request.args.get("account_id", type=int)
    if not account_id:
        return jsonify({"error": "account_id erforderlich"}), 400

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )
        if not account:
            return jsonify({"error": "Konto nicht gefunden"}), 404
        removed = clear_known_contacts(db, user.id, account_id)
        return jsonify({"success": True, "removed": removed})


@audit_config_bp.route(
    "/api/audit-config/known-contacts/<int:contact_id>", methods=["DELETE"]
)
@login_required
def audit_known_contacts_delete_one(contact_id: int):
    from src.services.audit_contact_import import delete_known_contact

    account_id = request.args.get("account_id", type=int)
    if not account_id:
        return jsonify({"error": "account_id erforderlich"}), 400

    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        models = _get_models()
        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )
        if not account:
            return jsonify({"error": "Konto nicht gefunden"}), 404
        if not delete_known_contact(db, user.id, account_id, contact_id):
            return jsonify({"error": "Kontakt nicht gefunden"}), 404
        return jsonify({"success": True, "id": contact_id})
