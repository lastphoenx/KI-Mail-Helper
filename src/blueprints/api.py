# src/blueprints/api.py
"""API Blueprint - Alle REST-API Endpoints mit /api Prefix.

Routes (67 total) - geordnet nach Funktionsbereich:

EMAILS:
    1.  /email/<id>/flags (GET) - api_get_email_flags
    2.  /emails/<id>/tags (GET) - api_get_email_tags
    3.  /emails/<id>/tag-suggestions (GET) - api_get_email_tag_suggestions
    4.  /emails/<id>/tags (POST) - api_add_tag_to_email
    5.  /emails/<id>/tags/<tag_id> (DELETE) - api_remove_tag_from_email
    6.  /emails/<id>/tags/<tag_id>/reject (POST) - api_reject_tag_for_email
    7.  /emails/<id>/similar (GET) - api_get_similar_emails
    8.  /emails/<id>/generate-reply (POST) - api_generate_reply
    9.  /emails/<id>/check-embedding-compatibility (GET) - api_check_embedding_compat
    10. /emails/<id>/reprocess (POST) - api_reprocess_email

TAGS:
    11. /tags (GET) - api_get_tags
    12. /tags (POST) - api_create_tag
    13. /tags/<id> (PUT) - api_update_tag
    14. /tags/<id> (DELETE) - api_delete_tag
    15. /tags/<id>/negative-examples (GET) - api_get_negative_examples

TAG-SUGGESTIONS:
    16. /tag-suggestions (GET) - api_get_pending_tag_suggestions
    17. /tag-suggestions/<id>/approve (POST) - api_approve_tag_suggestion
    18. /tag-suggestions/<id>/reject (POST) - api_reject_tag_suggestion
    19. /tag-suggestions/<id>/merge (POST) - api_merge_tag_suggestion
    20. /tag-suggestions/batch-reject (POST) - api_batch_reject_suggestions
    21. /tag-suggestions/batch-approve (POST) - api_batch_approve_suggestions
    22. /tag-suggestions/settings (GET,POST) - api_tag_suggestions_settings

PHASE-Y (KI-Prio):
    23. /phase-y/vip-senders (GET) - api_get_vip_senders
    24. /phase-y/vip-senders (POST) - api_add_vip_sender
    25. /phase-y/vip-senders/<id> (PUT) - api_update_vip_sender
    26. /phase-y/vip-senders/<id> (DELETE) - api_delete_vip_sender
    27. /phase-y/keyword-sets (GET) - api_get_keyword_sets
    28. /phase-y/keyword-sets (POST) - api_save_keyword_sets
    29. /phase-y/scoring-config (GET) - api_get_scoring_config
    30. /phase-y/scoring-config (POST) - api_save_scoring_config
    31. /phase-y/user-domains (GET) - api_get_user_domains
    32. /phase-y/user-domains (POST) - api_add_user_domain
    33. /phase-y/user-domains/<id> (DELETE) - api_delete_user_domain

SEARCH & EMBEDDINGS:
    34. /search/semantic (GET) - api_semantic_search
    35. /embeddings/stats (GET) - api_embeddings_stats
    36. /batch-reprocess-embeddings (POST) - api_batch_reprocess_embeddings

REPLY-STYLES:
    37. /reply-tones (GET) - api_get_reply_tones
    38. /reply-styles (GET) - api_get_reply_styles
    39. /reply-styles/<key> (GET) - api_get_reply_style
    40. /reply-styles/<key> (PUT) - api_update_reply_style
    41. /reply-styles/<key> (DELETE) - api_delete_reply_style
    42. /reply-styles/preview (POST) - api_preview_reply_style

RULES (API-Part):
    43. /rules (GET) - api_get_rules
    44. /rules (POST) - api_create_rule
    45. /rules/<id> (PUT) - api_update_rule
    46. /rules/<id> (DELETE) - api_delete_rule
    47. /rules/<id>/test (POST) - api_test_rule
    48. /rules/apply (POST) - api_apply_rules
    49. /rules/templates (GET) - api_get_rule_templates
    50. /rules/templates/<name> (POST) - api_apply_rule_template

ACCOUNTS & MODELS:
    51. /accounts (GET) - api_get_accounts
    52. /models/<provider> (GET) - api_get_models
    53. /available-models/<provider> (GET) - api_available_models
    54. /available-providers (GET) - api_available_providers
    55. /training-stats (GET) - api_training_stats

IMAP:
    56. /imap-diagnostics/<id> (POST) - api_imap_diagnostics

TRUSTED-SENDERS:
    57. /trusted-senders (GET) - api_get_trusted_senders
    58. /trusted-senders (POST) - api_add_trusted_sender
    59. /trusted-senders/<id> (PATCH) - api_update_trusted_sender
    60. /trusted-senders/<id> (DELETE) - api_delete_trusted_sender
    61. /trusted-senders/suggestions (GET) - api_get_trusted_sender_suggestions
    62. /trusted-senders/bulk-add (POST) - api_bulk_add_trusted_senders

URGENCY-BOOSTER:
    63. /settings/urgency-booster (GET) - api_get_urgency_booster
    64. /settings/urgency-booster (POST) - api_save_urgency_booster
    65. /accounts/urgency-booster-settings (GET) - api_get_urgency_booster_settings
    66. /accounts/<id>/urgency-booster (POST) - api_save_account_urgency_booster

IMAP SCANNER:
    67. /scan-account-senders/<id> (POST) - api_scan_account_senders

Extracted from 01_web_app.py various sections.
"""

from flask import Blueprint, request, jsonify, session, g
from flask_login import login_required, current_user
from datetime import datetime, UTC
from sqlalchemy.exc import IntegrityError
import json
import logging
import importlib
import time
import re

from src.helpers import get_db_session, get_current_user_model

api_bp = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)


# =============================================================================
# GLOBALS: IMAP Sender Scanner (Phase X.3)
# =============================================================================
# Concurrent Scan Prevention (in-memory lock)
_active_scans = set()  # Set von account_ids die gerade scannen

# Rate-Limiting pro User (60s Cooldown zwischen Scans)
_last_scan_time = {}  # Dict: user_id -> timestamp
SCAN_COOLDOWN_SECONDS = 60  # Minimum Zeit zwischen Scans


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def validate_string(value, field_name, min_len=1, max_len=255, allow_empty=False, pattern=None):
    """Validiert String-Input mit konfigurierbaren Regeln.
    
    Args:
        value: Der zu validierende Wert
        field_name: Name des Feldes für Fehlermeldungen
        min_len: Minimale Länge (default: 1)
        max_len: Maximale Länge (default: 255)
        allow_empty: Erlaube leere Strings (default: False)
        pattern: Optionales Regex-Pattern
        
    Returns:
        Getrimmter String
        
    Raises:
        ValueError: Bei Validierungsfehler
    """
    if value is None:
        if allow_empty:
            return ""
        raise ValueError(f"{field_name} ist erforderlich")
    
    if not isinstance(value, str):
        raise ValueError(f"{field_name} muss ein String sein")
    
    value = value.strip()
    
    if not value and not allow_empty:
        raise ValueError(f"{field_name} darf nicht leer sein")
    
    if len(value) < min_len and not (allow_empty and len(value) == 0):
        raise ValueError(f"{field_name} muss mindestens {min_len} Zeichen haben")
    
    if len(value) > max_len:
        raise ValueError(f"{field_name} darf maximal {max_len} Zeichen haben")
    
    if pattern and value and not re.match(pattern, value):
        raise ValueError(f"{field_name} hat ein ungültiges Format")
    
    return value


def _update_user_override_tags(db, processed_email_id, user_id, tag_manager):
    """Updates user_override_tags for ML training (Phase F.3).
    
    Args:
        db: Database session
        processed_email_id: ID der ProcessedEmail
        user_id: User-ID
        tag_manager: TagManager Klasse
    """
    models = _get_models()
    try:
        override_tags = tag_manager.get_user_override_tags(
            db, processed_email_id, user_id
        )
        if override_tags:
            processed = db.query(models.ProcessedEmail).get(processed_email_id)
            if processed:
                processed.user_override_tags = override_tags
                db.commit()
    except Exception as e:
        logger.warning(f"Could not update override tags: {e}")
        # Nicht kritisch - nicht abbrechen

# Lazy imports
_models = None
_encryption = None
_tag_manager = None
_auto_rules = None
_mail_fetcher = None
_semantic_search = None
_ai_client = None


def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


def _get_encryption():
    global _encryption
    if _encryption is None:
        _encryption = importlib.import_module(".08_encryption", "src")
    return _encryption


def _get_tag_manager():
    global _tag_manager
    if _tag_manager is None:
        tag_mod = importlib.import_module("src.services.tag_manager", "src")
        _tag_manager = tag_mod.TagManager
    return _tag_manager


def _get_auto_rules():
    global _auto_rules
    if _auto_rules is None:
        rules_mod = importlib.import_module("src.auto_rules_engine", "src")
        _auto_rules = rules_mod.AutoRulesEngine
    return _auto_rules


def _get_mail_fetcher():
    global _mail_fetcher
    if _mail_fetcher is None:
        _mail_fetcher = importlib.import_module(".06_mail_fetcher", "src")
    return _mail_fetcher


def _get_semantic_search():
    global _semantic_search
    if _semantic_search is None:
        _semantic_search = importlib.import_module(".semantic_search", "src")
    return _semantic_search


def _get_ai_client():
    global _ai_client
    if _ai_client is None:
        _ai_client = importlib.import_module(".03_ai_client", "src")
    return _ai_client


# =============================================================================
# EMAIL FLAGS & TAGS (Routes 1-10)
# =============================================================================
@api_bp.route("/email/<int:raw_email_id>/flags", methods=["GET"])
@login_required
def api_get_email_flags(raw_email_id):
    """Liefert IMAP-Flags für eine Email"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            raw_email = db.query(models.RawEmail).get(raw_email_id)
            if not raw_email or raw_email.mail_account.user_id != user.id:
                return jsonify({"error": "Not found"}), 404
            
            return jsonify({
                "raw_email_id": raw_email_id,
                "is_read": raw_email.is_read,
                "is_flagged": raw_email.is_flagged,
            })
    except Exception as e:
        logger.error(f"api_get_email_flags: Fehler für Email {raw_email_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/emails/<int:raw_email_id>/tags", methods=["GET"])
@login_required
def api_get_email_tags(raw_email_id):
    """Liefert alle Tags einer Email"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            raw_email = db.query(models.RawEmail).get(raw_email_id)
            if not raw_email or raw_email.mail_account.user_id != user.id:
                return jsonify({"error": "Not found"}), 404
            
            processed = db.query(models.ProcessedEmail).filter_by(raw_email_id=raw_email_id).first()
            if not processed:
                return jsonify({"tags": []})
            
            tags = [{"id": t.id, "name": t.name, "color": t.color} for t in processed.tags]
            return jsonify({"tags": tags})
    except Exception as e:
        logger.error(f"api_get_email_tags: Fehler für Email {raw_email_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/emails/<int:raw_email_id>/tag-suggestions", methods=["GET"])
