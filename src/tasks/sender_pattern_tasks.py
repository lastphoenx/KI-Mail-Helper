"""
Celery Tasks: Sender-Pattern Management (Tag 13)

Migriert Sender-Pattern Scan/Cleanup von Legacy zu Celery.

Tasks:
- scan_sender_patterns: Scannt E-Mails und lernt Sender-Muster
- cleanup_old_patterns: Entfernt alte/ungenutzte Patterns
- get_pattern_statistics: Holt User-Statistiken (async)

Security: Keine master_key benötigt (nur DB-Operationen).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from celery import Task
from celery.exceptions import Reject
from sqlalchemy.exc import SQLAlchemyError

from src.celery_app import celery_app
from src.helpers.database import get_session_factory

logger = logging.getLogger(__name__)


class BaseSenderPatternTask(Task):
    """Base Task für Sender-Pattern Operations"""
    
    autoretry_for = (SQLAlchemyError,)
    retry_kwargs = {"max_retries": 2}
    retry_backoff = True
    retry_backoff_max = 300  # 5 minutes
    retry_jitter = True


@celery_app.task(
    bind=True,
    base=BaseSenderPatternTask,
    name="tasks.sender_patterns.scan_sender_patterns",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=600,  # 10 minutes hard limit
    soft_time_limit=540
)
def scan_sender_patterns(
    self,
    user_id: int,
    limit: int = 1000
) -> Dict[str, Any]:
    """
    Scannt E-Mails des Users und aktualisiert Sender-Patterns.
    
    Wird periodisch ausgeführt (z.B. täglich via Celery Beat) oder
    manuell vom User getriggert.
    
    Args:
        user_id: User ID
        limit: Max. Anzahl E-Mails zu scannen (default: 1000)
        
    Returns:
        Dict mit Statistiken:
        {
            "patterns_created": int,
            "patterns_updated": int,
            "emails_scanned": int,
            "user_id": int
        }
        
    Raises:
        Reject: Bei ungültigen Parametern
        Retry: Bei DB-Fehlern
    """
    if not user_id:
        raise Reject("Invalid parameter: user_id required", requeue=False)
    
    logger.info(
        f"🔍 [Task {self.request.id}] Scanning sender patterns: "
        f"user={user_id}, limit={limit}"
    )
    
    SessionFactory = get_session_factory()
    
    try:
        with SessionFactory() as db:
            from src.services.sender_patterns import SenderPatternManager
            import importlib
            models = importlib.import_module(".02_models", "src")
            
            # Hole neueste E-Mails des Users
            emails = db.query(models.RawEmail).filter(
                models.RawEmail.user_id == user_id,
                models.RawEmail.deleted_at == None
            ).order_by(models.RawEmail.created_at.desc()).limit(limit).all()
            
            stats = {
                "patterns_created": 0,
                "patterns_updated": 0,
                "emails_scanned": 0,
                "user_id": user_id
            }
            
            # Scanne Emails und aktualisiere Patterns
            for email in emails:
                try:
                    # Check if pattern exists
                    sender = email.sender_address  # Encrypted, aber Hash funktion funktioniert trotzdem
                    if not sender:
                        continue
                    
                    existing_pattern = SenderPatternManager.get_pattern(
                        db, user_id, sender
                    )
                    
                    # Update/Create pattern basierend auf Email-Klassifizierung
                    pattern = SenderPatternManager.update_from_classification(
                        db=db,
                        user_id=user_id,
                        sender=sender,
                        category=getattr(email, 'ai_category', None),
                        priority=getattr(email, 'ai_priority', None),
                        is_newsletter=getattr(email, 'ai_is_newsletter', None),
                        is_correction=False  # Nur AI-Klassifizierung
                    )
                    
                    if existing_pattern:
                        stats["patterns_updated"] += 1
                    else:
                        stats["patterns_created"] += 1
                    
                    stats["emails_scanned"] += 1
                    
                except Exception as e:
                    logger.warning(f"Error processing email {email.id}: {e}")
                    continue
            
            # Commit changes
            db.commit()
            
            logger.info(
                f"✅ [Task {self.request.id}] Scan complete: "
                f"{stats['emails_scanned']} emails scanned, "
                f"{stats['patterns_created']} created, "
                f"{stats['patterns_updated']} updated"
            )
            
            return stats
            
    except SQLAlchemyError as e:
        logger.warning(f"Database error in sender pattern scan (will retry): {e}")
        raise self.retry(exc=e, countdown=60)
        
    except Exception as e:
        logger.error(
            f"Unexpected error in sender pattern scan: {type(e).__name__}: {e}"
        )
        raise Reject(f"Sender pattern scan failed: {e}", requeue=False)


@celery_app.task(
    bind=True,
    base=BaseSenderPatternTask,
    name="tasks.sender_patterns.cleanup_old_patterns",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=300,  # 5 minutes
    soft_time_limit=240
)
def cleanup_old_patterns(
    self,
    user_id: int,
    min_emails: int = 1,
    max_age_days: int = 180
) -> Dict[str, Any]:
    """
    Entfernt alte/ungenutzte Sender-Patterns.
    
    Wird periodisch ausgeführt (z.B. monatlich) um die DB sauber zu halten.
    
    Args:
        user_id: User ID
        min_emails: Minimum E-Mails um Pattern zu behalten (default: 1)
        max_age_days: Maximales Alter in Tagen (default: 180)
        
    Returns:
        Dict mit Statistiken:
        {
            "patterns_deleted": int,
            "user_id": int
        }
        
    Raises:
        Reject: Bei ungültigen Parametern
    """
    if not user_id:
        raise Reject("Invalid parameter: user_id required", requeue=False)
    
    logger.info(
        f"🧹 [Task {self.request.id}] Cleaning sender patterns: "
        f"user={user_id}, min_emails={min_emails}, max_age_days={max_age_days}"
    )
    
    SessionFactory = get_session_factory()
    
    try:
        with SessionFactory() as db:
            from src.services.sender_patterns import SenderPatternManager
            
            deleted_count = SenderPatternManager.cleanup_old_patterns(
                db=db,
                user_id=user_id,
                min_emails=min_emails,
                max_age_days=max_age_days
            )
            
            logger.info(
                f"✅ [Task {self.request.id}] Cleanup complete: "
                f"{deleted_count} patterns deleted"
            )
            
            return {
                "patterns_deleted": deleted_count,
                "user_id": user_id
            }
            
    except SQLAlchemyError as e:
        logger.warning(f"Database error in pattern cleanup (will retry): {e}")
        raise self.retry(exc=e, countdown=60)
        
    except Exception as e:
        logger.error(f"Unexpected error in pattern cleanup: {type(e).__name__}: {e}")
        raise Reject(f"Pattern cleanup failed: {e}", requeue=False)


@celery_app.task(
    bind=True,
    base=BaseSenderPatternTask,
    name="tasks.sender_patterns.get_pattern_statistics",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=60,  # 1 minute
    soft_time_limit=50
)
def get_pattern_statistics(
    self,
    user_id: int
) -> Dict[str, Any]:
    """
    Holt Statistiken über Sender-Patterns eines Users (async).
    
    Nützlich für Dashboard/Analytics ohne Frontend zu blocken.
    
    Args:
        user_id: User ID
        
    Returns:
        Dict mit Statistiken:
        {
            "total_patterns": int,
            "high_confidence_count": int,
            "total_emails_tracked": int,
            "total_corrections": int,
            "avg_confidence": float,
            "user_id": int
        }
        
    Raises:
        Reject: Bei ungültigen Parametern
    """
    if not user_id:
        raise Reject("Invalid parameter: user_id required", requeue=False)
    
    logger.info(
        f"📊 [Task {self.request.id}] Fetching pattern statistics: user={user_id}"
    )
    
    SessionFactory = get_session_factory()
    
    try:
        with SessionFactory() as db:
            from src.services.sender_patterns import SenderPatternManager
            
            stats = SenderPatternManager.get_user_statistics(db, user_id)
            stats["user_id"] = user_id
            
            logger.info(
                f"✅ [Task {self.request.id}] Statistics fetched: "
                f"{stats['total_patterns']} patterns"
            )
            
            return stats
            
    except Exception as e:
        logger.error(f"Error fetching pattern statistics: {type(e).__name__}: {e}")
        raise Reject(f"Statistics fetch failed: {e}", requeue=False)


@celery_app.task(
    bind=True,
    base=BaseSenderPatternTask,
    name="tasks.sender_patterns.update_pattern_from_correction",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=30,
    soft_time_limit=25
)
def update_pattern_from_correction(
    self,
    user_id: int,
    sender: str,
    category: Optional[str] = None,
    priority: Optional[int] = None,
    is_newsletter: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Aktualisiert Sender-Pattern basierend auf User-Korrektur.
    
    Wird aufgerufen wenn User eine AI-Klassifizierung korrigiert.
    
    Args:
        user_id: User ID
        sender: E-Mail-Adresse des Absenders
        category: Korrigierte Kategorie
        priority: Korrigierte Priorität
        is_newsletter: Korrigiertes Newsletter-Flag
        
    Returns:
        Dict mit Pattern-Info:
        {
            "pattern_updated": bool,
            "confidence": int,
            "user_id": int
        }
        
    Raises:
        Reject: Bei ungültigen Parametern
    """
    if not user_id or not sender:
        raise Reject("Invalid parameters: user_id and sender required", requeue=False)
    
    logger.info(
        f"✏️ [Task {self.request.id}] Updating pattern from correction: "
        f"user={user_id}, sender={sender[:20]}..."
    )
    
    SessionFactory = get_session_factory()
    
    try:
        with SessionFactory() as db:
            from src.services.sender_patterns import SenderPatternManager
            
            pattern = SenderPatternManager.update_from_classification(
                db=db,
                user_id=user_id,
                sender=sender,
                category=category,
                priority=priority,
                is_newsletter=is_newsletter,
                is_correction=True  # User-Korrektur hat hohes Gewicht
            )
            
            logger.info(
                f"✅ [Task {self.request.id}] Pattern updated: "
                f"confidence={pattern.confidence}"
            )
            
            return {
                "pattern_updated": True,
                "confidence": pattern.confidence,
                "user_id": user_id
            }
            
    except SQLAlchemyError as e:
        logger.warning(f"Database error updating pattern (will retry): {e}")
        raise self.retry(exc=e, countdown=30)
        
    except Exception as e:
        logger.error(f"Error updating pattern: {type(e).__name__}: {e}")
        raise Reject(f"Pattern update failed: {e}", requeue=False)
