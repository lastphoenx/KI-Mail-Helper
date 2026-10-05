"""Ordner-Audit Identitäts-LLM: User-DB mit .env-Fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from src.ollama_timeouts import model_supports_ollama_think


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _default_audit_model(provider: str = "ollama") -> str:
    if provider != "ollama":
        return (os.getenv("AUDIT_SCAM_LLM_MODEL") or "").strip() or "gpt-4o-mini"
    model = (os.getenv("AUDIT_SCAM_LLM_MODEL") or os.getenv("OLLAMA_CHAT_MODEL") or "").strip()
    if model:
        return model
    try:
        import importlib

        discovery = importlib.import_module("src.04_model_discovery")
        return discovery.get_default_model("ollama", "chat") or "qwen3.8:27b"
    except Exception:
        return "qwen3.8:27b"


AUDIT_SCAM_PROMPT_VERSION = 2

AUDIT_LLM_PROVIDERS = frozenset({"ollama", "openai", "anthropic", "mistral"})


@dataclass(frozen=True)
class AuditScamLlmConfig:
    enabled: bool
    provider: str
    model: str
    think: bool
    base_url: str
    prompt_version: int
    timeout: int
    configured_via: str  # "user" | "env"


def resolve_audit_scam_llm_config(user: Optional[Any] = None) -> AuditScamLlmConfig:
    """User-Spalten überschreiben .env; fehlende User-Felder → Env-Default."""
    provider = (os.getenv("AUDIT_SCAM_LLM_PROVIDER") or "ollama").strip().lower()
    if provider not in AUDIT_LLM_PROVIDERS:
        provider = "ollama"

    enabled = _bool_env("AUDIT_SCAM_LLM_ENABLED", True)
    model = _default_audit_model(provider)
    think = _bool_env("AUDIT_SCAM_LLM_THINK", False)
    configured_via = "env"

    if user is not None:
        user_enabled = getattr(user, "audit_scam_llm_enabled", None)
        user_model = (getattr(user, "audit_scam_llm_model", None) or "").strip()
        user_think = getattr(user, "audit_scam_llm_think", None)
        user_provider = (getattr(user, "audit_scam_llm_provider", None) or "").strip().lower()

        if user_enabled is not None or user_model or user_think is not None or user_provider:
            configured_via = "user"
        if user_enabled is not None:
            enabled = bool(user_enabled)
        if user_provider and user_provider in AUDIT_LLM_PROVIDERS:
            provider = user_provider
            if not user_model:
                model = _default_audit_model(provider)
        if user_model:
            model = user_model[:100]
        if user_think is not None:
            think = bool(user_think)

    if provider != "ollama" or not model_supports_ollama_think(model):
        think = False

    try:
        timeout = int(os.getenv("AUDIT_SCAM_LLM_TIMEOUT", "90"))
    except (TypeError, ValueError):
        timeout = 90

    base_url = (
        os.getenv("OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_API_URL")
        or "http://127.0.0.1:11434"
    ).rstrip("/")

    return AuditScamLlmConfig(
        enabled=enabled,
        provider=provider,
        model=model,
        think=think,
        base_url=base_url,
        prompt_version=AUDIT_SCAM_PROMPT_VERSION,
        timeout=timeout,
        configured_via=configured_via,
    )


def audit_scam_llm_progress_meta(cfg: AuditScamLlmConfig) -> dict:
    """Felder für Scan-Fortschritt (Celery meta / UI)."""
    mode = "think" if cfg.think else "no-think"
    return {
        "llm_provider": cfg.provider,
        "llm_model": cfg.model,
        "llm_mode": mode,
        "llm_prompt_version": cfg.prompt_version,
    }
