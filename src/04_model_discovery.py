"""
Mail Helper - Dynamische Model Discovery
Fragt Modelle direkt von den Provider-APIs ab statt hardcodierte Listen.
"""

import os
import re
import requests
import logging
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache-Timeout für API-Abfragen (5 Minuten)
_model_cache: Dict[str, Tuple[datetime, List[Dict[str, Any]]]] = {}
CACHE_TTL = timedelta(minutes=5)


def _is_cache_valid(provider: str) -> bool:
    """Prüft ob der Cache noch gültig ist."""
    if provider not in _model_cache:
        return False
    cached_time, _ = _model_cache[provider]
    return datetime.now() - cached_time < CACHE_TTL


def _get_cached_models(provider: str) -> Optional[List[Dict[str, Any]]]:
    """Gibt gecachte Modelle zurück falls noch gültig."""
    if _is_cache_valid(provider):
        return _model_cache[provider][1]
    return None


def _cache_models(provider: str, models: List[Dict[str, Any]]) -> None:
    """Speichert Modelle im Cache."""
    _model_cache[provider] = (datetime.now(), models)


# =============================================================================
# OLLAMA - Vollständig dynamisch mit Typ-Erkennung
# =============================================================================

def get_ollama_models() -> List[Dict[str, Any]]:
    """
    Fragt Ollama-Modelle dynamisch ab mit Typ-Erkennung.
    
    Returns:
        Liste von Dicts: {
            "id": "llama3.2:1b",
            "name": "llama3.2:1b", 
            "display_name": "Llama 3.2 1B",
            "type": "chat" | "embedding",
            "size_bytes": 1300000000,
            "parameter_size": "1b"
        }
    """
    cached = _get_cached_models("ollama")
    if cached is not None:
        return cached
    
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        if resp.status_code != 200:
            logger.warning(f"Ollama /api/tags returned {resp.status_code}")
            return []
        
        models = []
        for m in resp.json().get("models", []):
            model_name = m.get("name", "")
            if not model_name:
                continue
            
            # Typ-Erkennung via /api/show
            model_type = _detect_ollama_model_type(base_url, model_name)
            
            # Parameter-Größe extrahieren (z.B. "1b", "3b", "7b")
            param_size = _extract_parameter_size(model_name)
            
            models.append({
                "id": model_name,
                "name": model_name,
                "display_name": _format_display_name(model_name),
                "type": model_type,
                "size_bytes": m.get("size", 0),
                "parameter_size": param_size,
                "modified_at": m.get("modified_at", ""),
                "supports_temperature": True,  # ✅ Ollama unterstützt immer temperature
            })
        
        # Sortieren: Embedding zuerst, dann nach Größe
        models.sort(key=lambda x: (
            0 if x["type"] == "embedding" else 1,
            _parse_param_size(x["parameter_size"])
        ))
        
        _cache_models("ollama", models)
        logger.info(f"✅ Ollama: {len(models)} Modelle gefunden")
        return models
        
    except requests.RequestException as e:
        logger.warning(f"⚠️ Ollama nicht erreichbar: {e}")
        return []


