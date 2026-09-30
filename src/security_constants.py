"""Shared security constants and helpers."""

CLOUD_AI_PROVIDERS = frozenset({"openai", "anthropic", "google", "mistral"})


def is_cloud_ai_provider(provider: str | None) -> bool:
    """Return True if the provider sends data to an external cloud API."""
    if not provider:
        return False
    return provider.lower() in CLOUD_AI_PROVIDERS
