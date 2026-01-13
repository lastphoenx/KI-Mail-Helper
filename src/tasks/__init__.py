# src/tasks/__init__.py
"""Celery Tasks - Asynchrone Verarbeitung für Mail Helper.

⚠️  TEMPLATE FÜR MULTI-USER MIGRATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dieses Verzeichnis enthält die Celery Task-Definitionen für
asynchrone, verteilte Verarbeitung in einem Multi-User System.

Implementierungs-Anleitung: doc/Multi-User/MULTI_USER_CELERY_LEITFADEN.md
Technische Analyse: doc/Multi-User/MULTI_USER_MIGRATION_REPORT.md

ARCHITEKTUR (Business-Logic Separation Pattern):
┌─────────────────────────────┐
│ Blueprint (HTTP-Layer)      │
│ email_actions.py            │
└────────────┬────────────────┘
             │ task.delay(...)
             ↓
┌─────────────────────────────┐
│ Task (Celery Wrapper)       │
│ mail_sync_tasks.py          │
│ - Session Management        │
│ - Error Handling            │
│ - User Ownership Check      │
└────────────┬────────────────┘
             │ service.method(...)
             ↓
┌─────────────────────────────┐
│ Service (Business Logic)    │
│ mail_sync_service.py        │
│ - Reine Business Logik      │
│ - Keine Celery-Abhängigkeit │
└─────────────────────────────┘

VORTEIL: Services bleiben unverändert, Tasks sind dünne Wrapper
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Task-Kategorien (zum Erweitern):
- mail_sync_tasks: Email-Synchronisation mit IMAP
- email_processing_tasks: AI-gestützte Email-Analyse
- embedding_tasks: Semantic Search Embeddings
- rule_execution_tasks: Auto-Rules Ausführung

Auto-discovered durch celery_app.autodiscover_tasks() in celery_app.py
"""

from src.tasks.mail_sync_tasks import (
    sync_user_emails,
    sync_all_accounts,
)

__all__ = [
    "sync_user_emails",
    "sync_all_accounts",
]
