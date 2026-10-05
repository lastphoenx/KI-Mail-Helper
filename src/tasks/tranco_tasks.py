"""Tranco-Liste wöchentlich aktualisieren."""

from __future__ import annotations

import logging

from src.celery_app import celery_app
from src.services.tranco_update import update_tranco_database

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=3600)
def update_tranco_popularity_list(self, force: bool = True):
    import time

    t0 = time.monotonic()
    result = update_tranco_database(force=force)
    elapsed = round(time.monotonic() - t0, 1)
    logger.info(
        "Tranco Celery task finished in %ss ok=%s",
        elapsed,
        result.get("ok"),
    )
    if not result.get("ok") and not result.get("skipped"):
        logger.warning("Tranco update: %s", result)
    return result