@login_required
def api_get_email_tag_suggestions(raw_email_id):
    """KI-basierte Tag-Vorschläge für eine Email"""
    models = _get_models()
    tag_manager = _get_tag_manager()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            raw_email = db.query(models.RawEmail).get(raw_email_id)
            if not raw_email or raw_email.mail_account.user_id != user.id:
                return jsonify({"error": "Not found"}), 404
            
            processed = db.query(models.ProcessedEmail).filter_by(raw_email_id=raw_email_id).first()
            if not processed:
                return jsonify({"suggestions": []})
            
            try:
                suggestions = tag_manager.get_tag_suggestions(db, processed.id, user.id)
                return jsonify({"suggestions": suggestions})
            except Exception as e:
                logger.warning(f"api_get_email_tag_suggestions: TagManager error: {e}")
                return jsonify({"suggestions": []})
    except Exception as e:
        logger.error(f"api_get_email_tag_suggestions: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/emails/<int:raw_email_id>/tags", methods=["POST"])
@login_required
def api_add_tag_to_email(raw_email_id):
    """Fügt Tag zu Email hinzu mit ML-Training Update"""
    models = _get_models()
    tag_manager = _get_tag_manager()
    data = request.get_json() or {}
    tag_id = data.get("tag_id")
    
    if not tag_id:
        return jsonify({"error": "tag_id ist erforderlich"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            raw_email = db.query(models.RawEmail).get(raw_email_id)
            if not raw_email or raw_email.mail_account.user_id != user.id:
                return jsonify({"error": "Email nicht gefunden"}), 404
            
            tag = db.query(models.Tag).filter_by(id=tag_id, user_id=user.id).first()
            if not tag:
                return jsonify({"error": "Tag nicht gefunden"}), 404
            
            processed = db.query(models.ProcessedEmail).filter_by(raw_email_id=raw_email_id).first()
            if not processed:
                return jsonify({"error": "Verarbeitete Email nicht gefunden"}), 404
            
            try:
                # Verwende TagManager für konsistente Zuordnung
                success = tag_manager.assign_tag(db, processed.id, tag_id, user.id)
                
                if not success:
                    return jsonify({"error": "Tag bereits zugeordnet oder nicht gefunden"}), 400
                
                db.commit()
                
                # ML-Training Update (Phase F.3)
                _update_user_override_tags(db, processed.id, user.id, tag_manager)
                
                logger.info(f"Tag {tag_id} zu Email {processed.id} hinzugefügt")
                return jsonify({"success": True})
                
            except IntegrityError:
                db.rollback()
                return jsonify({"error": "Tag bereits zugeordnet"}), 409
            except Exception as e:
                db.rollback()
                logger.error(f"api_add_tag_to_email: DB-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Hinzufügen des Tags"}), 500
    except Exception as e:
        logger.error(f"api_add_tag_to_email: Unerwarteter Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/emails/<int:raw_email_id>/tags/<int:tag_id>", methods=["DELETE"])
@login_required
def api_remove_tag_from_email(raw_email_id, tag_id):
    """Entfernt Tag von Email mit ML-Training Update"""
    models = _get_models()
    tag_manager = _get_tag_manager()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            raw_email = db.query(models.RawEmail).get(raw_email_id)
            if not raw_email or raw_email.mail_account.user_id != user.id:
                return jsonify({"error": "Email nicht gefunden"}), 404
            
            processed = db.query(models.ProcessedEmail).filter_by(raw_email_id=raw_email_id).first()
            if not processed:
                return jsonify({"error": "Verarbeitete Email nicht gefunden"}), 404
            
            try:
                # Verwende TagManager für konsistente Entfernung
                success = tag_manager.remove_tag(db, processed.id, tag_id, user.id)
                
                if success:
                    db.commit()
                    
                    # ML-Training Update (Phase F.3)
                    _update_user_override_tags(db, processed.id, user.id, tag_manager)
                    
                    logger.info(f"Tag {tag_id} von Email {processed.id} entfernt")
                
                return jsonify({"success": True})
                
            except Exception as e:
                db.rollback()
                logger.error(f"api_remove_tag_from_email: DB-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Entfernen des Tags"}), 500
    except Exception as e:
        logger.error(f"api_remove_tag_from_email: Unerwarteter Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/emails/<int:raw_email_id>/tags/<int:tag_id>/reject", methods=["POST"])
@login_required
def api_reject_tag_for_email(raw_email_id, tag_id):
    """Lehnt Tag-Vorschlag für Email ab (Negative Example für ML)"""
    models = _get_models()
    tag_manager = _get_tag_manager()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            raw_email = db.query(models.RawEmail).get(raw_email_id)
            if not raw_email or raw_email.mail_account.user_id != user.id:
                return jsonify({"error": "Email nicht gefunden"}), 404
            
            processed = db.query(models.ProcessedEmail).filter_by(raw_email_id=raw_email_id).first()
            if not processed:
                return jsonify({"error": "Verarbeitete Email nicht gefunden"}), 404
            
            tag = db.query(models.Tag).filter_by(id=tag_id, user_id=user.id).first()
            if not tag:
                return jsonify({"error": "Tag nicht gefunden"}), 404
            
            try:
                # Verwende TagManager für konsistentes Negative Example
                success = tag_manager.reject_tag(db, processed.id, tag_id, user.id)
                
                if success:
                    db.commit()
                    logger.info(f"Tag {tag_id} als Negative Example für Email {processed.id} markiert")
                
                return jsonify({"success": True})
                
            except IntegrityError:
                db.rollback()
                # Bereits abgelehnt ist kein Fehler
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_reject_tag_for_email: DB-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Ablehnen des Tags"}), 500
    except Exception as e:
        logger.error(f"api_reject_tag_for_email: Unerwarteter Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/emails/<int:raw_email_id>/similar", methods=["GET"])
@login_required
def api_get_similar_emails(raw_email_id):
    """API: Ähnliche E-Mails finden (Phase F.1)
    
    Query Parameters:
    - limit: Max. Anzahl Ergebnisse (default: 5)
    - account_id: Optional Account-Filter
    
    Returns:
    {
        "similar_emails": [{"email_id": 456, "subject": "...", "similarity_score": 0.92}],
        "reference_email_id": 123,
        "total": 3
    }
    """
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            try:
                limit = min(int(request.args.get("limit", 5)), 20)
                account_id = request.args.get("account_id")
                if account_id:
                    try:
                        account_id = int(account_id)
                    except ValueError:
                        account_id = None
            except ValueError:
                return jsonify({"error": "Invalid limit parameter"}), 400
            
            # Ownership Check
            ref_email = db.query(models.RawEmail).filter_by(
                id=raw_email_id,
                user_id=user.id
            ).first()
            
            if not ref_email:
                return jsonify({"error": "Email not found or access denied"}), 404
            
            # Similar Emails finden
            try:
                semantic_search = _get_semantic_search()
                search_service = semantic_search.SemanticSearchService(db)
                results = search_service.find_similar(
                    email_id=raw_email_id,
                    limit=limit,
                    account_id=account_id
                )
                
                # Ergebnisse formatieren (mit Decryption)
                master_key = session.get("master_key")
                if not master_key:
                    return jsonify({"error": "Master key not in session"}), 401
                
                formatted_results = []
                for result in results:
                    try:
                        subject_plain = encryption.EmailDataManager.decrypt_email_subject(
                            result["encrypted_subject"], master_key
                        ) if result.get("encrypted_subject") else ""
                        
                        sender = result.get("encrypted_sender", "")
                        date_str = result["received_at"].isoformat() if result.get("received_at") else None
                        
                        formatted_results.append({
                            "email_id": result["id"],
                            "subject": subject_plain,
                            "from": sender,
                            "date": date_str,
                            "similarity_score": result["similarity_score"]
                        })
                    except Exception as decrypt_err:
                        logger.warning(f"Decryption failed for email {result['id']}: {decrypt_err}")
                        continue
                
                return jsonify({
                    "similar_emails": formatted_results,
                    "reference_email_id": raw_email_id,
                    "total": len(formatted_results)
                }), 200
                
            except ValueError as ve:
                return jsonify({"error": str(ve)}), 404
            except ImportError:
                logger.warning("SemanticSearchService nicht verfügbar")
                return jsonify({
                    "similar_emails": [],
                    "reference_email_id": raw_email_id,
                    "total": 0,
                    "error": "Search service unavailable"
                }), 200
            except Exception as search_err:
                logger.error(f"Similar search failed: {search_err}")
                return jsonify({
                    "similar_emails": [],
                    "reference_email_id": raw_email_id,
                    "total": 0,
                    "error": "Search service unavailable"
                }), 500
    except Exception as e:
        logger.error(f"api_get_similar_emails: Fehler für Email {raw_email_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/emails/<int:raw_email_id>/generate-reply", methods=["POST"])
