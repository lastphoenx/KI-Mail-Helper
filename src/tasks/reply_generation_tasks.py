# src/tasks/reply_generation_tasks.py
"""
Celery Task für Antwort-Entwurf Generierung.

UI-Button-getriggert: "Antwort-Entwurf generieren"

KRITISCH: ServiceToken Pattern für Multi-User Security!
"""

from __future__ import annotations
import importlib
import json
import logging
from datetime import datetime, UTC
from typing import Any, Dict, Optional

from celery.exceptions import Reject

from src.celery_app import celery_app
from src.helpers.database import get_session_factory

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER: DEK aus ServiceToken laden (Phase 2 Security)
# =============================================================================
def _get_dek_from_service_token(service_token_id: int, user_id: int, db) -> str:
    """
    Phase 2 Security: Lädt DEK aus ServiceToken mit User-Ownership-Check.
    
    KRITISCH: user_id Check verhindert Cross-User-Token-Leak!
    """
    models = importlib.import_module(".02_models", "src")
    
    service_token = db.query(models.ServiceToken).filter_by(
        id=service_token_id,
        user_id=user_id  # ← Multi-User Security!
    ).first()
    
    if not service_token:
        raise ValueError(
            f"ServiceToken {service_token_id} nicht gefunden oder gehört anderem User"
        )
    
    if not service_token.is_valid():
        raise ValueError(
            f"ServiceToken {service_token_id} abgelaufen (expires: {service_token.expires_at})"
        )
    
    dek = service_token.encrypted_dek
    service_token.mark_verified()
    db.commit()
    
    logger.info(f"✅ DEK aus ServiceToken {service_token_id} geladen (user={user_id})")
    return dek


# =============================================================================
# TASK: Generate Reply Draft
# =============================================================================
@celery_app.task(
    bind=True,
    name="tasks.reply_generation.generate_reply_draft",
    max_retries=3,
    default_retry_delay=60,
    time_limit=90,       # 90 Sekunden hard limit
    soft_time_limit=60,  # 60 Sekunden soft limit
    acks_late=True,
    reject_on_worker_lost=True
)
def generate_reply_draft(
    self,
    user_id: int,
    raw_email_id: int,
    service_token_id: int,
    tone: str = "formal",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    use_anonymization: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Task: Antwort-Entwurf für Email generieren (async).
    
    Entspricht dem "Antwort-Entwurf generieren" Button in der UI.
    
    Args:
        user_id: User ID (für Ownership-Check)
        raw_email_id: RawEmail ID
        service_token_id: ServiceToken ID für DEK-Abruf
        tone: Ton der Antwort (formal, friendly, brief, decline)
        provider: AI Provider (optional, überschreibt User-Settings)
        model: AI Model (optional, überschreibt User-Settings)
        use_anonymization: Anonymisierung nutzen? (optional)
        
    Returns:
        Dict mit reply_text, tone_used, was_anonymized, etc.
    """
    if not user_id or not raw_email_id or not service_token_id:
        raise Reject("Ungültige Parameter", requeue=False)
    
    logger.info(
        f"🔧 [Task {self.request.id}] Generate Reply: "
        f"user={user_id}, email={raw_email_id}, tone={tone}"
    )
    
    SessionFactory = get_session_factory()
    master_key = None
    
    try:
        with SessionFactory() as db:
            models = importlib.import_module(".02_models", "src")
            encryption = importlib.import_module(".08_encryption", "src")
            ai_client = importlib.import_module(".03_ai_client", "src")
            
            # 1. Phase 2 Security: DEK aus ServiceToken laden
            master_key = _get_dek_from_service_token(service_token_id, user_id, db)
            
            # 2. Ownership-Check: Email gehört User?
            raw_email = db.query(models.RawEmail).filter_by(
                id=raw_email_id,
                user_id=user_id
            ).filter(models.RawEmail.deleted_at == None).first()
            
            if not raw_email:
                raise Reject(
                    f"Email {raw_email_id} nicht gefunden oder unauthorized",
                    requeue=False
                )
            
            # 3. User laden
            user = db.query(models.User).filter_by(id=user_id).first()
            if not user:
                raise Reject(f"User {user_id} nicht gefunden", requeue=False)
            
            # Progress-Update
            self.update_state(
                state='PROGRESS',
                meta={'progress': 20, 'message': 'Email entschlüsseln...'}
            )
            
            # 4. Email entschlüsseln
            decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                raw_email.encrypted_subject or "", master_key
            )
            decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                raw_email.encrypted_body or "", master_key
            )
            decrypted_sender = encryption.EmailDataManager.decrypt_email_sender(
                raw_email.encrypted_sender or "", master_key
            )
            
            # 5. Provider/Model Selection
            if provider and model:
                selected_provider = provider.lower()
                resolved_model = ai_client.resolve_model(selected_provider, model, kind="optimize")
            else:
                selected_provider = (
                    getattr(user, 'preferred_ai_provider_optimize', None) or 
                    getattr(user, 'preferred_ai_provider', None) or 
                    "ollama"
                ).lower()
                optimize_model = (
                    getattr(user, 'preferred_ai_model_optimize', None) or 
                    getattr(user, 'preferred_ai_model', None)
                )
                resolved_model = ai_client.resolve_model(
                    selected_provider, optimize_model, kind="optimize"
                )
            
            # 6. Anonymisierungs-Logik
            cloud_providers = ["openai", "anthropic", "google"]
            is_cloud_provider = selected_provider in cloud_providers
            
            if use_anonymization is None:
                use_anonymization = is_cloud_provider
            
            content_for_ai_subject = decrypted_subject
            content_for_ai_body = decrypted_body
            sender_for_ai = decrypted_sender
            entity_map = None
            was_anonymized = False
            
            # Progress-Update
            self.update_state(
                state='PROGRESS',
                meta={'progress': 40, 'message': 'Vorbereitung...'}
            )
            
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
                                logger.debug(f"✅ Entity-Map geladen: {len(entity_map.get('reverse', {}))} Mappings")
                            except Exception as em_err:
                                logger.warning(f"⚠️ Entity-Map Entschlüsselung fehlgeschlagen: {em_err}")
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
            
            # Progress-Update
            self.update_state(
                state='PROGRESS',
                meta={'progress': 60, 'message': f'Antwort generieren mit {resolved_model}...'}
            )
            
            # 7. Thread-Context für bessere Antworten
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
            
            # 8. Reply Generator
            reply_generator_mod = importlib.import_module("src.reply_generator")
            client = ai_client.build_client(selected_provider, model=resolved_model)
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
            
            if not result.get("success"):
                raise Exception(result.get("error", "Reply generation failed"))
            
            logger.info(
                f"✅ [Task {self.request.id}] Reply generiert: "
                f"tone={result['tone_used']}, anonymized={was_anonymized}"
            )
            
            return {
                "status": "success",
                "success": True,
                "email_id": raw_email_id,
                "reply_text": result.get("reply_text", ""),
                "tone_used": result.get("tone_used", tone),
                "was_anonymized": was_anonymized,
                "entity_map": entity_map,
                "provider_used": selected_provider,
                "model_used": resolved_model
            }
            
    except Reject:
        raise  # Permanent error
        
    except Exception as exc:
        logger.error(
            f"❌ [Task {self.request.id}] Reply generation fehlgeschlagen: "
            f"{type(exc).__name__}: {exc}"
        )
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    
    finally:
        # Security: DEK aus RAM bereinigen
        if master_key:
            import gc
            master_key = '\x00' * len(master_key) if master_key else None
            del master_key
            gc.collect()
