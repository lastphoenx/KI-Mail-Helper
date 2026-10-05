"""Max. ein laufender Marken-Domain-Health-Check pro User (Redis)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_LOCK_TTL = 900


def _redis():
    import redis

    return redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _key(user_id: int) -> str:
    return f"brand_health:lock:user_{user_id}"


def try_acquire_brand_health_check_lock(user_id: int) -> bool:
    try:
        return bool(_redis().set(_key(user_id), "1", nx=True, ex=_LOCK_TTL))
    except Exception as exc:
        logger.warning("brand health lock acquire: %s", exc)
        return True


def release_brand_health_check_lock(user_id: int) -> None:
    try:
        _redis().delete(_key(user_id))
    except Exception as exc:
        logger.debug("brand health lock release: %s", exc)
