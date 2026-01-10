"""
Mail Helper - Embedding Clients
Unterstützt: Ollama (lokal), OpenAI (Cloud), Mistral (Cloud)
Anthropic hat KEINE eigene Embedding-API!
"""

import os
import requests
import logging
from abc import ABC, abstractmethod
from typing import List, Optional

logger = logging.getLogger(__name__)


class EmbeddingClient(ABC):
    """Abstraktes Interface für Embedding-Backends"""
    
    @abstractmethod
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generiert einen Embedding-Vektor für einen Text."""
        raise NotImplementedError
    
    @abstractmethod
    def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generiert Embeddings für mehrere Texte (effizienter)."""
        raise NotImplementedError
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Gibt die Dimension der Embeddings zurück."""
        raise NotImplementedError


# =============================================================================
# OLLAMA - Lokale Embeddings
# =============================================================================

class OllamaEmbeddingClient(EmbeddingClient):
    """Lokale Embeddings via Ollama."""
    
    # Bekannte Dimensionen für Ollama-Modelle
    MODEL_DIMENSIONS = {
        "all-minilm": 384,
        "all-minilm:22m": 384,
        "all-minilm:33m": 384,
        "nomic-embed-text": 768,
        "mxbai-embed-large": 1024,
        "bge-m3": 1024,
        "bge-large": 1024,
    }
    
    def __init__(
        self,
        model: str = "all-minilm:22m",
        base_url: Optional[str] = None
    ):
        self.model = model
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self._dimension: Optional[int] = None
    
    @property
    def embeddings_url(self) -> str:
        return f"{self.base_url}/api/embeddings"
    
    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # Lookup oder via Test-Request ermitteln
            for prefix, dim in self.MODEL_DIMENSIONS.items():
                if self.model.startswith(prefix):
                    self._dimension = dim
                    break
            else:
                # Fallback: Einmal testen
                test_emb = self.get_embedding("test")
                self._dimension = len(test_emb) if test_emb else 384
        return self._dimension
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        
        try:
            response = requests.post(
                self.embeddings_url,
                json={"model": self.model, "prompt": text.strip()},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.warning(f"Ollama Embedding Error: {response.status_code}")
                return None
            
            data = response.json()
            embedding = data.get("embedding")
            
            if embedding and isinstance(embedding, list):
                return embedding
            return None
            
        except requests.RequestException as e:
            logger.warning(f"Ollama Embedding Request failed: {e}")
            return None
    
    def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        # Ollama hat keinen Batch-Endpoint, also sequentiell
        return [self.get_embedding(text) for text in texts]


# =============================================================================
# OPENAI - Cloud Embeddings
# =============================================================================

class OpenAIEmbeddingClient(EmbeddingClient):
    """OpenAI Embeddings via /v1/embeddings."""
    
    API_URL = "https://api.openai.com/v1/embeddings"
    
    # Dimensionen der OpenAI-Modelle
    MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small"
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API Key fehlt")
        self.model = model
    
    @property
    def dimension(self) -> int:
        return self.MODEL_DIMENSIONS.get(self.model, 1536)
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        
        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": text.strip()
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.warning(f"OpenAI Embedding Error: {response.status_code} - {response.text[:200]}")
                return None
            
            data = response.json()
            embeddings = data.get("data", [])
            
            if embeddings and len(embeddings) > 0:
                return embeddings[0].get("embedding")
            return None
            
        except requests.RequestException as e:
            logger.warning(f"OpenAI Embedding Request failed: {e}")
            return None
    
    def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Batch-Request - OpenAI unterstützt bis zu 2048 Inputs pro Request."""
        if not texts:
            return []
        
        # Leere Texte filtern, Position merken
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text.strip())
                valid_indices.append(i)
        
        if not valid_texts:
            return [None] * len(texts)
        
        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": valid_texts
                },
                timeout=60
            )
            
            if response.status_code != 200:
                logger.warning(f"OpenAI Batch Embedding Error: {response.status_code}")
                return [None] * len(texts)
            
            data = response.json()
            embeddings_data = data.get("data", [])
            
            # Ergebnisse zusammenbauen
            results: List[Optional[List[float]]] = [None] * len(texts)
            for emb_data in embeddings_data:
                idx_in_batch = emb_data.get("index", 0)
                if idx_in_batch < len(valid_indices):
                    original_idx = valid_indices[idx_in_batch]
                    results[original_idx] = emb_data.get("embedding")
            
            return results
            
        except requests.RequestException as e:
            logger.warning(f"OpenAI Batch Embedding failed: {e}")
            return [None] * len(texts)


# =============================================================================
# MISTRAL - Cloud Embeddings
# =============================================================================

