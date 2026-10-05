"""Shared Ollama timeout and inference defaults for HTTP clients and Celery tasks."""

from __future__ import annotations

import os
import re

OLLAMA_THINK_MODEL_RE = re.compile(r"qwen3", re.I)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _str_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Per-request chat tuning (does not change EVO OLLAMA_CONTEXT_LENGTH global setting)
OLLAMA_CHAT_NUM_CTX = _int_env("OLLAMA_CHAT_NUM_CTX", 8192)
OLLAMA_CHAT_NUM_PREDICT = _int_env("OLLAMA_CHAT_NUM_PREDICT", 1024)
OLLAMA_CHAT_KEEP_ALIVE = _str_env("OLLAMA_CHAT_KEEP_ALIVE", "10m")


def model_supports_ollama_think(model: str) -> bool:
    """Qwen3 on Ollama supports optional ``think`` (reasoning) mode."""
    return bool(model and OLLAMA_THINK_MODEL_RE.search(model))


def ollama_chat_think_enabled(model: str, *, explicit: bool | None = None) -> bool:
    """Whether to send think=true to Ollama /api/chat (Qwen3 only). Default off."""
    if not model_supports_ollama_think(model):
        return False
    if explicit is not None:
        return bool(explicit)
    return _bool_env("OLLAMA_CHAT_THINK", False)


def ollama_chat_payload_extras(
    model: str,
    *,
    think: bool | None = None,
    include_think: bool = False,
) -> dict:
    """Extra top-level /api/chat fields (``think`` nur wenn include_think)."""
    if include_think:
        if think is None:
            return {}
        return {"think": bool(think)}
    if not model_supports_ollama_think(model):
        return {}
    return {"think": ollama_chat_think_enabled(model, explicit=think)}


def ollama_chat_request_options(*, think_active: bool = False) -> dict[str, int]:
    """Ollama /api/chat options for bounded inference (num_ctx caps KV per request)."""
    num_predict = OLLAMA_CHAT_NUM_PREDICT
    if think_active:
        num_predict = _int_env("OLLAMA_CHAT_NUM_PREDICT_THINK", 4096)
    return {
        "num_ctx": OLLAMA_CHAT_NUM_CTX,
        "num_predict": num_predict,
    }


# Chat / analyze / reply (LocalOllamaClient)
OLLAMA_TIMEOUT = _int_env("OLLAMA_TIMEOUT", 900)

# Embeddings (cold start on remote Ollama can exceed 30s)
OLLAMA_EMBEDDING_TIMEOUT = _int_env("OLLAMA_EMBEDDING_TIMEOUT", 120)

# Celery: soft = OLLAMA_TIMEOUT, hard = +2 min cleanup buffer
OLLAMA_LLM_TASK_SOFT_LIMIT = OLLAMA_TIMEOUT
OLLAMA_LLM_TASK_HARD_LIMIT = OLLAMA_TIMEOUT + 120

# Classification prompt size (embedding/archiv paths keep full body limits)
CLASSIFICATION_BODY_MAX = _int_env("CLASSIFICATION_BODY_MAX", 6000)

_CLASSIFICATION_TRUNCATION_SUFFIX = "\n\n[... Text gekürzt für KI-Klassifizierung ...]"


def truncate_for_classification(body: str, max_len: int | None = None) -> str:
    """Limit body length sent to the classification LLM without affecting embeddings."""
    limit = max_len if max_len is not None else CLASSIFICATION_BODY_MAX
    if not body or len(body) <= limit:
        return body or ""
    if limit <= len(_CLASSIFICATION_TRUNCATION_SUFFIX):
        return body[:limit]
    return body[: limit - len(_CLASSIFICATION_TRUNCATION_SUFFIX)] + _CLASSIFICATION_TRUNCATION_SUFFIX
