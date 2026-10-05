"""Temporäre Ablage für große Ordner-Audit-Scan-Ergebnisse (nicht im Celery-Result-Backend)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_KEY = "folder_audit:scan:{task_id}"


def _ttl_seconds() -> int:
    try:
        return int(os.getenv("FOLDER_AUDIT_SCAN_TTL", "1800"))
    except (TypeError, ValueError):
        return 1800


def _redis():
    import redis

    return redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def store_scan_payload(task_id: str, payload: dict) -> None:
    try:
        client = _redis()
        client.setex(
            _KEY.format(task_id=task_id),
            _ttl_seconds(),
            json.dumps(payload, ensure_ascii=False, default=str),
        )
    except Exception as exc:
        logger.error("folder_audit scan store failed for %s: %s", task_id, exc)
        raise


def pop_scan_payload(task_id: str) -> Optional[dict[str, Any]]:
    """Einmalig laden und Schlüssel löschen."""
    try:
        client = _redis()
        key = _KEY.format(task_id=task_id)
        pipe = client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        raw, _deleted = pipe.execute()
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as exc:
        logger.warning("folder_audit scan pop failed for %s: %s", task_id, exc)
        return None
