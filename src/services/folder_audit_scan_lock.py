"""Ein Ordner-Audit-Scan pro User+Account (Redis)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_LOCK_TTL = 7200


def _redis():
    import redis

    return redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _key(user_id: int, account_id: int) -> str:
    return f"folder_audit:scan_lock:user_{user_id}:account_{account_id}"


def try_acquire_folder_audit_scan_lock(
    user_id: int, account_id: int, owner: str
) -> bool:
    try:
        client = _redis()
        return bool(
            client.set(_key(user_id, account_id), owner, nx=True, ex=_LOCK_TTL)
        )
    except Exception as exc:
        logger.warning("folder audit lock acquire: %s", exc)
        return True


def release_folder_audit_scan_lock(
    user_id: int, account_id: int, owner: str
) -> None:
    try:
        client = _redis()
        key = _key(user_id, account_id)
        current = client.get(key)
        if current and current.decode() == owner:
            client.delete(key)
    except Exception as exc:
        logger.debug("folder audit lock release: %s", exc)


def handoff_folder_audit_scan_lock(
    user_id: int, account_id: int, old_owner: str, new_owner: str
) -> None:
    try:
        client = _redis()
        key = _key(user_id, account_id)
        current = client.get(key)
        if current and current.decode() == old_owner:
            client.set(key, new_owner, ex=_LOCK_TTL)
    except Exception as exc:
        logger.warning("folder audit lock handoff: %s", exc)
