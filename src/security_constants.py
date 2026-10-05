"""Shared security constants and helpers."""

import os

CLOUD_AI_PROVIDERS = frozenset({"openai", "anthropic", "google", "mistral"})

_CLOUD_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


def is_cloud_ai_provider(provider: str | None) -> bool:
    """Return True if the provider sends data to an external cloud API."""
    if not provider:
        return False
    return provider.lower() in CLOUD_AI_PROVIDERS


def cloud_api_keys_configured() -> dict[str, bool]:
    """Ob Cloud-API-Keys im Prozess-Environment gesetzt sind (ohne Werte)."""
    out: dict[str, bool] = {}
    for provider_id, env_name in _CLOUD_ENV_KEYS.items():
        val = os.getenv(env_name)
        out[provider_id] = bool(val and str(val).strip())
    return out


def user_cloud_ai_context(user) -> dict:
    """Base/Optimize-Provider des Users + Cloud-Flags für UI."""
    base = (getattr(user, "preferred_ai_provider", None) or "ollama").lower()
    optimize = (
        getattr(user, "preferred_ai_provider_optimize", None) or "ollama"
    ).lower()
    cloud_base = is_cloud_ai_provider(base)
    cloud_optimize = is_cloud_ai_provider(optimize)
    labels = []
    if cloud_base:
        labels.append(f"Base: {base}")
    if cloud_optimize:
        labels.append(f"Optimize: {optimize}")
    return {
        "base_provider": base,
        "optimize_provider": optimize,
        "cloud_base": cloud_base,
        "cloud_optimize": cloud_optimize,
        "cloud_any": cloud_base or cloud_optimize,
        "cloud_provider_labels": labels,
        "cloud_keys_configured": cloud_api_keys_configured(),
    }
