"""Shared Ollama timeout defaults for HTTP clients and Celery LLM tasks."""

from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Chat / analyze / reply (LocalOllamaClient)
OLLAMA_TIMEOUT = _int_env("OLLAMA_TIMEOUT", 900)

# Embeddings (cold start on remote Ollama can exceed 30s)
OLLAMA_EMBEDDING_TIMEOUT = _int_env("OLLAMA_EMBEDDING_TIMEOUT", 120)

# Celery: soft = OLLAMA_TIMEOUT, hard = +2 min cleanup buffer
OLLAMA_LLM_TASK_SOFT_LIMIT = OLLAMA_TIMEOUT
OLLAMA_LLM_TASK_HARD_LIMIT = OLLAMA_TIMEOUT + 120
