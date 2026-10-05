"""Ollama Denk-Modus pro Modell (API /api/show + Cache)."""
from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from typing import Any, Literal, Optional

import requests

from src.ollama_timeouts import model_supports_ollama_think

logger = logging.getLogger(__name__)

ThinkMode = Literal["never", "toggle", "always", "unknown"]

_ALWAYS_NAME_RE = re.compile(r"thinking|[-_]think\b|\br1\b|deepseek-r", re.I)

_memory_cache: dict[tuple[str, str], "OllamaThinkCapability"] = {}
_CACHE_TTL = timedelta(days=7)


def clear_ollama_think_capability_cache() -> None:
    """Test-/Admin-Hook: In-Memory-Cache leeren."""
    _memory_cache.clear()


@dataclass(frozen=True)
class OllamaThinkCapability:
    mode: ThinkMode
    source: str
    model_digest: Optional[str] = None

    @property
    def ui_badge(self) -> str:
        if self.mode == "unknown":
            return "Fähigkeit unbekannt"
        if self.mode == "never":
            return "Denkt nie"
        if self.mode == "always":
            return "Denkt immer (langsam)"
        return "Denken umschaltbar"

    @property
    def ui_hint(self) -> str:
        if self.mode == "unknown":
            return "Ollama /api/show nicht erreichbar — Regler deaktiviert, kein Cache."
        if self.mode == "toggle":
            return "Denken an: gründlicher, typisch deutlich langsamer."
        if self.mode == "always":
            return "Modell nutzt Reasoning — kein schneller Modus verfügbar."
        return ""

    def sends_think_parameter(self, model: str) -> bool:
        """Ob /api/chat ein ``think``-Feld erhalten soll."""
        if self.mode == "unknown":
            return False
        if self.mode in ("toggle", "always"):
            return True
        if self.mode == "never" and model_supports_ollama_think(model):
            return True
        return False


def _default_base_url() -> str:
    return (
        os.getenv("OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_API_URL")
        or "http://127.0.0.1:11434"
    ).rstrip("/")


def _name_suggests_always_thinking(model: str) -> bool:
    return bool(model and _ALWAYS_NAME_RE.search(model))


def _capabilities_from_show(data: dict) -> set[str]:
    caps: set[str] = set()
    for key in ("capabilities",):
        raw = data.get(key)
        if isinstance(raw, list):
            caps.update(str(c).lower() for c in raw)
    details = data.get("details") or {}
    if isinstance(details, dict):
        raw = details.get("capabilities")
        if isinstance(raw, list):
            caps.update(str(c).lower() for c in raw)
    return caps


