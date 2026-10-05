"""ServiceToken → DEK für Celery-Tasks (ohne Task-Modul-Imports)."""

from __future__ import annotations

import importlib
import logging

from src.helpers.service_token_storage import decrypt_service_token_dek

logger = logging.getLogger(__name__)


def get_dek_from_service_token(service_token_id: int, session) -> str:
    """Lädt DEK aus ServiceToken; aktualisiert last_verified_at."""
    models = importlib.import_module(".02_models", "src")

    service_token = session.query(models.ServiceToken).filter_by(
        id=service_token_id
    ).first()

    if not service_token:
        raise ValueError(f"ServiceToken {service_token_id} nicht gefunden")

    if not service_token.is_valid():
        raise ValueError(
            f"ServiceToken {service_token_id} abgelaufen "
            f"(expires: {service_token.expires_at})"
        )

    dek = decrypt_service_token_dek(service_token.encrypted_dek)
    service_token.mark_verified()
    session.commit()

    logger.info("DEK aus ServiceToken %s geladen", service_token_id)
    return dek


def delete_service_token(service_token_id: int, session) -> None:
    """Entfernt Token-Zeile inkl. Klartext-DEK nach Task-Ende."""
    if not service_token_id:
        return
    try:
        models = importlib.import_module(".02_models", "src")
        row = session.query(models.ServiceToken).filter_by(id=service_token_id).first()
        if row:
            session.delete(row)
            session.commit()
            logger.debug("ServiceToken %s gelöscht", service_token_id)
    except Exception as exc:
        session.rollback()
        logger.warning(
            "ServiceToken %s löschen fehlgeschlagen: %s",
            service_token_id,
            type(exc).__name__,
        )
