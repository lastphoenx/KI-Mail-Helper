# src/blueprints/api.py
"""API Blueprint - Alle REST-API Endpoints mit /api Prefix.

Routes (67 total) - geordnet nach Funktionsbereich.
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
# LAZY IMPORTS
# =============================================================================
_models = None

def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


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
    """KI-basierte Tag-Vorschläge für eine Email (Phase F.2)"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            # Phase F.2: Nutze Email-Embeddings direkt
            processed = (
                db.query(models.ProcessedEmail)
                .join(models.RawEmail)
                .filter(
                    models.RawEmail.id == raw_email_id,
                    models.RawEmail.mail_account.has(user_id=user.id),
                    models.RawEmail.deleted_at == None
                )
                .first()
            )
            
            if not processed or not processed.raw_email:
                return jsonify({"suggestions": [], "email_id": raw_email_id, "method": "none"}), 200
            
            raw_email = processed.raw_email
            
            try:
                import importlib
                tag_manager_mod = importlib.import_module("src.services.tag_manager")
                
                # Phase F.2: Wenn Email-Embedding vorhanden
                if raw_email.email_embedding:
                    # Bereits zugewiesene Tags holen
                    assigned_tag_ids = [
                        assignment.tag_id 
                        for assignment in db.query(models.EmailTagAssignment)
                        .filter_by(email_id=processed.id).all()
                    ]
                    
                    # Phase F.2 Enhanced: Email-Embedding-basierte Suggestions
                    tag_suggestions = tag_manager_mod.TagManager.suggest_tags_by_email_embedding(
                        db=db,
                        user_id=user.id,
                        email_embedding_bytes=raw_email.email_embedding,
                        top_k=5,
                        min_similarity=None,  # Dynamisch
                        exclude_tag_ids=assigned_tag_ids
                    )
                    
                    suggestions = [
                        {
                            "id": tag.id,
                            "name": tag.name,
                            "color": tag.color,
                            "similarity": round(similarity, 3)
                        }
                        for tag, similarity in tag_suggestions
                    ]
                    
                    return jsonify({
                        "suggestions": suggestions, 
                        "email_id": raw_email_id,
                        "method": "embedding",
                        "embedding_available": True
                    }), 200
                else:
                    # Fallback: Text-basierte Methode
                    suggestions = tag_manager_mod.TagManager.get_tag_suggestions_for_email(
                        db, processed.id, user.id, top_k=5
                    )
                    
                    return jsonify({
                        "suggestions": suggestions, 
                        "email_id": raw_email_id,
                        "method": "text-fallback",
                        "embedding_available": False
                    }), 200
                    
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
            
            tag = db.query(models.EmailTag).filter_by(id=tag_id, user_id=user.id).first()
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
    tag_manager_mod = importlib.import_module("src.services.tag_manager", "src")
    
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
            
            tag = db.query(models.EmailTag).filter_by(id=tag_id, user_id=user.id).first()
            if not tag:
                return jsonify({"error": "Tag nicht gefunden"}), 404
            
            try:
                # Verwende add_negative_example für konsistentes Negative Example
                success = tag_manager_mod.add_negative_example(db, tag_id, processed.id, "ui")
                
                if success:
                    # add_negative_example macht bereits commit
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
    """API: Generiert Antwort-Entwurf auf eine Email - ASYNC via Celery
    
    Request Body:
    {
        "tone": "formal|friendly|brief|decline",
        "provider": "ollama|openai|anthropic",
        "model": "llama3.2|gpt-4o|claude-sonnet",
        "use_anonymization": true|false
    }
    """
    import os
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
            
            # Validiere Email-Zugriff (schneller Check, kein AI-Call!)
            raw_email = db.query(models.RawEmail).filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None
            ).first()
            
            if not raw_email:
                return jsonify({"success": False, "error": "Email nicht gefunden"}), 404
            
            # ═══════════════════════════════════════════════════════════════
            # CELERY PATH (Standard) - Async Processing
            # ═══════════════════════════════════════════════════════════════
            from src.tasks.reply_generation_tasks import generate_reply_draft
            auth = importlib.import_module(".07_auth", "src")
            ServiceTokenManager = auth.ServiceTokenManager
            
            try:
                # Phase 2 Security: ServiceToken erstellen
                _, service_token = ServiceTokenManager.create_token(
                    user_id=user.id,
                    master_key=master_key,
                    session=db,
                    days=1  # Reply-Token nur 1 Tag gültig
                )
                
                # Provider/Model Selection (hier vorab, da Task sie braucht)
                ai_client = _get_ai_client()
                if requested_provider and requested_model:
                    provider = requested_provider.lower()
                    resolved_model = ai_client.resolve_model(provider, requested_model, kind="optimize")
                else:
                    provider = (getattr(user, 'preferred_ai_provider_optimize', None) or 
                               getattr(user, 'preferred_ai_provider', None) or "ollama").lower()
                    optimize_model = getattr(user, 'preferred_ai_model_optimize', None) or getattr(user, 'preferred_ai_model', None)
                    resolved_model = ai_client.resolve_model(provider, optimize_model, kind="optimize")
                
                # Anonymisierungs-Default ermitteln
                if use_anonymization is None:
                    cloud_providers = ["openai", "anthropic", "google"]
                    use_anonymization = provider in cloud_providers
                
                # Task starten (ASYNC!)
                task = generate_reply_draft.delay(
                    user_id=user.id,
                    raw_email_id=raw_email_id,
                    service_token_id=service_token.id,
                    tone=tone,
                    provider=provider,
                    model=resolved_model,
                    use_anonymization=use_anonymization
                )
                
                logger.info(f"✅ Reply Task {task.id} gequeued für Email {raw_email_id} ({provider}/{resolved_model})")
                
                return jsonify({
                    "success": True,
                    "status": "queued",
                    "task_id": task.id,
                    "message": "Entwurf wird generiert..."
                })
                
            except Exception as e:
                logger.error(f"api_generate_reply: Celery-Fehler: {type(e).__name__}: {e}")
                return jsonify({"success": False, "error": "Fehler beim Starten des Generierungs-Tasks"}), 500

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
    """API: Email neu verarbeiten (Phase F.2 Enhanced) - ASYNC via Celery
    
    Regeneriert:
    - Email-Embedding (mit aktuellem Base Model aus Settings)
    - AI-Score + Kategorie
    - Tag-Suggestions (automatisch mit neuem Embedding)
    """
    import os
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
            
            # ═══════════════════════════════════════════════════════════════
            # CELERY PATH (Standard) - Async Processing
            # ═══════════════════════════════════════════════════════════════
            import importlib
            from src.tasks.email_processing_tasks import reprocess_email_base
            auth = importlib.import_module(".07_auth", "src")
            ServiceTokenManager = auth.ServiceTokenManager
            
            try:
                # Phase 2 Security: ServiceToken erstellen
                _, service_token = ServiceTokenManager.create_token(
                    user_id=user.id,
                    master_key=master_key,
                    session=db,
                    days=1  # Reprocess-Token nur 1 Tag gültig
                )
                
                # Task starten (ASYNC!)
                task = reprocess_email_base.delay(
                    user_id=user.id,
                    raw_email_id=raw_email_id,
                    service_token_id=service_token.id
                )
                
                logger.info(f"✅ ReprocessEmail Task {task.id} gequeued für Email {raw_email_id}")
                
                return jsonify({
                    "success": True,
                    "status": "queued",
                    "task_id": task.id,
                    "task_type": "celery",
                    "message": "Email wird neu verarbeitet..."
                })
                
            except Exception as e:
                logger.error(f"api_reprocess_email: Celery-Fehler: {type(e).__name__}: {e}")
                return jsonify({"success": False, "error": "Fehler beim Starten des Tasks"}), 500
            
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
            
            tags = db.query(models.EmailTag).filter_by(user_id=user.id).order_by(models.EmailTag.name).all()
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
            
            tag = db.query(models.EmailTag).filter_by(id=tag_id, user_id=user.id).first()
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
            
            tag = db.query(models.EmailTag).filter_by(id=tag_id, user_id=user.id).first()
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
            
            tag = db.query(models.EmailTag).filter_by(id=tag_id, user_id=user.id).first()
            if not tag:
                return jsonify({"error": "Not found"}), 404
            
            examples = db.query(models.EmailTagNegativeExample).filter_by(
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
            
            if not hasattr(models, 'TagSuggestionQueue'):
                return jsonify([])
            
            suggestions = db.query(models.TagSuggestionQueue).filter_by(
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
            
            if not hasattr(models, 'TagSuggestionQueue'):
                return jsonify({"error": "Feature not available"}), 501
            
            suggestion = db.query(models.TagSuggestionQueue).filter_by(
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
            
            if not hasattr(models, 'TagSuggestionQueue'):
                return jsonify({"error": "Feature not available"}), 501
            
            suggestion = db.query(models.TagSuggestionQueue).filter_by(
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
            
            if not hasattr(models, 'TagSuggestionQueue'):
                return jsonify({"error": "Feature not available"}), 501
            
            suggestion = db.query(models.TagSuggestionQueue).filter_by(
                id=id, user_id=user.id
            ).first()
            
            if not suggestion:
                return jsonify({"error": "Vorschlag nicht gefunden"}), 404
            
            target_tag = db.query(models.EmailTag).filter_by(
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
            
            if not hasattr(models, 'TagSuggestionQueue'):
                return jsonify({"error": "Feature not available"}), 501
            
            try:
                rejected_count = db.query(models.TagSuggestionQueue).filter(
                    models.TagSuggestionQueue.id.in_(ids),
                    models.TagSuggestionQueue.user_id == user.id
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
            
            if not hasattr(models, 'TagSuggestionQueue'):
                return jsonify({"error": "Feature not available"}), 501
            
            approved_count = 0
            errors = []
            
            for suggestion_id in ids:
                suggestion = db.query(models.TagSuggestionQueue).filter_by(
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
                    # Speichere Settings direkt in User-Model-Spalten
                    if "enable_tag_suggestion_queue" in data:
                        user.enable_tag_suggestion_queue = bool(data["enable_tag_suggestion_queue"])
                    if "enable_auto_assignment" in data:
                        user.enable_auto_assignment = bool(data["enable_auto_assignment"])
                    
                    db.commit()
                    
                    logger.info(f"Tag-suggestion settings updated for user {user.id}: queue={user.enable_tag_suggestion_queue}, auto={user.enable_auto_assignment}")
                    return jsonify({"success": True})
                except Exception as e:
                    db.rollback()
                    logger.error(f"api_tag_suggestions_settings: Save-Fehler: {e}")
                    return jsonify({"error": "Fehler beim Speichern"}), 500
            
            # GET: Lade Settings aus User-Model-Spalten
            return jsonify({
                "enable_tag_suggestion_queue": getattr(user, 'enable_tag_suggestion_queue', False) or False,
                "enable_auto_assignment": getattr(user, 'enable_auto_assignment', False) or False,
            })
    except Exception as e:
        logger.error(f"api_tag_suggestions_settings: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/classifier-preferences", methods=["GET", "POST"])
@login_required
def api_classifier_preferences():
    """Classifier-Präferenzen: Personal vs. Global ML-Modell.
    
    GET: Gibt aktuelle Präferenz zurück
    POST: Speichert neue Präferenz {"prefer_personal_classifier": bool}
    """
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if request.method == "POST":
                data = request.get_json() or {}
                
                try:
                    if "prefer_personal_classifier" in data:
                        user.prefer_personal_classifier = bool(data["prefer_personal_classifier"])
                        db.commit()
                        
                        logger.info(
                            f"Classifier preference updated for user {user.id}: "
                            f"prefer_personal={user.prefer_personal_classifier}"
                        )
                        return jsonify({"success": True})
                    else:
                        return jsonify({"error": "prefer_personal_classifier required"}), 400
                except Exception as e:
                    db.rollback()
                    logger.error(f"api_classifier_preferences: Save-Fehler: {e}")
                    return jsonify({"error": "Fehler beim Speichern"}), 500
            
            # GET: Lade Präferenz aus User-Model
            return jsonify({
                "prefer_personal_classifier": getattr(user, 'prefer_personal_classifier', False) or False
            })
    except Exception as e:
        logger.error(f"api_classifier_preferences: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# PHASE-Y / KI-PRIO (Routes 23-33)
# =============================================================================
@api_bp.route("/ki-prio/vip-senders", methods=["GET"])
@login_required
def api_get_vip_senders():
    """VIP-Absender laden"""
    models = _get_models()
    
    try:
        account_id = request.args.get("account_id", type=int)
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if not hasattr(models, 'SpacyVIPSender'):
                return jsonify({"vips": []})
            
            vips = db.query(models.SpacyVIPSender).filter_by(account_id=account_id).all()
            return jsonify({
                "vips": [
                    {
                        "id": v.id,
                        "sender_pattern": v.sender_pattern,
                        "pattern_type": v.pattern_type,
                        "importance_boost": v.importance_boost,
                        "label": v.label,
                        "is_active": v.is_active
                    }
                    for v in vips
                ]
            }), 200
    except Exception as e:
        logger.error(f"api_get_vip_senders: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/ki-prio/vip-senders", methods=["POST"])
@login_required
def api_add_vip_sender():
    """VIP-Absender hinzufügen"""
    models = _get_models()
    data = request.get_json() or {}
    
    # Input Validation
    try:
        account_id = int(data.get("account_id"))
        sender_pattern = validate_string(data.get("sender_pattern"), "Sender Pattern", min_len=1, max_len=255)
        label = validate_string(data.get("label", ""), "Label", min_len=0, max_len=100, allow_empty=True)
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    
    importance_boost = data.get("importance_boost", 3)
    if not isinstance(importance_boost, (int, float)) or importance_boost < 1 or importance_boost > 100:
        return jsonify({"error": "importance_boost muss zwischen 1 und 100 liegen"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if not hasattr(models, 'SpacyVIPSender'):
                return jsonify({"error": "Feature nicht verfügbar"}), 501
            
            try:
                vip = models.SpacyVIPSender(
                    user_id=user.id,
                    account_id=account_id,
                    sender_pattern=sender_pattern,
                    pattern_type=data.get("pattern_type", "exact"),
                    importance_boost=importance_boost,
                    label=label,
                    is_active=data.get("is_active", True),
                )
                    
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


@api_bp.route("/ki-prio/vip-senders/<int:vip_id>", methods=["PUT"])
@login_required
def api_update_vip_sender(vip_id):
    """VIP-Absender aktualisieren"""
    models = _get_models()
    data = request.get_json() or {}
    
    # Input Validation (optional fields)
    try:
        sender_pattern = validate_string(data.get("sender_pattern"), "Sender Pattern", min_len=1, max_len=255) if "sender_pattern" in data else None
        label = validate_string(data.get("label", ""), "Label", min_len=0, max_len=100, allow_empty=True) if "label" in data else None
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    importance_boost = data.get("importance_boost")
    if importance_boost is not None:
        if not isinstance(importance_boost, (int, float)) or importance_boost < 1 or importance_boost > 100:
            return jsonify({"error": "importance_boost muss zwischen 1 und 100 liegen"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'SpacyVIPSender'):
                return jsonify({"error": "Nicht gefunden"}), 404
            
            # Verify ownership through MailAccount
            vip = db.query(models.SpacyVIPSender).join(models.MailAccount).filter(
                models.SpacyVIPSender.id == vip_id,
                models.MailAccount.user_id == user.id
            ).first()
            
            if not vip:
                return jsonify({"error": "Nicht gefunden"}), 404
            
            try:
                if sender_pattern is not None:
                    vip.sender_pattern = sender_pattern
                if importance_boost is not None:
                    vip.importance_boost = importance_boost
                if label is not None:
                    vip.label = label
                if "pattern_type" in data:
                    vip.pattern_type = data["pattern_type"]
                if "is_active" in data:
                    vip.is_active = data["is_active"]
                
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


@api_bp.route("/ki-prio/vip-senders/<int:vip_id>", methods=["DELETE"])
@login_required
def api_delete_vip_sender(vip_id):
    """VIP-Absender löschen"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'SpacyVIPSender'):
                return jsonify({"error": "Nicht gefunden"}), 404
            
            # Verify ownership through MailAccount
            vip = db.query(models.SpacyVIPSender).join(models.MailAccount).filter(
                models.SpacyVIPSender.id == vip_id,
                models.MailAccount.user_id == user.id
            ).first()
            
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


@api_bp.route("/ki-prio/keyword-sets", methods=["GET"])
@login_required
def api_get_keyword_sets():
    """Keyword-Sets für Priorisierung laden"""
    models = _get_models()
    
    try:
        account_id = request.args.get("account_id", type=int)
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if not hasattr(models, 'SpacyKeywordSet'):
                return jsonify({"keyword_sets": []})
            
            sets = db.query(models.SpacyKeywordSet).filter_by(user_id=user.id, account_id=account_id).all()
            
            # Wenn keine Custom-Sets existieren, Default-Sets laden
            if not sets:
                try:
                    spacy_config = importlib.import_module(".services.spacy_config_manager", "src")
                    config_manager = spacy_config.SpacyConfigManager(db)
                    default_sets = config_manager._get_default_keyword_sets()
                    
                    return jsonify({
                        "keyword_sets": [
                            {
                                "id": None,
                                "keyword_set_name": name,
                                "keywords": keywords,
                                "is_active": True,
                                "is_default": True
                            }
                            for name, keywords in default_sets.items()
                        ]
                    }), 200
                except Exception:
                    return jsonify({"keyword_sets": []})
            
            return jsonify({"keyword_sets": [{
                "id": s.id,
                "keyword_set_name": s.set_type,
                "keywords": json.loads(s.keywords_json) if s.keywords_json else [],
                "is_active": s.is_active,
                "is_default": False
            } for s in sets]})
    except Exception as e:
        logger.error(f"api_get_keyword_sets: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/ki-prio/keyword-sets", methods=["POST"])
@login_required
def api_save_keyword_sets():
    """Keyword-Sets speichern"""
    models = _get_models()
    data = request.get_json() or {}
    
    try:
        account_id = int(data.get("account_id"))
    except (ValueError, TypeError):
        return jsonify({"error": "account_id erforderlich"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if not hasattr(models, 'SpacyKeywordSet'):
                return jsonify({"error": "Feature nicht verfügbar"}), 501
            
            try:
                set_type = data.get("keyword_set_name")
                keywords = data.get("keywords", [])
                
                if not set_type:
                    return jsonify({"error": "keyword_set_name erforderlich"}), 400
                
                # Prüfe ob Set bereits existiert
                existing = db.query(models.SpacyKeywordSet).filter_by(
                    user_id=user.id,
                    account_id=account_id,
                    set_type=set_type
                ).first()
                
                if existing:
                    # Update
                    existing.keywords_json = json.dumps(keywords)
                    existing.is_active = data.get("is_active", True)
                    existing.points_per_match = data.get("points_per_match", 2)
                    existing.max_points = data.get("max_points", 4)
                else:
                    # Create
                    new_set = models.SpacyKeywordSet(
                        user_id=user.id,
                        account_id=account_id,
                        set_type=set_type,
                        keywords_json=json.dumps(keywords),
                        is_active=data.get("is_active", True),
                        points_per_match=data.get("points_per_match", 2),
                        max_points=data.get("max_points", 4),
                        is_custom=data.get("is_custom", False)
                    )
                    db.add(new_set)
                
                db.commit()
                
                logger.info(f"Keyword-Set gespeichert: {set_type}")
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_save_keyword_sets: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Speichern"}), 500
    except Exception as e:
        logger.error(f"api_save_keyword_sets: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/ki-prio/scoring-config", methods=["GET"])
@login_required
def api_get_scoring_config():
    """Scoring-Konfiguration laden"""
    models = _get_models()
    
    try:
        account_id = request.args.get("account_id", type=int)
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if not hasattr(models, 'SpacyScoringConfig'):
                # Default-Werte
                try:
                    spacy_config = importlib.import_module(".services.spacy_config_manager", "src")
                    config_manager = spacy_config.SpacyConfigManager(db)
                    default_config = config_manager._get_default_scoring_config()
                    return jsonify({"config": default_config, "is_default": True}), 200
                except Exception:
                    return jsonify({"config": {}, "is_default": True}), 200
            
            config = db.query(models.SpacyScoringConfig).filter_by(account_id=account_id).first()
            
            if not config:
                # Default-Werte
                try:
                    spacy_config = importlib.import_module(".services.spacy_config_manager", "src")
                    config_manager = spacy_config.SpacyConfigManager(db)
                    default_config = config_manager._get_default_scoring_config()
                    return jsonify({"config": default_config, "is_default": True}), 200
                except Exception:
                    return jsonify({
                        "config": {
                            "imperative_weight": 3,
                            "deadline_weight": 4,
                            "keyword_weight": 2,
                            "vip_weight": 3,
                            "question_threshold": 3,
                            "negation_sensitivity": 2,
                            "spacy_weight_initial": 100,
                            "spacy_weight_learning": 30,
                            "spacy_weight_trained": 15
                        },
                        "is_default": True
                    }), 200
            
            return jsonify({
                "config": {
                    "imperative_weight": config.imperative_weight,
                    "deadline_weight": config.deadline_weight,
                    "keyword_weight": config.keyword_weight,
                    "vip_weight": config.vip_weight,
                    "question_threshold": config.question_threshold,
                    "negation_sensitivity": config.negation_sensitivity,
                    "spacy_weight_initial": config.spacy_weight_initial,
                    "spacy_weight_learning": config.spacy_weight_learning,
                    "spacy_weight_trained": config.spacy_weight_trained
                },
                "is_default": False
            }), 200
    except Exception as e:
        logger.error(f"api_get_scoring_config: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/ki-prio/scoring-config", methods=["POST"])
@login_required
def api_save_scoring_config():
    """Scoring-Konfiguration speichern"""
    models = _get_models()
    data = request.get_json() or {}
    
    try:
        account_id = int(data.get("account_id"))
    except (ValueError, TypeError):
        return jsonify({"error": "account_id erforderlich"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if not hasattr(models, 'SpacyScoringConfig'):
                return jsonify({"error": "Feature nicht verfügbar"}), 501
            
            try:
                config = db.query(models.SpacyScoringConfig).filter_by(account_id=account_id).first()
                
                if config:
                    # Update
                    config.imperative_weight = data.get("imperative_weight", config.imperative_weight)
                    config.deadline_weight = data.get("deadline_weight", config.deadline_weight)
                    config.keyword_weight = data.get("keyword_weight", config.keyword_weight)
                    config.vip_weight = data.get("vip_weight", config.vip_weight)
                    config.question_threshold = data.get("question_threshold", config.question_threshold)
                    config.negation_sensitivity = data.get("negation_sensitivity", config.negation_sensitivity)
                    config.spacy_weight_initial = data.get("spacy_weight_initial", config.spacy_weight_initial)
                    config.spacy_weight_learning = data.get("spacy_weight_learning", config.spacy_weight_learning)
                    config.spacy_weight_trained = data.get("spacy_weight_trained", config.spacy_weight_trained)
                else:
                    # Create
                    config = models.SpacyScoringConfig(
                        user_id=user.id,
                        account_id=account_id,
                        imperative_weight=data.get("imperative_weight", 3),
                        deadline_weight=data.get("deadline_weight", 4),
                        keyword_weight=data.get("keyword_weight", 2),
                        vip_weight=data.get("vip_weight", 3),
                        question_threshold=data.get("question_threshold", 3),
                        negation_sensitivity=data.get("negation_sensitivity", 2),
                        spacy_weight_initial=data.get("spacy_weight_initial", 100),
                        spacy_weight_learning=data.get("spacy_weight_learning", 30),
                        spacy_weight_trained=data.get("spacy_weight_trained", 15)
                    )
                    db.add(config)
                
                db.commit()
                
                logger.info(f"Scoring-Config für Account {account_id} gespeichert")
                return jsonify({"success": True})
            except Exception as e:
                db.rollback()
                logger.error(f"api_save_scoring_config: DB-Fehler: {e}")
                return jsonify({"error": "Fehler beim Speichern"}), 500
    except Exception as e:
        logger.error(f"api_save_scoring_config: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/ki-prio/user-domains", methods=["GET"])
@login_required
def api_get_user_domains():
    """User-Domains für Internal-Detection laden"""
    models = _get_models()
    
    try:
        account_id = request.args.get("account_id", type=int)
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if not hasattr(models, 'SpacyUserDomain'):
                return jsonify({"domains": []})
            
            domains = db.query(models.SpacyUserDomain).filter_by(account_id=account_id).all()
            return jsonify({"domains": [{
                "id": d.id,
                "domain": d.domain,
                "is_active": d.is_active
            } for d in domains]})
    except Exception as e:
        logger.error(f"api_get_user_domains: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/ki-prio/user-domains", methods=["POST"])
@login_required
def api_add_user_domain():
    """User-Domain hinzufügen"""
    models = _get_models()
    data = request.get_json() or {}
    
    try:
        account_id = int(data.get("account_id"))
        domain = validate_string(data.get("domain"), "Domain", min_len=3, max_len=255)
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
            if not account:
                return jsonify({"error": "Account nicht gefunden"}), 404
            
            if not hasattr(models, 'SpacyUserDomain'):
                return jsonify({"error": "Feature nicht verfügbar"}), 501
            
            try:
                ud = models.SpacyUserDomain(
                    user_id=user.id,
                    account_id=account_id,
                    domain=domain.lower(),
                    is_active=data.get("is_active", True)
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


@api_bp.route("/ki-prio/user-domains/<int:domain_id>", methods=["DELETE"])
@login_required
def api_delete_user_domain(domain_id):
    """User-Domain löschen"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            if not hasattr(models, 'SpacyUserDomain'):
                return jsonify({"error": "Nicht gefunden"}), 404
            
            # Verify ownership through MailAccount
            ud = db.query(models.SpacyUserDomain).join(models.MailAccount).filter(
                models.SpacyUserDomain.id == domain_id,
                models.MailAccount.user_id == user.id
            ).first()
            
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
    
    try:
        validate_string(query, "query", max_len=500)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
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
    Batch-Reprocess: Regeneriert Embeddings fuer ALLE Emails (async mit Progress)
    
    Use Case: User wechselt Embedding-Model (z.B. all-minilm -> bge-large)
    Alle Emails muessen neu embedded werden fuer konsistente Semantic Search!
    
    Returns job_id fuer Progress-Tracking
    """
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"success": False, "error": "Unauthorized"}), 401
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"success": False, "error": "Master-Key nicht verfügbar"}), 401
            
            # Hole aktuelles Embedding-Model aus Settings
            provider_embedding = (user.preferred_embedding_provider or "ollama").lower()
            model_embedding = user.preferred_embedding_model or "all-minilm:22m"
            
            # Celery: Batch-Reprocess Task
            try:
                from src.tasks.mail_sync_tasks import batch_reprocess_emails
                auth = importlib.import_module(".07_auth", "src")
                ServiceTokenManager = auth.ServiceTokenManager
                
                # Phase 2 Security: ServiceToken erstellen (DEK nicht in Redis!)
                with get_db_session() as token_db:
                    _, service_token = ServiceTokenManager.create_token(
                        user_id=user.id,
                        master_key=master_key,
                        session=token_db,
                        days=1  # Batch-Reprocess-Token nur 1 Tag gültig
                    )
                    service_token_id = service_token.id
                
                # Enqueue Celery Task
                task = batch_reprocess_emails.delay(
                    user_id=user.id,
                    service_token_id=service_token_id,
                    provider=provider_embedding,
                    model=model_embedding
                )
                
                logger.info(f"✅ [CELERY] Batch-reprocess task enqueued: {task.id}")
                
                return jsonify({
                    "success": True,
                    "status": "queued",
                    "task_id": task.id,
                    "message": "Batch-Reprocess gestartet"
                }), 202  # Accepted
                
            except ImportError as e:
                logger.error(f"api_batch_reprocess: Import-Fehler: {e}")
                return jsonify({
                    "success": False,
                    "error": "Batch-Reprocess-Task nicht verfügbar"
                }), 503
            except Exception as e:
                logger.error(f"api_batch_reprocess: Celery-Fehler: {type(e).__name__}: {e}")
                return jsonify({
                    "success": False,
                    "error": "Fehler beim Enqueuen des Batch-Reprocess"
                }), 500
            
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Batch-Reprocess enqueue failed: {e}")
        return jsonify({
            "success": False,
            "error": f"Batch-Reprocess fehlgeschlagen: {str(e)}"
        }), 500


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
    """Holt alle Reply-Style-Settings des Users"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            # Zero-Knowledge: Brauchen master_key zum Entschlüsseln
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key nicht verfügbar"}), 401
            
            from src.services.reply_style_service import ReplyStyleService
            settings = ReplyStyleService.get_user_settings(db, user.id, master_key)
            
            return jsonify(settings)
    except Exception as e:
        logger.error(f"api_get_reply_styles: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/reply-styles/<style_key>", methods=["GET"])
@login_required
def api_get_reply_style(style_key):
    """Holt effektive Settings fuer einen spezifischen Stil (Merged: Defaults -> Global -> Style-Specific)"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key nicht verfügbar"}), 401
            
            from src.services.reply_style_service import ReplyStyleService
            try:
                settings = ReplyStyleService.get_effective_settings(
                    db, user.id, style_key, master_key
                )
                return jsonify({"style_key": style_key, "settings": settings})
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"api_get_reply_style: Fehler bei '{style_key}': {type(e).__name__}: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/reply-styles/<style_key>", methods=["PUT"])
@login_required
def api_update_reply_style(style_key):
    """Speichert Settings für einen Stil"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key nicht verfügbar"}), 401
            
            data = request.get_json() or {}
            
            from src.services.reply_style_service import ReplyStyleService
            try:
                setting = ReplyStyleService.save_settings(
                    db, user.id, style_key, data, master_key
                )
                return jsonify({
                    "success": True,
                    "style_key": style_key,
                    "message": f"Einstellungen für '{style_key}' gespeichert"
                })
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"api_update_reply_style: Fehler bei '{style_key}': {type(e).__name__}: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/reply-styles/<style_key>", methods=["DELETE"])
@login_required
def api_delete_reply_style(style_key):
    """Löscht Style-spezifische Überschreibung (setzt auf Global zurück)"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            from src.services.reply_style_service import ReplyStyleService
            success = ReplyStyleService.delete_style_override(db, user.id, style_key)
            
            if success:
                return jsonify({
                    "success": True,
                    "message": f"Überschreibung für '{style_key}' gelöscht, nutze jetzt Global"
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "Konnte nicht löschen (evtl. 'global' oder nicht vorhanden)"
                }), 400
    except Exception as e:
        logger.error(f"api_delete_reply_style: Fehler bei '{style_key}': {type(e).__name__}: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/reply-styles/preview", methods=["POST"])
@login_required
def api_preview_reply_style():
    """Generiert eine Vorschau mit den aktuellen Settings"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key nicht verfügbar"}), 401
            
            data = request.get_json() or {}
            style_key = data.get("style_key", "formal")
            sample_sender = data.get("sample_sender", "Max Mustermann <max@example.com>")
            
            from src.services.reply_style_service import ReplyStyleService
            
            try:
                settings = ReplyStyleService.get_effective_settings(
                    db, user.id, style_key, master_key
                )
            except ValueError:
                return jsonify({"error": "Invalid style_key"}), 400
            
            # Einfache Vorschau bauen (ohne KI)
            preview_parts = []
            
            # Anrede
            salutation = settings.get("salutation", "Hallo")
            # Extrahiere Name aus Sender
            name = sample_sender.split("<")[0].strip() if "<" in sample_sender else sample_sender
            if name:
                preview_parts.append(f"{salutation} {name},")
            else:
                preview_parts.append(f"{salutation},")
            
            preview_parts.append("")
            preview_parts.append("[Ihr Antwort-Text wird hier erscheinen...]")
            preview_parts.append("")
            
            # Gruss
            closing = settings.get("closing", "Grüsse")
            preview_parts.append(closing)
            
            # Signatur
            if settings.get("signature_enabled") and settings.get("signature_text"):
                preview_parts.append(settings["signature_text"])
            
            return jsonify({
                "preview_text": "\n".join(preview_parts),
                "settings_used": settings
            })
    except Exception as e:
        logger.error(f"api_preview_reply_style: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# RULES API (Routes 43-50)
# =============================================================================
@api_bp.route("/rules", methods=["GET"])
@login_required
def api_get_rules():
    """Alle Auto-Rules laden"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            rules = db.query(models.AutoRule).filter_by(user_id=user.id).order_by(
                models.AutoRule.priority.asc()
            ).all()
            
            return jsonify({
                "rules": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "description": r.description,
                        "is_active": r.is_active,
                        "priority": r.priority,
                        "conditions": r.conditions,
                        "actions": r.actions,
                        "enable_learning": r.enable_learning if hasattr(r, 'enable_learning') else False,
                        "times_triggered": r.times_triggered if hasattr(r, 'times_triggered') else 0,
                        "last_triggered_at": r.last_triggered_at.isoformat() if hasattr(r, 'last_triggered_at') and r.last_triggered_at else None,
                        "created_at": r.created_at.isoformat() if r.created_at else None
                    }
                    for r in rules
                ]
            }), 200
    except Exception as e:
        logger.error(f"api_get_rules: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules", methods=["POST"])
@login_required
def api_create_rule():
    """Neue Auto-Rule erstellen"""
    models = _get_models()
    data = request.get_json() or {}
    
    # Validate input
    name = data.get("name", "").strip()
    try:
        validate_string(name, "name", max_len=100)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    conditions = data.get("conditions", {})
    actions = data.get("actions", {})
    
    if not conditions:
        return jsonify({"error": "Mindestens eine Bedingung erforderlich"}), 400
    
    if not actions:
        return jsonify({"error": "Mindestens eine Aktion erforderlich"}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            # Regel erstellen
            rule = models.AutoRule(
                user_id=user.id,
                name=name,
                description=data.get("description"),
                priority=data.get("priority", 100),
                is_active=data.get("is_active", True),
                conditions=conditions,
                actions=actions,
                enable_learning=data.get("enable_learning", False)
            )
            
            db.add(rule)
            db.commit()
            db.refresh(rule)
            
            logger.info(f"✅ Regel erstellt: '{rule.name}' (ID: {rule.id}) für User {user.id}")
            
            return jsonify({
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "is_active": rule.is_active,
                "priority": rule.priority,
                "conditions": rule.conditions,
                "actions": rule.actions,
                "enable_learning": rule.enable_learning,
                "created_at": rule.created_at.isoformat() if rule.created_at else None
            }), 201
    except Exception as e:
        logger.error(f"api_create_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/<int:rule_id>", methods=["PUT"])
@login_required
def api_update_rule(rule_id):
    """Auto-Rule aktualisieren"""
    models = _get_models()
    data = request.get_json() or {}
    
    # Validate input
    if "name" in data:
        name = data.get("name", "").strip()
        try:
            validate_string(name, "name", max_len=100)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            rule = db.query(models.AutoRule).filter_by(
                id=rule_id,
                user_id=user.id
            ).first()
            
            if not rule:
                return jsonify({"error": "Regel nicht gefunden"}), 404
            
            # Update fields
            if "name" in data:
                rule.name = data["name"]
            if "description" in data:
                rule.description = data["description"]
            if "priority" in data:
                rule.priority = data["priority"]
            if "is_active" in data:
                rule.is_active = data["is_active"]
            if "conditions" in data:
                rule.conditions = data["conditions"]
            if "actions" in data:
                rule.actions = data["actions"]
            if "enable_learning" in data:
                rule.enable_learning = bool(data["enable_learning"])
            
            db.commit()
            db.refresh(rule)
            
            logger.info(f"✅ Regel aktualisiert: '{rule.name}' (ID: {rule.id})")
            
            return jsonify({
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "is_active": rule.is_active,
                "priority": rule.priority,
                "conditions": rule.conditions,
                "actions": rule.actions,
                "enable_learning": rule.enable_learning if hasattr(rule, 'enable_learning') else False,
                "updated_at": rule.updated_at.isoformat() if rule.updated_at else None
            })
    except Exception as e:
        logger.error(f"api_update_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/<int:rule_id>", methods=["DELETE"])
@login_required
def api_delete_rule(rule_id):
    """Auto-Rule löschen"""
    models = _get_models()
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            rule = db.query(models.AutoRule).filter_by(
                id=rule_id,
                user_id=user.id
            ).first()
            
            if not rule:
                return jsonify({"error": "Regel nicht gefunden"}), 404
            
            rule_name = rule.name
            db.delete(rule)
            db.commit()
            
            logger.info(f"🗑️  Regel gelöscht: '{rule_name}' (ID: {rule_id})")
            
            return jsonify({"success": True})
    except Exception as e:
        logger.error(f"api_delete_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/<int:rule_id>/test", methods=["POST"])
@login_required
def api_test_rule(rule_id):
    """Testet Rule gegen Sample-Emails"""
    models = _get_models()
    AutoRulesEngine = _get_auto_rules()
    data = request.get_json() or {}
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            rule = db.query(models.AutoRule).filter_by(
                id=rule_id,
                user_id=user.id
            ).first()
            
            if not rule:
                return jsonify({"error": "Regel nicht gefunden"}), 404
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key nicht verfügbar"}), 401
            
            engine = AutoRulesEngine(user.id, master_key, db)
            matches = []
            email_id = data.get("email_id")
            
            if email_id:
                # Teste eine spezifische E-Mail
                results = engine.process_email(email_id, dry_run=True, rule_id=rule_id)
                for result in results:
                    matches.append({
                        "email_id": result.email_id,
                        "matched": result.success,
                        "actions_would_execute": result.actions_executed
                    })
            else:
                # Teste gegen die letzten 20 E-Mails
                recent_emails = db.query(models.RawEmail).filter_by(
                    user_id=user.id,
                    deleted_at=None
                ).order_by(models.RawEmail.received_at.desc()).limit(20).all()
                
                for email in recent_emails:
                    results = engine.process_email(email.id, dry_run=True, rule_id=rule_id)
                    if results and results[0].success:
                        matches.append({
                            "email_id": email.id,
                            "matched": True,
                            "actions_would_execute": results[0].actions_executed
                        })
            
            logger.info(f"🧪 Regel '{rule.name}' getestet: {len(matches)} Matches")
            
            return jsonify({
                "success": True,
                "matches": matches,
                "total_tested": 1 if email_id else 20,
                "total_matches": len(matches),
                "rule_name": rule.name
            })
    except Exception as e:
        logger.error(f"api_test_rule: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/apply", methods=["POST"])
@login_required
def api_apply_rules():
    """Wendet alle aktiven Rules auf unverarbeitete Emails an"""
    models = _get_models()
    AutoRulesEngine = _get_auto_rules()
    data = request.get_json() or {}
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master-Key nicht verfügbar"}), 401
            
            engine = AutoRulesEngine(user.id, master_key, db)
            email_ids = data.get("email_ids", [])
            
            stats = {
                "emails_processed": 0,
                "rules_triggered": 0,
                "actions_executed": 0,
                "errors": 0
            }
            
            if email_ids:
                # Spezifische E-Mails verarbeiten
                for email_id in email_ids:
                    try:
                        results = engine.process_email(email_id, dry_run=False)
                        
                        for result in results:
                            if result.success:
                                stats["rules_triggered"] += 1
                                stats["actions_executed"] += len(result.actions_executed)
                            else:
                                stats["errors"] += 1
                        
                        stats["emails_processed"] += 1
                    except Exception as e:
                        logger.error(f"Fehler bei E-Mail {email_id}: {e}")
                        stats["errors"] += 1
            else:
                # Alle unverarbeiteten E-Mails
                unprocessed = db.query(models.RawEmail).filter_by(
                    user_id=user.id,
                    deleted_at=None
                ).limit(100).all()
                
                for email in unprocessed:
                    try:
                        results = engine.process_email(email.id, dry_run=False)
                        
                        for result in results:
                            if result.success:
                                stats["rules_triggered"] += 1
                                stats["actions_executed"] += len(result.actions_executed)
                        
                        stats["emails_processed"] += 1
                    except Exception as e:
                        logger.error(f"Fehler bei E-Mail {email.id}: {e}")
                        stats["errors"] += 1
            
            logger.info(f"✅ Regeln angewendet: {stats}")
            return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.error(f"api_apply_rules: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/rules/templates", methods=["GET"])
@login_required
def api_get_rule_templates():
    """API: Vordefinierte Regel-Templates abrufen"""
    try:
        from src.auto_rules_engine import RULE_TEMPLATES
        
        return jsonify({
            "templates": [
                {
                    "id": key,
                    "name": template["name"],
                    "description": template["description"],
                    "priority": template.get("priority", 100),
                    "conditions": template["conditions"],
                    "actions": template["actions"]
                }
                for key, template in RULE_TEMPLATES.items()
            ]
        }), 200
    
    except Exception as e:
        logger.error(f"Fehler beim Laden der Templates: {e}")
        return jsonify({"templates": []}), 500


@api_bp.route("/rules/templates/<template_name>", methods=["POST"])
@login_required
def api_apply_rule_template(template_name):
    """Wendet Rule-Template an"""
    # Validate input
    try:
        validate_string(template_name, "template_name", max_len=50)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            data = request.get_json() or {}
            overrides = data.get("overrides", {})
            
            from src.auto_rules_engine import create_rule_from_template
            
            rule = create_rule_from_template(
                db_session=db,
                user_id=user.id,
                template_name=template_name,
                overrides=overrides
            )
            
            if not rule:
                return jsonify({"error": "Template nicht gefunden"}), 404
            
            return jsonify({
                "success": True,
                "rule": {
                    "id": rule.id,
                    "name": rule.name,
                    "description": rule.description,
                    "is_active": rule.is_active,
                    "priority": rule.priority,
                    "conditions": rule.conditions,
                    "actions": rule.actions
                }
            }), 201
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
            
            return jsonify({"accounts": result}), 200
    except Exception as e:
        logger.error(f"api_get_accounts: Fehler: {type(e).__name__}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route("/models/<provider>", methods=["GET"])
@login_required
def api_get_models(provider):
    """API: Dynamische Model-Abfrage für Provider."""
    # Validate input
    try:
        validate_string(provider, "provider", max_len=50)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    try:
        import importlib
        model_discovery = importlib.import_module('.04_model_discovery', 'src')
        
        # Modelle dynamisch von Provider abrufen
        models_list = model_discovery.get_available_models(provider)
        
        return jsonify({
            "provider": provider,
            "models": models_list
        }), 200
        
    except Exception as e:
        logger.error(f"Model discovery failed for {provider}: {e}")
        return jsonify({
            "provider": provider,
            "models": [],
            "error": str(e)
        }), 500


@api_bp.route("/available-models/<provider>", methods=["GET"])
@login_required
def api_available_models(provider):
    """Live-Abfrage verfügbarer Models"""
    # Validate input
    try:
        validate_string(provider, "provider", max_len=50)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
    # Nutze die gleiche Logik wie api_get_models
    return api_get_models(provider)


@api_bp.route("/available-providers", methods=["GET"])
@login_required
def api_available_providers():
    """Gibt verfügbare KI-Provider zurück (basierend auf API-Keys)"""
    try:
        import importlib
        provider_utils = importlib.import_module('.15_provider_utils', 'src')
        providers = provider_utils.get_available_providers()
        return jsonify({"providers": providers})
    except Exception as e:
        logger.error(f"Fehler beim Abrufen von Providern: {e}")
        return jsonify({"error": "Provider konnten nicht abgerufen werden"}), 500


@api_bp.route("/training-stats", methods=["GET"])
@login_required
def api_training_stats():
    """Gibt Statistiken über Training für UI-Dashboard."""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            
            ProcessedEmail = models.ProcessedEmail
            
            total_emails = db.query(ProcessedEmail).count()
            corrections_count = (
                db.query(ProcessedEmail)
                .filter(ProcessedEmail.user_override_dringlichkeit != None)
                .count()
            )
            
            last_correction = (
                db.query(ProcessedEmail)
                .filter(ProcessedEmail.correction_timestamp != None)
                .order_by(ProcessedEmail.correction_timestamp.desc())
                .first()
            )
            
            last_correction_date = None
            if last_correction and last_correction.correction_timestamp:
                last_correction_date = last_correction.correction_timestamp.isoformat()
            
            from pathlib import Path
            classifier_dir = Path(__file__).resolve().parent.parent / "classifiers"
            trained_models = []
            if classifier_dir.exists():
                for f in classifier_dir.glob("*_clf.pkl"):
                    model_name = f.stem.replace("_clf", "")
                    trained_models.append(
                        {"name": model_name, "exists": True, "modified": f.stat().st_mtime}
                    )
            
            return jsonify({
                "total_emails": total_emails,
                "corrections_count": corrections_count,
                "trained_models_count": len(trained_models),
                "trained_models": trained_models,
                "last_correction_date": last_correction_date,
                "ready_for_training": corrections_count >= 5,
            }), 200
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
    
    with get_db_session() as db:
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


# =============================================================================
# TRUSTED-SENDERS (Routes 57-61)
# =============================================================================
@api_bp.route("/trusted-senders", methods=["GET"])
@login_required
def api_get_trusted_senders():
    """List trusted senders for current user, optionally filtered by account_id"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return {"success": False, "error": "Unauthorized"}, 401
            
            # Get optional account_id parameter
            account_id = request.args.get('account_id', type=int)
            
            # Build query
            query = db.query(models.TrustedSender).filter_by(user_id=user.id)
            
            if account_id:
                # For specific account: include account-specific AND global (account_id=NULL)
                query = query.filter(
                    (models.TrustedSender.account_id == account_id) |
                    (models.TrustedSender.account_id.is_(None))
                )
            
            trusted_senders = query.all()
            
            senders = []
            for ts in trusted_senders:
                senders.append({
                    "id": ts.id,
                    "sender_pattern": ts.sender_pattern,
                    "pattern_type": ts.pattern_type,
                    "label": ts.label or "",
                    "use_urgency_booster": ts.use_urgency_booster,
                    "added_at": ts.added_at.isoformat() if ts.added_at else None,
                    "last_seen_at": ts.last_seen_at.isoformat() if ts.last_seen_at else None,
                    "email_count": ts.email_count or 0,
                    "account_id": ts.account_id
                })
            
            return {"success": True, "senders": senders}, 200
    except Exception as e:
        logger.error(f"api_get_trusted_senders: Fehler: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}, 500


@api_bp.route("/trusted-senders", methods=["POST"])
@login_required
def api_add_trusted_sender():
    """Add a new trusted sender"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return {"success": False, "error": "Unauthorized"}, 401
            
            data = request.get_json()
            if not data:
                return {"success": False, "error": "No JSON data"}, 400
            
            sender_pattern = (data.get("sender_pattern") or "").strip()
            pattern_type = (data.get("pattern_type") or "exact").strip()
            label = (data.get("label") or "").strip() or None
            use_urgency_booster = data.get("use_urgency_booster", True)
            account_id = data.get("account_id")
            
            if not sender_pattern:
                return {"success": False, "error": "sender_pattern erforderlich"}, 400
            
            # Normalisiere pattern_type
            if not pattern_type or pattern_type not in ["exact", "email_domain", "domain"]:
                pattern_type = "exact"
            
            # Use TrustedSenderManager to add with validation
            import importlib
            trusted_senders_mod = importlib.import_module(".services.trusted_senders", "src")
            try:
                ts = trusted_senders_mod.TrustedSenderManager.add_trusted_sender(
                    db=db,
                    user_id=user.id,
                    sender_pattern=sender_pattern,
                    account_id=account_id,
                    pattern_type=pattern_type,
                    label=label
                )
                if ts and ts.get('success'):
                    response = {
                        "success": True,
                        "sender": {
                            "id": ts['id'],
                            "sender_pattern": ts['sender_pattern'],
                            "pattern_type": ts['pattern_type'],
                            "label": ts['label']
                        }
                    }
                    # Pass through already_exists flag if present
                    if ts.get('already_exists'):
                        response['already_exists'] = True
                        response['message'] = ts.get('message', 'Sender bereits in Liste')
                    return response, 201
                elif ts and not ts.get('success'):
                    return {"success": False, "error": ts.get('error', 'Unknown error')}, 400
                else:
                    return {"success": False, "error": "Failed to add trusted sender"}, 400
            except ValueError as e:
                return {"success": False, "error": str(e)}, 400
    except Exception as e:
        logger.error(f"api_add_trusted_sender: Fehler: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}, 500


@api_bp.route("/trusted-senders/<int:sender_id>", methods=["PATCH"])
@login_required
def api_update_trusted_sender(sender_id):
    """Update a trusted sender (toggle use_urgency_booster flag)"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return {"success": False, "error": "Unauthorized"}, 401
            
            account_id = request.args.get('account_id', type=int)
            
            # Query with account filter if provided
            query = db.query(models.TrustedSender).filter_by(
                id=sender_id,
                user_id=user.id
            )
            
            if account_id:
                # Verify sender belongs to this account or is global
                query = query.filter(
                    (models.TrustedSender.account_id == account_id) |
                    (models.TrustedSender.account_id.is_(None))
                )
            
            ts = query.first()
            
            if not ts:
                return {"success": False, "error": "Trusted sender not found"}, 404
            
            data = request.get_json()
            if not data:
                return {"success": False, "error": "No JSON data"}, 400
            
            # Update use_urgency_booster flag
            if "use_urgency_booster" in data:
                ts.use_urgency_booster = bool(data["use_urgency_booster"])
            
            if "label" in data:
                label = data.get("label")
                ts.label = label.strip() if label else None
            
            if "pattern_type" in data:
                valid_types = ["exact", "email_domain", "domain"]
                new_type = data.get("pattern_type", "").strip().lower()
                if new_type in valid_types:
                    ts.pattern_type = new_type
                else:
                    return {"success": False, "error": f"Invalid pattern_type: {new_type}"}, 400
            
            db.commit()
            return {
                "success": True,
                "sender": {
                    "id": ts.id,
                    "sender_pattern": ts.sender_pattern,
                    "pattern_type": ts.pattern_type,
                    "label": ts.label,
                    "use_urgency_booster": ts.use_urgency_booster,
                    "account_id": ts.account_id
                }
            }, 200
    except Exception as e:
        logger.error(f"api_update_trusted_sender: Fehler: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}, 500


@api_bp.route("/trusted-senders/<int:sender_id>", methods=["DELETE"])
@login_required
def api_delete_trusted_sender(sender_id):
    """Delete a trusted sender"""
    models = _get_models()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return {"success": False, "error": "Unauthorized"}, 401
            
            account_id = request.args.get('account_id', type=int)
            
            # Query with account filter if provided
            query = db.query(models.TrustedSender).filter_by(
                id=sender_id,
                user_id=user.id
            )
            
            if account_id:
                # Verify sender belongs to this account or is global
                query = query.filter(
                    (models.TrustedSender.account_id == account_id) |
                    (models.TrustedSender.account_id.is_(None))
                )
            
            ts = query.first()
            
            if not ts:
                return {"success": False, "error": "Trusted sender not found"}, 404
            
            db.delete(ts)
            db.commit()
            return {"success": True}, 200
    except Exception as e:
        logger.error(f"api_delete_trusted_sender: Fehler: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}, 500


@api_bp.route("/trusted-senders/suggestions", methods=["GET"])
@login_required
def api_get_trusted_sender_suggestions():
    """Get suggestions for new trusted senders based on email history"""
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return {"success": False, "error": "Unauthorized"}, 401
            
            import importlib
            trusted_senders_mod = importlib.import_module(".services.trusted_senders", "src")
            
            # Get master key from Flask session
            master_key = session.get("master_key")
            if not master_key:
                return {"success": False, "error": "Master key not available"}, 400
            
            # Get optional account_id parameter
            account_id = request.args.get('account_id', type=int)
            
            # Get suggestions
            suggestions = trusted_senders_mod.TrustedSenderManager.get_suggestions_from_emails(
                db=db,
                user_id=user.id,
                master_key=master_key,
                limit=10,
                account_id=account_id
            )
            
            return {
                "success": True,
                "suggestions": suggestions,
                "account_id": account_id
            }, 200
    except Exception as e:
        logger.error(f"api_get_trusted_sender_suggestions: Fehler: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}, 500


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
    """Get UrgencyBooster settings for all user accounts"""
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return {"success": False, "error": "Unauthorized"}, 401
            
            accounts = db.query(models.MailAccount).filter_by(user_id=user.id).order_by(models.MailAccount.name).all()
            
            # Get master key for decryption
            master_key = session.get("master_key")
            
            accounts_data = []
            for account in accounts:
                # Decrypt IMAP username for display
                decrypted_email = None
                if master_key and account.encrypted_imap_username:
                    try:
                        decrypted_email = encryption.EmailDataManager.decrypt_email_sender(
                            account.encrypted_imap_username, master_key
                        )
                    except Exception as e:
                        logger.warning(f"Could not decrypt email for account {account.id}: {e}")
                
                accounts_data.append({
                    'id': account.id,
                    'name': account.name,
                    'decrypted_imap_username': decrypted_email,
                    'urgency_booster_enabled': getattr(account, 'urgency_booster_enabled', True),
                    'enable_ai_analysis_on_fetch': getattr(account, 'enable_ai_analysis_on_fetch', True),
                    'anonymize_with_spacy': getattr(account, 'anonymize_with_spacy', False),
                    'ai_analysis_anon_enabled': getattr(account, 'ai_analysis_anon_enabled', False),
                    'ai_analysis_original_enabled': getattr(account, 'ai_analysis_original_enabled', False),
                    'effective_ai_mode': account.effective_ai_mode if hasattr(account, 'effective_ai_mode') else 'llm_original'
                })
            
            return {
                "success": True,
                "accounts": accounts_data
            }, 200
    except Exception as e:
        logger.error(f"api_get_urgency_booster_settings: Fehler: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}, 500


@api_bp.route("/accounts/<int:account_id>/urgency-booster", methods=["POST"])
@login_required
def api_save_account_urgency_booster(account_id):
    """Set UrgencyBooster and Analysis Modes for a specific account (Phase Y2)"""
    models = _get_models()
    data = request.get_json() or {}
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return {"success": False, "error": "Unauthorized"}, 401
            
            account = db.query(models.MailAccount).filter_by(
                id=account_id, user_id=user.id
            ).first()
            
            if not account:
                return {"success": False, "error": "Account nicht gefunden"}, 404
            
            # ===== PHASE Y2: ANALYSIS MODES =====
            # Legacy-Support (alte Toggles)
            if "urgency_booster_enabled" in data:
                account.urgency_booster_enabled = bool(data["urgency_booster_enabled"])
            if "enable_ai_analysis_on_fetch" in data:
                account.enable_ai_analysis_on_fetch = bool(data["enable_ai_analysis_on_fetch"])
            
            # Phase Y2: Neue Toggle-Struktur
            if "anonymize_with_spacy" in data:
                account.anonymize_with_spacy = bool(data["anonymize_with_spacy"])
            
            if "analysis_mode" in data:
                # Radio-Button Modus: Setze alle Toggles zurück, aktiviere nur gewählten
                mode = data["analysis_mode"]
                
                account.urgency_booster_enabled = False
                account.ai_analysis_anon_enabled = False
                account.ai_analysis_original_enabled = False
                
                if mode == "spacy_booster":
                    account.urgency_booster_enabled = True
                elif mode == "llm_anon":
                    if not account.anonymize_with_spacy:
                        logger.warning("llm_anon gewählt aber anonymize_with_spacy=False, Fallback auf none")
                    else:
                        account.ai_analysis_anon_enabled = True
                elif mode == "llm_original":
                    account.ai_analysis_original_enabled = True
                
                # Legacy-Support: Synchronisiere enable_ai_analysis_on_fetch
                account.enable_ai_analysis_on_fetch = (
                    account.ai_analysis_original_enabled or account.ai_analysis_anon_enabled
                )
            
            db.commit()
            
            logger.info(f"Account {account_id} settings: effective_mode={account.effective_ai_mode}")
            return {
                "success": True,
                "effective_mode": account.effective_ai_mode,
                "urgency_booster_enabled": account.urgency_booster_enabled,
                "enable_ai_analysis_on_fetch": account.enable_ai_analysis_on_fetch,
                "anonymize_with_spacy": account.anonymize_with_spacy,
                "ai_analysis_anon_enabled": getattr(account, 'ai_analysis_anon_enabled', False),
                "ai_analysis_original_enabled": getattr(account, 'ai_analysis_original_enabled', False)
            }, 200
    except Exception as e:
        logger.error(f"api_save_account_urgency_booster: Fehler für Account {account_id}: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}, 500


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
        "limit": 1000       // default: 1000 (Max fuer Timeout-Prevention)
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
    
    models = _get_models()
    
    # CRITICAL: Account-Ownership validieren
    with get_db_session() as db:
        try:
            encryption = importlib.import_module(".08_encryption", "src")
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
        
        except Exception as e:
            logger.error(f"api_scan_account_senders: Fehler für Account {account_id}: {type(e).__name__}: {e}")
            return jsonify({"error": "Internal server error"}), 500
        
        finally:
            # Scan-Lock immer freigeben
            _active_scans.discard(account_id)


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
    
    models = _get_models()
    
    try:
        data = request.get_json()
        if not data or 'senders' not in data:
            return jsonify({
                'success': False,
                'error': 'Keine Absender angegeben'
            }), 400
        
        senders = data.get('senders', [])
        account_id = data.get('account_id')
        
        logger.info(f"📥 Bulk-Add Request: {len(senders)} Absender für User {current_user.id}, Account {account_id}")
        
        with get_db_session() as db:
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
                
                # Alle erfolgreich -> Commit
                db.commit()
                
                logger.info(f"✅ Bulk-Add abgeschlossen: {len(added)} hinzugefügt, {len(skipped)} übersprungen")
                
            except Exception as critical_error:
                # Kritischer Fehler -> ROLLBACK alles!
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


# =============================================================================
# Route 68: /auto-fetch-mails GET (Background Mail Fetch)
# =============================================================================
@api_bp.route("/auto-fetch-mails", methods=["GET"])
@login_required
def api_auto_fetch_mails():
    """
    Startet automatischen Mail-Fetch für alle User-Accounts im Hintergrund.
    
    Wird vom Frontend alle 10 Minuten aufgerufen (wenn User Setting aktiviert).
    Nutzt die EXAKT GLEICHE Logik wie der "Abrufen"-Button pro Account!
    
    Security:
        - Nur während aktiver Session (master_key in Session)
        - ServiceToken-Pattern (kein master_key in Redis)
        - User muss enable_auto_fetch=True haben
    
    Returns:
        {
            "success": true,
            "tasks_queued": int,
            "accounts": [account_ids]
        }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            'success': False,
            'error': 'Unauthorized - keine aktive Session'
        }), 401
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return jsonify({'success': False, 'error': 'User nicht gefunden'}), 404
            
            # Prüfe ob User Auto-Fetch aktiviert hat
            if not user.enable_auto_fetch:
                return jsonify({
                    'success': False,
                    'error': 'Auto-Fetch ist deaktiviert',
                    'hint': 'Aktiviere Auto-Fetch in den Einstellungen'
                }), 403
            
            # Lade alle aktiven Mail-Accounts des Users
            models = _get_models()
            accounts = db.query(models.MailAccount).filter_by(
                user_id=user.id
            ).all()
            
            if not accounts:
                return jsonify({
                    'success': True,
                    'tasks_queued': 0,
                    'accounts': [],
                    'message': 'Keine Mail-Accounts konfiguriert'
                }), 200
            
            # Lazy imports
            import importlib
            ai_client = importlib.import_module(".03_ai_client", "src")
            sanitizer = importlib.import_module(".04_sanitizer", "src")
            auth = importlib.import_module(".07_auth", "src")
            from src.tasks.mail_sync_tasks import sync_user_emails
            
            ServiceTokenManager = auth.ServiceTokenManager
            
            tasks_queued = []
            
            # Für jeden Account: GLEICHE LOGIK wie fetch_mails Button!
            for account in accounts:
                try:
                    # 1. Fetch-Limits (EXAKT wie Button)
                    is_initial = not account.initial_sync_done
                    fetch_limit = 500 if is_initial else 50
                    
                    # 2. AI Provider/Model (EXAKT wie Button)
                    provider = (user.preferred_ai_provider or "ollama").lower()
                    resolved_model = ai_client.resolve_model(provider, user.preferred_ai_model)
                    
                    # 3. ServiceToken erstellen (EXAKT wie Button)
                    with get_db_session() as token_db:
                        _, service_token = ServiceTokenManager.create_token(
                            user_id=user.id,
                            master_key=master_key,
                            session=token_db,
                            days=1
                        )
                        service_token_id = service_token.id
                    
                    # 4. Celery Task queuen (EXAKT wie Button)
                    task = sync_user_emails.delay(
                        user_id=user.id,
                        account_id=account.id,
                        service_token_id=service_token_id,
                        max_emails=fetch_limit
                    )
                    
                    tasks_queued.append({
                        'account_id': account.id,
                        'task_id': task.id,
                        'email': account.email,
                        'is_initial': is_initial,
                        'fetch_limit': fetch_limit
                    })
                    logger.info(f"Auto-Fetch: Task {task.id} für Account {account.id} gequeued (fetch_limit={fetch_limit})")
                    
                except Exception as e:
                    logger.error(f"Auto-Fetch: Fehler für Account {account.id}: {e}")
                    # Weiter mit nächstem Account
                    continue
            
            return jsonify({
                'success': True,
                'tasks_queued': len(tasks_queued),
                'accounts': [t['account_id'] for t in tasks_queued],
                'tasks': tasks_queued
            }), 200
            
    except Exception as e:
        logger.error(f"api_auto_fetch_mails: Fehler: {type(e).__name__}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

