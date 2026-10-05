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
            "claude-fable-5-1",
            "claude-sonnet-5-5",
            "claude-opus-5-5",
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
    """Gibt verfügbare Modelle für einen Provider zurück (Allowlist über model_allowlist)."""
    provider = provider.lower()
    role_map = {"base": "base", "optimize": "optimize"}
    role = role_map.get((kind or "").lower()) if kind else None

    try:
        discovery = importlib.import_module("src.04_model_discovery")
        models = discovery.get_models_for_ui(provider, role=role)
    except ImportError:
        models = []

    if (
        provider == "ollama"
        and isinstance(models, list)
        and models
        and isinstance(models[0], dict)
    ):
        return models

    if isinstance(models, list) and models and isinstance(models[0], dict):
        return [m.get("id") or m.get("name") for m in models if m.get("id") or m.get("name")]
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
    key_status = {}
    try:
        from src.security_constants import cloud_api_keys_configured

        key_status = cloud_api_keys_configured()
    except ImportError:
        key_status = {
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "mistral": bool(os.getenv("MISTRAL_API_KEY")),
        }

    if key_status.get("openai"):
        providers.append(
            {"id": "openai", "name": "🔷 OpenAI", "description": "GPT-4, GPT-3.5"}
        )

    if key_status.get("anthropic"):
        providers.append(
            {"id": "anthropic", "name": "🧠 Anthropic", "description": "Claude models"}
        )

    if key_status.get("mistral"):
        providers.append(
            {"id": "mistral", "name": "✨ Mistral", "description": "Mistral AI models"}
        )

    return providers