def _detect_ollama_model_type(base_url: str, model_name: str) -> str:
    """Erkennt Modelltyp via Ollama /api/show."""
    try:
        resp = requests.post(
            f"{base_url}/api/show",
            json={"name": model_name},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            details = data.get("details", {})
            family = details.get("family", "").lower()
            
            # Bekannte Embedding-Familien
            if family in ("bert", "nomic-bert") or "embedding" in family:
                return "embedding"
            
            # Modelfile-Check für zusätzliche Hinweise
            modelfile = data.get("modelfile", "").lower()
            if "embedding" in modelfile:
                return "embedding"
            
            return "chat"
    except requests.RequestException:
        pass
    
    # Fallback: Name-basierte Erkennung
    name_lower = model_name.lower()
    embedding_indicators = ["minilm", "bge", "e5", "embed", "nomic-embed"]
    if any(ind in name_lower for ind in embedding_indicators):
        return "embedding"
    
    return "chat"


def _extract_parameter_size(model_name: str) -> str:
    """Extrahiert Parameter-Größe aus Modellnamen (z.B. '1b', '7b', '70b')."""
    # Pattern: :1b, :3b, :7b, :70b, etc.
    match = re.search(r':(\d+\.?\d*[bm])', model_name.lower())
    if match:
        return match.group(1)
    
    # Pattern im Namen selbst: llama3.2-1b
    match = re.search(r'(\d+\.?\d*[bm])(?:[^a-z]|$)', model_name.lower())
    if match:
        return match.group(1)
    
    return "unknown"


def _parse_param_size(size_str: str) -> float:
    """Konvertiert Parameter-Größe zu Float für Sortierung."""
    if not size_str or size_str == "unknown":
        return float('inf')
    
    size_str = size_str.lower()
    try:
        if size_str.endswith('b'):
            return float(size_str[:-1])
        elif size_str.endswith('m'):
            return float(size_str[:-1]) / 1000
    except ValueError:
        pass
    return float('inf')


def _format_display_name(model_name: str) -> str:
    """Formatiert Modellnamen für Anzeige."""
    # "llama3.2:1b" -> "Llama 3.2 (1B)"
    name = model_name.replace(":", " (").replace("-", " ")
    if "(" in name and not name.endswith(")"):
        name += ")"
    return name.title()


# =============================================================================
# ANTHROPIC - Dynamische Abfrage
# =============================================================================

def get_anthropic_models() -> List[Dict[str, Any]]:
    """
    Fragt Anthropic-Modelle dynamisch via /v1/models ab.
    Alle Anthropic-Modelle sind Chat-Modelle.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return []
    
    cached = _get_cached_models("anthropic")
    if cached is not None:
        return cached
    
    try:
        resp = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            params={"limit": 100},
            timeout=10
        )
        
        if resp.status_code != 200:
            logger.warning(f"Anthropic /v1/models returned {resp.status_code}")
            return _anthropic_fallback()
        
        data = resp.json()
        models = []
        
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if not model_id:
                continue
            
            # Tier aus Modellnamen ableiten
            tier = _detect_anthropic_tier(model_id)
            
            models.append({
                "id": model_id,
                "name": model_id,
                "display_name": m.get("display_name", model_id),
                "type": "chat",  # Alle Anthropic-Modelle sind Chat
                "tier": tier,  # "haiku", "sonnet", "opus"
                "created_at": m.get("created_at", ""),
                "supports_temperature": True,  # ✅ Anthropic unterstützt immer temperature
            })
        
        # Sortieren: Haiku → Sonnet → Opus (günstig → teuer)
        tier_order = {"haiku": 0, "sonnet": 1, "opus": 2, "unknown": 3}
        models.sort(key=lambda x: tier_order.get(x["tier"], 3))
        
        _cache_models("anthropic", models)
        logger.info(f"✅ Anthropic: {len(models)} Modelle gefunden")
        return models
        
    except requests.RequestException as e:
        logger.warning(f"⚠️ Anthropic API nicht erreichbar: {e}")
        return _anthropic_fallback()


def _detect_anthropic_tier(model_id: str) -> str:
    """Erkennt Anthropic-Tier aus Modell-ID."""
    model_lower = model_id.lower()
    if "haiku" in model_lower or "fable" in model_lower:
        return "haiku"
    elif "sonnet" in model_lower:
        return "sonnet"
    elif "opus" in model_lower:
        return "opus"
    return "unknown"


def _anthropic_fallback() -> List[Dict[str, Any]]:
    """Minimaler Fallback falls API nicht erreichbar (Registry-Stand, Live-API bevorzugt)."""
    return [
        {
            "id": "claude-fable-5-1",
            "name": "claude-fable-5-1",
            "display_name": "Claude Fable 5.1",
            "type": "chat",
            "tier": "haiku",
            "supports_temperature": True,
        },
        {
            "id": "claude-sonnet-5-5",
            "name": "claude-sonnet-5-5",
            "display_name": "Claude Sonnet 5.5",
            "type": "chat",
            "tier": "sonnet",
            "supports_temperature": True,
        },
        {
            "id": "claude-opus-5-5",
            "name": "claude-opus-5-5",
            "display_name": "Claude Opus 5.5",
            "type": "chat",
            "tier": "opus",
            "supports_temperature": True,
        },
    ]


# =============================================================================
# OPENAI - Dynamische Abfrage mit Typ-Filterung
# =============================================================================

def get_openai_models() -> List[Dict[str, Any]]:
    """
    Fragt OpenAI-Modelle dynamisch via /v1/models ab.
    Filtert nach Chat-fähigen Modellen (gpt-*).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return []
    
    cached = _get_cached_models("openai")
    if cached is not None:
        return cached
    
    try:
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        
        if resp.status_code != 200:
            logger.warning(f"OpenAI /v1/models returned {resp.status_code}")
            return _openai_fallback()
        
        data = resp.json()
        models = []
        
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if not model_id:
                continue
            
            # Typ-Erkennung nach Namenskonvention
            model_type = _detect_openai_model_type(model_id)
            
            # Nur relevante Modelle (Chat + Embedding, keine Fine-tunes, etc.)
            if model_type not in ("chat", "embedding"):
                continue
            
            # ✅ Reasoning-Modelle (o1/o3/gpt-5) unterstützen KEINE custom temperature
            supports_temperature = not model_id.startswith(("o1-", "o3-", "gpt-5"))
            
            models.append({
                "id": model_id,
                "name": model_id,
                "display_name": _format_openai_display_name(model_id),
                "type": model_type,
                "owned_by": m.get("owned_by", ""),
                "created": m.get("created", 0),
                "supports_temperature": supports_temperature,
            })
        
        # Sortieren: Neueste zuerst, innerhalb nach Typ
        models.sort(key=lambda x: (
            0 if x["type"] == "embedding" else 1,
            -x.get("created", 0)
        ))
        
        _cache_models("openai", models)
        logger.info(f"✅ OpenAI: {len(models)} Modelle gefunden")
        return models
        
    except requests.RequestException as e:
        logger.warning(f"⚠️ OpenAI API nicht erreichbar: {e}")
        return _openai_fallback()


def _detect_openai_model_type(model_id: str) -> str:
    """Erkennt OpenAI-Modelltyp nach Namenskonvention."""
    model_lower = model_id.lower()
    
    # Embedding-Modelle
    if "embedding" in model_lower or model_lower.startswith("text-embedding"):
        return "embedding"
    
    # Chat-Modelle
    chat_prefixes = ("gpt-4.1", "gpt-4", "gpt-3.5", "gpt-5", "o1", "o3", "o4", "chatgpt")
    if any(model_lower.startswith(p) for p in chat_prefixes):
        return "chat"
    
    # Whisper, DALL-E, etc. ausschließen
    excluded_prefixes = ("whisper", "dall-e", "tts", "davinci", "babbage", "ada", "curie")
    if any(model_lower.startswith(p) for p in excluded_prefixes):
        return "other"
    
    return "other"


def _format_openai_display_name(model_id: str) -> str:
    """Formatiert OpenAI-Modellnamen für Anzeige."""
    from src.services.model_allowlist import format_model_display_name

    return format_model_display_name("openai", model_id, model_id)


def _openai_fallback() -> List[Dict[str, Any]]:
    """Minimaler Fallback falls API nicht erreichbar (Registry-Stand)."""
    return [
        {
            "id": "gpt-4.1-mini",
            "name": "gpt-4.1-mini",
            "display_name": "GPT-4.1 Mini",
            "type": "chat",
            "supports_temperature": True,
        },
        {
            "id": "gpt-4.1",
            "name": "gpt-4.1",
            "display_name": "GPT-4.1",
            "type": "chat",
            "supports_temperature": True,
        },
        {
            "id": "gpt-4o-mini",
            "name": "gpt-4o-mini",
            "display_name": "GPT-4o Mini",
            "type": "chat",
            "supports_temperature": True,
        },
    ]


# =============================================================================
# MISTRAL - Dynamische Abfrage
# =============================================================================

def get_mistral_models() -> List[Dict[str, Any]]:
    """Fragt Mistral-Modelle dynamisch ab."""
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        return []
    
    cached = _get_cached_models("mistral")
    if cached is not None:
        return cached
    
    try:
        resp = requests.get(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        
        if resp.status_code != 200:
            logger.warning(f"Mistral /v1/models returned {resp.status_code}")
            return _mistral_fallback()
        
        data = resp.json()
        models = []
        
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if not model_id:
                continue
            
            model_type = "embedding" if "embed" in model_id.lower() else "chat"
            
            models.append({
                "id": model_id,
                "name": model_id,
                "display_name": model_id.replace("-", " ").title(),
                "type": model_type,
            })
        
        _cache_models("mistral", models)
        logger.info(f"✅ Mistral: {len(models)} Modelle gefunden")
        return models
        
    except requests.RequestException as e:
        logger.warning(f"⚠️ Mistral API nicht erreichbar: {e}")
        return _mistral_fallback()


def _mistral_fallback() -> List[Dict[str, Any]]:
    """Minimaler Fallback (Registry-Stand; -latest zeigt auf aktuelle Mistral-Version)."""
    return [
        {
            "id": "mistral-small-latest",
            "name": "mistral-small-latest",
            "display_name": "Mistral Small",
            "type": "chat",
        },
        {
            "id": "mistral-large-latest",
            "name": "mistral-large-latest",
            "display_name": "Mistral Large",
            "type": "chat",
        },
    ]


# =============================================================================
# UNIFIED API - Hauptfunktionen
# =============================================================================

def get_available_models(
    provider: str,
    model_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Holt verfügbare Modelle für einen Provider.
    
    Args:
        provider: 'ollama', 'openai', 'anthropic', 'mistral'
        model_type: Optional Filter - 'chat', 'embedding', oder None für alle
        
    Returns:
        Liste von Model-Dicts mit mindestens {id, name, display_name, type}
    """
    provider = provider.lower()
    
    if provider == "ollama":
        models = get_ollama_models()
    elif provider == "openai":
        models = get_openai_models()
    elif provider == "anthropic":
        models = get_anthropic_models()
    elif provider == "mistral":
        models = get_mistral_models()
    else:
        logger.warning(f"Unbekannter Provider: {provider}")
        return []
    
    # Typ-Filter anwenden
    if model_type:
        models = [m for m in models if m.get("type") == model_type]

    if not models and provider in ("openai", "anthropic", "mistral"):
        models = _registry_models_for_provider(provider, model_type)

    return models


def get_models_for_ui(
    provider: str,
    role: Optional[str] = None,
    saved_model_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Modelle für UI: optional Rolle (base|optimize|embedding|audit) + Allowlist/Filter.
    Ohne Rolle: nur Snapshot-/Hilfsmodell-Filter (z. B. Mail-Detail).
    """
    from src.services.model_allowlist import (
        apply_standard_ui_filter,
        filter_models_for_role,
        format_model_display_name,
        role_from_query,
    )

    provider = provider.lower()
    normalized = role_from_query(role)

    if normalized == "embedding":
        models = get_available_models(provider, model_type="embedding")
    elif normalized in ("base", "optimize", "audit"):
        models = get_available_models(provider, model_type="chat")
    else:
        models = get_available_models(provider, model_type=None)

    if normalized:
        return filter_models_for_role(
            provider, normalized, models, saved_model_id=saved_model_id
        )

    filtered = apply_standard_ui_filter(provider, models)
    for m in filtered:
        mid = m.get("id") or m.get("name") or ""
        if mid:
            m["display_name"] = format_model_display_name(
                provider, mid, m.get("display_name")
            )
    return filtered


def _registry_models_for_provider(
    provider: str,
    model_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Kuratierte Modelle aus PROVIDER_REGISTRY wenn Live-API leer ist (Key gesetzt)."""
    import importlib

    try:
        ai_client = importlib.import_module("src.03_ai_client")
        cfg = ai_client.PROVIDER_REGISTRY.get(provider.lower(), {})
    except ImportError:
        return []

    if not cfg:
        return []

    env_key = cfg.get("env_key")
    if env_key and not os.getenv(env_key):
        return []

    result: List[Dict[str, Any]] = []
    id_source = cfg.get("models") or []
    if model_type == "embedding":
        id_source = cfg.get("models_embedding") or id_source
    for model_id in id_source:
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        mid = model_id.strip()
        if provider == "ollama":
            mtype = _detect_ollama_model_type(
                os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                mid,
            )
        else:
            mtype = "embedding" if "embed" in mid.lower() else "chat"
        if model_type and mtype != model_type:
            continue
        result.append(
            {
                "id": mid,
                "name": mid,
                "display_name": mid,
                "type": mtype,
            }
        )
    if result:
        logger.info(
            "Provider %s: %d Registry-Fallback-Modelle (Live-Liste leer)",
            provider,
            len(result),
        )
    return result


def get_default_model(
    provider: str,
    model_type: str = "chat",
    prefer_smallest: bool = True
) -> Optional[str]:
    """
    Gibt das Standard-Modell für einen Provider zurück.
    
    Args:
        provider: Provider-Name
        model_type: 'chat' oder 'embedding'
        prefer_smallest: True = günstigstes/kleinstes, False = bestes
        
    Returns:
        Model-ID oder None
    """
    models = get_available_models(provider, model_type=model_type)
    
    if not models:
        return None
    
    if prefer_smallest:
        # Erstes Modell (bereits sortiert: klein → groß)
        return models[0]["id"]
    else:
        # Letztes Modell (größtes/teuerstes)
        return models[-1]["id"]


def get_available_providers() -> List[Dict[str, Any]]:
    """
    Gibt alle verfügbaren Provider mit Status zurück.
    Prüft dynamisch die Erreichbarkeit.
    """
    providers = []
    
    # Ollama - immer versuchen
    ollama_models = get_ollama_models()
    if ollama_models:
        providers.append({
            "id": "ollama",
            "name": "⚡ Ollama (Lokal)",
            "description": f"{len(ollama_models)} Modelle verfügbar",
            "available": True,
            "model_count": len(ollama_models),
        })
    
    # Cloud-Provider
    cloud_providers = [
        ("openai", "🔷 OpenAI", "OPENAI_API_KEY", get_openai_models),
        ("anthropic", "🧠 Anthropic", "ANTHROPIC_API_KEY", get_anthropic_models),
        ("mistral", "✨ Mistral", "MISTRAL_API_KEY", get_mistral_models),
    ]
    
    for provider_id, name, env_key, fetch_func in cloud_providers:
        api_key = os.getenv(env_key)
        if api_key:
            models = fetch_func()
            providers.append({
                "id": provider_id,
                "name": name,
                "description": f"{len(models)} Modelle" if models else "API-Key gesetzt",
                "available": bool(models),
                "model_count": len(models),
            })
    
    return providers


def clear_model_cache(provider: Optional[str] = None) -> None:
    """Löscht den Model-Cache (für alle oder einen spezifischen Provider)."""
    global _model_cache
    if provider:
        _model_cache.pop(provider.lower(), None)
    else:
        _model_cache.clear()
    logger.info(f"🗑️ Model-Cache gelöscht: {provider or 'alle'}")


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    
    print("\n=== Verfügbare Provider ===")
    for p in get_available_providers():
        print(f"  {p['name']}: {p['description']}")
    
    print("\n=== Ollama Modelle ===")
    for m in get_ollama_models():
        print(f"  [{m['type']:9}] {m['id']} - {m.get('parameter_size', '?')}")
    
    print("\n=== Anthropic Modelle ===")
    for m in get_anthropic_models():
        print(f"  [{m['tier']:6}] {m['id']}")
    
    print("\n=== OpenAI Chat-Modelle ===")
    for m in get_available_models("openai", model_type="chat")[:5]:
        print(f"  {m['id']}")
    
    print("\n=== Defaults ===")
    print(f"  Ollama Embedding: {get_default_model('ollama', 'embedding')}")
    print(f"  Ollama Chat:      {get_default_model('ollama', 'chat')}")
    print(f"  Anthropic Chat:   {get_default_model('anthropic', 'chat')}")
