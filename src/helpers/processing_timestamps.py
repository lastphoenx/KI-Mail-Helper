"""
Helper-Funktionen für Timestamp-basiertes Processing (Phase 27.1)

Diese Helpers ersetzen die bestehenden Status-Checks durch Timestamp-basierte Logik.
"""

from datetime import datetime, UTC
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


def needs_processing_step(raw_email, step: str) -> bool:
    """
    Prüfe ob ein Verarbeitungs-Schritt noch ausgeführt werden muss.
    
    Args:
        raw_email: RawEmail-Instanz
        step: "embedding", "translation", "ai_classification", "auto_rules"
    
    Returns:
        True wenn Step ausgeführt werden muss, False wenn bereits erledigt
    """
    if step == "embedding":
        return raw_email.embedding_generated_at is None
    
    elif step == "translation":
        # Translation nur wenn:
        # 1. Noch nicht gemacht UND
        # 2. Sprache erkannt UND != de
        return (
            raw_email.translation_completed_at is None and
            raw_email.detected_language and
            raw_email.detected_language not in ('de', 'en')
        )
    
    elif step == "ai_classification":
        return raw_email.ai_classification_completed_at is None
    
    elif step == "auto_rules":
        return raw_email.auto_rules_completed_at is None
    
    else:
        raise ValueError(f"Unknown step: {step}")


def check_dependencies(raw_email, step: str) -> tuple[bool, Optional[str]]:
    """
    Prüfe ob Dependencies für einen Step erfüllt sind.
    
    Args:
        raw_email: RawEmail-Instanz
        step: "embedding", "translation", "ai_classification", "auto_rules"
    
    Returns:
        (can_proceed: bool, missing_dependency: Optional[str])
    """
    if step == "embedding":
        # Keine Dependencies
        return True, None
    
    elif step == "translation":
        # Benötigt: Embedding (für bessere Translation durch Context)
        if not raw_email.embedding_generated_at:
            return False, "embedding"
        return True, None
    
    elif step == "ai_classification":
        # Benötigt: Embedding (für Semantic Features)
        # Translation ist OPTIONAL (manche Emails brauchen keine)
        if not raw_email.embedding_generated_at:
            return False, "embedding"
        return True, None
    
    elif step == "auto_rules":
        # Benötigt: AI-Classification (für Kategorien/Scores)
        if not raw_email.ai_classification_completed_at:
            return False, "ai_classification"
        return True, None
    
    else:
        raise ValueError(f"Unknown step: {step}")


def mark_step_completed(raw_email, step: str):
    """
    Markiere einen Verarbeitungs-Schritt als abgeschlossen.
    
    Args:
        raw_email: RawEmail-Instanz
        step: "embedding", "translation", "ai_classification", "auto_rules"
    """
    now = datetime.now(UTC)
    
    if step == "embedding":
        raw_email.embedding_generated_at = now
    elif step == "translation":
        raw_email.translation_completed_at = now
    elif step == "ai_classification":
        raw_email.ai_classification_completed_at = now
    elif step == "auto_rules":
        raw_email.auto_rules_completed_at = now
    else:
        raise ValueError(f"Unknown step: {step}")
    
    logger.debug(f"✅ Step '{step}' marked completed at {now}")


def is_fully_processed(raw_email) -> bool:
    """
    Prüfe ob alle Processing-Steps abgeschlossen sind.
    
    Returns:
        True wenn alle Steps fertig (oder übersprungen), False sonst
    """
    # Embedding: Muss immer da sein
    if not raw_email.embedding_generated_at:
        return False
    
    # Translation: Nur nötig wenn Sprache != de/en
    needs_translation = (
        raw_email.detected_language and 
        raw_email.detected_language not in ('de', 'en')
    )
    if needs_translation and not raw_email.translation_completed_at:
        return False
    
    # AI-Classification: Muss immer da sein
    if not raw_email.ai_classification_completed_at:
        return False
    
    # Auto-Rules: Muss immer da sein
    if not raw_email.auto_rules_completed_at:
        return False
    
    return True


def update_overall_status(raw_email):
    """
    Aktualisiere den Overall-Status basierend auf Timestamps.
    
    Der processing_status (0-100) wird nur noch für Monitoring verwendet.
    Die tatsächliche Steuerung läuft über Timestamps.
    
    Status-Mapping:
    - 0: Unbearbeitet (kein Timestamp gesetzt)
    - 10: Embedding fertig
    - 20: Translation fertig (oder übersprungen)
    - 40: AI-Classification fertig
    - 50: Auto-Rules fertig
    - 100: Alles fertig
    """
    if is_fully_processed(raw_email):
        raw_email.processing_status = 100
    elif raw_email.auto_rules_completed_at:
        raw_email.processing_status = 50
    elif raw_email.ai_classification_completed_at:
        raw_email.processing_status = 40
    elif raw_email.translation_completed_at or (
        raw_email.detected_language in ('de', 'en')
    ):
        raw_email.processing_status = 20
    elif raw_email.embedding_generated_at:
        raw_email.processing_status = 10
    else:
        raw_email.processing_status = 0


