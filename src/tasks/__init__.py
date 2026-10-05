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
Neue Module mit @celery_app.task zusätzlich hier importieren (Worker-Registrierung).
"""

from src.tasks.mail_sync_tasks import (
    sync_user_emails,
    sync_all_accounts,
)

from src.tasks.rule_execution_tasks import (
    apply_rules_to_emails,
    apply_rules_to_new_emails,
    apply_rules_manual_all,
    test_rule,
)

from src.tasks.sender_pattern_tasks import (
    scan_sender_patterns,
    cleanup_old_patterns,
    get_pattern_statistics,
    update_pattern_from_correction,
)

from src.tasks.email_processing_tasks import (
    reprocess_email_base,
    optimize_email_processing,
)

from src.tasks.reply_generation_tasks import (
    generate_reply_draft,
)

from src.tasks.training_tasks import (
    train_personal_classifier,
)

from src.tasks.maintenance_tasks import (
    cleanup_expired_service_tokens,
)

from src.tasks.audit_scam_tasks import (
    run_golden_benchmark_task,
)

from src.tasks.tranco_tasks import (
    update_tranco_popularity_list,
)

from src.tasks.brand_health_tasks import (
    retry_brand_health_rdap_task,
    run_brand_health_check_task,
)

from src.tasks.folder_audit_tasks import (
    run_folder_audit_scan_task,
)

from src.tasks.audit_contacts_tasks import (
    import_audit_known_contacts_task,
)

__all__ = [
    "sync_user_emails",
    "sync_all_accounts",
    "apply_rules_to_emails",
    "apply_rules_to_new_emails",
    "apply_rules_manual_all",
    "test_rule",
    "scan_sender_patterns",
    "cleanup_old_patterns",
    "get_pattern_statistics",
    "update_pattern_from_correction",
    "reprocess_email_base",
    "optimize_email_processing",
    "generate_reply_draft",
    "train_personal_classifier",
    "cleanup_expired_service_tokens",
    "run_golden_benchmark_task",
    "run_folder_audit_scan_task",
    "update_tranco_popularity_list",
    "retry_brand_health_rdap_task",
    "run_brand_health_check_task",
    "import_audit_known_contacts_task",
]
