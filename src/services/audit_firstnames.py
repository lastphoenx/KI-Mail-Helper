"""BFS-Vornamen (global, einmal pro Worker geladen)."""

from __future__ import annotations

import logging
from typing import Optional, Set

logger = logging.getLogger(__name__)

_CACHE: Optional[Set[str]] = None


def get_firstname_set(db_session=None) -> Set[str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if db_session is None:
        return set()
    try:
        import importlib

        models = importlib.import_module(".02_models", "src")
        if not hasattr(models, "AuditFirstname"):
            _CACHE = set()
            return _CACHE
        rows = db_session.query(models.AuditFirstname.name_key).all()
        _CACHE = {r[0] for r in rows if r[0]}
    except Exception as e:
        logger.debug("firstname set not loaded: %s", e)
        _CACHE = set()
    return _CACHE


def invalidate_firstname_cache() -> None:
    global _CACHE
    _CACHE = None