@login_required
def api_generate_reply(raw_email_id):
    """API: Generiert Antwort-Entwurf auf eine Email (Phase G.1 + Provider/Anonymization)
    
    Request Body:
    {
        "tone": "formal|friendly|brief|decline",
        "provider": "ollama|openai|anthropic",
        "model": "llama3.2|gpt-4o|claude-sonnet",
        "use_anonymization": true|false
    }
    """
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"success": False, "error": "Unauthorized"}), 401
            
            # Parse request body
            data = request.get_json() or {}
            tone = data.get("tone", "formal")
            requested_provider = data.get("provider")
            requested_model = data.get("model")
            use_anonymization = data.get("use_anonymization")
            
            # Validiere Email-Zugriff
            processed = db.query(models.ProcessedEmail).join(models.RawEmail).filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None
            ).first()
            
            if not processed or not processed.raw_email:
                return jsonify({"success": False, "error": "Email nicht gefunden"}), 404
            
            raw_email = processed.raw_email
            
            # Zero-Knowledge: Entschlüssele Email-Daten
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"success": False, "error": "Master-Key nicht verfügbar"}), 401
            
            try:
                decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                    raw_email.encrypted_subject or "", master_key
                )
                decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                    raw_email.encrypted_body or "", master_key
                )
                decrypted_sender = encryption.EmailDataManager.decrypt_email_sender(
                    raw_email.encrypted_sender or "", master_key
                )
            except Exception as e:
                logger.error(f"Decryption failed for email raw_id={raw_email_id}: {e}")
                return jsonify({"success": False, "error": "Entschlüsselung fehlgeschlagen"}), 500
            
            # Thread-Context für bessere Antworten
            thread_context = ""
            try:
                processing_mod = importlib.import_module(".12_processing", "src")
                thread_context = processing_mod.build_thread_context(
                    session=db,
                    raw_email=raw_email,
                    master_key=master_key,
                    max_context_emails=3
                )
            except Exception as ctx_err:
                logger.warning(f"Thread-Context build failed: {ctx_err}")
            
            # Generate Reply
            try:
                ai_client = _get_ai_client()
                reply_generator_mod = importlib.import_module("src.reply_generator")
                
                # Provider/Model Selection
                if requested_provider and requested_model:
                    provider = requested_provider.lower()
                    resolved_model = ai_client.resolve_model(provider, requested_model, kind="optimize")
                else:
                    provider = (getattr(user, 'preferred_ai_provider_optimize', None) or 
                               getattr(user, 'preferred_ai_provider', None) or "ollama").lower()
                    optimize_model = getattr(user, 'preferred_ai_model_optimize', None) or getattr(user, 'preferred_ai_model', None)
                    resolved_model = ai_client.resolve_model(provider, optimize_model, kind="optimize")
                
                client = ai_client.build_client(provider, model=resolved_model)
                
                # Anonymisierungs-Logik
                cloud_providers = ["openai", "anthropic", "google"]
                is_cloud_provider = provider in cloud_providers
                
                if use_anonymization is None:
                    use_anonymization = is_cloud_provider
                
                content_for_ai_subject = decrypted_subject
                content_for_ai_body = decrypted_body
                sender_for_ai = decrypted_sender
                entity_map = None
                was_anonymized = False
                
                if use_anonymization:
                    # Nutze sanitized Content wenn verfügbar
                    if raw_email.encrypted_subject_sanitized and raw_email.encrypted_body_sanitized:
                        try:
                            content_for_ai_subject = encryption.EmailDataManager.decrypt_email_subject(
                                raw_email.encrypted_subject_sanitized, master_key
                            )
                            content_for_ai_body = encryption.EmailDataManager.decrypt_email_body(
                                raw_email.encrypted_body_sanitized, master_key
                            )
                            was_anonymized = True
                            sender_for_ai = "[ABSENDER]"
                            
                            if raw_email.encrypted_entity_map:
                                try:
                                    entity_map_json = encryption.EncryptionManager.decrypt_data(
                                        raw_email.encrypted_entity_map, master_key
                                    )
                                    entity_map = json.loads(entity_map_json)
                                except Exception:
                                    pass
                        except Exception as decrypt_err:
                            logger.warning(f"Sanitized content decryption failed: {decrypt_err}")
                    else:
                        # On-the-fly Anonymisierung
                        try:
                            from src.services.content_sanitizer import ContentSanitizer
                            sanitizer = ContentSanitizer()
                            result = sanitizer.sanitize_with_roles(
                                subject=decrypted_subject,
                                body=decrypted_body,
                                sender=decrypted_sender,
                                recipient=user.username,
                                level=2
                            )
                            content_for_ai_subject = result.subject
                            content_for_ai_body = result.body
                            sender_for_ai = "[ABSENDER]"
                            entity_map = result.entity_map.to_dict()
                            was_anonymized = True
                            
                            # Speichere in DB
                            raw_email.encrypted_subject_sanitized = encryption.EmailDataManager.encrypt_email_subject(
                                result.subject, master_key
                            )
                            raw_email.encrypted_body_sanitized = encryption.EmailDataManager.encrypt_email_body(
                                result.body, master_key
                            )
                            raw_email.sanitization_entities_count = result.entities_found
                            raw_email.encrypted_entity_map = encryption.EncryptionManager.encrypt_data(
                                json.dumps(entity_map), master_key
                            )
                            db.commit()
                        except Exception as anon_err:
                            logger.error(f"On-the-fly anonymization failed: {anon_err}")
                            db.rollback()
                
                generator = reply_generator_mod.ReplyGenerator(ai_client=client)
                
                result = generator.generate_reply_with_user_style(
                    db=db,
                    user_id=user.id,
                    original_subject=content_for_ai_subject,
                    original_body=content_for_ai_body,
                    original_sender=sender_for_ai,
                    tone=tone,
                    thread_context=thread_context if thread_context else None,
                    has_attachments=raw_email.has_attachments or False,
                    master_key=master_key,
                    account_id=raw_email.mail_account_id
                )
                
                if result["success"]:
                    result["was_anonymized"] = was_anonymized
                    result["entity_map"] = entity_map
                    result["provider_used"] = provider
                    result["model_used"] = resolved_model
                    logger.info(f"✅ Reply generiert für Email {raw_email_id} (Ton: {result['tone_used']})")
                
                return jsonify(result), 200 if result["success"] else 500
                
            except ImportError as e:
                logger.error(f"Reply generator import failed: {e}")
                return jsonify({"success": False, "error": "Reply Generator nicht verfügbar"}), 500
            except Exception as gen_err:
                logger.error(f"Reply generation failed: {gen_err}")
                return jsonify({
                    "success": False,
                    "error": "Generierung fehlgeschlagen",
                    "reply_text": "",
                    "tone_used": tone
                }), 500
    except Exception as e:
        logger.error(f"api_generate_reply: Fehler für Email {raw_email_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/emails/<int:raw_email_id>/check-embedding-compatibility", methods=["GET"])
@login_required
def api_check_embedding_compat(raw_email_id):
    """Prüft Embedding-Kompatibilität einer Email"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            raw_email = db.query(models.RawEmail).get(raw_email_id)
            if not raw_email or raw_email.mail_account.user_id != user.id:
                return jsonify({"error": "Not found"}), 404
            
            processed = db.query(models.ProcessedEmail).filter_by(raw_email_id=raw_email_id).first()
            if not processed:
                return jsonify({"compatible": False, "reason": "No processed email"})
            
            has_embedding = processed.embedding_vector is not None
            embedding_model = processed.embedding_model if hasattr(processed, 'embedding_model') else None
            
            return jsonify({
                "compatible": has_embedding,
                "has_embedding": has_embedding,
                "embedding_model": embedding_model,
            })
    except Exception as e:
        logger.error(f"api_check_embedding_compat: Fehler für Email {raw_email_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/emails/<int:raw_email_id>/reprocess", methods=["POST"])
@login_required
def api_reprocess_email(raw_email_id):
    """API: Email neu verarbeiten (Phase F.2 Enhanced)
    
    Regeneriert:
    - Email-Embedding (mit aktuellem Base Model aus Settings)
    - AI-Score + Kategorie
    - Tag-Suggestions (automatisch mit neuem Embedding)
    """
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"success": False, "error": "Unauthorized"}), 401
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"success": False, "error": "Master-Key nicht verfügbar"}), 401
            
            # Validiere Email-Zugriff
            raw_email = db.query(models.RawEmail).filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None
            ).first()
            
            if not raw_email:
                return jsonify({"success": False, "error": "Email nicht gefunden"}), 404
            
            # Entschlüssele für Reprocessing
            try:
                decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                    raw_email.encrypted_subject or "", master_key
                )
                decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                    raw_email.encrypted_body or "", master_key
                )
            except Exception as e:
                logger.error(f"Decryption failed for email {raw_email_id}: {e}")
                return jsonify({"success": False, "error": "Entschlüsselung fehlgeschlagen"}), 500
            
            ai_score = None
            
            # 1. EMBEDDING neu generieren
            try:
                semantic_search = _get_semantic_search()
                ai_client = _get_ai_client()
                
                provider_embedding = (getattr(user, 'preferred_embedding_provider', None) or "ollama").lower()
                model_embedding = getattr(user, 'preferred_embedding_model', None) or "all-minilm:22m"
                resolved_model_embedding = ai_client.resolve_model(provider_embedding, model_embedding)
                
                embedding_client = ai_client.build_client(provider_embedding, model=resolved_model_embedding)
                
                embedding_bytes, model_name, timestamp = semantic_search.generate_embedding_for_email(
                    subject=decrypted_subject,
                    body=decrypted_body,
                    ai_client=embedding_client,
                    model_name=resolved_model_embedding
                )
                
                if embedding_bytes:
                    raw_email.email_embedding = embedding_bytes
                    raw_email.embedding_model = model_name or resolved_model_embedding
                    raw_email.embedding_generated_at = timestamp
                    logger.info(f"✅ Embedding regenerated: {model_name}")
            except Exception as emb_err:
                logger.warning(f"Embedding regeneration error: {emb_err}")
            
            # 2. AI-SCORE + KATEGORIE neu berechnen
            try:
                processing_mod = importlib.import_module(".12_processing", "src")
                ai_client = _get_ai_client()
                
                thread_context = processing_mod.build_thread_context(
                    session=db,
                    raw_email=raw_email,
                    master_key=master_key,
                    max_context_emails=5
                )
                
                provider_optimize = (getattr(user, 'preferred_ai_provider_optimize', None) or "ollama").lower()
                model_optimize = getattr(user, 'preferred_ai_model_optimize', None) or "llama3.2:1b"
                resolved_model_optimize = ai_client.resolve_model(provider_optimize, model_optimize)
                
                optimize_client = ai_client.build_client(provider_optimize, model=resolved_model_optimize)
                
                result = optimize_client.analyze_email(
                    subject=decrypted_subject,
                    body=decrypted_body,
                    language="de",
                    context=thread_context if thread_context else None
                )
                
                processed = db.query(models.ProcessedEmail).filter_by(
                    raw_email_id=raw_email.id
                ).first()
                
                if processed and result:
                    processed.score = result.get("score", processed.score)
                    processed.farbe = result.get("farbe", processed.farbe)
                    processed.kategorie_aktion = result.get("kategorie_aktion", processed.kategorie_aktion)
                    ai_score = processed.score
                    logger.info(f"✅ Score regenerated: {processed.score}")
            except Exception as score_err:
                logger.warning(f"Score regeneration error: {score_err}")
            
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"api_reprocess_email: Commit-Fehler: {e}")
                return jsonify({"success": False, "error": "Speichern fehlgeschlagen"}), 500
            
            return jsonify({
                "success": True,
                "message": "Email erfolgreich neu verarbeitet",
                "embedding_model": getattr(raw_email, 'embedding_model', None),
                "ai_score": ai_score
            }), 200
            
    except Exception as e:
        logger.error(f"api_reprocess_email: Fehler für Email {raw_email_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# TAGS (Routes 11-15)
# =============================================================================
@api_bp.route("/tags", methods=["GET"])
@login_required
def api_get_tags():
    """Liefert alle Tags des Users"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            tags = db.query(models.Tag).filter_by(user_id=user.id).order_by(models.Tag.name).all()
            return jsonify([{
                "id": t.id,
                "name": t.name,
                "color": t.color,
                "description": t.description,
            } for t in tags])
    except Exception as e:
        logger.error(f"api_get_tags: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tags", methods=["POST"])
@login_required
def api_create_tag():
    """Erstellt neuen Tag"""
    models = _get_models()
    tag_manager = _get_tag_manager()
    data = request.get_json() or {}
    
    # Input Validation
    try:
        name = validate_string(data.get("name"), "Tag-Name", min_len=1, max_len=50)
        color = validate_string(data.get("color", "#3B82F6"), "Farbe", min_len=4, max_len=20)
        description = validate_string(
            data.get("description"), "Beschreibung", 
            min_len=0, max_len=500, allow_empty=True
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            try:
                # Verwende TagManager für Business Logic
                tag = tag_manager.create_tag(
                    db, user.id, name, color, description=description
                )
                db.commit()
                
                logger.info(f"Tag erstellt: {tag.id} für User {user.id}")
                
                return jsonify({
                    "id": tag.id,
                    "name": tag.name,
                    "color": tag.color,
                    "description": tag.description,
                }), 201
                
            except IntegrityError:
                db.rollback()
                logger.warning(f"api_create_tag: Tag existiert bereits: {name}")
                return jsonify({"error": "Tag existiert bereits"}), 409
            except ValueError as e:
                db.rollback()
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                db.rollback()
                logger.error(f"api_create_tag: DB-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Erstellen des Tags"}), 500
    except Exception as e:
        logger.error(f"api_create_tag: Unerwarteter Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tags/<int:tag_id>", methods=["PUT"])