def _fetch_show(model: str, base_url: str) -> Optional[dict]:
    try:
        resp = requests.post(
            f"{base_url}/api/show",
            json={"name": model},
            timeout=8,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.debug("Ollama /api/show failed for %s: %s", model, type(exc).__name__)
    return None


def _digest_from_show(data: Optional[dict]) -> Optional[str]:
    if not data:
        return None
    digest = data.get("digest") or data.get("model_info", {}).get("digest")
    if digest:
        return str(digest)[:128]
    modelfile = data.get("modelfile") or ""
    if modelfile:
        return hashlib.sha256(modelfile.encode()).hexdigest()[:64]
    return None


def _load_from_db(db, base_url: str, model: str) -> Optional[OllamaThinkCapability]:
    try:
        import importlib

        models = importlib.import_module(".02_models", "src")
        row = (
            db.query(models.OllamaModelCapabilityCache)
            .filter_by(base_url=base_url, model_name=model)
            .first()
        )
        if not row:
            return None
        if row.checked_at and row.checked_at.replace(tzinfo=UTC) < datetime.now(UTC) - _CACHE_TTL:
            return None
        mode = row.think_mode
        if mode not in ("never", "toggle", "always"):
            return None
        return OllamaThinkCapability(
            mode=mode, source="db", model_digest=row.model_digest
        )
    except Exception:
        return None


def _save_to_db(db, base_url: str, model: str, cap: OllamaThinkCapability) -> None:
    if cap.mode == "unknown":
        return
    try:
        import importlib

        models = importlib.import_module(".02_models", "src")
        row = (
            db.query(models.OllamaModelCapabilityCache)
            .filter_by(base_url=base_url, model_name=model)
            .first()
        )
        now = datetime.now(UTC)
        if row:
            row.think_mode = cap.mode
            row.model_digest = cap.model_digest
            row.checked_at = now
        else:
            db.add(
                models.OllamaModelCapabilityCache(
                    base_url=base_url,
                    model_name=model,
                    think_mode=cap.mode,
                    model_digest=cap.model_digest,
                    checked_at=now,
                )
            )
        db.commit()
    except Exception as exc:
        logger.debug("Could not persist think capability: %s", type(exc).__name__)
        try:
            db.rollback()
        except Exception:
            pass


def _cache_and_return(
    cache_key: tuple[str, str],
    cap: OllamaThinkCapability,
    *,
    db_session=None,
    base_url: str,
    model: str,
) -> OllamaThinkCapability:
    _memory_cache[cache_key] = cap
    if db_session is not None:
        _save_to_db(db_session, base_url, model, cap)
    return cap


def detect_ollama_think_capability(
    model: str,
    base_url: Optional[str] = None,
    *,
    db_session=None,
) -> OllamaThinkCapability:
    """Erkennt never | toggle | always | unknown für ein Ollama-Modell."""
    model = (model or "").strip()
    url = (base_url or _default_base_url()).rstrip("/")
    if not model:
        return OllamaThinkCapability(mode="never", source="empty")

    cache_key = (url, model)
    cached = _memory_cache.get(cache_key)
    if cached:
        return cached

    if _name_suggests_always_thinking(model):
        cap = OllamaThinkCapability(mode="always", source="name")
        return _cache_and_return(
            cache_key, cap, db_session=db_session, base_url=url, model=model
        )

    if model_supports_ollama_think(model):
        cap = OllamaThinkCapability(mode="toggle", source="qwen3")
        return _cache_and_return(
            cache_key, cap, db_session=db_session, base_url=url, model=model
        )

    show = _fetch_show(model, url)
    if show is None:
        return OllamaThinkCapability(mode="unknown", source="show_unavailable")

    digest = _digest_from_show(show)
    if db_session is not None:
        db_cap = _load_from_db(db_session, url, model)
        if (
            db_cap
            and db_cap.model_digest
            and digest
            and db_cap.model_digest != digest
        ):
            _memory_cache.pop(cache_key, None)
        elif db_cap and digest and db_cap.model_digest == digest:
            _memory_cache[cache_key] = db_cap
            return db_cap
        elif db_cap and not digest:
            # Show ohne Digest — DB-Eintrag nicht blind vertrauen
            pass

    caps = _capabilities_from_show(show)

    if "thinking" in caps:
        cap = OllamaThinkCapability(mode="toggle", source="show", model_digest=digest)
    else:
        cap = OllamaThinkCapability(mode="never", source="show", model_digest=digest)

    return _cache_and_return(
        cache_key, cap, db_session=db_session, base_url=url, model=model
    )


def effective_ollama_think(
    model: str,
    user_wants_think: bool,
    *,
    base_url: Optional[str] = None,
    db_session=None,
    cap: Optional[OllamaThinkCapability] = None,
) -> bool:
    """Liefert den tatsächlichen think-Wert für /api/chat."""
    if cap is None:
        cap = detect_ollama_think_capability(
            model, base_url, db_session=db_session
        )
    if cap.mode in ("never", "unknown"):
        return False
    if cap.mode == "always":
        return True
    return bool(user_wants_think)


def think_mode_label(model: str, think_active: bool, *, base_url: Optional[str] = None) -> str:
    cap = detect_ollama_think_capability(model, base_url)
    if cap.mode == "always":
        return "mit Denken"
    if cap.mode in ("never", "unknown"):
        return "ohne Denken"
    return "mit Denken" if think_active else "ohne Denken"


def ollama_chat_think_extras(
    model: str,
    think_active: bool,
    *,
    base_url: Optional[str] = None,
    db_session=None,
    cap: Optional[OllamaThinkCapability] = None,
) -> dict:
    """think-Feld für /api/chat gemäss Capability (nicht nur Qwen3-Name)."""
    from src.ollama_timeouts import ollama_chat_payload_extras

    if cap is None:
        cap = detect_ollama_think_capability(
            model, base_url, db_session=db_session
        )
    include = cap.sends_think_parameter(model)
    return ollama_chat_payload_extras(
        model, think=think_active, include_think=include
    )