class MistralEmbeddingClient(EmbeddingClient):
    """Mistral Embeddings via /v1/embeddings."""
    
    API_URL = "https://api.mistral.ai/v1/embeddings"
    
    MODEL_DIMENSIONS = {
        "mistral-embed": 1024,
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "mistral-embed"
    ):
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("Mistral API Key fehlt")
        self.model = model
    
    @property
    def dimension(self) -> int:
        return self.MODEL_DIMENSIONS.get(self.model, 1024)
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        
        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": [text.strip()]
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.warning(f"Mistral Embedding Error: {response.status_code}")
                return None
            
            data = response.json()
            embeddings = data.get("data", [])
            
            if embeddings and len(embeddings) > 0:
                return embeddings[0].get("embedding")
            return None
            
        except requests.RequestException as e:
            logger.warning(f"Mistral Embedding Request failed: {e}")
            return None
    
    def get_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Batch-Request für Mistral."""
        if not texts:
            return []
        
        valid_texts = [t.strip() for t in texts if t and t.strip()]
        if not valid_texts:
            return [None] * len(texts)
        
        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": valid_texts
                },
                timeout=60
            )
            
            if response.status_code != 200:
                logger.warning(f"Mistral Batch Embedding Error: {response.status_code}")
                return [None] * len(texts)
            
            data = response.json()
            embeddings_data = data.get("data", [])
            
            # Mistral gibt Embeddings in Reihenfolge zurück
            results: List[Optional[List[float]]] = []
            emb_iter = iter(embeddings_data)
            
            for text in texts:
                if text and text.strip():
                    try:
                        emb_data = next(emb_iter)
                        results.append(emb_data.get("embedding"))
                    except StopIteration:
                        results.append(None)
                else:
                    results.append(None)
            
            return results
            
        except requests.RequestException as e:
            logger.warning(f"Mistral Batch Embedding failed: {e}")
            return [None] * len(texts)


# =============================================================================
# FACTORY - Unified Builder
# =============================================================================

# Provider-Konfiguration für Embeddings
EMBEDDING_PROVIDERS = {
    "ollama": {
        "label": "Ollama (lokal)",
        "client_class": OllamaEmbeddingClient,
        "default_model": "all-minilm:22m",
        "requires_api_key": False,
        "env_key": None,
    },
    "openai": {
        "label": "OpenAI",
        "client_class": OpenAIEmbeddingClient,
        "default_model": "text-embedding-3-small",
        "requires_api_key": True,
        "env_key": "OPENAI_API_KEY",
    },
    "mistral": {
        "label": "Mistral",
        "client_class": MistralEmbeddingClient,
        "default_model": "mistral-embed",
        "requires_api_key": True,
        "env_key": "MISTRAL_API_KEY",
    },
    # Anthropic hat KEINE Embedding-API!
}


def build_embedding_client(
    provider: str = "ollama",
    model: Optional[str] = None,
    **kwargs
) -> EmbeddingClient:
    """
    Factory-Funktion für Embedding-Clients.
    
    Args:
        provider: 'ollama', 'openai', oder 'mistral'
        model: Optional - spezifisches Modell
        **kwargs: Weitere Argumente (api_key, base_url, etc.)
    
    Returns:
        EmbeddingClient Instanz
        
    Raises:
        ValueError: Bei unbekanntem Provider oder fehlendem API-Key
    """
    provider_key = provider.lower()
    
    if provider_key not in EMBEDDING_PROVIDERS:
        raise ValueError(
            f"Unbekannter Embedding-Provider: {provider}. "
            f"Verfügbar: {list(EMBEDDING_PROVIDERS.keys())}. "
            f"Hinweis: Anthropic bietet KEINE eigene Embedding-API!"
        )
    
    config = EMBEDDING_PROVIDERS[provider_key]
    
    # API-Key prüfen
    if config["requires_api_key"]:
        api_key = kwargs.get("api_key") or os.getenv(config["env_key"] or "")
        if not api_key:
            raise ValueError(f"{config['label']} benötigt {config['env_key']}")
        kwargs["api_key"] = api_key
    
    # Modell setzen
    resolved_model = model or config["default_model"]
    
    # Client erstellen
    client_class = config["client_class"]
    return client_class(model=resolved_model, **kwargs)


def get_available_embedding_providers() -> List[dict]:
    """Gibt verfügbare Embedding-Provider zurück."""
    available = []
    
    for provider_id, config in EMBEDDING_PROVIDERS.items():
        is_available = True
        
        if config["requires_api_key"]:
            env_key = config["env_key"]
            is_available = bool(os.getenv(env_key or ""))
        
        available.append({
            "id": provider_id,
            "label": config["label"],
            "default_model": config["default_model"],
            "available": is_available,
            "requires_api_key": config["requires_api_key"],
        })
    
    return available


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=== Verfügbare Embedding-Provider ===")
    for p in get_available_embedding_providers():
        status = "✅" if p["available"] else "❌"
        print(f"  {status} {p['label']}: {p['default_model']}")
    
    print("\n=== Test: Ollama Embedding ===")
    try:
        client = build_embedding_client("ollama")
        emb = client.get_embedding("Dies ist ein Test.")
        if emb:
            print(f"  ✅ Dimension: {len(emb)}")
            print(f"  Erste 5 Werte: {emb[:5]}")
        else:
            print("  ❌ Kein Embedding erhalten")
    except Exception as e:
        print(f"  ❌ Fehler: {e}")
    
    print("\n=== Test: OpenAI Embedding ===")
    if os.getenv("OPENAI_API_KEY"):
        try:
            client = build_embedding_client("openai")
            emb = client.get_embedding("This is a test.")
            if emb:
                print(f"  ✅ Dimension: {len(emb)}")
            else:
                print("  ❌ Kein Embedding erhalten")
        except Exception as e:
            print(f"  ❌ Fehler: {e}")
    else:
        print("  ⏭️ OPENAI_API_KEY nicht gesetzt")