@login_required
def api_update_tag(tag_id):
    """Aktualisiert Tag"""
    models = _get_models()
    tag_manager = _get_tag_manager()
    data = request.get_json() or {}
    
    # Input Validation (optional fields)
    try:
        name = validate_string(data.get("name"), "Tag-Name", min_len=1, max_len=50) if "name" in data else None
        color = validate_string(data.get("color"), "Farbe", min_len=4, max_len=20) if "color" in data else None
        description = validate_string(
            data.get("description"), "Beschreibung",
            min_len=0, max_len=500, allow_empty=True
        ) if "description" in data else None
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            tag = db.query(models.Tag).filter_by(id=tag_id, user_id=user.id).first()
            if not tag:
                return jsonify({"error": "Tag nicht gefunden"}), 404
            
            try:
                # Update fields
                if name is not None:
                    tag.name = name
                if color is not None:
                    tag.color = color
                if description is not None:
                    tag.description = description
                
                db.commit()
                
                logger.info(f"Tag aktualisiert: {tag_id}")
                return jsonify({
                    "id": tag.id,
                    "name": tag.name,
                    "color": tag.color,
                    "description": tag.description,
                    "success": True
                })
                
            except IntegrityError:
                db.rollback()
                logger.warning(f"api_update_tag: Duplikat-Name: {name}")
                return jsonify({"error": "Tag-Name existiert bereits"}), 409
            except Exception as e:
                db.rollback()
                logger.error(f"api_update_tag: DB-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Aktualisieren"}), 500
    except Exception as e:
        logger.error(f"api_update_tag: Unerwarteter Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tags/<int:tag_id>", methods=["DELETE"])
