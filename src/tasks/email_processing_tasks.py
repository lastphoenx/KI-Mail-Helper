# src/tasks/email_processing_tasks.py
"""
Celery Tasks für Email-Processing (Reprocess + Optimize).

Diese Tasks sind UI-Button-getriggert und müssen async sein:
- reprocess_email_base: Basis-Lauf neu generieren
- optimize_email_processing: Mit stärkerem Model (GPT-4) analysieren

KRITISCH: ServiceToken Pattern für Multi-User Security!
"""

from __future__ import annotations
import importlib
import logging
from datetime import datetime, UTC
from typing import Any, Dict, Optional

from celery import states
from celery.exceptions import Reject

from src.celery_app import celery_app
from src.helpers.database import get_session_factory
from src.services.personal_classifier_service import enhance_with_personal_predictions

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER: DEK aus ServiceToken laden (Phase 2 Security)
# =============================================================================
def _get_dek_from_service_token(service_token_id: int, user_id: int, db) -> str:
    """
    Phase 2 Security: Lädt DEK aus ServiceToken mit User-Ownership-Check.
    
    KRITISCH: user_id Check verhindert Cross-User-Token-Leak!
    
    Args:
        service_token_id: Token ID
        user_id: User ID für Ownership-Check
        db: SQLAlchemy Session
        
    Returns:
        str: DEK (Base64-encoded)
        
    Raises:
        ValueError: Token nicht gefunden, abgelaufen, oder falscher User
    """
    models = importlib.import_module(".02_models", "src")
    
    # KRITISCH: user_id Filter verhindert Cross-User-Attack!
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
    
    # Audit-Trail: Markiere Token als verwendet
    dek = service_token.encrypted_dek
    service_token.mark_verified()
    db.commit()
    
    logger.info(f"✅ DEK aus ServiceToken {service_token_id} geladen (user={user_id})")
    return dek


