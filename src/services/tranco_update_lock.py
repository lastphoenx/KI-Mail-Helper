"""Globaler Redis-Lock: höchstens ein Tranco-Update gleichzeitig."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_LOCK_KEY = "tranco:update:lock"
_LOCK_TTL = 3600


def _redis():
    import redis

    return redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def try_acquire_tranco_update_lock() -> bool:
    try:
        return bool(_redis().set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL))
    except Exception as exc:
        logger.warning("tranco update lock acquire: %s", exc)
        return True


def release_tranco_update_lock() -> None:
    try:
        _redis().delete(_LOCK_KEY)
    except Exception as exc:
        logger.debug("tranco update lock release: %s", exc)