@login_required
def api_delete_tag(tag_id):
    """Löscht Tag"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            tag = db.query(models.Tag).filter_by(id=tag_id, user_id=user.id).first()
            if not tag:
                return jsonify({"error": "Tag nicht gefunden"}), 404
            
            try:
                db.delete(tag)
                db.commit()
                
                logger.info(f"Tag gelöscht: {tag_id}")
                return jsonify({"success": True})
                
            except Exception as e:
                db.rollback()
                logger.error(f"api_delete_tag: DB-Fehler: {type(e).__name__}: {e}")
                return jsonify({"error": "Fehler beim Löschen"}), 500
    except Exception as e:
        logger.error(f"api_delete_tag: Unerwarteter Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tags/<int:tag_id>/negative-examples", methods=["GET"])
@login_required
def api_get_negative_examples(tag_id):
    """Liefert Negative Examples für einen Tag"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            tag = db.query(models.Tag).filter_by(id=tag_id, user_id=user.id).first()
            if not tag:
                return jsonify({"error": "Not found"}), 404
            
            examples = db.query(models.TagNegativeExample).filter_by(
                user_id=user.id, tag_id=tag_id
            ).all()
            
            return jsonify([{
                "id": ex.id,
                "processed_email_id": ex.processed_email_id,
                "created_at": ex.created_at.isoformat() if hasattr(ex, 'created_at') else None,
            } for ex in examples])
    except Exception as e:
        logger.error(f"api_get_negative_examples: Fehler für Tag {tag_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# TAG-SUGGESTIONS (Routes 16-22)
# =============================================================================
@api_bp.route("/tag-suggestions", methods=["GET"], endpoint="api_get_pending_tag_suggestions")
@login_required
def api_get_pending_tag_suggestions():
    """Pending Tag-Vorschläge für Review"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TagSuggestion'):
                return jsonify([])
            
            suggestions = db.query(models.TagSuggestion).filter_by(
                user_id=user.id, status="pending"
            ).limit(50).all()
            
            return jsonify([{
                "id": s.id,
                "tag_name": s.tag_name,
                "email_count": s.email_count if hasattr(s, 'email_count') else 1,
            } for s in suggestions])
    except Exception as e:
        logger.error(f"api_get_pending_tag_suggestions: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tag-suggestions/<int:id>/approve", methods=["POST"])
@login_required
def api_approve_tag_suggestion(id):
    """Akzeptiert Tag-Vorschlag und erstellt Tag"""
    models = _get_models()
    tag_manager = _get_tag_manager()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TagSuggestion'):
                return jsonify({"error": "Feature not available"}), 501
            
            suggestion = db.query(models.TagSuggestion).filter_by(
                id=id, user_id=user.id
            ).first()
            
            if not suggestion:
                return jsonify({"error": "Vorschlag nicht gefunden"}), 404
            
            try:
                # Erstelle Tag aus Vorschlag
                tag = tag_manager.create_tag(
                    db, user.id, suggestion.tag_name, 
                    suggestion.color if hasattr(suggestion, 'color') else "#3B82F6"
                )
                
                # Markiere als approved
                suggestion.status = "approved"
                suggestion.approved_tag_id = tag.id
                db.commit()
                
                logger.info(f"Tag-Suggestion {id} approved, Tag {tag.id} created")
                return jsonify({"success": True, "tag_id": tag.id})
                
            except IntegrityError:
                db.rollback()
                return jsonify({"error": "Tag existiert bereits"}), 409
            except Exception as e:
                db.rollback()
                logger.error(f"api_approve_tag_suggestion: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Erstellen"}), 500
    except Exception as e:
        logger.error(f"api_approve_tag_suggestion: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tag-suggestions/<int:id>/reject", methods=["POST"])
@login_required
def api_reject_tag_suggestion(id):
    """Lehnt Tag-Vorschlag ab"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TagSuggestion'):
                return jsonify({"error": "Feature not available"}), 501
            
            suggestion = db.query(models.TagSuggestion).filter_by(
                id=id, user_id=user.id
            ).first()
            
            if not suggestion:
                return jsonify({"error": "Vorschlag nicht gefunden"}), 404
            
            try:
                suggestion.status = "rejected"
                db.commit()
                
                logger.info(f"Tag-Suggestion {id} rejected")
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_reject_tag_suggestion: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Ablehnen"}), 500
    except Exception as e:
        logger.error(f"api_reject_tag_suggestion: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tag-suggestions/<int:id>/merge", methods=["POST"])
@login_required
def api_merge_tag_suggestion(id):
    """Merged Tag-Vorschlag mit existierendem Tag"""
    models = _get_models()
    data = request.get_json() or {}
    target_tag_id = data.get("target_tag_id")
    
    if not target_tag_id:
        return jsonify({"error": "target_tag_id ist erforderlich"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TagSuggestion'):
                return jsonify({"error": "Feature not available"}), 501
            
            suggestion = db.query(models.TagSuggestion).filter_by(
                id=id, user_id=user.id
            ).first()
            
            if not suggestion:
                return jsonify({"error": "Vorschlag nicht gefunden"}), 404
            
            target_tag = db.query(models.Tag).filter_by(
                id=target_tag_id, user_id=user.id
            ).first()
            
            if not target_tag:
                return jsonify({"error": "Ziel-Tag nicht gefunden"}), 404
            
            try:
                suggestion.status = "merged"
                suggestion.merged_to_tag_id = target_tag_id
                db.commit()
                
                logger.info(f"Tag-Suggestion {id} merged to tag {target_tag_id}")
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_merge_tag_suggestion: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Mergen"}), 500
    except Exception as e:
        logger.error(f"api_merge_tag_suggestion: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tag-suggestions/batch-reject", methods=["POST"])
@login_required
def api_batch_reject_suggestions():
    """Batch-Ablehnung von Tag-Vorschlägen"""
    models = _get_models()
    data = request.get_json() or {}
    ids = data.get("ids", [])
    
    if not ids:
        return jsonify({"error": "ids ist erforderlich"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TagSuggestion'):
                return jsonify({"error": "Feature not available"}), 501
            
            try:
                rejected_count = db.query(models.TagSuggestion).filter(
                    models.TagSuggestion.id.in_(ids),
                    models.TagSuggestion.user_id == user.id
                ).update({"status": "rejected"}, synchronize_session=False)
                
                db.commit()
                
                logger.info(f"Batch rejected {rejected_count} tag suggestions")
                return jsonify({"success": True, "rejected": rejected_count})
            except Exception as e:
                db.rollback()
                logger.error(f"api_batch_reject_suggestions: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Ablehnen"}), 500
    except Exception as e:
        logger.error(f"api_batch_reject_suggestions: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tag-suggestions/batch-approve", methods=["POST"])
@login_required
def api_batch_approve_suggestions():
    """Batch-Akzeptierung von Tag-Vorschlägen"""
    models = _get_models()
    tag_manager = _get_tag_manager()
    data = request.get_json() or {}
    ids = data.get("ids", [])
    
    if not ids:
        return jsonify({"error": "ids ist erforderlich"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TagSuggestion'):
                return jsonify({"error": "Feature not available"}), 501
            
            approved_count = 0
            errors = []
            
            for suggestion_id in ids:
                suggestion = db.query(models.TagSuggestion).filter_by(
                    id=suggestion_id, user_id=user.id, status="pending"
                ).first()
                
                if not suggestion:
                    continue
                
                try:
                    tag = tag_manager.create_tag(
                        db, user.id, suggestion.tag_name,
                        suggestion.color if hasattr(suggestion, 'color') else "#3B82F6"
                    )
                    suggestion.status = "approved"
                    suggestion.approved_tag_id = tag.id
                    approved_count += 1
                except IntegrityError:
                    db.rollback()
                    errors.append(f"Tag '{suggestion.tag_name}' existiert bereits")
                except Exception as e:
                    errors.append(f"Fehler bei '{suggestion.tag_name}': {str(e)}")
            
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"api_batch_approve_suggestions: Commit-Fehler: {e}")
                return jsonify({"error": "Fehler beim Speichern"}), 500
            
            logger.info(f"Batch approved {approved_count} tag suggestions")
            return jsonify({
                "success": True, 
                "approved": approved_count,
                "errors": errors if errors else None
            })
    except Exception as e:
        logger.error(f"api_batch_approve_suggestions: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/tag-suggestions/settings", methods=["GET", "POST"])
@login_required
def api_tag_suggestions_settings():
    """Tag-Suggestion Einstellungen"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if request.method == "POST":
                data = request.get_json() or {}
                
                try:
                    # Speichere Settings in User-Preferences
                    if hasattr(user, 'preferences') and user.preferences:
                        prefs = json.loads(user.preferences) if isinstance(user.preferences, str) else user.preferences
                    else:
                        prefs = {}
                    
                    prefs['tag_suggestions'] = {
                        'auto_suggest': data.get('auto_suggest', True),
                        'min_confidence': data.get('min_confidence', 0.5),
                    }
                    
                    user.preferences = json.dumps(prefs)
                    db.commit()
                    
                    return jsonify({"success": True})
                except Exception as e:
                    db.rollback()
                    logger.error(f"api_tag_suggestions_settings: Save-Fehler: {e}")
                    return jsonify({"error": "Fehler beim Speichern"}), 500
            
            # GET: Lade Settings
            prefs = {}
            if hasattr(user, 'preferences') and user.preferences:
                try:
                    prefs = json.loads(user.preferences) if isinstance(user.preferences, str) else user.preferences
                except:
                    pass
            
            tag_settings = prefs.get('tag_suggestions', {})
            return jsonify({
                "auto_suggest": tag_settings.get('auto_suggest', True),
                "min_confidence": tag_settings.get('min_confidence', 0.5),
            })
    except Exception as e:
        logger.error(f"api_tag_suggestions_settings: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# PHASE-Y / KI-PRIO (Routes 23-33)
# =============================================================================
@api_bp.route("/phase-y/vip-senders", methods=["GET"])
@login_required
def api_get_vip_senders():
    """VIP-Absender laden"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'VIPSender'):
                return jsonify([])
            
            vips = db.query(models.VIPSender).filter_by(user_id=user.id).all()
            return jsonify([{
                "id": v.id,
                "email_pattern": v.email_pattern,
                "priority_boost": v.priority_boost,
                "label": v.label if hasattr(v, 'label') else None,
            } for v in vips])
    except Exception as e:
        logger.error(f"api_get_vip_senders: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/vip-senders", methods=["POST"])
@login_required
def api_add_vip_sender():
    """VIP-Absender hinzufügen"""
    models = _get_models()
    data = request.get_json() or {}
    
    # Input Validation
    try:
        email_pattern = validate_string(data.get("email_pattern"), "Email-Pattern", min_len=1, max_len=255)
        label = validate_string(data.get("label"), "Label", min_len=0, max_len=100, allow_empty=True)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    priority_boost = data.get("priority_boost", 10)
    if not isinstance(priority_boost, (int, float)) or priority_boost < -100 or priority_boost > 100:
        return jsonify({"error": "priority_boost muss zwischen -100 und 100 liegen"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'VIPSender'):
                return jsonify({"error": "Feature nicht verfügbar"}), 501
            
            try:
                vip = models.VIPSender(
                    user_id=user.id,
                    email_pattern=email_pattern,
                    priority_boost=priority_boost,
                )
                if hasattr(models.VIPSender, 'label'):
                    vip.label = label
                    
                db.add(vip)
                db.commit()
                
                logger.info(f"VIP-Sender erstellt: {vip.id}")
                return jsonify({"id": vip.id, "success": True}), 201
                
            except IntegrityError:
                db.rollback()
                return jsonify({"error": "VIP-Sender existiert bereits"}), 409
            except Exception as e:
                db.rollback()
                logger.error(f"api_add_vip_sender: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Erstellen"}), 500
    except Exception as e:
        logger.error(f"api_add_vip_sender: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/vip-senders/<int:vip_id>", methods=["PUT"])
@login_required
def api_update_vip_sender(vip_id):
    """VIP-Absender aktualisieren"""
    models = _get_models()
    data = request.get_json() or {}
    
    # Input Validation (optional fields)
    try:
        email_pattern = validate_string(data.get("email_pattern"), "Email-Pattern", min_len=1, max_len=255) if "email_pattern" in data else None
        label = validate_string(data.get("label"), "Label", min_len=0, max_len=100, allow_empty=True) if "label" in data else None
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    priority_boost = data.get("priority_boost")
    if priority_boost is not None:
        if not isinstance(priority_boost, (int, float)) or priority_boost < -100 or priority_boost > 100:
            return jsonify({"error": "priority_boost muss zwischen -100 und 100 liegen"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'VIPSender'):
                return jsonify({"error": "Nicht gefunden"}), 404
            
            vip = db.query(models.VIPSender).filter_by(id=vip_id, user_id=user.id).first()
            if not vip:
                return jsonify({"error": "Nicht gefunden"}), 404
            
            try:
                if email_pattern is not None:
                    vip.email_pattern = email_pattern
                if priority_boost is not None:
                    vip.priority_boost = priority_boost
                if label is not None and hasattr(vip, 'label'):
                    vip.label = label
                
                db.commit()
                
                logger.info(f"VIP-Sender aktualisiert: {vip_id}")
                return jsonify({"success": True})
                
            except IntegrityError:
                db.rollback()
                return jsonify({"error": "Duplikat-Eintrag"}), 409
            except Exception as e:
                db.rollback()
                logger.error(f"api_update_vip_sender: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Aktualisieren"}), 500
    except Exception as e:
        logger.error(f"api_update_vip_sender: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/vip-senders/<int:vip_id>", methods=["DELETE"])
@login_required
def api_delete_vip_sender(vip_id):
    """VIP-Absender löschen"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'VIPSender'):
                return jsonify({"error": "Nicht gefunden"}), 404
            
            vip = db.query(models.VIPSender).filter_by(id=vip_id, user_id=user.id).first()
            if not vip:
                return jsonify({"error": "Nicht gefunden"}), 404
            
            try:
                db.delete(vip)
                db.commit()
                
                logger.info(f"VIP-Sender gelöscht: {vip_id}")
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_delete_vip_sender: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Löschen"}), 500
    except Exception as e:
        logger.error(f"api_delete_vip_sender: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/keyword-sets", methods=["GET"])
@login_required
def api_get_keyword_sets():
    """Keyword-Sets für Priorisierung laden"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'KeywordSet'):
                return jsonify({"keyword_sets": []})
            
            sets = db.query(models.KeywordSet).filter_by(user_id=user.id).all()
            return jsonify({"keyword_sets": [{
                "id": s.id,
                "name": s.name,
                "keywords": json.loads(s.keywords) if s.keywords else [],
                "priority_boost": s.priority_boost,
            } for s in sets]})
    except Exception as e:
        logger.error(f"api_get_keyword_sets: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/keyword-sets", methods=["POST"])
@login_required
def api_save_keyword_sets():
    """Keyword-Sets speichern"""
    models = _get_models()
    data = request.get_json() or {}
    
    keyword_sets = data.get("keyword_sets", [])
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'KeywordSet'):
                return jsonify({"error": "Feature nicht verfügbar"}), 501
            
            try:
                # Lösche existierende Sets
                db.query(models.KeywordSet).filter_by(user_id=user.id).delete()
                
                # Erstelle neue Sets
                for ks in keyword_sets:
                    try:
                        name = validate_string(ks.get("name"), "Name", min_len=1, max_len=100)
                    except ValueError as e:
                        return jsonify({"error": str(e)}), 400
                    
                    new_set = models.KeywordSet(
                        user_id=user.id,
                        name=name,
                        keywords=json.dumps(ks.get("keywords", [])),
                        priority_boost=ks.get("priority_boost", 0),
                    )
                    db.add(new_set)
                
                db.commit()
                
                logger.info(f"Keyword-Sets gespeichert: {len(keyword_sets)} Sets")
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_save_keyword_sets: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Speichern"}), 500
    except Exception as e:
        logger.error(f"api_save_keyword_sets: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/scoring-config", methods=["GET"])
@login_required
def api_get_scoring_config():
    """Scoring-Konfiguration laden"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            # Lade Scoring-Config aus User-Preferences
            prefs = {}
            if hasattr(user, 'preferences') and user.preferences:
                try:
                    prefs = json.loads(user.preferences) if isinstance(user.preferences, str) else user.preferences
                except:
                    pass
            
            scoring_config = prefs.get('scoring_config', {})
            return jsonify({
                "base_score": scoring_config.get('base_score', 50),
                "recency_weight": scoring_config.get('recency_weight', 1.0),
                "sender_weight": scoring_config.get('sender_weight', 1.0),
                "keyword_weight": scoring_config.get('keyword_weight', 1.0),
            })
    except Exception as e:
        logger.error(f"api_get_scoring_config: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/scoring-config", methods=["POST"])
@login_required
def api_save_scoring_config():
    """Scoring-Konfiguration speichern"""
    models = _get_models()
    data = request.get_json() or {}
    
    # Validierung
    base_score = data.get("base_score", 50)
    recency_weight = data.get("recency_weight", 1.0)
    sender_weight = data.get("sender_weight", 1.0)
    keyword_weight = data.get("keyword_weight", 1.0)
    
    if not isinstance(base_score, (int, float)) or base_score < 0 or base_score > 100:
        return jsonify({"error": "base_score muss zwischen 0 und 100 liegen"}), 400
    
    for name, val in [("recency_weight", recency_weight), ("sender_weight", sender_weight), ("keyword_weight", keyword_weight)]:
        if not isinstance(val, (int, float)) or val < 0 or val > 10:
            return jsonify({"error": f"{name} muss zwischen 0 und 10 liegen"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            try:
                prefs = {}
                if hasattr(user, 'preferences') and user.preferences:
                    try:
                        prefs = json.loads(user.preferences) if isinstance(user.preferences, str) else user.preferences
                    except:
                        pass
                
                prefs['scoring_config'] = {
                    'base_score': base_score,
                    'recency_weight': recency_weight,
                    'sender_weight': sender_weight,
                    'keyword_weight': keyword_weight,
                }
                
                user.preferences = json.dumps(prefs)
                db.commit()
                
                logger.info(f"Scoring-Config für User {user.id} gespeichert")
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_save_scoring_config: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Speichern"}), 500
    except Exception as e:
        logger.error(f"api_save_scoring_config: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/user-domains", methods=["GET"])
@login_required
def api_get_user_domains():
    """User-Domains für Internal-Detection laden"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'UserDomain'):
                return jsonify({"domains": []})
            
            domains = db.query(models.UserDomain).filter_by(user_id=user.id).all()
            return jsonify({"domains": [{
                "id": d.id,
                "domain": d.domain,
            } for d in domains]})
    except Exception as e:
        logger.error(f"api_get_user_domains: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/user-domains", methods=["POST"])
@login_required
def api_add_user_domain():
    """User-Domain hinzufügen"""
    models = _get_models()
    data = request.get_json() or {}
    
    try:
        domain = validate_string(data.get("domain"), "Domain", min_len=3, max_len=255)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'UserDomain'):
                return jsonify({"error": "Feature nicht verfügbar"}), 501
            
            try:
                ud = models.UserDomain(
                    user_id=user.id,
                    domain=domain.lower(),
                )
                db.add(ud)
                db.commit()
                
                logger.info(f"User-Domain erstellt: {ud.id}")
                return jsonify({"id": ud.id, "success": True}), 201
            except IntegrityError:
                db.rollback()
                return jsonify({"error": "Domain existiert bereits"}), 409
            except Exception as e:
                db.rollback()
                logger.error(f"api_add_user_domain: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Erstellen"}), 500
    except Exception as e:
        logger.error(f"api_add_user_domain: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/phase-y/user-domains/<int:domain_id>", methods=["DELETE"])
@login_required
def api_delete_user_domain(domain_id):
    """User-Domain löschen"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'UserDomain'):
                return jsonify({"error": "Nicht gefunden"}), 404
            
            ud = db.query(models.UserDomain).filter_by(id=domain_id, user_id=user.id).first()
            if not ud:
                return jsonify({"error": "Nicht gefunden"}), 404
            
            try:
                db.delete(ud)
                db.commit()
                
                logger.info(f"User-Domain gelöscht: {domain_id}")
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_delete_user_domain: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Löschen"}), 500
    except Exception as e:
        logger.error(f"api_delete_user_domain: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# SEARCH & EMBEDDINGS (Routes 34-36)
# =============================================================================
@api_bp.route("/search/semantic", methods=["GET"])
@login_required
def api_semantic_search():
    """Semantische Email-Suche via Embeddings"""
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 10)), 100)  # Cap at 100
    
    if not query:
        return jsonify({"results": []})
    
    if not validate_string(query, max_len=500):
        return jsonify({"error": "Query too long (max 500)"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            # TODO: Embedding-basierte Suche
            return jsonify({"results": [], "query": query})
    except Exception as e:
        logger.error(f"api_semantic_search: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/embeddings/stats", methods=["GET"])
@login_required
def api_embeddings_stats():
    """Embedding-Statistiken"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            total = db.query(models.ProcessedEmail).join(models.RawEmail).join(models.MailAccount).filter(
                models.MailAccount.user_id == user.id
            ).count()
            
            with_embedding = db.query(models.ProcessedEmail).join(models.RawEmail).join(models.MailAccount).filter(
                models.MailAccount.user_id == user.id,
                models.ProcessedEmail.embedding_vector.isnot(None)
            ).count()
            
            return jsonify({
                "total_emails": total,
                "with_embedding": with_embedding,
                "coverage": round(with_embedding / total * 100, 1) if total > 0 else 0,
            })
    except Exception as e:
        logger.error(f"api_embeddings_stats: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/batch-reprocess-embeddings", methods=["POST"])
@login_required
def api_batch_reprocess_embeddings():
    """
    Batch-Reprocess: Regeneriert Embeddings für ALLE Emails (async mit Progress)
    
    Use Case: User wechselt Embedding-Model (z.B. all-minilm → bge-large)
    → Alle Emails müssen neu embedded werden für konsistente Semantic Search!
    
    Returns job_id für Progress-Tracking
    """
    try:
        models = importlib.import_module(".02_models")
    except ImportError:
        return jsonify({"error": "Models not available"}), 500
    
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"success": False, "error": "Master-Key nicht verfügbar"}), 401
        
        # Hole aktuelles Embedding-Model aus Settings
        provider_embedding = (user.preferred_embedding_provider or "ollama").lower()
        model_embedding = user.preferred_embedding_model or "all-minilm:22m"
        
        # Enqueue async job
        try:
            job_queue = importlib.import_module("src.14_background_jobs")
            job_id = job_queue.enqueue_batch_reprocess_job(
                user_id=user.id,
                master_key=master_key,
                provider=provider_embedding,
                model=model_embedding
            )
        except (ImportError, AttributeError) as e:
            logger.warning(f"Job-Queue nicht verfügbar: {e}")
            return jsonify({
                "success": False,
                "error": "Background-Jobs nicht verfügbar"
            }), 503
        
        return jsonify({
            "success": True,
            "status": "queued",
            "job_id": job_id,
            "message": "Batch-Reprocess gestartet"
        }), 200
        
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Batch-Reprocess enqueue failed: {e}")
        return jsonify({
            "success": False,
            "error": f"Batch-Reprocess fehlgeschlagen: {str(e)}"
        }), 500
    finally:
        db.close()


