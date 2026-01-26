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
"""

import logging
import re
from flask import Blueprint, request, jsonify
from flask_login import login_required
import importlib

from src.helpers import get_db_session, get_current_user_model
from src.services.folder_audit_service import AuditConfigCache

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
    disposition = request.args.get("disposition")  # DELETABLE, PROTECTED, JUNK
    
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
        by_disposition = {"DELETABLE": [], "PROTECTED": [], "JUNK": []}
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
    if not disposition or disposition not in ("DELETABLE", "PROTECTED", "JUNK"):
        return jsonify({"error": "Ungültige disposition (DELETABLE, PROTECTED, JUNK)"}), 400
    
    if not sender_pattern and not subject_pattern:
        return jsonify({"error": "Mindestens sender_pattern oder subject_pattern erforderlich"}), 400
    
    # DELETABLE braucht max_age_days
    if disposition == "DELETABLE" and max_age_days is None:
        return jsonify({"error": "DELETABLE benötigt max_age_days"}), 400
    
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
            if not disposition or disposition not in ("DELETABLE", "PROTECTED", "JUNK"):
                errors.append(f"Ungültige disposition: {disposition}")
                continue
            
            if not sender_pattern and not subject_pattern:
                errors.append("Regel ohne Pattern übersprungen")
                continue
            
            if disposition == "DELETABLE" and max_age_days is None:
                errors.append(f"DELETABLE ohne max_age_days: {sender_pattern}/{subject_pattern}")
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
        
        return jsonify({
            "trusted_domains": count_entries(models.AuditTrustedDomain),
            "important_keywords": count_entries(models.AuditImportantKeyword),
            "safe_patterns": count_entries(models.AuditSafePattern),
            "vip_senders": count_entries(models.AuditVIPSender),
            "auto_delete_rules": count_entries(models.AuditAutoDeleteRule) if hasattr(models, 'AuditAutoDeleteRule') else 0,
        })