def get_pending_emails_query(session, user_id: int, mail_account_id: Optional[int] = None):
    """
    Query für Emails die noch Processing benötigen.
    
    Ersetzt die alte Logik: WHERE processing_status < 100
    
    Returns:
        SQLAlchemy Query für pending emails
    """
    from src import models
    
    # Base Query
    query = session.query(models.RawEmail).filter(
        models.RawEmail.user_id == user_id,
        models.RawEmail.deleted_at.is_(None)
    )
    
    # Optional: Filter nach Account
    if mail_account_id:
        query = query.filter(models.RawEmail.mail_account_id == mail_account_id)
    
    # Filter: Mindestens EIN Step fehlt
    # (Komplexe OR-Bedingung - prüft jeden Step einzeln)
    from sqlalchemy import or_, and_
    
    query = query.filter(
        or_(
            # Embedding fehlt
            models.RawEmail.embedding_generated_at.is_(None),
            
            # Translation fehlt (nur wenn nötig)
            # Phase 27.1: NULL handling - auch Mails ohne detected_language einschließen
            and_(
                or_(
                    models.RawEmail.detected_language.is_(None),
                    models.RawEmail.detected_language.notin_(['de', 'en'])
                ),
                models.RawEmail.translation_completed_at.is_(None)
            ),
            
            # AI-Classification fehlt
            models.RawEmail.ai_classification_completed_at.is_(None),
            
            # Auto-Rules fehlen
            models.RawEmail.auto_rules_completed_at.is_(None)
        )
    )
    
    # Sortierung: Älteste zuerst (chronologische Verarbeitung)
    query = query.order_by(models.RawEmail.received_at.asc())
    
    return query


def get_processing_stats(session, user_id: int) -> dict:
    """
    Statistiken über Processing-Status aller Emails eines Users.
    
    Returns:
        {
            "total": 100,
            "fully_processed": 85,
            "pending_embedding": 5,
            "pending_translation": 3,
            "pending_ai_classification": 7,
            "pending_auto_rules": 10,
            "with_errors": 2
        }
    """
    from src import models
    from sqlalchemy import func, or_
    
    total = session.query(func.count(models.RawEmail.id)).filter(
        models.RawEmail.user_id == user_id,
        models.RawEmail.deleted_at.is_(None)
    ).scalar()
    
    fully_processed = session.query(func.count(models.RawEmail.id)).filter(
        models.RawEmail.user_id == user_id,
        models.RawEmail.deleted_at.is_(None),
        models.RawEmail.processing_status == 100
    ).scalar()
    
    pending_embedding = session.query(func.count(models.RawEmail.id)).filter(
        models.RawEmail.user_id == user_id,
        models.RawEmail.deleted_at.is_(None),
        models.RawEmail.embedding_generated_at.is_(None)
    ).scalar()
    
    # Phase 27.1: NULL handling - auch Mails ohne detected_language einschließen
    pending_translation = session.query(func.count(models.RawEmail.id)).filter(
        models.RawEmail.user_id == user_id,
        models.RawEmail.deleted_at.is_(None),
        or_(
            models.RawEmail.detected_language.is_(None),
            models.RawEmail.detected_language.notin_(['de', 'en'])
        ),
        models.RawEmail.translation_completed_at.is_(None)
    ).scalar()
    
    pending_ai = session.query(func.count(models.RawEmail.id)).filter(
        models.RawEmail.user_id == user_id,
        models.RawEmail.deleted_at.is_(None),
        models.RawEmail.ai_classification_completed_at.is_(None)
    ).scalar()
    
    pending_rules = session.query(func.count(models.RawEmail.id)).filter(
        models.RawEmail.user_id == user_id,
        models.RawEmail.deleted_at.is_(None),
        models.RawEmail.auto_rules_completed_at.is_(None)
    ).scalar()
    
    with_errors = session.query(func.count(models.RawEmail.id)).filter(
        models.RawEmail.user_id == user_id,
        models.RawEmail.deleted_at.is_(None),
        models.RawEmail.processing_error.isnot(None)
    ).scalar()
    
    return {
        "total": total,
        "fully_processed": fully_processed,
        "pending_embedding": pending_embedding,
        "pending_translation": pending_translation,
        "pending_ai_classification": pending_ai,
        "pending_auto_rules": pending_rules,
        "with_errors": with_errors
    }