# =============================================================================
# REPLY-STYLES (Routes 37-42)
# =============================================================================
@api_bp.route("/reply-tones", methods=["GET"])
@login_required
def api_get_reply_tones():
    """Verfügbare Antwort-Tonalitäten"""
    return jsonify([
        {"key": "formal", "label": "Formell", "description": "Geschäftlicher, höflicher Ton"},
        {"key": "casual", "label": "Locker", "description": "Freundlicher, informeller Ton"},
        {"key": "friendly", "label": "Freundlich", "description": "Warm und zugänglich"},
        {"key": "concise", "label": "Prägnant", "description": "Kurz und auf den Punkt"},
    ])


@api_bp.route("/reply-styles", methods=["GET"])
@login_required
def api_get_reply_styles():
    """User-definierte Antwort-Stile"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'ReplyStyle'):
                return jsonify([])
            
            styles = db.query(models.ReplyStyle).filter_by(user_id=user.id).all()
            return jsonify([{
                "key": s.key,
                "name": s.name,
                "template": s.template,
            } for s in styles])
    except Exception as e:
        logger.error(f"api_get_reply_styles: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/reply-styles/<style_key>", methods=["GET"])
@login_required
def api_get_reply_style(style_key):
    """Einzelnen Reply-Style laden"""
    models = _get_models()
    
    # Validate input
    if not validate_string(style_key, max_len=50):
        return jsonify({"error": "Invalid style key"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'ReplyStyle'):
                return jsonify({"error": "Not found"}), 404
            
            style = db.query(models.ReplyStyle).filter_by(
                user_id=user.id, key=style_key
            ).first()
            
            if not style:
                return jsonify({"error": "Not found"}), 404
            
            return jsonify({
                "key": style.key,
                "name": style.name,
                "template": style.template,
            })
    except Exception as e:
        logger.error(f"api_get_reply_style: Fehler bei '{style_key}': {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/reply-styles/<style_key>", methods=["PUT"])
@login_required
def api_update_reply_style(style_key):
    """Reply-Style aktualisieren"""
    models = _get_models()
    data = request.get_json() or {}
    
    # Validate input
    if not validate_string(style_key, max_len=50):
        return jsonify({"error": "Invalid style key"}), 400
    
    name = data.get("name", "").strip()
    template = data.get("template", "")
    
    if name and not validate_string(name, max_len=100):
        return jsonify({"error": "Style name too long (max 100)"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'ReplyStyle'):
                return jsonify({"error": "Not found"}), 404
            
            style = db.query(models.ReplyStyle).filter_by(
                user_id=user.id, key=style_key
            ).first()
            
            if not style:
                # Create new
                style = models.ReplyStyle(
                    user_id=user.id,
                    key=style_key,
                    name=name or style_key,
                    template=template,
                )
                db.add(style)
            else:
                if name:
                    style.name = name
                if "template" in data:
                    style.template = template
            
            try:
                db.commit()
                return jsonify({"success": True})
            except IntegrityError:
                db.rollback()
                logger.warning(f"api_update_reply_style: Duplicate key '{style_key}'")
                return jsonify({"error": "Style key already exists"}), 409
            except Exception as e:
                db.rollback()
                logger.error(f"api_update_reply_style: Commit-Fehler: {e}")
                return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"api_update_reply_style: Fehler bei '{style_key}': {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/reply-styles/<style_key>", methods=["DELETE"])
@login_required
def api_delete_reply_style(style_key):
    """Reply-Style löschen"""
    models = _get_models()
    
    # Validate input
    if not validate_string(style_key, max_len=50):
        return jsonify({"error": "Invalid style key"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'ReplyStyle'):
                return jsonify({"error": "Not found"}), 404
            
            style = db.query(models.ReplyStyle).filter_by(
                user_id=user.id, key=style_key
            ).first()
            
            if style:
                db.delete(style)
                try:
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.error(f"api_delete_reply_style: Commit-Fehler: {e}")
                    return jsonify({"error": "Database error"}), 500
            
            return jsonify({"success": True})
    except Exception as e:
        logger.error(f"api_delete_reply_style: Fehler bei '{style_key}': {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/reply-styles/preview", methods=["POST"])
@login_required
def api_preview_reply_style():
    """Preview eines Reply-Styles"""
    data = request.get_json() or {}
    template = data.get("template", "")
    sample_email = data.get("sample_email", "")
    
    # TODO: AI-basierte Preview-Generierung
    return jsonify({
        "preview": f"[Preview not implemented]\n\nTemplate: {template[:100]}...",
    })


# =============================================================================
# RULES API (Routes 43-50)
# =============================================================================
@api_bp.route("/rules", methods=["GET"])
@login_required
def api_get_rules():
    """Alle Auto-Rules laden"""
    AutoRulesEngine = _get_auto_rules()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            engine = AutoRulesEngine(db, user.id)
            rules = engine.get_rules()
            return jsonify([r.to_dict() for r in rules])
    except Exception as e:
        logger.error(f"api_get_rules: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules", methods=["POST"])
@login_required
def api_create_rule():
    """Neue Auto-Rule erstellen"""
    AutoRulesEngine = _get_auto_rules()
    data = request.get_json() or {}
    
    # Validate input
    name = data.get("name", "").strip()
    if not validate_string(name, max_len=100):
        return jsonify({"error": "Rule name required (max 100 chars)"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            engine = AutoRulesEngine(db, user.id)
            
            try:
                rule = engine.create_rule(
                    name=name,
                    conditions=data.get("conditions", {}),
                    actions=data.get("actions", {}),
                    priority=data.get("priority", 0),
                )
                return jsonify(rule.to_dict()), 201
            except ValueError as e:
                logger.warning(f"api_create_rule: Validation error: {e}")
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                db.rollback()
                logger.error(f"api_create_rule: Fehler beim Erstellen: {e}")
                return jsonify({"error": "Failed to create rule"}), 500
    except Exception as e:
        logger.error(f"api_create_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/<int:rule_id>", methods=["PUT"])
@login_required
def api_update_rule(rule_id):
    """Auto-Rule aktualisieren"""
    AutoRulesEngine = _get_auto_rules()
    data = request.get_json() or {}
    
    # Validate input
    if "name" in data:
        name = data.get("name", "").strip()
        if not validate_string(name, max_len=100):
            return jsonify({"error": "Rule name too long (max 100)"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            engine = AutoRulesEngine(db, user.id)
            
            try:
                rule = engine.update_rule(rule_id, data)
                if not rule:
                    return jsonify({"error": "Not found"}), 404
                return jsonify(rule.to_dict())
            except ValueError as e:
                logger.warning(f"api_update_rule: Validation error: {e}")
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                db.rollback()
                logger.error(f"api_update_rule: Fehler beim Update: {e}")
                return jsonify({"error": "Failed to update rule"}), 500
    except Exception as e:
        logger.error(f"api_update_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/<int:rule_id>", methods=["DELETE"])
@login_required
def api_delete_rule(rule_id):
    """Auto-Rule löschen"""
    AutoRulesEngine = _get_auto_rules()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            engine = AutoRulesEngine(db, user.id)
            
            try:
                success = engine.delete_rule(rule_id)
                if not success:
                    return jsonify({"error": "Not found"}), 404
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_delete_rule: Fehler beim Löschen: {e}")
                return jsonify({"error": "Failed to delete rule"}), 500
    except Exception as e:
        logger.error(f"api_delete_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/<int:rule_id>/test", methods=["POST"])
@login_required
def api_test_rule(rule_id):
    """Testet Rule gegen Sample-Emails"""
    AutoRulesEngine = _get_auto_rules()
    data = request.get_json() or {}
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            engine = AutoRulesEngine(db, user.id)
            
            try:
                result = engine.test_rule(rule_id, limit=data.get("limit", 10))
                return jsonify(result)
            except Exception as e:
                logger.error(f"api_test_rule: Fehler beim Testen: {e}")
                return jsonify({"error": "Failed to test rule"}), 500
    except Exception as e:
        logger.error(f"api_test_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/apply", methods=["POST"])
@login_required
def api_apply_rules():
    """Wendet alle aktiven Rules auf unverarbeitete Emails an"""
    AutoRulesEngine = _get_auto_rules()
    data = request.get_json() or {}
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            engine = AutoRulesEngine(db, user.id)
            
            try:
                result = engine.apply_all_rules(
                    account_id=data.get("account_id"),
                    limit=data.get("limit", 100),
                )
                return jsonify(result)
            except Exception as e:
                db.rollback()
                logger.error(f"api_apply_rules: Fehler beim Anwenden: {e}")
                return jsonify({"error": "Failed to apply rules"}), 500
    except Exception as e:
        logger.error(f"api_apply_rules: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/templates", methods=["GET"])
@login_required
def api_get_rule_templates():
    """Vordefinierte Rule-Templates"""
    return jsonify([
        {"name": "newsletter", "description": "Newsletter automatisch taggen"},
        {"name": "important_sender", "description": "Wichtige Absender priorisieren"},
        {"name": "spam_filter", "description": "Spam-Erkennung"},
    ])


@api_bp.route("/rules/templates/<template_name>", methods=["POST"])
@login_required
def api_apply_rule_template(template_name):
    """Wendet Rule-Template an"""
    AutoRulesEngine = _get_auto_rules()
    
    # Validate input
    if not validate_string(template_name, max_len=50):
        return jsonify({"error": "Invalid template name"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            engine = AutoRulesEngine(db, user.id)
            
            try:
                rule = engine.apply_template(template_name)
                return jsonify(rule.to_dict()), 201
            except ValueError as e:
                logger.warning(f"api_apply_rule_template: Unknown template '{template_name}'")
                return jsonify({"error": str(e)}), 400
            except Exception as e:
                db.rollback()
                logger.error(f"api_apply_rule_template: Fehler: {e}")
                return jsonify({"error": "Failed to apply template"}), 500
    except Exception as e:
        logger.error(f"api_apply_rule_template: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# ACCOUNTS & MODELS (Routes 51-55)
# =============================================================================
@api_bp.route("/accounts", methods=["GET"])
@login_required
def api_get_accounts():
    """Alle Mail-Accounts des Users"""
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()
            
            master_key = session.get("master_key")
            result = []
            
            for acc in accounts:
                account_data = {
                    "id": acc.id,
                    "name": acc.name,
                    "auth_type": acc.auth_type,
                }
                
                if master_key and acc.encrypted_imap_username:
                    try:
                        account_data["email"] = encryption.CredentialManager.decrypt_email_address(
                            acc.encrypted_imap_username, master_key
                        )
                    except Exception:
                        account_data["email"] = None
                
                result.append(account_data)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"api_get_accounts: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/models/<provider>", methods=["GET"])
@login_required
def api_get_models(provider):
    """Verfügbare Models für einen Provider"""
    # Validate input
    if not validate_string(provider, max_len=50):
        return jsonify({"error": "Invalid provider"}), 400
    
    # Hardcoded fallback - echte Implementation würde Provider abfragen
    if provider.lower() == "ollama":
        return jsonify([
            {"name": "llama3.2:1b", "size": "1B"},
            {"name": "llama3.2:3b", "size": "3B"},
            {"name": "mistral:7b", "size": "7B"},
        ])
    
    return jsonify([])


@api_bp.route("/available-models/<provider>", methods=["GET"])
@login_required
def api_available_models(provider):
    """Live-Abfrage verfügbarer Models"""
    # Validate input
    if not validate_string(provider, max_len=50):
        return jsonify({"error": "Invalid provider"}), 400
    
    # TODO: Echte Provider-Abfrage
    return api_get_models(provider)


@api_bp.route("/available-providers", methods=["GET"])
@login_required
def api_available_providers():
    """Verfügbare AI-Provider"""
    return jsonify([
        {"key": "ollama", "name": "Ollama (Local)", "available": True},
        {"key": "openai", "name": "OpenAI", "available": False},
        {"key": "anthropic", "name": "Anthropic", "available": False},
    ])


@api_bp.route("/training-stats", methods=["GET"])
@login_required
def api_training_stats():
    """Training-Statistiken"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            total_emails = db.query(models.ProcessedEmail).join(models.RawEmail).join(models.MailAccount).filter(
                models.MailAccount.user_id == user.id
            ).count()
            
            tagged_emails = db.query(models.ProcessedEmail).join(models.RawEmail).join(models.MailAccount).filter(
                models.MailAccount.user_id == user.id,
                models.ProcessedEmail.tags.any()
            ).count()
            
            return jsonify({
                "total_emails": total_emails,
                "tagged_emails": tagged_emails,
                "training_ready": tagged_emails >= 10,
            })
    except Exception as e:
        logger.error(f"api_training_stats: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# IMAP (Route 56)
# =============================================================================
@api_bp.route("/imap-diagnostics/<int:account_id>", methods=["POST"])
@login_required
def api_imap_diagnostics(account_id):
    """API: Run IMAP diagnostics for a specific account"""
    models = _get_models()
    encryption = _get_encryption()
    
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        
        # Lade Account
        account = db.query(models.MailAccount).filter_by(
            id=account_id, user_id=user.id
        ).first()
        
        if not account:
            return jsonify({"success": False, "error": "Account nicht gefunden"}), 404
        
        if account.auth_type != "imap":
            return jsonify({"success": False, "error": "Nur IMAP-Accounts unterstützt"}), 400
        
        # Entschlüssele Credentials
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({
                "success": False,
                "error": "Session abgelaufen - bitte erneut anmelden"
            }), 401
        
        try:
            imap_server = encryption.CredentialManager.decrypt_server(
                account.encrypted_imap_server, master_key
            )
            imap_username = encryption.CredentialManager.decrypt_email_address(
                account.encrypted_imap_username, master_key
            )
            imap_password = encryption.CredentialManager.decrypt_imap_password(
                account.encrypted_imap_password, master_key
            )
        except Exception as e:
            logger.error(f"Fehler beim Entschlüsseln der Credentials: {e}")
            return jsonify({
                "success": False,
                "error": "Fehler beim Entschlüsseln der Credentials"
            }), 500
        
        # Run Diagnostics
        try:
            # Check for subscribed_only parameter
            subscribed_only = False
            try:
                if request.args.get("subscribed_only"):
                    subscribed_only = request.args.get("subscribed_only").lower() in ("true", "1", "yes")
                elif request.is_json:
                    json_data = request.get_json(silent=True) or {}
                    subscribed_only = json_data.get("subscribed_only", False)
            except Exception as param_error:
                logger.debug(f"Parameter parsing error (using default): {param_error}")
                subscribed_only = False
            
            try:
                imap_diag_mod = importlib.import_module("src.imap_diagnostics")
            except ImportError:
                return jsonify({
                    "success": False,
                    "error": "IMAP-Diagnostics-Modul nicht verfügbar"
                }), 503
            
            diagnostics = imap_diag_mod.IMAPDiagnostics(
                host=imap_server,
                port=account.imap_port or 993,
                username=imap_username,
                password=imap_password,
                timeout=120,
                ssl=(account.imap_encryption == "SSL"),
            )
            
            # Folder-Parameter für Test 12
            target_folder = None
            if request.is_json:
                json_data = request.get_json(silent=True) or {}
                target_folder = json_data.get("folder_name", None)
                logger.info(f"📁 Test 12 folder selection: {target_folder or 'ALL folders'}")
            
            result = diagnostics.run_diagnostics(
                subscribed_only=subscribed_only,
                account_id=account_id,
                session=db,
                folder_name=target_folder
            )
            
            return jsonify({"success": True, "diagnostics": result}), 200
        
        except TimeoutError as e:
            logger.error(f"IMAP Diagnostics Timeout: {e}")
            return jsonify({
                "success": False,
                "error": "Verbindungs-Timeout: Server antwortet zu langsam."
            }), 504
        except Exception as e:
            logger.error(f"IMAP Diagnostics Fehler: {e}")
            return jsonify({
                "success": False,
                "error": f"Diagnostics fehlgeschlagen: {str(e)}"
            }), 500
    
    finally:
        db.close()


# =============================================================================
# TRUSTED-SENDERS (Routes 57-61)
# =============================================================================
@api_bp.route("/trusted-senders", methods=["GET"])
@login_required
def api_get_trusted_senders():
    """Trusted Senders laden"""
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TrustedSender'):
                return jsonify([])
            
            senders = db.query(models.TrustedSender).filter_by(user_id=user.id).all()
            master_key = session.get("master_key")
            
            result = []
            for s in senders:
                sender_data = {
                    "id": s.id,
                    "trust_level": s.trust_level if hasattr(s, 'trust_level') else "full",
                }
                
                if master_key and hasattr(s, 'encrypted_email'):
                    try:
                        sender_data["email"] = encryption.EmailDataManager.decrypt_email_sender(
                            s.encrypted_email, master_key
                        )
                    except Exception:
                        sender_data["email"] = "[encrypted]"
                
                result.append(sender_data)
            
            return jsonify(result)
    except Exception as e:
        logger.error(f"api_get_trusted_senders: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/trusted-senders", methods=["POST"])
@login_required
def api_add_trusted_sender():
    """Trusted Sender hinzufügen"""
    models = _get_models()
    encryption = _get_encryption()
    data = request.get_json() or {}
    
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Email required"}), 400
    
    if not validate_string(email, max_len=255):
        return jsonify({"error": "Email too long (max 255)"}), 400
    
    trust_level = data.get("trust_level", "full")
    if trust_level not in ["full", "partial", "low"]:
        return jsonify({"error": "Invalid trust level"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TrustedSender'):
                return jsonify({"error": "Feature not available"}), 501
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Session expired"}), 401
            
            sender = models.TrustedSender(
                user_id=user.id,
                encrypted_email=encryption.EmailDataManager.encrypt_email_sender(email, master_key),
                trust_level=trust_level,
            )
            db.add(sender)
            
            try:
                db.commit()
                return jsonify({"id": sender.id}), 201
            except IntegrityError:
                db.rollback()
                logger.warning(f"api_add_trusted_sender: Duplicate email for user {user.id}")
                return jsonify({"error": "Sender already exists"}), 409
            except Exception as e:
                db.rollback()
                logger.error(f"api_add_trusted_sender: Commit-Fehler: {e}")
                return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"api_add_trusted_sender: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/trusted-senders/<int:sender_id>", methods=["PATCH"])
@login_required
def api_update_trusted_sender(sender_id):
    """Trusted Sender aktualisieren"""
    models = _get_models()
    data = request.get_json() or {}
    
    # Validate input
    trust_level = data.get("trust_level")
    if trust_level and trust_level not in ["full", "partial", "low"]:
        return jsonify({"error": "Invalid trust level"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TrustedSender'):
                return jsonify({"error": "Not found"}), 404
            
            sender = db.query(models.TrustedSender).filter_by(
                id=sender_id, user_id=user.id
            ).first()
            
            if not sender:
                return jsonify({"error": "Not found"}), 404
            
            if trust_level:
                sender.trust_level = trust_level
            
            try:
                db.commit()
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_update_trusted_sender: Commit-Fehler: {e}")
                return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"api_update_trusted_sender: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/trusted-senders/<int:sender_id>", methods=["DELETE"])
@login_required
def api_delete_trusted_sender(sender_id):
    """Trusted Sender löschen"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'TrustedSender'):
                return jsonify({"error": "Not found"}), 404
            
            sender = db.query(models.TrustedSender).filter_by(
                id=sender_id, user_id=user.id
            ).first()
            
            if sender:
                db.delete(sender)
                try:
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.error(f"api_delete_trusted_sender: Commit-Fehler: {e}")
                    return jsonify({"error": "Database error"}), 500
            
            return jsonify({"success": True})
    except Exception as e:
        logger.error(f"api_delete_trusted_sender: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/trusted-senders/suggestions", methods=["GET"])
@login_required
def api_get_trusted_sender_suggestions():
    """Vorschläge für Trusted Senders basierend auf Email-Historie"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            # TODO: Analyse der häufigsten Absender
            return jsonify({"suggestions": []})
    except Exception as e:
        logger.error(f"api_get_trusted_sender_suggestions: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# URGENCY-BOOSTER (Routes 62-65)
# =============================================================================
@api_bp.route("/settings/urgency-booster", methods=["GET"])
@login_required
def api_get_urgency_booster():
    """Urgency-Booster Einstellungen laden"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            return jsonify({
                "enabled": getattr(user, 'urgency_booster_enabled', False),
                "boost_factor": getattr(user, 'urgency_boost_factor', 1.5),
            })
    except Exception as e:
        logger.error(f"api_get_urgency_booster: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/settings/urgency-booster", methods=["POST"])
@login_required
def api_save_urgency_booster():
    """Urgency-Booster Einstellungen speichern"""
    data = request.get_json() or {}
    
    # Validate input
    boost_factor = data.get("boost_factor", 1.5)
    if not isinstance(boost_factor, (int, float)) or boost_factor < 1.0 or boost_factor > 5.0:
        return jsonify({"error": "Invalid boost factor (1.0-5.0)"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if hasattr(user, 'urgency_booster_enabled'):
                user.urgency_booster_enabled = bool(data.get("enabled", False))
            if hasattr(user, 'urgency_boost_factor'):
                user.urgency_boost_factor = boost_factor
            
            try:
                db.commit()
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_save_urgency_booster: Commit-Fehler: {e}")
                return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"api_save_urgency_booster: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/accounts/urgency-booster-settings", methods=["GET"])
@login_required
def api_get_urgency_booster_settings():
    """Account-spezifische Urgency-Booster Settings"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()
            
            return jsonify([{
                "account_id": a.id,
                "account_name": a.name,
                "urgency_enabled": getattr(a, 'urgency_booster_enabled', False),
            } for a in accounts])
    except Exception as e:
        logger.error(f"api_get_urgency_booster_settings: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/accounts/<int:account_id>/urgency-booster", methods=["POST"])
@login_required
def api_save_account_urgency_booster(account_id):
    """Account-spezifische Urgency-Booster Settings speichern"""
    models = _get_models()
    data = request.get_json() or {}
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            account = db.query(models.MailAccount).filter_by(
                id=account_id, user_id=user.id
            ).first()
            
            if not account:
                return jsonify({"error": "Account not found"}), 404
            
            if hasattr(account, 'urgency_booster_enabled'):
                account.urgency_booster_enabled = bool(data.get("enabled", False))
            
            try:
                db.commit()
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_save_account_urgency_booster: Commit-Fehler: {e}")
                return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"api_save_account_urgency_booster: Fehler für Account {account_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# Route 66: /scan-account-senders/<id> POST (IMAP Sender Scan)
# =============================================================================
def check_scan_rate_limit(user_id: int) -> tuple:
    """
    Prüft ob User sein Rate-Limit für IMAP-Scans überschritten hat.
    
    Returns:
        (allowed: bool, seconds_remaining: int)
    """
    current_time = time.time()
    last_scan = _last_scan_time.get(user_id)
    
    if last_scan is None:
        # Erster Scan
        _last_scan_time[user_id] = current_time
        return (True, 0)
    
    elapsed = current_time - last_scan
    
    if elapsed < SCAN_COOLDOWN_SECONDS:
        seconds_remaining = int(SCAN_COOLDOWN_SECONDS - elapsed)
        return (False, seconds_remaining)
    
    # Cooldown abgelaufen
    _last_scan_time[user_id] = current_time
    return (True, 0)


@api_bp.route("/scan-account-senders/<int:account_id>", methods=["POST"])
@login_required
def api_scan_account_senders(account_id):
    """
    Scannt Mail-Account nach Absendern (nur IMAP-Header, kein Full-Fetch).
    
    Security:
        - Account-Ownership validiert (CRITICAL)
        - Concurrent-Scan Prevention
        - Rate-Limiting (60s Cooldown)
        - CSRF-Token required
    
    POST Body:
    {
        "folder": "INBOX",  // default: INBOX
        "limit": 1000       // default: 1000 (Max für Timeout-Prevention)
    }
    
    Returns:
        {
            "success": true,
            "senders": [{"email": str, "name": str, "count": int, "suggested_type": str}, ...],
            "total_senders": int,
            "total_emails": int,
            "scanned_emails": int,
            "limited": bool
        }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            'success': False,
            'error': 'Nicht authentifiziert'
        }), 401
    
    # CRITICAL: Account-Ownership validieren
    db = get_db_session()
    try:
        try:
            models = importlib.import_module(".02_models")
        except ImportError:
            return jsonify({"error": "Models not available"}), 500
        
        try:
            encryption = importlib.import_module(".08_encryption")
        except ImportError:
            return jsonify({"error": "Encryption not available"}), 500
        
        account = db.query(models.MailAccount).filter_by(
            id=account_id,
            user_id=current_user.id  # ✅ User darf nur eigene Accounts scannen
        ).first()
        
        if not account:
            logger.warning(f"Unauthorized scan attempt: account_id={account_id}, user_id={current_user.id}")
            return jsonify({
                'success': False,
                'error': 'Account nicht gefunden oder keine Berechtigung'
            }), 404
        
        # Rate-Limiting prüfen
        allowed, seconds_remaining = check_scan_rate_limit(current_user.id)
        if not allowed:
            return jsonify({
                'success': False,
                'error': f'Rate-Limit erreicht. Bitte warte noch {seconds_remaining} Sekunden.',
                'seconds_remaining': seconds_remaining
            }), 429  # HTTP 429 Too Many Requests
        
        # Concurrent-Scan Prevention
        if account_id in _active_scans:
            return jsonify({
                'success': False,
                'error': 'Scan läuft bereits für diesen Account. Bitte warten.'
            }), 409  # HTTP 409 Conflict
        
        # Request-Body parsen
        data = request.get_json() or {}
        folder = data.get('folder', 'INBOX')
        limit = data.get('limit', 1000)
        
        # Limit validieren
        if not isinstance(limit, int) or limit < 1 or limit > 5000:
            return jsonify({
                'success': False,
                'error': 'Limit muss zwischen 1 und 5000 liegen'
            }), 400
        
        # Credentials entschlüsseln
        try:
            imap_server = encryption.EmailDataManager.decrypt_email_sender(
                account.encrypted_imap_server, master_key
            )
            imap_username = encryption.EmailDataManager.decrypt_email_sender(
                account.encrypted_imap_username, master_key
            )
            imap_password = encryption.EmailDataManager.decrypt_email_sender(
                account.encrypted_imap_password, master_key
            )
        except Exception as e:
            logger.error(f"Decryption error for account {account_id}: {e}")
            return jsonify({
                'success': False,
                'error': 'Fehler beim Entschlüsseln der Credentials'
            }), 500
        
        # Scan-Lock setzen
        _active_scans.add(account_id)
        
        try:
            # IMAP-Scan durchführen
            from src.services.imap_sender_scanner import scan_account_senders
            
            result = scan_account_senders(
                imap_server=imap_server,
                imap_username=imap_username,
                imap_password=imap_password,
                folder=folder,
                limit=limit
            )
            
            return jsonify(result)
        
        finally:
            # Scan-Lock immer freigeben
            _active_scans.discard(account_id)
    
    except Exception as e:
        logger.error(f"api_scan_account_senders: Fehler für Account {account_id}: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        db.close()


# =============================================================================
# Route 67: /trusted-senders/bulk-add POST (Bulk Whitelist)
# =============================================================================
@api_bp.route("/trusted-senders/bulk-add", methods=["POST"])
@login_required
def api_bulk_add_trusted_senders():
    """
    Fügt mehrere Absender zur Whitelist hinzu (Bulk-Insert).
    
    Duplikat-Handling:
        - Existierende Sender werden übersprungen (Skip + Warning)
        - Transactional mit Rollback bei kritischen Fehlern
        - Detailed Error-Reporting
    
    POST Body:
    {
        "senders": [
            {"pattern": "boss@firma.de", "type": "exact", "label": "Chef"},
            ...
        ],
        "account_id": 1  // optional: null = global
    }
    
    Returns:
        {
            "success": true,
            "added": int,
            "skipped": int,
            "details": {
                "added": [str, ...],
                "skipped": [{"pattern": str, "reason": str}, ...]
            }
        }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            'success': False,
            'error': 'Nicht authentifiziert'
        }), 401
    
    db = get_db_session()
    try:
        try:
            models = importlib.import_module(".02_models")
        except ImportError:
            return jsonify({"error": "Models not available"}), 500
        
        data = request.get_json()
        if not data or 'senders' not in data:
            return jsonify({
                'success': False,
                'error': 'Keine Absender angegeben'
            }), 400
        
        senders = data.get('senders', [])
        account_id = data.get('account_id')
        
        logger.info(f"📥 Bulk-Add Request: {len(senders)} Absender für User {current_user.id}, Account {account_id}")
        
        # Account validieren (falls angegeben)
        if account_id is not None:
            account = db.query(models.MailAccount).filter_by(
                id=account_id,
                user_id=current_user.id  # ✅ Ownership-Check
            ).first()
            
            if not account:
                return jsonify({
                    'success': False,
                    'error': 'Account nicht gefunden oder keine Berechtigung'
                }), 404
        
        added = []
        skipped = []
        
        # Import Service
        try:
            from src.services.trusted_senders import TrustedSenderManager
        except ImportError:
            logger.error("TrustedSenderManager nicht verfügbar")
            return jsonify({"error": "TrustedSenderManager not available"}), 500
        
        # TRANSACTIONAL Bulk-Add
        try:
            for sender_data in senders:
                try:
                    pattern = sender_data.get('pattern', '').strip()
                    pattern_type = sender_data.get('type', 'exact')
                    label = sender_data.get('label', '').strip() or None
                    
                    logger.debug(f"  Processing: {pattern} ({pattern_type})")
                    
                    if not pattern:
                        skipped.append({
                            'pattern': pattern,
                            'reason': 'Leeres Pattern'
                        })
                        continue
                    
                    # Hinzufügen (Duplikat-Check im Service)
                    result = TrustedSenderManager.add_trusted_sender(
                        db=db,
                        user_id=current_user.id,
                        sender_pattern=pattern,
                        pattern_type=pattern_type,
                        label=label,
                        account_id=account_id
                    )
                    
                    if result.get('success'):
                        if result.get('already_exists'):
                            # Duplikat - skippen
                            logger.info(f"  ⚠️  Duplikat: {pattern}")
                            skipped.append({
                                'pattern': pattern,
                                'reason': result.get('message', 'Absender existiert bereits')
                            })
                        else:
                            # Erfolgreich hinzugefügt
                            logger.info(f"  ✅ Hinzugefügt: {pattern}")
                            added.append(pattern)
                    else:
                        # Fehler (z.B. Validierung, Limit)
                        logger.warning(f"  ❌ Fehler für {pattern}: {result.get('error')}")
                        skipped.append({
                            'pattern': pattern,
                            'reason': result.get('error', 'Unbekannter Fehler')
                        })
                        
                except Exception as e:
                    logger.error(f"Bulk-Add Error for {sender_data}: {e}")
                    skipped.append({
                        'pattern': sender_data.get('pattern', 'unknown'),
                        'reason': f"Exception: {str(e)}"
                    })
            
            # Alle erfolgreich → Commit
            db.commit()
            
            logger.info(f"✅ Bulk-Add abgeschlossen: {len(added)} hinzugefügt, {len(skipped)} übersprungen")
            
        except Exception as critical_error:
            # Kritischer Fehler → ROLLBACK alles!
            logger.error(f"CRITICAL: Bulk-Add Transaction failed, rolling back: {critical_error}")
            db.rollback()
            
            return jsonify({
                'success': False,
                'error': f'Kritischer Fehler: {str(critical_error)}. Keine Änderungen wurden gespeichert.'
            }), 500
        
        return jsonify({
            'success': True,
            'added': len(added),
            'skipped': len(skipped),
            'details': {
                'added': added,
                'skipped': skipped
            }
        })
    
    except Exception as e:
        logger.error(f"api_bulk_add_trusted_senders: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        db.close()
