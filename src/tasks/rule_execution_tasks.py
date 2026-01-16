"""
Celery Tasks: Auto-Rules Execution (Tag 11)

Migriert Auto-Rules von Legacy Background-Jobs zu Celery.

Tasks:
- apply_rules_to_emails: Wendet Regeln auf spezifische E-Mails an
- apply_rules_to_new_emails: Verarbeitet neue E-Mails (Batch)

Phase 2 Security: ServiceToken Pattern
- Kein master_key als Parameter (wäre Plaintext in Redis!)
- service_token_id → DEK wird aus DB geladen
"""

from __future__ import annotations

import logging
import importlib
from typing import Any, Dict, List, Optional

from celery import Task
from celery.exceptions import Reject, Retry
from sqlalchemy.exc import SQLAlchemyError

from src.celery_app import celery_app
from src.helpers.database import get_session_factory

logger = logging.getLogger(__name__)


def _get_dek_from_service_token(service_token_id: int, session) -> str:
    """
    Phase 2 Security: Lädt und verifiziert ServiceToken, gibt DEK zurück.
    
    Args:
        service_token_id: ID des ServiceTokens
        session: DB-Session
        
    Returns:
        str: DEK (Base64-encoded)
        
    Raises:
        ValueError: Token nicht gefunden/abgelaufen
    """
    models = importlib.import_module(".02_models", "src")
    
    service_token = session.query(models.ServiceToken).filter_by(
        id=service_token_id
    ).first()
    
    if not service_token:
        raise ValueError(f"ServiceToken {service_token_id} nicht gefunden")
    
    if not service_token.is_valid():
        raise ValueError(f"ServiceToken {service_token_id} abgelaufen (expires: {service_token.expires_at})")
    
    dek = service_token.encrypted_dek
    service_token.mark_verified()
    session.commit()
    
    logger.info(f"✅ DEK aus ServiceToken {service_token_id} geladen")
    return dek


class BaseRuleTask(Task):
    """Base Task mit Retry-Logic und Error-Handling für Rule-Execution"""
    
    autoretry_for = (SQLAlchemyError,)
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True


