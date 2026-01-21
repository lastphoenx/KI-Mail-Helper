# src/celery_app.py
"""Celery Application für asynchrone Task-Verarbeitung.

⚠️  TEMPLATE FÜR MULTI-USER MIGRATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dies ist ein Production-ready Template für die Job-Orchestration
in einem Multi-User Szenario (0-20 Benutzer).

Implementierungs-Anleitung: doc/Multi-User/MULTI_USER_CELERY_LEITFADEN.md
Technische Analyse: doc/Multi-User/MULTI_USER_MIGRATION_REPORT.md

INHALT:
- Konfiguration für Redis als Message Broker
- PostgreSQL-Result-Backend
- Auto-discovery von Tasks in src/tasks/
- Production-ready Timeouts & Konfiguration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VERWENDUNG:
    1. .env updaten mit:
       - CELERY_BROKER_URL=redis://localhost:6379/1
       - CELERY_RESULT_BACKEND=redis://localhost:6379/2
    
    2. Worker starten:
       celery -A src.celery_app worker --loglevel=info
    
    3. Tasks definieren in src/tasks/ (siehe Beispiel: mail_sync_tasks.py)
    
    4. Aus Blueprint aufrufen:
       from src.tasks.mail_sync_tasks import sync_user_emails
       task = sync_user_emails.delay(user_id, account_id)
"""

import os
from pathlib import Path
from celery import Celery
from dotenv import load_dotenv

# Load .env.local first (priority), then .env (fallback)
# Gleiche Logik wie in app_factory.py
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env.local", override=True)
load_dotenv(project_root / ".env", override=False)

celery_app = Celery(
    "mail_helper",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Berlin",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=15 * 60,      # 15 Minuten Hard-Limit
    task_soft_time_limit=12 * 60,  # 12 Minuten Soft-Limit (für lokale LLMs)
    worker_prefetch_multiplier=1,
)

celery_app.autodiscover_tasks(["src.tasks"])


@celery_app.task(bind=True)
def debug_task(self):
    """Debugging-Task für Celery-Verifikation."""
    print(f"Request: {self.request!r}")


if __name__ == "__main__":
    celery_app.start()
