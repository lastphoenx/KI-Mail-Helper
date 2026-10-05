"""Celery task ownership tracking for IDOR-safe status polling."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

TASK_OWNER_KEY = "celery_task_owner:{task_id}"
TASK_OWNER_TTL_SECONDS = 86_400  # 24h


def _redis_client():
    import redis

    return redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def register_celery_task_owner(task_id: str, user_id: int) -> None:
    """Bind a Celery task ID to the user who queued it."""
    try:
        client = _redis_client()
        client.setex(TASK_OWNER_KEY.format(task_id=task_id), TASK_OWNER_TTL_SECONDS, user_id)
    except Exception as exc:
        logger.warning(f"register_celery_task_owner failed for {task_id}: {type(exc).__name__}")


def track_celery_task(async_result: Any, user_id: int) -> Any:
    """Register ownership and return the AsyncResult unchanged."""
    register_celery_task_owner(async_result.id, user_id)
    return async_result


def _user_id_from_celery_meta(celery_app, task_id: str) -> Optional[int]:
    try:
        meta = celery_app.backend.get_task_meta(task_id)
    except Exception:
        return None

    kwargs = meta.get("kwargs") or {}
    if "user_id" in kwargs:
        return int(kwargs["user_id"])

    args = meta.get("args") or []
    if args and isinstance(args[0], int):
        return int(args[0])

    result = meta.get("result")
    if isinstance(result, dict) and result.get("user_id") is not None:
        return int(result["user_id"])

    return None


def verify_celery_task_access(celery_app, task_id: str, user_id: int) -> bool:
    """Return True only if the task belongs to the given user."""
    try:
        client = _redis_client()
        stored = client.get(TASK_OWNER_KEY.format(task_id=task_id))
        if stored is not None:
            return int(stored) == user_id
    except Exception as exc:
        logger.debug(f"Redis task-owner lookup failed: {type(exc).__name__}")

    task_user_id = _user_id_from_celery_meta(celery_app, task_id)
    if task_user_id is None:
        return False
    return task_user_id == user_id
