# =============================================================================
# PROVIDER_REGISTRY - Vereinfacht (Modelle werden dynamisch abgefragt)
# =============================================================================
# 
# Diese Version ersetzt die hardcodierten Modell-Listen.
# Modelle werden via src/04_model_discovery_dynamic.py dynamisch abgefragt.
#

PROVIDER_REGISTRY = {
    "ollama": {
        "label": "Ollama (lokal)",
        "is_cloud": False,
        "requires_api_key": False,
        "needs_cloud_sanitization": False,
        # Keine hardcodierten Modelle mehr!
        # Defaults werden dynamisch ermittelt.
    },
    "openai": {
        "label": "OpenAI (Cloud)",
        "is_cloud": True,
        "requires_api_key": True,
        "env_key": "OPENAI_API_KEY",
        "needs_cloud_sanitization": True,
    },
    "anthropic": {
        "label": "Anthropic Claude (Cloud)",
        "is_cloud": True,
        "requires_api_key": True,
        "env_key": "ANTHROPIC_API_KEY",
        "needs_cloud_sanitization": True,
    },
    "mistral": {
        "label": "Mistral AI (Cloud)",
        "is_cloud": True,
        "requires_api_key": True,
        "env_key": "MISTRAL_API_KEY",
        "needs_cloud_sanitization": True,
    },
}


# =============================================================================
# Dynamische resolve_model Funktion
# =============================================================================

def resolve_model(
    provider: str,
    requested_model: str | None = None,
    model_type: str = "chat"
) -> str:
    """
    Resolves das Modell für einen Provider - DYNAMISCH.
    
    Args:
        provider: KI-Provider (ollama, openai, etc.)
        requested_model: Gewünschtes Modell (optional)
        model_type: 'chat' oder 'embedding'
        
    Returns:
        Resolved model ID
    """
    # Explizites Modell hat Vorrang
    if requested_model and requested_model.strip():
        return requested_model.strip()
    
    # Dynamisch Default ermitteln
    from src.04_model_discovery_dynamic import get_default_model
    
    default = get_default_model(
        provider=provider,
        model_type=model_type,
        prefer_smallest=True  # Günstigstes/Kleinstes als Default
    )
    
    if default:
        return default
    
    # Ultimate Fallback (sollte nie erreicht werden)
    fallbacks = {
        "ollama": "llama3.2:1b",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-haiku-4-5-20251001",
        "mistral": "mistral-small-latest",
    }
    return fallbacks.get(provider.lower(), "unknown")


# =============================================================================
# Dynamische describe_provider_options Funktion
# =============================================================================

def describe_provider_options() -> list[dict]:
    """
    Gibt Provider-Optionen mit dynamisch abgefragten Modellen zurück.
    Für die Settings-Seite.
    """
    from src.04_model_discovery_dynamic import (
        get_available_models,
        get_default_model,
    )
    import os
    
    options = []
    
    for provider_key, cfg in PROVIDER_REGISTRY.items():
        # API-Key prüfen
        env_key = cfg.get("env_key")
        available = True
        if cfg.get("requires_api_key"):
            available = bool(os.getenv(env_key or ""))
        
        # Modelle dynamisch holen
        all_models = get_available_models(provider_key) if available else []
        chat_models = [m for m in all_models if m.get("type") == "chat"]
        embedding_models = [m for m in all_models if m.get("type") == "embedding"]
        
        options.append({
            "id": provider_key,
            "label": cfg["label"],
            
            # Dynamische Defaults
            "default_model_base": get_default_model(provider_key, "embedding") 
                                  or get_default_model(provider_key, "chat"),
            "default_model_optimize": get_default_model(provider_key, "chat", prefer_smallest=False),
            
            # Dynamische Modell-Listen
            "models": [m["id"] for m in all_models],
            "models_base": [m["id"] for m in embedding_models] or [m["id"] for m in chat_models[:2]],
            "models_optimize": [m["id"] for m in chat_models],
            
            # Strukturierte Modell-Infos für UI
            "model_details": all_models,
            
            # Meta
            "requires_api_key": cfg.get("requires_api_key", False),
            "env_key": env_key,
            "available": available and len(all_models) > 0,
        })
    
    return options
