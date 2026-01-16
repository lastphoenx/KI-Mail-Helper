# src/tasks/mail_sync_tasks.py
"""Mail Sync Tasks - Asynchrone Email-Synchronisation.

⚠️  TEMPLATE FÜR MULTI-USER MIGRATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Beispiel-Implementierung für Celery Tasks mit:
- Business-Logic Separation (Services bleiben unverändert)
- User-Isolation & Security Checks
- Exponential Backoff Retry-Mechanismus
- Session-Management für Celery Worker

Implementierungs-Anleitung: doc/Multi-User/MULTI_USER_CELERY_LEITFADEN.md
Technische Analyse: doc/Multi-User/MULTI_USER_MIGRATION_REPORT.md

PATTERN:
1. Task erbt von celery_app.task
2. Session wird beim Start geholt, beim End geschlossen (finally!)
3. User & Account Ownership wird validiert (Security!)
4. Service wird aufgerufen mit validiertem User
5. Fehler werden mit Retry + Backoff gehandhabt
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VERWENDUNG (aus Blueprint):
    from src.tasks.mail_sync_tasks import sync_user_emails
    
    @blueprint.route("/sync", methods=["POST"])
    def start_sync():
        # ✅ Non-blocking: Task wird gequeued
        task = sync_user_emails.delay(
            user_id=current_user.id,
            account_id=request.json['account_id']
        )
        return jsonify({"task_id": task.id, "status": "queued"})
    
    @blueprint.route("/sync-status/<task_id>", methods=["GET"])
    def sync_status(task_id):
        # Task-Status abfragen
        result = celery_app.AsyncResult(task_id)
        return jsonify({
            "status": result.state,  # PENDING, STARTED, SUCCESS, FAILURE
            "result": result.result if result.ready() else None
        })
"""

import logging
from src.celery_app import celery_app
from src.helpers.database import get_session, get_user, get_mail_account

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="tasks.sync_user_emails",
)
def sync_user_emails(self, user_id: int, account_id: int, max_emails: int = 50):
    """
    Synchronisiere Emails für einen Mail-Account asynchron.
    
    Ersetzt die alte BackgroundJobQueue-Mechanik aus 14_background_jobs.py
    mit Celery für skalierbare, verteilte Job-Verarbeitung.
    
    Args:
        user_id: ID des Benutzers
        account_id: ID des Mail-Accounts
        max_emails: Maximale Anzahl zu fetchende Emails (default: 50)
    
    Returns:
        dict mit Status und Ergebnis:
        {
            "status": "success",
            "user_id": 1,
            "account_id": 2,
            "email_count": 42
        }
    
    Raises:
        Automatisch retry bei Fehler mit exponential backoff:
        - Attempt 1: 60s delay
        - Attempt 2: 120s delay
        - Attempt 3: 240s delay
        - Danach: FAILURE
    
    Security:
        ✅ User-Ownership wird validiert (user_id check)
        ✅ Account-Ownership wird validiert (account_id + user_id check)
        ✅ Keine Cross-User Data Access möglich
    """
    session = get_session()
    try:
        # ✅ SECURITY: Validate User Existence
        user = get_user(session, user_id)
        if not user:
            logger.error(f"User {user_id} not found")
            return {"status": "error", "message": "User not found"}
        
        # ✅ SECURITY: Validate Account Ownership
        account = get_mail_account(session, account_id, user_id)
        if not account:
            logger.error(f"Account {account_id} not owned by user {user_id}")
            return {"status": "error", "message": "Unauthorized"}
        
        logger.info(f"Starting email sync for user {user_id}, account {account_id}")
        
        # ✅ BUSINESS LOGIC: Rufe Service auf (unverändert vom alten Code)
        # Services haben KEINE Celery-Abhängigkeit und sind weiterhin
        # direkt testbar und einsetzbar
        #
        # ⚠️ HINWEIS: MailSyncService muss noch erstellt werden!
        # Extrahiere die Logik aus 14_background_jobs.py:_process_fetch_job()
        # in eine neue Datei: src/services/mail_sync_service.py
        from src.services.mail_sync_service import MailSyncService
        
        service = MailSyncService(session)
        result = service.sync_emails(user, account, max_mails=max_emails)
        
        logger.info(f"Successfully synced {result.get('email_count', 0)} emails")
        
        return {
            "status": "success",
            "user_id": user_id,
            "account_id": account_id,
            "email_count": result.get("email_count", 0),
        }
    
    except Exception as exc:
        logger.exception(f"Sync task failed for user {user_id}: {exc}")
        
        # Auto-retry mit exponential backoff
        # Attempt N: 60 * 2^N Sekunden Delay
        # Attempt 1: 60s, Attempt 2: 120s, Attempt 3: 240s
        retry_delay = 60 * (2 ** self.request.retries)
        
        raise self.retry(exc=exc, countdown=retry_delay)
    
    finally:
        session.close()


@celery_app.task(
    bind=True,
    max_retries=1,
    name="tasks.sync_all_accounts",
)
def sync_all_accounts(self, user_id: int):
    """
    Synchronisiere ALLE Accounts eines Users (triggered von User-Button).
    
    Nutzt sich selbst wiederholende Looping mit Exception-Handling pro Account.
    
    Args:
        user_id: ID des Benutzers
    
    Returns:
        dict mit Status und Zusammenfassung:
        {
            "status": "success",
            "user_id": 1,
            "accounts_synced": 3,
            "total_emails": 127
        }
    
    Security:
        ✅ Nur Accounts des Users werden synced
        ✅ Fehler bei einem Account stoppen nicht die ganzen anderen
    """
    session = get_session()
    try:
        # ✅ SECURITY: Validate User
        user = get_user(session, user_id)
        if not user:
            return {"status": "error", "message": "User not found"}
        
        logger.info(f"Syncing all accounts for user {user_id}")
        
        # ✅ BUSINESS LOGIC
        from src.services.mail_sync_service import MailSyncService
        
        service = MailSyncService(session)
        total_emails = 0
        
        # Iterate über alle Accounts des Users
        for account in user.mail_accounts:
            logger.info(f"Syncing account {account.id} ({account.email})")
            
            try:
                result = service.sync_emails(user, account)
                total_emails += result.get("email_count", 0)
            except Exception as e:
                # Fehler bei einem Account = nicht fatal
                # Weitermachen mit nächstem Account
                logger.error(f"Failed to sync account {account.id}: {e}")
                continue
        
        return {
            "status": "success",
            "user_id": user_id,
            "accounts_synced": len(user.mail_accounts),
            "total_emails": total_emails,
        }
    
    except Exception as exc:
        logger.exception(f"Sync all accounts failed: {exc}")
        raise self.retry(exc=exc, countdown=300)
    
    finally:
        session.close()