@celery_app.task(
    bind=True,
    base=BaseRuleTask,
    name="tasks.rule_execution.apply_rules_to_emails",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=300,  # 5 minutes hard limit
    soft_time_limit=240  # 4 minutes soft limit
)
def apply_rules_to_emails(
    self,
    user_id: int,
    email_ids: List[int],
    service_token_id: int,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Wendet Auto-Rules auf spezifische E-Mails an.
    
    Args:
        user_id: User ID
        email_ids: Liste von E-Mail-IDs
        service_token_id: ServiceToken ID für DEK-Abruf (Phase 2 Security)
        dry_run: Wenn True, nur simulieren (keine echten Aktionen)
        
    Returns:
        Dict mit Statistiken:
        {
            "emails_processed": int,
            "rules_triggered": int,
            "actions_executed": int,
            "errors": int,
            "email_ids": List[int]
        }
        
    Raises:
        Reject: Bei kritischen Fehlern (ungültige Parameter)
        Retry: Bei vorübergehenden DB-Fehlern
    """
    if not user_id or not email_ids:
        raise Reject("Invalid parameters: user_id and email_ids required", requeue=False)
    
    if not service_token_id:
        raise Reject("ServiceToken ID required for rule execution", requeue=False)
    
    logger.info(
        f"🔧 [Task {self.request.id}] Applying rules: "
        f"user={user_id}, emails={len(email_ids)}, dry_run={dry_run}"
    )
    
    SessionFactory = get_session_factory()
    
    try:
        with SessionFactory() as db:
            # Phase 2 Security: DEK aus ServiceToken laden
            master_key = _get_dek_from_service_token(service_token_id, db)
            
            # Import AutoRulesEngine (lazy import to avoid circular dependencies)
            from src.auto_rules_engine import AutoRulesEngine
            
            # Initialisiere Engine
            engine = AutoRulesEngine(user_id, master_key, db)
            
            stats = {
                "emails_processed": 0,
                "rules_triggered": 0,
                "actions_executed": 0,
                "errors": 0,
                "email_ids": []
            }
            
            # Verarbeite jede E-Mail
            for email_id in email_ids:
                try:
                    results = engine.process_email(email_id, dry_run=dry_run)
                    
                    for result in results:
                        if result.success:
                            stats["rules_triggered"] += 1
                            stats["actions_executed"] += len(result.actions_executed)
                        else:
                            stats["errors"] += 1
                    
                    stats["emails_processed"] += 1
                    stats["email_ids"].append(email_id)
                    
                except Exception as e:
                    logger.error(
                        f"Error processing email {email_id}: {type(e).__name__}: {e}"
                    )
                    stats["errors"] += 1
            
            # Commit wenn nicht dry-run
            if not dry_run:
                db.commit()
            
            logger.info(
                f"✅ [Task {self.request.id}] Rules applied: "
                f"{stats['emails_processed']} emails, "
                f"{stats['rules_triggered']} rules triggered, "
                f"{stats['actions_executed']} actions executed"
            )
            
            return stats
            
    except ImportError as e:
        logger.error(f"AutoRulesEngine import failed: {e}")
        raise Reject(f"AutoRulesEngine not available: {e}", requeue=False)
        
    except SQLAlchemyError as e:
        logger.warning(f"Database error in rule execution (will retry): {e}")
        raise self.retry(exc=e, countdown=60)
        
    except Exception as e:
        logger.error(f"Unexpected error in rule execution: {type(e).__name__}: {e}")
        raise Reject(f"Rule execution failed: {e}", requeue=False)


@celery_app.task(
    bind=True,
    base=BaseRuleTask,
    name="tasks.rule_execution.apply_rules_to_new_emails",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=600,  # 10 minutes hard limit
    soft_time_limit=540  # 9 minutes soft limit
)
def apply_rules_to_new_emails(
    self,
    user_id: int,
    service_token_id: int,
    since_minutes: int = 60,
    limit: int = 500
) -> Dict[str, Any]:
    """
    Verarbeitet neue E-Mails mit Auto-Rules (Batch-Modus).
    
    Typischerweise von Celery Beat aufgerufen (periodisch).
    
    Args:
        user_id: User ID
        service_token_id: ServiceToken ID für DEK-Abruf (Phase 2 Security)
        since_minutes: Zeitfenster in Minuten (default: 60)
        limit: Max. Anzahl E-Mails (default: 500)
        
    Returns:
        Dict mit Statistiken:
        {
            "emails_checked": int,
            "rules_triggered": int,
            "actions_executed": int,
            "errors": int,
            "processed_email_ids": List[int]
        }
        
    Raises:
        Reject: Bei kritischen Fehlern
        Retry: Bei vorübergehenden DB-Fehlern
    """
    if not user_id:
        raise Reject("Invalid parameter: user_id required", requeue=False)
    
    if not service_token_id:
        raise Reject("ServiceToken ID required for rule execution", requeue=False)
    
    logger.info(
        f"🔧 [Task {self.request.id}] Processing new emails: "
        f"user={user_id}, since_minutes={since_minutes}, limit={limit}"
    )
    
    SessionFactory = get_session_factory()
    
    try:
        with SessionFactory() as db:
            # Phase 2 Security: DEK aus ServiceToken laden
            master_key = _get_dek_from_service_token(service_token_id, db)
            
            # Import AutoRulesEngine (lazy import)
            from src.auto_rules_engine import AutoRulesEngine
            
            # Initialisiere Engine
            engine = AutoRulesEngine(user_id, master_key, db)
            
            # Batch-Verarbeitung
            stats = engine.process_new_emails(
                since_minutes=since_minutes,
                limit=limit
            )
            
            # Commit
            db.commit()
            
            logger.info(
                f"✅ [Task {self.request.id}] New emails processed: "
                f"{stats['emails_checked']} checked, "
                f"{stats['rules_triggered']} rules triggered"
            )
            
            return stats
            
    except ImportError as e:
        logger.error(f"AutoRulesEngine import failed: {e}")
        raise Reject(f"AutoRulesEngine not available: {e}", requeue=False)
        
    except SQLAlchemyError as e:
        logger.warning(f"Database error in batch rule execution (will retry): {e}")
        raise self.retry(exc=e, countdown=60)
        
    except Exception as e:
        logger.error(
            f"Unexpected error in batch rule execution: {type(e).__name__}: {e}"
        )
        raise Reject(f"Batch rule execution failed: {e}", requeue=False)


@celery_app.task(
    bind=True,
    base=BaseRuleTask,
    name="tasks.rule_execution.test_rule",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=60,  # 1 minute hard limit
    soft_time_limit=50
)
def test_rule(
    self,
    user_id: int,
    rule_id: int,
    email_id: int,
    master_key: str
) -> Dict[str, Any]:
    """
    Testet eine Regel auf einer E-Mail (Dry-Run).
    
    Für Rule-Preview im Frontend.
    
    Args:
        user_id: User ID
        rule_id: Regel-ID
        email_id: E-Mail-ID
        master_key: Master-Key für Entschlüsselung
        
    Returns:
        Dict mit Test-Ergebnis:
        {
            "matched": bool,
            "would_execute": List[str],  # Aktionen die ausgeführt würden
            "rule_name": str
        }
        
    Raises:
        Reject: Bei ungültigen Parametern
    """
    if not all([user_id, rule_id, email_id, master_key]):
        raise Reject("Invalid parameters: all fields required", requeue=False)
    
    logger.info(
        f"🧪 [Task {self.request.id}] Testing rule: "
        f"user={user_id}, rule={rule_id}, email={email_id}"
    )
    
    SessionFactory = get_session_factory()
    
    try:
        with SessionFactory() as db:
            from src.auto_rules_engine import AutoRulesEngine
            
            engine = AutoRulesEngine(user_id, master_key, db)
            
            # Dry-Run für spezifische Regel
            results = engine.process_email(
                email_id=email_id,
                dry_run=True,
                rule_id=rule_id
            )
            
            if results:
                result = results[0]
                return {
                    "matched": result.success,
                    "would_execute": result.actions_executed,
                    "rule_name": result.rule_name,
                    "rule_id": result.rule_id
                }
            else:
                return {
                    "matched": False,
                    "would_execute": [],
                    "rule_name": None,
                    "rule_id": rule_id
                }
                
    except ImportError as e:
        logger.error(f"AutoRulesEngine import failed: {e}")
        raise Reject(f"AutoRulesEngine not available: {e}", requeue=False)
        
    except Exception as e:
        logger.error(f"Error testing rule: {type(e).__name__}: {e}")
        raise Reject(f"Rule test failed: {e}", requeue=False)
