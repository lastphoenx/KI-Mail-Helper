"""Shared Ollama timeout and inference defaults for HTTP clients and Celery tasks."""

from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _str_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


# Chat / analyze / reply (LocalOllamaClient)
OLLAMA_TIMEOUT = _int_env("OLLAMA_TIMEOUT", 900)

# Embeddings (cold start on remote Ollama can exceed 30s)
OLLAMA_EMBEDDING_TIMEOUT = _int_env("OLLAMA_EMBEDDING_TIMEOUT", 120)

# Celery: soft = OLLAMA_TIMEOUT, hard = +2 min cleanup buffer
OLLAMA_LLM_TASK_SOFT_LIMIT = OLLAMA_TIMEOUT
OLLAMA_LLM_TASK_HARD_LIMIT = OLLAMA_TIMEOUT + 120

# Per-request chat tuning (does not change EVO OLLAMA_CONTEXT_LENGTH global setting)
OLLAMA_CHAT_NUM_CTX = _int_env("OLLAMA_CHAT_NUM_CTX", 8192)
OLLAMA_CHAT_NUM_PREDICT = _int_env("OLLAMA_CHAT_NUM_PREDICT", 1024)
OLLAMA_CHAT_KEEP_ALIVE = _str_env("OLLAMA_CHAT_KEEP_ALIVE", "10m")

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


def ollama_chat_request_options() -> dict[str, int]:
    """Ollama /api/chat options for bounded inference (num_ctx caps KV per request)."""
    return {
        "num_ctx": OLLAMA_CHAT_NUM_CTX,
        "num_predict": OLLAMA_CHAT_NUM_PREDICT,
    }
