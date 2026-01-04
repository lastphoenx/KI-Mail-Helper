import os
import requests
import importlib
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")


def get_ollama_models() -> List[Dict[str, str]]:
    """Gibt Ollama-Modelle mit Typ (embedding/chat) zurück"""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            models = []
            for m in resp.json().get("models", []):
                model_name = m.get("name", "")
                model_type = _detect_ollama_model_type(model_name)
                models.append(
                    {
                        "name": model_name,
                        "type": model_type,
                        "icon": "🔍" if model_type == "embedding" else "💬",
                    }
                )
            return models
    except requests.RequestException:
        pass
    return []


def _detect_ollama_model_type(model_name: str) -> str:
    """Erkennt Modelltyp: 'embedding' oder 'chat'"""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/show", json={"name": model_name}, timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            details = data.get("details", {})
            family = details.get("family", "").lower()
            if family == "bert" or "embedding" in family:
                return "embedding"
            return "chat"
    except requests.RequestException:
        pass
    return "unknown"


def get_openai_models() -> List[str]:
    """Gibt kuratierte OpenAI-Modelle aus PROVIDER_REGISTRY zurück (nicht von API)."""
    if not os.getenv("OPENAI_API_KEY"):
        return []

    try:
        ai_client = importlib.import_module("src.03_ai_client")
        registry = getattr(ai_client, "PROVIDER_REGISTRY", {})
        cfg = registry.get("openai", {})
        models = cfg.get("models", [])
        return [m for m in models if isinstance(m, str) and m.strip()]
    except (ImportError, AttributeError):
        return ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]


def get_anthropic_models() -> List[str]:
    """Gibt kuratierte Anthropic-Modelle aus PROVIDER_REGISTRY zurück."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return []

    try:
        ai_client = importlib.import_module("src.03_ai_client")
        registry = getattr(ai_client, "PROVIDER_REGISTRY", {})
        cfg = registry.get("anthropic", {})
        models = cfg.get("models", [])
        return [m for m in models if isinstance(m, str) and m.strip()]
    except (ImportError, AttributeError):
        return [
            "claude-sonnet-4-5-20250929",
            "claude-sonnet-4-20250514",
            "claude-opus-4-5-20251101",
            "claude-opus-4-1-20250805",
            "claude-haiku-4-5-20251001",
        ]


def get_mistral_models() -> List[str]:
    """Gibt kuratierte Mistral-Modelle aus PROVIDER_REGISTRY zurück."""
    if not os.getenv("MISTRAL_API_KEY"):
        return []

    try:
        ai_client = importlib.import_module("src.03_ai_client")
        registry = getattr(ai_client, "PROVIDER_REGISTRY", {})
        cfg = registry.get("mistral", {})
        models = cfg.get("models", [])
        return [m for m in models if isinstance(m, str) and m.strip()]
    except (ImportError, AttributeError):
        return ["mistral-large-latest", "mistral-small-latest", "mistral-tiny"]


def get_available_models(provider: str, kind: Optional[str] = None) -> List:
    """Gibt verfügbare Modelle für einen Provider zurück.

    Args:
        provider: 'ollama', 'openai', 'anthropic', 'mistral'
        kind: Optional 'base' oder 'optimize' - filtern nach PROVIDER_REGISTRY

    Returns:
        Für Ollama: Liste von Dicts mit {name, type, icon}
        Für andere: Liste von Strings
    """
    provider = provider.lower()

    models: List[Any] = []
    if provider == "ollama":
        models = get_ollama_models()
    elif provider == "openai":
        models = get_openai_models()
    elif provider == "anthropic":
        models = get_anthropic_models()
    elif provider == "mistral":
        models = get_mistral_models()

    if kind and kind.lower() in ("base", "optimize"):
        try:
            ai_client = importlib.import_module("src.03_ai_client")
            registry = getattr(ai_client, "PROVIDER_REGISTRY", {})
            cfg = registry.get(provider.lower(), {})

            if kind.lower() == "base":
                filtered = cfg.get("models_base", [])
            else:
                filtered = cfg.get("models_optimize", [])

            if not filtered:
                return models

            if (
                provider == "ollama"
                and isinstance(models, list)
                and models
                and isinstance(models[0], dict)
            ):
                return [m for m in models if m.get("name") in filtered]
            else:
                return [m for m in models if m in filtered]
        except (ImportError, AttributeError):
            pass

    return models


def get_available_providers() -> List[Dict[str, str]]:
    providers = []

    # Always include Ollama
    if get_ollama_models():
        providers.append(
            {
                "id": "ollama",
                "name": "⚡ Ollama (Local)",
                "description": "Fast local inference",
            }
        )

    # Include if key exists
    if os.getenv("OPENAI_API_KEY"):
        providers.append(
            {"id": "openai", "name": "🔷 OpenAI", "description": "GPT-4, GPT-3.5"}
        )

    if os.getenv("ANTHROPIC_API_KEY"):
        providers.append(
            {"id": "anthropic", "name": "🧠 Anthropic", "description": "Claude models"}
        )

    if os.getenv("MISTRAL_API_KEY"):
        providers.append(
            {"id": "mistral", "name": "✨ Mistral", "description": "Mistral AI models"}
        )

    return providers