# =============================================================================
# TASK 1: Reprocess Email (Base-Lauf neu)
# =============================================================================
@celery_app.task(
    bind=True,
    name="tasks.email_processing.reprocess_email_base",
    max_retries=3,
    default_retry_delay=60,
    time_limit=120,      # 2 Minuten hard limit
    soft_time_limit=90,  # 90 Sekunden soft limit
    acks_late=True,
    reject_on_worker_lost=True
)
def reprocess_email_base(
    self,
    user_id: int,
    raw_email_id: int,
    service_token_id: int
) -> Dict[str, Any]:
    """
    Task: Base-Lauf für Email neu generieren (async).
    
    Entspricht dem "Basis-Lauf neu machen" Button in der UI.
    
    Args:
        user_id: User ID (für Ownership-Check)
        raw_email_id: RawEmail ID
        service_token_id: ServiceToken ID für DEK-Abruf
        
    Returns:
        Dict mit score, reasoning, model_used
        
    Raises:
        Reject: Bei permanenten Fehlern (Email nicht gefunden, unauthorized)
        Retry: Bei transienten Fehlern (AI timeout, DB lock)
    """
    if not user_id or not raw_email_id or not service_token_id:
        raise Reject("Ungültige Parameter", requeue=False)
    
    logger.info(
        f"🔧 [Task {self.request.id}] Reprocess Base: "
        f"user={user_id}, email={raw_email_id}"
    )
    
    SessionFactory = get_session_factory()
    master_key = None
    
    try:
        with SessionFactory() as db:
            models = importlib.import_module(".02_models", "src")
            encryption = importlib.import_module(".08_encryption", "src")
            ai_client = importlib.import_module(".03_ai_client", "src")
            sanitizer = importlib.import_module(".04_sanitizer", "src")
            scoring = importlib.import_module(".05_scoring", "src")
            
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
            
            # 3. ProcessedEmail laden
            processed = db.query(models.ProcessedEmail).filter_by(
                raw_email_id=raw_email_id
            ).filter(models.ProcessedEmail.deleted_at == None).first()
            
            if not processed:
                raise Reject(
                    f"ProcessedEmail für raw_email_id={raw_email_id} nicht gefunden",
                    requeue=False
                )
            
            # 4. User laden für Provider-Settings
            user = db.query(models.User).filter_by(id=user_id).first()
            if not user:
                raise Reject(f"User {user_id} nicht gefunden", requeue=False)
            
            # 5. Provider/Model aus User-Settings
            provider = (user.preferred_ai_provider or "ollama").lower()
            resolved_model = ai_client.resolve_model(provider, user.preferred_ai_model)
            use_cloud = ai_client.provider_requires_cloud(provider)
            sanitize_level = sanitizer.get_sanitization_level(use_cloud)
            
            # Progress-Update
            self.update_state(
                state='PROGRESS',
                meta={'progress': 20, 'message': 'Email entschlüsseln...'}
            )
            
            # 6. Email entschlüsseln
            decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                raw_email.encrypted_subject or "", master_key
            )
            decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                raw_email.encrypted_body or "", master_key
            )
            decrypted_sender = encryption.EmailDataManager.decrypt_email_sender(
                raw_email.encrypted_sender or "", master_key
            )
            
            # Progress-Update
            self.update_state(
                state='PROGRESS',
                meta={'progress': 40, 'message': f'AI-Analyse mit {resolved_model}...'}
            )
            
            # 7. AI-Client und Analyse
            client = ai_client.build_client(provider, model=resolved_model)
            sanitized_body = sanitizer.sanitize_email(decrypted_body, level=sanitize_level)
            
            result = client.analyze_email(
                subject=decrypted_subject,
                body=sanitized_body,
                language="de"
            )
            
            # 7b. Hybrid Score-Learning: Erweitere mit Personal Classifier Predictions
            try:
                result, used_model_source = enhance_with_personal_predictions(
                    user_id=user_id,
                    raw_email=raw_email,
                    result=result,
                    db_session=db
                )
                logger.debug(
                    f"🎯 Personal Classifier: source={used_model_source}, "
                    f"dring={result.get('dringlichkeit')}, wichtig={result.get('wichtigkeit')}"
                )
            except Exception as e:
                logger.warning(f"⚠️ Personal Classifier fehlgeschlagen, nutze AI-only: {e}")
                used_model_source = "global"  # Fallback bei Fehler
            
            # Progress-Update
            self.update_state(
                state='PROGRESS',
                meta={'progress': 80, 'message': 'Ergebnisse speichern...'}
            )
            
            # 8. Scoring
            priority = scoring.analyze_priority(
                result["dringlichkeit"], 
                result["wichtigkeit"]
            )
            
            # 9. Verschlüssele KI-Ergebnisse
            encrypted_summary = encryption.EmailDataManager.encrypt_summary(
                result["summary_de"], master_key
            )
            encrypted_text = encryption.EmailDataManager.encrypt_summary(
                result["text_de"], master_key
            )
            encrypted_tags = encryption.EmailDataManager.encrypt_summary(
                ",".join(result.get("tags", [])), master_key
            )
            
            # 10. ProcessedEmail updaten
            processed.dringlichkeit = result["dringlichkeit"]
            processed.wichtigkeit = result["wichtigkeit"]
            processed.kategorie_aktion = result["kategorie_aktion"]
            processed.encrypted_tags = encrypted_tags
            processed.spam_flag = result["spam_flag"]
            processed.encrypted_summary_de = encrypted_summary
            processed.encrypted_text_de = encrypted_text
            processed.score = priority["score"]
            processed.matrix_x = priority["matrix_x"]
            processed.matrix_y = priority["matrix_y"]
            processed.farbe = priority["farbe"]
            processed.base_model = resolved_model
            processed.base_provider = provider
            processed.processed_at = datetime.now(UTC)
            processed.rebase_at = datetime.now(UTC)
            processed.updated_at = datetime.now(UTC)
            processed.optimization_status = models.OptimizationStatus.PENDING.value
            
            # Hybrid Score-Learning: Speichere welches Modell genutzt wurde
            if used_model_source in ("personal", "global"):
                processed.used_model_source = used_model_source
            else:
                processed.used_model_source = "global"  # Default für ai_only
            
            db.commit()
            
            logger.info(
                f"✅ [Task {self.request.id}] Reprocess abgeschlossen: "
                f"score={processed.score}, model={resolved_model}"
            )
            
            return {
                "status": "success",
                "email_id": raw_email_id,
                "score": processed.score,
                "farbe": processed.farbe,
                "kategorie_aktion": processed.kategorie_aktion,
                "dringlichkeit": processed.dringlichkeit,
                "wichtigkeit": processed.wichtigkeit,
                "model_used": resolved_model,
                "provider_used": provider
            }
            
    except Reject:
        raise  # Permanent error, don't retry
        
    except Exception as exc:
        logger.error(
            f"❌ [Task {self.request.id}] Reprocess fehlgeschlagen: "
            f"{type(exc).__name__}: {exc}"
        )
        # Retry bei transienten Fehlern
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    
    finally:
        # Security: DEK aus RAM bereinigen
        if master_key:
            import gc
            master_key = '\x00' * len(master_key) if master_key else None
            del master_key
            gc.collect()


