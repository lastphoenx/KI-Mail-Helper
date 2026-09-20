# src/tasks/maintenance_tasks.py
"""
Celery Tasks: Periodische Wartung.

cleanup_expired_service_tokens: Loescht abgelaufene ServiceToken-Rows.

Sicherheitshintergrund (siehe docs/SECURITY.md Abschnitt 16 "ServiceToken"):
ServiceToken.encrypted_dek speichert den Data-Encryption-Key eines Users
IM KLARTEXT (Spaltenname ist historisch), damit Celery-Tasks ohne aktive
Flask-Session auf verschluesselte Mail-Daten zugreifen koennen. Der Schutz
besteht ausschliesslich in der kurzen Lebensdauer (TTL) dieser Zeilen.
Ohne einen periodischen Reaper wird abgelaufener Tokens nur beim naechsten
expliziten /logout geloescht - schliesst der User nur den Tab (der
haeufigere Fall), bleibt der Klartext-DEK bis zu TTL_DAYS in der DB stehen.
Ein DB-Dump in diesem Fenster hebelt Zero-Knowledge fuer den betroffenen
User vollstaendig aus, ganz ohne dessen Passwort zu kennen.
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC

from src.celery_app import celery_app
from src.helpers.database import get_session_factory

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def cleanup_expired_service_tokens(self) -> int:
    """Loescht alle ServiceToken-Rows mit expires_at in der Vergangenheit.

    Laeuft stuendlich via Celery Beat (siehe src/celery_app.py beat_schedule).
    Reine Wartungsaufgabe ohne User-Kontext - kein Ownership-Check noetig.
    """
    import importlib

    models = importlib.import_module(".02_models", "src")

    SessionFactory = get_session_factory()
    try:
        with SessionFactory() as db:
            deleted = (
                db.query(models.ServiceToken)
                .filter(models.ServiceToken.expires_at < datetime.now(UTC))
                .delete(synchronize_session=False)
            )
            db.commit()
            if deleted:
                logger.info(f"🧹 cleanup_expired_service_tokens: {deleted} abgelaufene ServiceTokens geloescht")
            return deleted
    except Exception as exc:
        logger.error(f"cleanup_expired_service_tokens fehlgeschlagen: {type(exc).__name__}: {exc}")
        raise self.retry(exc=exc)