# =============================================================================
# TASK 2: Optimize Email (mit stärkerem Model)
# =============================================================================
@celery_app.task(
    bind=True,
    name="tasks.email_processing.optimize_email_processing",
    max_retries=3,
    default_retry_delay=120,  # Länger wegen GPT-4 Rate-Limits
    time_limit=180,           # 3 Minuten max (GPT-4 ist langsamer)
    soft_time_limit=150,
    acks_late=True,
    reject_on_worker_lost=True
)
def optimize_email_processing(
    self,
    user_id: int,
    raw_email_id: int,
    service_token_id: int
) -> Dict[str, Any]:
    """
    Task: Optimize-Lauf mit stärkerem Model (async).
    
    Entspricht dem "Optimize-Lauf" Button in der UI.
    Nutzt das in user.preferred_ai_provider_optimize konfigurierte Model.
    
    Args:
        user_id: User ID (für Ownership-Check)
        raw_email_id: RawEmail ID
        service_token_id: ServiceToken ID für DEK-Abruf
        
    Returns:
        Dict mit score_base, score_optimize, improvement, model_used
    """
    if not user_id or not raw_email_id or not service_token_id:
        raise Reject("Ungültige Parameter", requeue=False)
    
    logger.info(
        f"🔧 [Task {self.request.id}] Optimize: "
        f"user={user_id}, email={raw_email_id}"
    )
    
    SessionFactory = get_session_factory()
    master_key = None
    
    try:
        with SessionFactory() as db:
            models = importlib.import_module(".02_models", "src")
            encryption = importlib.import_module(".08_encryption", "src")
            ai_client = importlib.import_module(".03_ai_client", "src")
            sanitizer = importlib.import_module(".04_sanitizer", "src")
            scoring = importlib.import_module(".05_scoring", "src")
            
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
            
            # 3. ProcessedEmail laden (muss existieren für Optimize!)
            processed = db.query(models.ProcessedEmail).filter_by(
                raw_email_id=raw_email_id
            ).filter(models.ProcessedEmail.deleted_at == None).first()
            
            if not processed:
                raise Reject(
                    f"ProcessedEmail nicht gefunden - Base-Lauf muss zuerst existieren!",
                    requeue=False
                )
            
            # 4. User laden für Optimize-Provider-Settings
            user = db.query(models.User).filter_by(id=user_id).first()
            if not user:
                raise Reject(f"User {user_id} nicht gefunden", requeue=False)
            
            # 5. OPTIMIZE Provider/Model (stärkeres Model!)
            provider_optimize = (user.preferred_ai_provider_optimize or "ollama").lower()
            resolved_model = ai_client.resolve_model(
                provider_optimize, 
                user.preferred_ai_model_optimize
            )
            use_cloud = ai_client.provider_requires_cloud(provider_optimize)
            sanitize_level = sanitizer.get_sanitization_level(use_cloud)
            
            # Progress-Update
            self.update_state(
                state='PROGRESS',
                meta={'progress': 20, 'message': 'Email entschlüsseln...'}
            )
            
            # 6. Email entschlüsseln
            decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                raw_email.encrypted_subject or "", master_key
            )
            decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                raw_email.encrypted_body or "", master_key
            )
            
            # Progress-Update
            self.update_state(
                state='PROGRESS',
                meta={
                    'progress': 40, 
                    'message': f'Optimize mit {resolved_model} (kann länger dauern)...'
                }
            )
            
            # 7. AI-Client und Analyse (stärkeres Model)
            client = ai_client.build_client(provider_optimize, model=resolved_model)
            sanitized_body = sanitizer.sanitize_email(decrypted_body, level=sanitize_level)
            
            logger.info(f"🤖 Optimize-Pass mit {provider_optimize.upper()}/{resolved_model}")
            
            result = client.analyze_email(
                subject=decrypted_subject,
                body=sanitized_body,
                language="de"
            )
            
            # Progress-Update
            self.update_state(
                state='PROGRESS',
                meta={'progress': 80, 'message': 'Ergebnisse speichern...'}
            )
            
            # 8. Scoring
            priority = scoring.analyze_priority(
                result["dringlichkeit"], 
                result["wichtigkeit"]
            )
            
            # 9. Verschlüssele KI-Ergebnisse
            encrypted_summary = encryption.EmailDataManager.encrypt_summary(
                result["summary_de"], master_key
            )
            encrypted_text = encryption.EmailDataManager.encrypt_summary(
                result["text_de"], master_key
            )
            encrypted_tags = encryption.EmailDataManager.encrypt_summary(
                ",".join(result.get("tags", [])), master_key
            )
            
            # 10. ProcessedEmail Optimize-Felder updaten
            processed.optimize_dringlichkeit = result["dringlichkeit"]
            processed.optimize_wichtigkeit = result["wichtigkeit"]
            processed.optimize_kategorie_aktion = result["kategorie_aktion"]
            processed.optimize_encrypted_tags = encrypted_tags
            processed.optimize_spam_flag = result["spam_flag"]
            processed.optimize_encrypted_summary_de = encrypted_summary
            processed.optimize_encrypted_text_de = encrypted_text
            processed.optimize_score = priority["score"]
            processed.optimize_matrix_x = priority["matrix_x"]
            processed.optimize_matrix_y = priority["matrix_y"]
            processed.optimize_farbe = priority["farbe"]
            processed.optimize_confidence = result.get("_phase_y_confidence")
            processed.optimize_model = resolved_model
            processed.optimize_provider = provider_optimize
            processed.optimization_status = models.OptimizationStatus.DONE.value
            processed.optimization_completed_at = datetime.now(UTC)
            processed.updated_at = datetime.now(UTC)
            
            db.commit()
            
            # Berechne Improvement
            base_score = processed.score or 0
            optimize_score = processed.optimize_score or 0
            improvement = optimize_score - base_score
            
            logger.info(
                f"✅ [Task {self.request.id}] Optimize abgeschlossen: "
                f"base={base_score} → optimize={optimize_score} (+{improvement})"
            )
            
            return {
                "status": "success",
                "email_id": raw_email_id,
                "score_base": base_score,
                "score_optimize": optimize_score,
                "improvement": improvement,
                "farbe": processed.optimize_farbe,
                "kategorie_aktion": processed.optimize_kategorie_aktion,
                "dringlichkeit": processed.optimize_dringlichkeit,
                "wichtigkeit": processed.optimize_wichtigkeit,
                "model_used": resolved_model,
                "provider_used": provider_optimize
            }
            
    except Reject:
        raise  # Permanent error
        
    except Exception as exc:
        logger.error(
            f"❌ [Task {self.request.id}] Optimize fehlgeschlagen: "
            f"{type(exc).__name__}: {exc}"
        )
        
        # Update optimization_status auf FAILED
        try:
            with SessionFactory() as db:
                models = importlib.import_module(".02_models", "src")
                processed = db.query(models.ProcessedEmail).filter_by(
                    raw_email_id=raw_email_id
                ).first()
                if processed:
                    processed.optimization_status = models.OptimizationStatus.FAILED.value
                    processed.optimization_tried_at = datetime.now(UTC)
                    db.commit()
        except Exception:
            pass  # Ignoriere Fehler beim Status-Update
        
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))
    
    finally:
        # Security: DEK aus RAM bereinigen
        if master_key:
            import gc
            master_key = '\x00' * len(master_key) if master_key else None
            del master_key
            gc.collect()
