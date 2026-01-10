"""
Mail Helper - KI-Client (Interface + Backends)
Unterstützt: Ollama (lokal), OpenAI (Cloud), Anthropic (Cloud)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import json
import os
import requests
import logging
import time
from pathlib import Path

try:
    import joblib
except ImportError:
    joblib = None

from .known_newsletters import (
    classify_newsletter_confidence,
)

logger = logging.getLogger(__name__)


# Security Fix (Layer 3): Input Sanitization for Email Content
def _sanitize_email_input(text: str, max_length: int = 10000) -> str:
    """Sanitizes email content before sending to AI APIs.

    Prevents:
    - JSON injection via control characters
    - DoS via extremely long inputs
    - HTTP header injection
    """
    if not isinstance(text, str):
        return ""

    # Limit length to prevent DoS
    text = text[:max_length]

    # Remove control characters that could break JSON/HTTP
    import re

    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)

    return text.strip()


# Security Fix (Layer 3): Safe Error Logging (redact API keys)
def _safe_response_text(response) -> str:
    """Extracts response text safely without exposing API keys.

    Redacts patterns like:
    - sk-... (OpenAI)
    - ak-... (Anthropic)
    - Any 20+ char alphanumeric after 2-letter prefix
    """
    text = response.text[:200]
    import re

    # Redact potential API keys
    text = re.sub(r"\b[a-z]{2}-[a-zA-Z0-9]{20,}\b", "[REDACTED_KEY]", text)
    return text


class AIClient(ABC):
    """Abstraktes Interface für KI-Backends"""

    @abstractmethod
    def analyze_email(
        self, subject: str, body: str, language: str = "de", context: Optional[str] = None,
        **kwargs  # Phase X: Accept but ignore sender, user_id, db, user_enabled_booster
    ) -> Dict[str, Any]:
        """Analysiert eine Mail und liefert strukturierte Ergebnisse.
        
        Args:
            subject: Email subject
            body: Email body (sanitized)
            language: Target language for analysis
            context: Optional thread context (Phase E) with previous emails
            **kwargs: Phase X - sender, user_id, db, user_enabled_booster (only used in LocalOllamaClient)
        """
        raise NotImplementedError
    
    def generate_text(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        max_tokens: int = 1000
    ) -> str:
        """Generiert Text basierend auf Prompts (für Reply Draft Generator etc.).
        
        Args:
            system_prompt: System instruction für AI
            user_prompt: User's actual request/input
            max_tokens: Maximum tokens for response
            
        Returns:
            Generated text response
            
        Note: Default implementation raises NotImplementedError.
              Provider-specific implementations override this method.
        """
        raise NotImplementedError(f"{self.__class__.__name__} hat generate_text() nicht implementiert")


OLLAMA_SYSTEM_PROMPT = """
Du bist ein Assistent, der E-Mails analysiert.

AUFGABE:
- Du bekommst Betreff und Text einer E-Mail, bereits bereinigt und ggf. pseudonymisiert.
- Antworte IMMER als gültiges JSON-Objekt (ohne Erklärung, ohne zusätzlichen Text).
- Verwende GENAU diese Felder:

{
  "dringlichkeit": <Ganzzahl 1-3>,
  "wichtigkeit": <Ganzzahl 1-3>,
  "kategorie_aktion": "<aktion_erforderlich|dringend|nur_information>",
  "tags": ["<kurze Tags auf Deutsch>"],
  "suggested_tags": ["<kontextuelle Tags für Kategorisierung>"],
  "spam_flag": <true|false>,
  "summary_de": "<kurze Zusammenfassung auf Deutsch>",
  "text_de": "<vollständige deutsche Übersetzung des Inhalts>"
}

DEFINITIONEN:
- dringlichkeit:
  1 = kann warten
  2 = sollte bald erledigt werden
  3 = sehr dringend / Frist unmittelbar
- wichtigkeit:
  1 = eher unwichtig
  2 = wichtig
  3 = sehr wichtig / große Auswirkungen
- kategorie_aktion:
  - "aktion_erforderlich" = der Empfänger soll etwas tun (antworten, zahlen, Termin bestätigen, etc.).
  - "dringend" = aktion_erforderlich UND hoher Zeitdruck/Frist.
  - "nur_information" = reine Info, Newsletter, Werbung, Statusupdate.
- tags: Alte Feld (DEPRECATED), verwende suggested_tags stattdessen
- suggested_tags: 1-5 semantische Tags für Kategorisierung und Filterung
  Beispiele: "Rechnung", "Termin", "Bestellung", "Finanzen", "Reise", "Gesundheit", "Arbeit", "Wichtig"
  Halte sie kurz (1-2 Wörter), konsistent und auf Deutsch
- summary_de: 1–3 Sätze, kurz und klar.
- text_de: so vollständig wie nötig, aber in gut lesbarem Deutsch.

NEWSLETTER-ERKENNUNG (WICHTIG):
- Achte auf typische Newsletter-Signale: "Abmelden", "Unsubscribe", "Blog", "Podcast", "Trendthemen", "Diese Woche", "Monatliche Zusammenfassung", Marketing-Sprache wie "Jetzt kostenlos spielen"
- Newsletter, Werbung und Promotions: IMMER spam_flag=true, dringlichkeit=1, wichtigkeit=1-2, kategorie_aktion="nur_information"
- Marketing-Inhalte und Angebote, selbst mit zeitlichen Angaben ("Jetzt", "Diese Woche"), sind NICHT dringend!
- Sicherheitshinweise in Newslettern (z.B. "Zwei-Faktor-Auth") sind Informationen, nicht Handlungsaufforderungen.

WICHTIG:
- Antworte NUR mit JSON, ohne Erklärungstext.
- Verwende gültiges JSON (doppelte Anführungszeichen, keine Kommentare).
""".strip()


PROVIDER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "ollama": {
        "label": "Ollama (lokal)",
        "is_cloud": False,
        "supports_base": True,
        "supports_optimize": True,
        "default_model_base": "all-minilm:22m",
        "default_model_optimize": "llama3.2:1b",
        "models_base": ["all-minilm:22m", "llama3.2:1b", "phi3:mini"],
        "models_optimize": ["llama3.2:1b", "llama3.2:3b", "phi3:mini", "mistral"],
        "models": [
            "all-minilm:22m",
            "llama3.2",
            "llama3.2:1b",
            "llama3.2:3b",
            "phi3:mini",
            "mistral",
        ],
        "requires_api_key": False,
        "needs_cloud_sanitization": False,
    },
    "openai": {
        "label": "OpenAI (Cloud)",
        "is_cloud": True,
        "supports_base": True,
        "supports_optimize": True,
        "default_model_base": "gpt-4o-mini",
        "default_model_optimize": "gpt-4o-mini",
        "models_base": ["gpt-4o-mini", "gpt-4o"],
        "models_optimize": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ],  # Alle verfügbaren Modelle (werden nach base/optimize gefiltert)
        "requires_api_key": True,
        "env_key": "OPENAI_API_KEY",
        "needs_cloud_sanitization": True,
    },
    "anthropic": {
        "label": "Anthropic Claude (Cloud)",
        "is_cloud": True,
        "supports_base": True,
        "supports_optimize": True,
        "default_model_base": "claude-haiku-4-5-20251001",
        "default_model_optimize": "claude-sonnet-4-5-20250929",
        "models_base": [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-20250514",
        ],
        "models_optimize": [
            "claude-sonnet-4-5-20250929",
            "claude-sonnet-4-20250514",
            "claude-opus-4-5-20251101",
            "claude-opus-4-1-20250805",
            "claude-haiku-4-5-20251001",
        ],
        "models": [
            "claude-sonnet-4-5-20250929",
            "claude-sonnet-4-20250514",
            "claude-opus-4-5-20251101",
            "claude-opus-4-1-20250805",
            "claude-haiku-4-5-20251001",
        ],
        "requires_api_key": True,
        "env_key": "ANTHROPIC_API_KEY",
        "needs_cloud_sanitization": True,
    },
    "mistral": {
        "label": "Mistral AI (Cloud)",
        "is_cloud": True,
        "supports_base": True,
        "supports_optimize": True,
        "default_model_base": "mistral-small-latest",
        "default_model_optimize": "mistral-large-latest",
        "models_base": ["mistral-small-latest", "mistral-tiny"],
        "models_optimize": ["mistral-large-latest", "mistral-small-latest"],
        "models": ["mistral-large-latest", "mistral-small-latest", "mistral-tiny"],
        "requires_api_key": True,
        "env_key": "MISTRAL_API_KEY",
        "needs_cloud_sanitization": True,
    },
}


def _build_user_payload(subject: str, body: str, language: str) -> str:
    return f"Betreff:\n{subject}\n\nText (Sprache: {language}):\n{body}"


def _build_standard_messages(
    subject: str, body: str, language: str, context: Optional[str] = None
) -> List[Dict[str, str]]:
    """Build messages for AI analysis, optionally prepending thread context.
    
    Phase E: If context is provided, it's prepended to the user message to give
    the AI conversation history for better classification.
    """
    user_content = _build_user_payload(subject, body, language)
    
    # Phase E: Prepend thread context if available
    if context:
        user_content = f"{context}\n\n---\n\nCURRENT EMAIL TO ANALYZE:\n{user_content}"
    
    return [
        {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _clamp(value: Any, min_val: int, max_val: int) -> int:
    try:
        return max(min_val, min(int(value), max_val))
    except (ValueError, TypeError):
        return 2


KNOWN_NEWSLETTER_SENDERS = {
    "gmx",
    "newsletter",
    "promo",
    "noreply",
    "no-reply",
    "news",
    "marketing",
    "info@",
    "updates@",
    "alerts@",
    "notifications@",
}

NEWSLETTER_KEYWORDS = {
    "newsletter",
    "unsubscribe",
    "abmelden",
    "subscription",
    "promotion",
    "offer",
    "angebot",
    "bestellen",
    "jetzt kostenlos",
    "spielen",
    "gewinn",
    "gratis",
    "trend",
    "trending",
    "top artikel",
    "highlight",
    "blog",
    "podcast",
    "magazin",
    "zeitschrift",
    "e-paper",
    "digest",
    "kuratiert",
    "handverlesene",
    "wöchentlich",
    "monatlich",
    "täglich",
    "jeden",
    "diese woche",
    "this week",
    "latest",
    "breaking",
}


def _parse_model_json(response_text: str) -> Dict[str, Any]:
    text = (response_text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError as exc:
                logger.error("JSON Parse Error im Fallback: %s", exc)
                return {}
        return {}


def _validate_ai_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    validated: Dict[str, Any] = {
        "dringlichkeit": _clamp(parsed.get("dringlichkeit", 2), 1, 3),
        "wichtigkeit": _clamp(parsed.get("wichtigkeit", 2), 1, 3),
        "kategorie_aktion": parsed.get("kategorie_aktion", "aktion_erforderlich"),
        "tags": parsed.get("tags", []) if isinstance(parsed.get("tags"), list) else [],
        "suggested_tags": parsed.get("suggested_tags", []) if isinstance(parsed.get("suggested_tags"), list) else [],
        "spam_flag": bool(parsed.get("spam_flag", False)),
        "summary_de": parsed.get("summary_de", "Keine Zusammenfassung verfügbar"),
        "text_de": parsed.get("text_de", ""),
    }
    return validated


def _fallback_response() -> Dict[str, Any]:
    logger.warning(
        "Nutze Fallback-Response (LLM nicht verfügbar oder Fehler bei der Analyse)"
    )
    return {
        "dringlichkeit": 2,
        "wichtigkeit": 2,
        "kategorie_aktion": "aktion_erforderlich",
        "tags": ["Unbekannt"],
        "suggested_tags": [],
        "spam_flag": False,
        "summary_de": "Analyse fehlgeschlagen - LLM nicht verfügbar oder Fehler.",
        "text_de": "",
    }


class LocalOllamaClient(AIClient):
    """Lokales LLM via Ollama (Standard-Backend)"""

    DEFAULT_MODEL = "all-minilm:22m"  # Base-Pass Default

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.base_url = base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://127.0.0.1:11434"
        )
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "600"))
        self.model = (model or os.getenv("OLLAMA_MODEL") or self.DEFAULT_MODEL).strip()
        self._available_models = self._fetch_available_models()
        normalized_model = self.model.split(":", 1)[0].strip()
        if self._available_models and normalized_model not in self._available_models:
            logger.warning(
                "⚠️ Modell %s ist in Ollama nicht installiert. Bitte mit 'ollama pull %s' bereitstellen.",
                self.model,
                self.model,
            )
        self._is_embedding_model = self._detect_model_type()
        if self._is_embedding_model:
            logger.info(
                "🔍 Embedding-Modell erkannt: %s → nutze Heuristiken für Analyse",
                self.model,
            )
        self._load_classifiers()

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/api/chat"

    @property
    def embeddings_url(self) -> str:
        return f"{self.base_url}/api/embeddings"

    def _detect_model_type(self) -> bool:
        """Erkennt, ob das Modell ein Embedding-Modell (bert) oder Chat-LLM (llama/mistral) ist."""
        show_url = f"{self.base_url}/api/show"
        try:
            response = requests.post(show_url, json={"name": self.model}, timeout=5)
            if response.status_code == 200:
                data = response.json()
                details = data.get("details", {})
                family = details.get("family", "").lower()
                is_embedding = family == "bert" or "embedding" in family.lower()
                return is_embedding
        except Exception as e:
            logger.debug(
                "Fehler beim Erkennen des Modelltyps für %s: %s", self.model, e
            )
        return False

    def _load_classifiers(self) -> None:
        """Lädt trainierte sklearn-Klassifikatoren aus src/classifiers/*.pkl (optional).
        
        Phase 11b: Priorisiert SGD-Klassifikatoren (Online-Learning) vor RandomForest.
        """
        if not joblib:
            logger.debug(
                "joblib nicht verfügbar - Klassifikatoren können nicht geladen werden"
            )
            return

        classifier_dir = Path(__file__).resolve().parent / "classifiers"
        self._classifiers = {}
        self._label_encoders = {}
        self._sgd_classifiers = {}
        self._sgd_scalers = {}

        # Phase 11b: Lade SGD-Klassifikatoren (Online-Learning, priorisiert)
        sgd_types = ["dringlichkeit", "wichtigkeit", "spam"]
        for clf_type in sgd_types:
            sgd_path = classifier_dir / f"{clf_type}_sgd.pkl"
            scaler_path = classifier_dir / f"{clf_type}_scaler.pkl"
            
            if sgd_path.exists():
                try:
                    self._sgd_classifiers[clf_type] = self._load_classifier_safely(sgd_path)
                    if scaler_path.exists():
                        self._sgd_scalers[clf_type] = self._load_classifier_safely(scaler_path)
                    logger.debug(f"✅ SGD-Klassifikator geladen: {clf_type} (Online-Learning)")
                except Exception as e:
                    logger.warning(f"Fehler beim Laden von SGD {clf_type}: {e}")

        # Fallback: RandomForest Klassifikatoren (Batch-Training)
        classifier_files = {
            "dringlichkeit": "dringlichkeit_clf.pkl",
            "wichtigkeit": "wichtigkeit_clf.pkl",
            "kategorie": "kategorie_clf.pkl",
            "spam": "spam_clf.pkl",
        }

        for key, filename in classifier_files.items():
            # Überspringe wenn bereits SGD-Klassifikator geladen
            if key in self._sgd_classifiers:
                continue
                
            clf_path = classifier_dir / filename
            encoder_path = classifier_dir / f"{key}_encoder.pkl"

            if clf_path.exists():
                try:
                    # Security: Load with integrity check
                    self._classifiers[key] = self._load_classifier_safely(clf_path)
                    if encoder_path.exists():
                        self._label_encoders[key] = self._load_classifier_safely(
                            encoder_path
                        )
                    logger.debug(f"✅ Klassifikator geladen: {key}")
                except Exception as e:
                    logger.warning(f"Fehler beim Laden von {clf_path}: {e}")
            else:
                logger.debug(
                    f"Klassifikator nicht gefunden: {clf_path} → Heuristiken als Fallback"
                )

    def _load_classifier_safely(self, pkl_path: Path) -> Any:
        """Lädt Pickle-Files mit optionaler Integrity-Prüfung (Phase 9: Security Hardening).

        Security-Note: Pickle-Deserialization kann zu RCE führen wenn Attacker
        malicious .pkl Files in src/classifiers/ platziert. Optional kann via
        CLASSIFIER_HMAC_KEY Environment-Variable HMAC-Verification aktiviert werden.
        """
        import hashlib
        import hmac

        secret_key = os.getenv("CLASSIFIER_HMAC_KEY", "").encode()

        # Optional: HMAC verification wenn Secret Key gesetzt
        if secret_key:
            # Check für .sig File
            sig_path = pkl_path.with_suffix(".pkl.sig")
            if sig_path.exists():
                with open(pkl_path, "rb") as f:
                    file_data = f.read()
                with open(sig_path, "r") as f:
                    expected_hash = f.read().strip()

                computed_hash = hmac.new(
                    secret_key, file_data, hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(computed_hash, expected_hash):
                    raise ValueError(f"Classifier integrity check failed: {pkl_path}")
                logger.debug(f"🔒 Integrity verified: {pkl_path.name}")
            else:
                logger.warning(
                    f"⚠️ No signature file found for {pkl_path.name} (HMAC key set but no .sig)"
                )

        # Load pickle file
        return joblib.load(pkl_path)

    def _fetch_available_models(self) -> set[str]:
        """Fragt verfügbare Modelle ab und meldet die Erreichbarkeit des Servers."""
        tags_url = f"{self.base_url}/api/tags"
        try:
            response = requests.get(tags_url, timeout=2)
            if response.status_code != 200:
                logger.warning(
                    "⚠️ Ollama-Server antwortet mit Status %s", response.status_code
                )
                return set()

            logger.info("✅ Ollama-Server erreichbar: %s", self.base_url)
            data = response.json() or {}
            models: set[str] = set()
            for entry in data.get("models", []):
                name = entry.get("name") or entry.get("model")
                if not name:
                    continue
                normalized = name.split(":", 1)[0].strip()
                if normalized:
                    models.add(normalized)
            return models
        except Exception as exc:  # pragma: no cover - network only
            logger.warning("⚠️ Ollama-Server nicht erreichbar: %s", exc)
            return set()

    def _get_embedding(self, text: str) -> list[float] | None:
        """Ruft /api/embeddings auf und gibt den Vektor zurück.
        
        Phase 11a: Nutzt Chunking + Mean-Pooling für lange Texte.
        Statt 512 Zeichen Limit werden längere Mails in Chunks verarbeitet
        und die Embeddings gemittelt.
        """
        if not text or not text.strip():
            return None

        clean_text = text.strip()
        
        # Chunking für lange Texte (>512 Zeichen)
        chunks = self._chunk_text(clean_text, chunk_size=512, overlap=50)
        
        if len(chunks) == 1:
            # Kurzer Text: Direkt verarbeiten
            return self._get_single_embedding(chunks[0])
        else:
            # Langer Text: Mean-Pooling über alle Chunks
            return self._get_chunked_embedding(chunks)
    
    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
        """Teilt Text in überlappende Chunks für bessere Embedding-Qualität.
        
        Args:
            text: Eingabetext
            chunk_size: Maximale Chunk-Größe in Zeichen
            overlap: Überlappung zwischen Chunks für Kontexterhalt
            
        Returns:
            Liste von Text-Chunks
        """
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            
            # Versuche am Satzende oder Wortende zu schneiden
            if end < len(text):
                # Suche letztes Satzende im Chunk
                for sep in ['. ', '! ', '? ', '\n', ' ']:
                    last_sep = chunk.rfind(sep)
                    if last_sep > chunk_size // 2:  # Mindestens halber Chunk
                        chunk = chunk[:last_sep + 1]
                        end = start + last_sep + 1
                        break
            
            chunks.append(chunk.strip())
            start = end - overlap  # Überlappung für Kontext
            
            # Sicherheit: Maximal 20 Chunks (ca. 10KB Text)
            if len(chunks) >= 20:
                logger.debug(f"Chunking abgebrochen nach 20 Chunks ({len(text)} Zeichen)")
                break
        
        return chunks
    
    def _get_single_embedding(self, text: str) -> list[float] | None:
        """Holt ein einzelnes Embedding vom Ollama-Server."""
        try:
            response = requests.post(
                self.embeddings_url,
                json={"model": self.model, "prompt": text},
                timeout=30,
            )
            if response.status_code != 200:
                logger.debug(
                    "Embedding API Error (%s): %s",
                    response.status_code,
                    _safe_response_text(response),
                )
                return None
            data = response.json()
            embedding = data.get("embedding")
            if embedding and isinstance(embedding, list):
                return embedding
        except Exception as e:
            logger.debug("Fehler beim Embedding: %s", e)
        return None
    
    def _get_chunked_embedding(self, chunks: list[str]) -> list[float] | None:
        """Mean-Pooling: Mittelt Embeddings aller Chunks.
        
        Dies ermöglicht die Verarbeitung langer E-Mails,
        ohne Informationsverlust durch Truncation.
        """
        import numpy as np
        
        embeddings = []
        for i, chunk in enumerate(chunks):
            emb = self._get_single_embedding(chunk)
            if emb:
                embeddings.append(emb)
            else:
                logger.debug(f"Chunk {i+1}/{len(chunks)} Embedding fehlgeschlagen")
        
        if not embeddings:
            return None
        
        # Mean-Pooling: Durchschnitt aller Chunk-Embeddings
        embedding_array = np.array(embeddings)
        mean_embedding = np.mean(embedding_array, axis=0)
        
        logger.debug(f"📊 Chunked Embedding: {len(chunks)} Chunks → {len(mean_embedding)}D Vektor")
        return mean_embedding.tolist()

    def _analyze_with_embeddings(
        self, subject: str, body: str, sender: str = ""
    ) -> Dict[str, Any]:
        """
        Analysiert Mail mit Embedding + Heuristiken/ML-Klassifikatoren (schnell, CPU-ok).
        Nutzt trainierte Klassifikatoren, falls vorhanden; sonst Heuristiken.
        """
        text = f"{subject} {body}".lower()
        embedding = self._get_embedding(f"{subject}\n{body}")

        dringlichkeit = 1
        wichtigkeit = 1
        kategorie_aktion = "nur_information"
        spam_flag = False
        tags = []

        newsletter_confidence = classify_newsletter_confidence(sender, subject, body)
        if newsletter_confidence >= 0.5:
            spam_flag = True
            tags.append("Newsletter/Promotion")
            dringlichkeit = 1
            wichtigkeit = 1
            kategorie_aktion = "nur_information"
            if newsletter_confidence >= 0.8:
                logger.debug(
                    f"Newsletter erkannt (Konfidenz={newsletter_confidence:.1%}): {sender} - {subject[:50]}"
                )
                embedding = None
            return {
                "dringlichkeit": _clamp(dringlichkeit, 1, 3),
                "wichtigkeit": _clamp(wichtigkeit, 1, 3),
                "kategorie_aktion": kategorie_aktion,
                "tags": tags,
                "suggested_tags": tags,  # Phase 11: Auch suggested_tags für Embedding-Analyse
                "spam_flag": spam_flag,
                "summary_de": subject[:100] if subject else "Keine Zusammenfassung",
                "text_de": body[:500] if body else "",
            }

        if embedding and self._classifiers:
            import numpy as np

            embedding_array = np.array(embedding).reshape(1, -1)

            if "dringlichkeit" in self._classifiers:
                try:
                    pred = self._classifiers["dringlichkeit"].predict(embedding_array)[
                        0
                    ]
                    dringlichkeit = _clamp(pred, 1, 3)
                except Exception as e:
                    logger.debug(f"Fehler bei dringlichkeit-Klassifikation: {e}")

            if "wichtigkeit" in self._classifiers:
                try:
                    pred = self._classifiers["wichtigkeit"].predict(embedding_array)[0]
                    wichtigkeit = _clamp(pred, 1, 3)
                except Exception as e:
                    logger.debug(f"Fehler bei wichtigkeit-Klassifikation: {e}")

            if "spam" in self._classifiers:
                try:
                    pred = self._classifiers["spam"].predict(embedding_array)[0]
                    spam_flag = bool(pred)
                except Exception as e:
                    logger.debug(f"Fehler bei spam-Klassifikation: {e}")

        # Phase 11b: SGD-Klassifikatoren (Online-Learning) haben Priorität
        if embedding and hasattr(self, '_sgd_classifiers') and self._sgd_classifiers:
            import numpy as np
            
            embedding_array = np.array(embedding).reshape(1, -1)
            
            for clf_type in ["dringlichkeit", "wichtigkeit", "spam"]:
                if clf_type not in self._sgd_classifiers:
                    continue
                    
                clf = self._sgd_classifiers[clf_type]
                scaler = self._sgd_scalers.get(clf_type)
                
                # Prüfen ob Modell trainiert wurde
                if not hasattr(clf, 'classes_') or clf.classes_ is None:
                    continue
                
                try:
                    X = embedding_array.copy()
                    if scaler and hasattr(scaler, 'mean_') and scaler.mean_ is not None:
                        X = scaler.transform(X)
                    
                    pred = clf.predict(X)[0]
                    
                    if clf_type == "dringlichkeit":
                        dringlichkeit = _clamp(int(pred), 1, 3)
                        logger.debug(f"🧠 SGD Dringlichkeit: {dringlichkeit}")
                    elif clf_type == "wichtigkeit":
                        wichtigkeit = _clamp(int(pred), 1, 3)
                        logger.debug(f"🧠 SGD Wichtigkeit: {wichtigkeit}")
                    elif clf_type == "spam":
                        spam_flag = bool(pred)
                        logger.debug(f"🧠 SGD Spam: {spam_flag}")
                        
                except Exception as e:
                    logger.debug(f"SGD {clf_type} Fehler: {e}")

        if not self._classifiers or not embedding:
            keywords_spam_high = [
                "unsubscribe",
                "no-reply",
                "newsletter",
                "promotion",
                "angebot",
                "gmx games",
                "gewinn",
                "spielen",
            ]
            keywords_spam_medium = ["game", "kostenlos", "gratis"]
            keywords_dringend = ["urgent", "sofort", "deadline"]
            keywords_aktion_required = [
                "bezahle",
                "überweise",
                "zahlung erforderlich",
                "payment required",
            ]
            keywords_rechnung = ["rechnung", "invoice", "rechnungsbetrag"]
            keywords_sicherheit_critical = [
                "passwort ändern",
                "password reset",
                "account locked",
                "verify now",
                "konto gesperrt",
            ]

            newsletter_keyword_count = sum(
                1 for kw in NEWSLETTER_KEYWORDS if kw in text
            )
            has_unsubscribe = "unsubscribe" in text or "abmelden" in text
            has_spam_keywords = any(kw in text for kw in keywords_spam_high)

            # Newsletter (mit Unsubscribe) = legitim, KEIN Spam
            if has_unsubscribe:
                tags.append("Newsletter/Promotion")
                dringlichkeit = 1
                wichtigkeit = 1
                kategorie_aktion = "nur_information"
                # spam_flag bleibt False - Newsletter sind kein Spam!
            elif newsletter_keyword_count >= 2:
                tags.append("Newsletter/Promotion")
                dringlichkeit = 1
                wichtigkeit = 1
                kategorie_aktion = "nur_information"
            # Echter Spam (ohne Unsubscribe-Option)
            elif has_spam_keywords:
                spam_flag = True
                tags.append("Spam")
                dringlichkeit = 1
                wichtigkeit = 1
                kategorie_aktion = "nur_information"
            elif any(kw in text for kw in keywords_spam_medium):
                wichtigkeit = max(wichtigkeit, 1)
                tags.append("Newsletter/Promotion")

            if not spam_flag:
                if any(kw in text for kw in keywords_dringend):
                    dringlichkeit = max(dringlichkeit, 3)
                    tags.append("Dringend")

                if any(kw in text for kw in keywords_aktion_required):
                    kategorie_aktion = "aktion_erforderlich"
                    dringlichkeit = max(dringlichkeit, 2)
                    wichtigkeit = max(wichtigkeit, 3)
                    tags.append("Handlung erforderlich")

                if any(kw in text for kw in keywords_rechnung):
                    kategorie_aktion = "dringend"
                    wichtigkeit = max(wichtigkeit, 3)
                    dringlichkeit = max(dringlichkeit, 2)
                    tags.append("Finanziell")

                if any(kw in text for kw in keywords_sicherheit_critical):
                    dringlichkeit = max(dringlichkeit, 3)
                    wichtigkeit = max(wichtigkeit, 3)
                    tags.append("Sicherheit")

        if not tags:
            tags = ["Klassifiziert"] if self._classifiers else ["Allgemein"]

        return {
            "dringlichkeit": _clamp(dringlichkeit, 1, 3),
            "wichtigkeit": _clamp(wichtigkeit, 1, 3),
            "kategorie_aktion": kategorie_aktion,
            "tags": tags,
            "suggested_tags": tags,  # Phase 11: Auch suggested_tags für Embedding-Analyse
            "spam_flag": spam_flag,
            "summary_de": subject[:100] if subject else "Keine Zusammenfassung",
            "text_de": body[:500] if body else "",
        }

    def _convert_booster_to_llm_format(self, booster_result: Dict, subject: str, body: str) -> Dict:
        """
        Konvertiert UrgencyBooster-Format in Standard-LLM-Format.
        
        UrgencyBooster gibt:
        - urgency_score: 0.0-1.0
        - importance_score: 0.0-1.0
        - category: "dringend", "aktion_erforderlich", "nur_information"
        
        LLM erwartet:
        - dringlichkeit: 1-3 (integer)
        - wichtigkeit: 1-3 (integer)
        - kategorie_aktion: string
        """
        # Konvertiere Scores (0.0-1.0) zu Levels (1-3)
        urgency_score = booster_result.get('urgency_score', 0.0)
        importance_score = booster_result.get('importance_score', 0.0)
        
        # Mapping: 0.0-0.33 → 1, 0.33-0.66 → 2, 0.66-1.0 → 3
        dringlichkeit = 1 if urgency_score < 0.33 else (2 if urgency_score < 0.66 else 3)
        wichtigkeit = 1 if importance_score < 0.33 else (2 if importance_score < 0.66 else 3)
        
        # Kategorie ist bereits im richtigen Format
        kategorie = booster_result.get('category', 'nur_information')
        
        # Erstelle Summary basierend auf Signalen
        signals = booster_result.get('signals', {})
        summary_parts = []
        
        if signals.get('invoice_detected'):
            summary_parts.append("Rechnung erkannt")
        if signals.get('time_pressure') and signals.get('deadline_hours'):
            hours = signals['deadline_hours']
            if hours < 24:
                summary_parts.append(f"Deadline in {hours}h")
            elif hours < 48:
                summary_parts.append("Deadline morgen")
        if signals.get('money_amount'):
            amount = signals['money_amount']
            summary_parts.append(f"Betrag: {amount:.2f}€")
        if signals.get('action_verbs'):
            verbs = signals['action_verbs'][:2]  # Erste 2
            summary_parts.append(f"Aktion: {', '.join(verbs)}")
        
        if summary_parts:
            summary = f"{subject[:50]}: {' | '.join(summary_parts)}"
        else:
            summary = subject[:100] if subject else "Keine Zusammenfassung"
        
        return {
            "dringlichkeit": dringlichkeit,
            "wichtigkeit": wichtigkeit,
            "kategorie_aktion": kategorie,
            "tags": [],  # Leer - Tag-Manager übernimmt Embedding-basierte Zuordnung
            "suggested_tags": [],  # Leer - Tag-Manager übernimmt Embedding-basierte Zuordnung
            "spam_flag": False,  # Trusted senders sind nie Spam
            "summary_de": summary,
            "text_de": body[:500] if body else "",
            "_used_booster": True,  # Marker für Processing: Wurde mit UrgencyBooster verarbeitet
        }

    def _convert_hybrid_to_llm_format(self, pipeline_result: Dict, subject: str, body: str, confidence: float) -> Dict:
        """
        Konvertiert Hybrid Pipeline Format in Standard-LLM-Format.
        
        Hybrid Pipeline gibt:
        - wichtigkeit: 1-5 (integer)
        - dringlichkeit: 1-5 (integer)
        - spacy_details: Dict mit Detector-Ergebnissen
        - ensemble_stats: Dict mit Learning-Stats
        
        LLM erwartet:
        - dringlichkeit: 1-3 (integer)
        - wichtigkeit: 1-3 (integer)
        - kategorie_aktion: string
        """
        # Konvertiere 1-5 Skala zu 1-3 Skala
        wichtigkeit_5 = pipeline_result.get('wichtigkeit', 3)
        dringlichkeit_5 = pipeline_result.get('dringlichkeit', 3)
        
        # Mapping: 1-2 → 1, 3 → 2, 4-5 → 3
        wichtigkeit = 1 if wichtigkeit_5 <= 2 else (2 if wichtigkeit_5 == 3 else 3)
        dringlichkeit = 1 if dringlichkeit_5 <= 2 else (2 if dringlichkeit_5 == 3 else 3)
        
        # Kategorie basierend auf Dringlichkeit
        if dringlichkeit >= 3:
            kategorie = "dringend"
        elif dringlichkeit >= 2:
            kategorie = "aktion_erforderlich"
        else:
            kategorie = "nur_information"
        
        # Summary aus spaCy Details erstellen
        spacy_details = pipeline_result.get('spacy_details', {})
        summary_parts = []
        
        # Imperative
        imperative = spacy_details.get('imperative', {})
        if imperative.get('imperative_count', 0) > 0:
            verbs = imperative.get('imperative_verbs', [])[:2]
            summary_parts.append(f"Aktion: {', '.join(verbs)}")
        
        # Deadlines
        deadline = spacy_details.get('deadline', {})
        if deadline.get('deadline_detected'):
            deadlines = deadline.get('deadlines', [])
            if deadlines:
                summary_parts.append(f"Deadline: {deadlines[0]}")
        
        # VIP
        vip = spacy_details.get('vip', {})
        if vip.get('is_vip'):
            summary_parts.append(f"VIP (+{vip.get('importance_boost')})")
        
        # Intern/Extern
        internal_external = spacy_details.get('internal_external', {})
        if not internal_external.get('is_internal'):
            summary_parts.append("Extern")
        
        # Ensemble Stats
        ensemble_stats = pipeline_result.get('ensemble_stats', {})
        learning_phase = ensemble_stats.get('learning_phase', 'initial')
        num_corrections = ensemble_stats.get('num_corrections', 0)
        
        if summary_parts:
            summary = f"{subject[:50]}: {' | '.join(summary_parts)} [Phase={learning_phase}, N={num_corrections}]"
        else:
            summary = f"{subject[:100] if subject else 'Keine Zusammenfassung'} [Phase Y]"
        
        return {
            "dringlichkeit": dringlichkeit,
            "wichtigkeit": wichtigkeit,
            "kategorie_aktion": kategorie,
            "tags": [],  # Leer - Tag-Manager übernimmt Embedding-basierte Zuordnung
            "suggested_tags": [],  # Leer - Tag-Manager übernimmt Embedding-basierte Zuordnung
            "spam_flag": False,
            "summary_de": summary,
            "text_de": body[:500] if body else "",
            "_used_phase_y": True,  # Marker: Wurde mit Phase Y verarbeitet
            "_phase_y_confidence": confidence,
            "_phase_y_method": pipeline_result.get('final_method', 'spacy_only'),
        }

    def analyze_email(
        self, subject: str, body: str, 
        sender: str = "",  # Phase X: UrgencyBooster
        language: str = "de", context: Optional[str] = None,
        user_id: Optional[int] = None,  # Phase X: UrgencyBooster
        account_id: Optional[int] = None,  # Phase X: UrgencyBooster account-specific trusted senders
        db = None,  # Phase X: UrgencyBooster
        user_enabled_booster: bool = True,  # Phase X: UrgencyBooster
        **kwargs  # Accept but ignore other Phase-X params
    ) -> Dict[str, Any]:
        """Dispatcher: nutzt Embedding-Heuristiken oder Chat-LLM je nach Modelltyp.
        
        Phase X: Mit optionalem UrgencyBooster für Trusted Senders (Ollama CPU-only).
        """
        # Security: Sanitize inputs before API calls
        subject = _sanitize_email_input(subject, max_length=500)
        body = _sanitize_email_input(body, max_length=50000)
        if context:
            context = _sanitize_email_input(context, max_length=5000)

        if self._is_embedding_model:
            # Note: Embeddings don't use context yet
            return self._analyze_with_embeddings(subject, body, sender=sender)
        return self._analyze_with_chat(subject, body, sender=sender, language=language, 
                                      context=context, user_id=user_id, account_id=account_id, db=db, 
                                      user_enabled_booster=user_enabled_booster)

    def _analyze_with_chat(
        self, subject: str, body: str, sender: str = "", language: str = "de", 
        context: Optional[str] = None, user_id: Optional[int] = None, account_id: Optional[int] = None,
        db = None, user_enabled_booster: bool = True
    ) -> Dict[str, Any]:
        """Analysiert eine Mail mit Chat-LLM (Standard).
        
        Phase X: Versucht UrgencyBooster für Trusted Senders vor LLM-Analyse.
        """
        # Urgency Booster: Hybrid Pipeline (spaCy NLP + Keywords + SGD Ensemble Learning)
        if sender and user_id and db and user_enabled_booster and account_id:
            logger.info(f"🔍 Urgency Booster Hybrid: sender={sender[:50]}, account_id={account_id}")
            try:
                from src.services.urgency_booster import get_hybrid_pipeline
                
                # Lazy import um circular dependency zu vermeiden
                try:
                    from src.train_classifier import OnlineLearner
                    sgd_classifier = OnlineLearner()
                except Exception as e:
                    logger.debug(f"SGD Classifier nicht verfügbar: {e}")
                    sgd_classifier = None
                
                # Hybrid Pipeline mit optionalem SGD Classifier
                hybrid_pipeline = get_hybrid_pipeline(db, sgd_classifier)
                
                if hybrid_pipeline:
                    logger.info(f"✅ Hybrid Pipeline aktiviert (spaCy + SGD Ensemble)")
                    try:
                        pipeline_result = hybrid_pipeline.analyze(
                            account_id=account_id,
                            sender_email=sender,
                            subject=subject,
                            body=body
                        )
                        
                        # Confidence basierend auf Ensemble-Stats
                        ensemble_stats = pipeline_result.get("ensemble_stats", {})
                        num_corrections = ensemble_stats.get("num_corrections", 0)
                        
                        # Je mehr Korrekturen, desto höher Confidence (SGD trainiert)
                        if num_corrections >= 50:
                            confidence = 0.9  # SGD dominant, sehr zuverlässig
                        elif num_corrections >= 20:
                            confidence = 0.75  # Hybrid, gute Qualität
                        else:
                            confidence = 0.65  # spaCy-only, solide
                        
                        logger.info(f"✅ Booster Analyse: W={pipeline_result['wichtigkeit']}, D={pipeline_result['dringlichkeit']}, method={pipeline_result['final_method']}, confidence={confidence:.2f}")
                        
                        # Convert Hybrid format to standard LLM format
                        result = self._convert_hybrid_to_llm_format(pipeline_result, subject, body, confidence)
                        result['_used_hybrid_booster'] = True
                        return result
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Hybrid Booster fehlgeschlagen: {e}", exc_info=True)
                        # Fall through to standard LLM analysis
                else:
                    # Fallback: Alter UrgencyBooster (nur für Trusted Senders)
                    logger.info(f"⚠️ Hybrid Pipeline nicht verfügbar, Fallback auf Legacy Booster")
                    try:
                        from importlib import import_module
                        trusted_senders_module = import_module(".services.trusted_senders", "src")
                        trusted_result = trusted_senders_module.TrustedSenderManager.is_trusted_sender(
                            db, user_id, sender, account_id=account_id
                        )
                        if trusted_result and trusted_result.get('use_urgency_booster'):
                            from src.services.urgency_booster import get_urgency_booster
                            urgency_booster = get_urgency_booster()
                            booster_result = urgency_booster.analyze_urgency(subject, body, sender)
                            if booster_result.get("confidence", 0) >= 0.6:
                                logger.info(f"✅ UrgencyBooster Fallback: confidence={booster_result.get('confidence'):.2f}")
                                return self._convert_booster_to_llm_format(booster_result, subject, body)
                    except Exception as e:
                        logger.warning(f"UrgencyBooster Fallback failed: {e}")
                        
            except Exception as e:
                logger.warning(f"Phase Y checks failed: {e}", exc_info=True)
                # Fall through to standard analysis

        
        messages = _build_standard_messages(
            subject=subject, body=body, language=language, context=context
        )

        try:
            response = requests.post(
                self.chat_url,
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                },
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout:
            logger.error("Ollama-Request timed out (model=%s)", self.model)
            return self._get_fallback_response()
        except requests.exceptions.ConnectionError:
            logger.error(
                "Ollama Connection failed (model=%s, url=%s)", self.model, self.chat_url
            )
            return self._get_fallback_response()
        except requests.exceptions.RequestException as e:
            logger.error(
                "Ollama Request Error (model=%s): %s", self.model, type(e).__name__
            )
            return self._get_fallback_response()
        except Exception as e:
            logger.error(
                "Unexpected Ollama Error (model=%s): %s", self.model, type(e).__name__
            )
            return self._get_fallback_response()

        if response.status_code == 404:
            logger.error(
                "Ollama meldet 404 für Modell %s. Bitte 'ollama pull %s' ausführen und den Dienst erneut probieren.",
                self.model,
                self.model,
            )
            return self._get_fallback_response()

        if response.status_code != 200:
            logger.error(
                "Ollama API Error (%s): %s - %s",
                self.model,
                response.status_code,
                _safe_response_text(response),
            )
            return self._get_fallback_response()

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            safe_subject = subject[:30] + "..." if len(subject) > 30 else subject
            logger.error(
                "Antwort von Ollama ist kein JSON (subject=%r, model=%s): %s",
                safe_subject,
                self.model,
                type(e).__name__,
            )
            return self._get_fallback_response()

        content = (data.get("message") or {}).get("content", "").strip()
        if not content:
            safe_subject = subject[:30] + "..." if len(subject) > 30 else subject
            logger.error(
                "Ollama-Antwort enthält keinen Content (subject=%r, model=%s)",
                safe_subject,
                self.model,
            )
            return self._get_fallback_response()

        parsed = _parse_model_json(content)
        if not parsed:
            return self._get_fallback_response()

        return _validate_ai_payload(parsed)

    def _get_fallback_response(self) -> Dict[str, Any]:
        """Fallback-Response wenn LLM nicht verfügbar oder Antwort unbrauchbar."""
        return _fallback_response()

    def generate_text(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        max_tokens: int = 1000
    ) -> str:
        """Generiert Text mit Ollama Chat API."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens
            }
        }
        
        try:
            response = requests.post(
                self.chat_url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result.get("message", {}).get("content", "")
        except requests.exceptions.RequestException as e:
            logger.error("Ollama generate_text fehlgeschlagen: %s", e)
            raise


class OpenAIClient(AIClient):
    """OpenAI Chat Completions API."""

    API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise ValueError("OpenAI API Key fehlt")
        self.api_key = api_key
        self.model = model or PROVIDER_REGISTRY["openai"]["default_model"]
        self.timeout = int(os.getenv("OPENAI_TIMEOUT", "300"))
        self.max_retries = 3
        self.retry_delay = 2  # Sekunden
    
    def _check_temperature_support(self) -> bool:
        """Prüft dynamisch ob Modell temperature unterstützt via Model Discovery."""
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("md04", "src/04_model_discovery.py")
            md04 = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(md04)
            models = md04.get_openai_models()
            for m in models:
                if m.get("id") == self.model:
                    return m.get("supports_temperature", True)  # Default: True
            # Fallback: Reasoning-Modelle (o1/o3/gpt-5) = False, Rest = True
            return not self.model.startswith(("o1-", "o3-", "gpt-5"))
        except Exception as e:
            logger.warning(f"Temperature-Check fehlgeschlagen: {e}, nutze Fallback")
            # Fallback: Reasoning-Modelle (o1/o3/gpt-5) = False, Rest = True
            return not self.model.startswith(("o1-", "o3-", "gpt-5"))

    def _check_model_type(self) -> str:
        """
        ALLE OpenAI Modelle verwenden nur noch Chat API.
        Der /v1/completions Endpoint ist deprecated.
        """
        logger.info(f"✅ {self.model} wird als Chat-Modell behandelt (alle modernen Modelle)") 
        return "chat"

    def analyze_email(
        self, subject: str, body: str, language: str = "de", context: Optional[str] = None,
        **kwargs  # Phase X: Accept but ignore sender, user_id, db, user_enabled_booster
    ) -> Dict[str, Any]:
        # Security: Sanitize inputs before API calls
        subject = _sanitize_email_input(subject, max_length=500)
        body = _sanitize_email_input(body, max_length=50000)
        if context:
            context = _sanitize_email_input(context, max_length=5000)

        payload = {
            "model": self.model,
            "messages": _build_standard_messages(subject, body, language, context=context),
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Retry-Loop mit Exponential Backoff
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.API_URL, json=payload, headers=headers, timeout=self.timeout
                )

                # Rate Limiting (429) → Retry mit Backoff
                if response.status_code == 429:
                    wait_time = self.retry_delay**attempt
                    logger.warning(
                        "OpenAI Rate Limit (429) - Retry %d/%d nach %ds",
                        attempt + 1,
                        self.max_retries,
                        wait_time,
                    )
                    if attempt < self.max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error("OpenAI Rate Limit - Max Retries erreicht")
                        return _fallback_response()

                response.raise_for_status()
                break  # Erfolgreich → Loop verlassen

            except requests.exceptions.Timeout:
                logger.error(
                    "OpenAI-Request timed out (model=%s, attempt=%d)",
                    self.model,
                    attempt + 1,
                )
                if attempt == self.max_retries - 1:
                    return _fallback_response()
                time.sleep(self.retry_delay**attempt)

            except requests.exceptions.ConnectionError:
                logger.error(
                    "OpenAI Connection failed (model=%s, attempt=%d)",
                    self.model,
                    attempt + 1,
                )
                if attempt == self.max_retries - 1:
                    return _fallback_response()
                time.sleep(self.retry_delay**attempt)

            except requests.exceptions.HTTPError as exc:
                if exc.response.status_code == 401:
                    logger.error("OpenAI Authentication failed (invalid API key)")
                elif exc.response.status_code == 429:
                    pass  # Bereits oben behandelt
                else:
                    # Security: Redact API keys from error response
                    logger.error(
                        "OpenAI HTTP Error (model=%s): %d - %s",
                        self.model,
                        exc.response.status_code,
                        _safe_response_text(exc.response),
                    )
                return _fallback_response()

            except requests.exceptions.RequestException as exc:
                logger.error(
                    "OpenAI Request Error (model=%s): %s",
                    self.model,
                    type(exc).__name__,
                )
                if attempt == self.max_retries - 1:
                    return _fallback_response()
                time.sleep(self.retry_delay**attempt)

            except Exception as exc:
                logger.error(
                    "Unexpected OpenAI Error (model=%s): %s",
                    self.model,
                    type(exc).__name__,
                )
                return _fallback_response()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            safe_subject = subject[:30] + "..." if len(subject) > 30 else subject
            logger.error(
                "OpenAI lieferte kein JSON (subject=%r): %s",
                safe_subject,
                type(exc).__name__,
            )
            return _fallback_response()

        choices = data.get("choices") or []
        if not choices:
            safe_subject = subject[:30] + "..." if len(subject) > 30 else subject
            logger.error("OpenAI Antwort ohne choices (subject=%r)", safe_subject)
            return _fallback_response()

        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not content:
            safe_subject = subject[:30] + "..." if len(subject) > 30 else subject
            logger.error("OpenAI Antwort ohne Content (subject=%r)", safe_subject)
            return _fallback_response()

        parsed = _parse_model_json(content)
        if not parsed:
            return _fallback_response()

        return _validate_ai_payload(parsed)

    def generate_text(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        max_tokens: int = 1000
    ) -> str:
        """Generiert Text mit OpenAI API (Chat oder Completion basierend auf Modell)."""
        model_type = self._check_model_type()
        supports_temp = self._check_temperature_support()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Dynamische API URL basierend auf Modell-Typ
        if model_type == "completion":
            api_url = "https://api.openai.com/v1/completions"
            # Completion API Format
            payload = {
                "model": self.model,
                "prompt": f"{system_prompt}\n\n{user_prompt}",
                "max_tokens": max_tokens
            }
        else:
            api_url = "https://api.openai.com/v1/chat/completions"
            # Chat API Format  
            is_new_chat_model = self.model.startswith(("gpt-4o", "o1", "o3", "gpt-5"))
            token_param = "max_completion_tokens" if is_new_chat_model else "max_tokens"
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
            payload[token_param] = max_tokens
        
        if supports_temp:
            payload["temperature"] = 0.7
        
        try:
            response = requests.post(
                api_url,  # ← Dynamische URL statt self.API_URL
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            # Antwort-Extraktion basierend auf API-Typ
            if model_type == "completion":
                return data["choices"][0]["text"]
            else:
                return data["choices"][0]["message"]["content"]
                
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = e.response.json().get("error", {}).get("message", "")
            except:
                error_detail = e.response.text[:200] if e.response else ""
            logger.error("OpenAI generate_text fehlgeschlagen: %s - %s", e, error_detail)
            raise
        except requests.exceptions.RequestException as e:
            logger.error("OpenAI generate_text fehlgeschlagen: %s", e)
            raise

    def _generate_completion(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        max_tokens: int = 1000
    ) -> str:
        """Generiert Text mit OpenAI Completions API für gpt-5.x Models."""
        # Kombiniere System + User Prompt für Completions API
        combined_prompt = f"{system_prompt}\n\nUser: {user_prompt}\nAssistant:"
        
        payload = {
            "model": self.model,
            "prompt": combined_prompt,
            "max_tokens": max_tokens
        }
        
        # Dynamisch temperature setzen (gpt-5 sollte es nicht unterstützen)
        if self._check_temperature_support():
            payload["temperature"] = 0.7
            logger.debug(f"OpenAI Completions: temperature=0.7 für Modell {self.model}")
        else:
            logger.debug(f"OpenAI Completions: temperature übersprungen für Reasoning-Modell {self.model}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/completions",  # Completions endpoint!
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["text"].strip()
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = e.response.json().get("error", {}).get("message", "")
            except:
                error_detail = e.response.text[:200] if e.response else ""
            logger.error("OpenAI Completions fehlgeschlagen: %s - %s", e, error_detail)
            raise
        except requests.exceptions.RequestException as e:
            logger.error("OpenAI Completions fehlgeschlagen: %s", e)
            raise

    def _get_embedding(self, text: str) -> list[float] | None:
        """
        Generiert Embedding via OpenAI Embeddings API.
        
        Nutzt text-embedding-3-small, text-embedding-3-large oder text-embedding-ada-002
        
        Returns:
            Liste von Floats (Embedding-Vektor) oder None bei Fehler
        """
        if not text or not text.strip():
            return None
        
        embeddings_url = "https://api.openai.com/v1/embeddings"
        payload = {
            "model": self.model,  # z.B. "text-embedding-3-small"
            "input": text.strip(),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(
                embeddings_url, 
                json=payload, 
                headers=headers, 
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            embeddings = data.get("data", [])
            
            if not embeddings:
                logger.warning(f"OpenAI Embeddings: Keine Daten für model={self.model}")
                return None
            
            return embeddings[0].get("embedding")
            
        except requests.exceptions.HTTPError as exc:
            logger.error(
                f"OpenAI Embeddings HTTP Error (model={self.model}): {exc.response.status_code}"
            )
            return None
        except Exception as exc:
            logger.error(f"OpenAI Embeddings Error: {exc}")
            return None


class AnthropicClient(AIClient):
    """Anthropic Claude Messages API mit Rate Limiting."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20240620"):
        if not api_key:
            raise ValueError("Anthropic API Key fehlt")
        self.api_key = api_key
        self.model = model or PROVIDER_REGISTRY["anthropic"]["default_model"]
        self.timeout = int(os.getenv("ANTHROPIC_TIMEOUT", "300"))
        self.max_retries = 3
        self.retry_delay = 2  # Sekunden

    def analyze_email(
        self, subject: str, body: str, language: str = "de", context: Optional[str] = None,
        **kwargs  # Phase X: Accept but ignore sender, user_id, db, user_enabled_booster
    ) -> Dict[str, Any]:
        # Security: Sanitize inputs before API calls
        subject = _sanitize_email_input(subject, max_length=500)
        body = _sanitize_email_input(body, max_length=50000)
        if context:
            context = _sanitize_email_input(context, max_length=5000)

        # Prepend context to user payload
        user_text = _build_user_payload(subject, body, language)
        if context:
            user_text = f"{context}\n\n---\n\nCURRENT EMAIL TO ANALYZE:\n{user_text}"

        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": OLLAMA_SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_text,
                        }
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        # Retry-Loop mit Exponential Backoff
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.API_URL, json=payload, headers=headers, timeout=self.timeout
                )

                # Rate Limiting (429) → Retry mit Backoff
                if response.status_code == 429:
                    wait_time = self.retry_delay**attempt
                    logger.warning(
                        "Anthropic Rate Limit (429) - Retry %d/%d nach %ds",
                        attempt + 1,
                        self.max_retries,
                        wait_time,
                    )
                    if attempt < self.max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error("Anthropic Rate Limit - Max Retries erreicht")
                        return _fallback_response()

                response.raise_for_status()
                break  # Erfolgreich → Loop verlassen

            except requests.exceptions.Timeout:
                logger.error(
                    "Anthropic-Request timed out (model=%s, attempt=%d)",
                    self.model,
                    attempt + 1,
                )
                if attempt == self.max_retries - 1:
                    return _fallback_response()
                time.sleep(self.retry_delay**attempt)

            except requests.exceptions.ConnectionError:
                logger.error(
                    "Anthropic Connection failed (model=%s, attempt=%d)",
                    self.model,
                    attempt + 1,
                )
                if attempt == self.max_retries - 1:
                    return _fallback_response()
                time.sleep(self.retry_delay**attempt)

            except requests.exceptions.HTTPError as exc:
                if exc.response.status_code == 401:
                    logger.error("Anthropic Authentication failed (invalid API key)")
                elif exc.response.status_code == 429:
                    pass  # Bereits oben behandelt
                else:
                    # Security: Redact API keys from error response
                    logger.error(
                        "Anthropic HTTP Error (model=%s): %d - %s",
                        self.model,
                        exc.response.status_code,
                        _safe_response_text(exc.response),
                    )
                return _fallback_response()

            except requests.exceptions.RequestException as exc:
                logger.error(
                    "Anthropic Request Error (model=%s): %s",
                    self.model,
                    type(exc).__name__,
                )
                if attempt == self.max_retries - 1:
                    return _fallback_response()
                time.sleep(self.retry_delay**attempt)

            except Exception as exc:
                logger.error(
                    "Unexpected Anthropic Error (model=%s): %s",
                    self.model,
                    type(exc).__name__,
                )
                return _fallback_response()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            safe_subject = subject[:30] + "..." if len(subject) > 30 else subject
            logger.error(
                "Anthropic lieferte kein JSON (subject=%r): %s",
                safe_subject,
                type(exc).__name__,
            )
            return _fallback_response()

        content_blocks = data.get("content") or []
        text_parts: List[str] = []
        for block in content_blocks:
            if block.get("type") == "text" and block.get("text"):
                text_parts.append(block["text"])
        content = "\n".join(text_parts).strip()
        if not content:
            safe_subject = subject[:30] + "..." if len(subject) > 30 else subject
            logger.error("Anthropic Antwort ohne Content (subject=%r)", safe_subject)
            return _fallback_response()

        parsed = _parse_model_json(content)
        if not parsed:
            return _fallback_response()

        return _validate_ai_payload(parsed)

    def _check_temperature_support(self) -> bool:
        """Prüft dynamisch ob Modell temperature unterstützt."""
        # Anthropic-spezifische Logik
        reasoning_models = ["claude-3.5-haiku", "claude-3.5-sonnet-reasoning", "claude-3.6-haiku"] 
        unsupported = [m for m in reasoning_models if self.model.startswith(m)]
        if unsupported:
            logger.debug(f"Anthropic Reasoning-Modell {self.model} unterstützt temperature nicht")
            return False
        return True  # Andere Claude-Modelle = OK
    
    def generate_text(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        max_tokens: int = 1000
    ) -> str:
        """Generiert Text mit Anthropic Messages API."""
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ]
        }
        
        # Dynamisch temperature setzen
        if self._check_temperature_support():
            payload["temperature"] = 0.7
            logger.debug(f"Anthropic: temperature=0.7 für Modell {self.model}")
        else:
            logger.debug(f"Anthropic: temperature übersprungen für Reasoning-Modell {self.model}")
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(
                self.API_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            # Anthropic gibt content als Liste von Blöcken zurück
            content_blocks = data.get("content", [])
            text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            return "\n".join(text_parts)
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = e.response.json().get("error", {}).get("message", "")
            except:
                error_detail = e.response.text[:200] if e.response else ""
            logger.error("Anthropic generate_text fehlgeschlagen: %s - %s", e, error_detail)
            raise
        except requests.exceptions.RequestException as e:
            logger.error("Anthropic generate_text fehlgeschlagen: %s", e)
            raise


class MistralClient(AIClient):
    """Mistral AI Chat & Embeddings API."""
    
    API_URL_CHAT = "https://api.mistral.ai/v1/chat/completions"
    API_URL_EMBEDDINGS = "https://api.mistral.ai/v1/embeddings"
    
    def __init__(self, api_key: str, model: str = "mistral-small-latest"):
        if not api_key:
            raise ValueError("Mistral API Key fehlt")
        self.api_key = api_key
        self.model = model or PROVIDER_REGISTRY["mistral"]["default_model"]
        self.timeout = int(os.getenv("MISTRAL_TIMEOUT", "300"))
        self.max_retries = 3
        self.retry_delay = 2
    
    def analyze_email(
        self, subject: str, body: str, language: str = "de", context: Optional[str] = None,
        **kwargs  # Phase X: Accept but ignore sender, user_id, db, user_enabled_booster
    ) -> Dict[str, Any]:
        # Security: Sanitize inputs before API calls
        subject = _sanitize_email_input(subject, max_length=500)
        body = _sanitize_email_input(body, max_length=50000)
        if context:
            context = _sanitize_email_input(context, max_length=5000)
        
        payload = {
            "model": self.model,
            "messages": _build_standard_messages(subject, body, language, context=context),
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.API_URL_CHAT, json=payload, headers=headers, timeout=self.timeout
                )
                
                if response.status_code == 429:
                    wait_time = self.retry_delay ** attempt
                    logger.warning(f"Mistral Rate Limit - Retry {attempt+1}/{self.max_retries} nach {wait_time}s")
                    if attempt < self.max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        return _fallback_response()
                
                response.raise_for_status()
                break
                
            except requests.exceptions.HTTPError as exc:
                logger.error(f"Mistral HTTP Error: {exc.response.status_code}")
                return _fallback_response()
            except Exception as exc:
                logger.error(f"Mistral Request Error: {type(exc).__name__}")
                if attempt == self.max_retries - 1:
                    return _fallback_response()
                time.sleep(self.retry_delay ** attempt)
        
        try:
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return _fallback_response()
            
            content = ((choices[0].get("message") or {}).get("content") or "").strip()
            if not content:
                return _fallback_response()
            
            parsed = _parse_model_json(content)
            if not parsed:
                return _fallback_response()
            
            return _validate_ai_payload(parsed)
        except Exception:
            return _fallback_response()

    def _check_temperature_support(self) -> bool:
        """Prüft ob Modell temperature unterstützt."""
        # Mistral-spezifische Reasoning-Modelle detection
        reasoning_models = ["mistral-reasoning"]  # Erweitern wenn neue kommen
        unsupported = [m for m in reasoning_models if self.model.startswith(m)]
        if unsupported:
            logger.debug(f"Mistral Reasoning-Modell {self.model} unterstützt temperature nicht")
            return False
        return True  # Andere Mistral-Modelle = OK

    def generate_text(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        max_tokens: int = 1000
    ) -> str:
        """Generiert Text mit Mistral Chat API."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens
        }
        
        # Dynamisch temperature setzen
        if self._check_temperature_support():
            payload["temperature"] = 0.7
            logger.debug(f"Mistral: temperature=0.7 für Modell {self.model}")
        else:
            logger.debug(f"Mistral: temperature übersprungen für Reasoning-Modell {self.model}")
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(
                self.API_URL_CHAT,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = e.response.json().get("error", {}).get("message", "")
            except:
                error_detail = e.response.text[:200] if e.response else ""
            logger.error("Mistral generate_text fehlgeschlagen: %s - %s", e, error_detail)
            raise
        except requests.exceptions.RequestException as e:
            logger.error("Mistral generate_text fehlgeschlagen: %s", e)
            raise
    
    def _get_embedding(self, text: str) -> list[float] | None:
        """Generiert Embedding via Mistral Embeddings API (mistral-embed, 1024 dim)."""
        if not text or not text.strip():
            return None
        
        payload = {
            "model": "mistral-embed",
            "input": [text.strip()],  # Mistral erwartet Array
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            response = requests.post(
                self.API_URL_EMBEDDINGS,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            embeddings = data.get("data", [])
            
            if not embeddings:
                logger.warning("Mistral Embeddings: Keine Daten")
                return None
            
            return embeddings[0].get("embedding")
            
        except Exception as exc:
            logger.error(f"Mistral Embeddings Error: {exc}")
            return None


def resolve_model(
    provider: str, requested_model: Optional[str], kind: str = "base"
) -> str:
    """
    Resolves das Modell für einen Provider.
    WICHTIG: Kein ENFORCED_MODEL mehr! Gibt angeforderte Modelle durch.

    Args:
        provider: KI-Provider (ollama, openai, etc.)
        requested_model: Gewünschtes Modell (optional)
        kind: 'base' oder 'optimize' für Default-Lookup

    Returns:
        Resolved model name
    """
    provider_key = (provider or "ollama").lower()
    config = PROVIDER_REGISTRY.get(provider_key) or {}

    if requested_model and requested_model.strip():
        return requested_model.strip()

    # Lookup: default_model_base oder default_model_optimize (Fallback: base)
    default_key = (
        f"default_model_{kind}"
        if kind in ("base", "optimize")
        else "default_model_base"
    )
    return config.get(
        default_key, config.get("default_model_base", LocalOllamaClient.DEFAULT_MODEL)
    )


def provider_requires_cloud(provider: str) -> bool:
    config = PROVIDER_REGISTRY.get((provider or "").lower())
    return bool(config and config.get("needs_cloud_sanitization"))


def ensure_provider_available(provider: str) -> None:
    provider_key = (provider or "").lower()
    config = PROVIDER_REGISTRY.get(provider_key)
    if not config:
        raise ValueError(f"Unbekannter Provider: {provider}")
    if config.get("requires_api_key"):
        env_key = config.get("env_key")
        if not os.getenv(env_key or ""):
            raise ValueError(
                f"{config['label']} benötigt den Environment-Parameter {env_key}."
            )


def describe_provider_options() -> List[Dict[str, Any]]:
    options: List[Dict[str, Any]] = []
    for provider_key, cfg in PROVIDER_REGISTRY.items():
        env_key = cfg.get("env_key")
        available = True
        if cfg.get("requires_api_key"):
            available = bool(os.getenv(env_key or ""))
        options.append(
            {
                "id": provider_key,
                "label": cfg["label"],
                "default_model_base": cfg.get("default_model_base"),
                "default_model_optimize": cfg.get("default_model_optimize"),
                "models": cfg.get("models", []),
                "models_base": cfg.get("models_base", []),
                "models_optimize": cfg.get("models_optimize", []),
                "requires_api_key": cfg.get("requires_api_key", False),
                "env_key": env_key,
                "available": available,
            }
        )
    return options


def build_client(
    provider: str = "ollama", model: Optional[str] = None, **kwargs
) -> AIClient:
    provider_key = (provider or "ollama").lower()
    if provider_key not in PROVIDER_REGISTRY:
        raise ValueError(f"Unbekanntes Backend: {provider}")

    resolved_model = resolve_model(provider_key, model)

    if provider_key == "ollama":
        return LocalOllamaClient(model=resolved_model, base_url=kwargs.get("base_url"))

    if provider_key == "openai":
        api_key = kwargs.get("api_key") or os.getenv(
            PROVIDER_REGISTRY["openai"]["env_key"], ""
        )
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY ist nicht gesetzt")
        return OpenAIClient(api_key=api_key, model=resolved_model)

    if provider_key == "anthropic":
        api_key = kwargs.get("api_key") or os.getenv(
            PROVIDER_REGISTRY["anthropic"]["env_key"], ""
        )
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt")
        return AnthropicClient(api_key=api_key, model=resolved_model)

    if provider_key == "mistral":
        api_key = kwargs.get("api_key") or os.getenv(
            PROVIDER_REGISTRY["mistral"]["env_key"], ""
        )
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY ist nicht gesetzt")
        return MistralClient(api_key=api_key, model=resolved_model)

    raise ValueError(f"Provider {provider} wird nicht unterstützt")


def get_ai_client(backend: str = "ollama", **kwargs) -> AIClient:
    model = kwargs.pop("model", None)
    return build_client(backend, model=model, **kwargs)


def validate_provider_choice(
    provider: str, model: Optional[str], kind: Optional[str] = None
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Validiert Provider & Modell-Auswahl aus den Settings.

    Args:
        provider: KI-Provider ('ollama', 'openai', etc.)
        model: Gewähltes Modell (optional - wird resolved falls nicht angegeben)
        kind: Optional 'base' oder 'optimize' - validiert gegen models_base/optimize

    Returns:
        (erfolg, resolved_model, error_message)
    """
    try:
        ensure_provider_available(provider)
    except ValueError as exc:
        return False, None, str(exc)

    config = PROVIDER_REGISTRY.get(provider.lower())
    if not config:
        return False, None, f"Provider '{provider}' nicht konfiguriert"

    resolved_model = resolve_model(provider, model)

    if kind and kind.lower() in ("base", "optimize"):
        key = f"models_{kind.lower()}"
        allowed_models = config.get(key, [])

        if allowed_models and resolved_model not in allowed_models:
            return (
                False,
                None,
                f"Modell '{resolved_model}' ist für {kind}-Pass nicht erlaubt. Erlaubte: {', '.join(allowed_models)}",
            )

    return True, resolved_model, None


if __name__ == "__main__":
    # P2-005: Nur ein __main__ Block - Zweiter entfernt (Dead Code)
    logging.basicConfig(level=logging.INFO)

    client = build_client("ollama")
    result = client.analyze_email(
        subject="Wichtig: Rechnung begleichen",
        body="Hallo, dies ist eine Erinnerung, dass Ihre Rechnung über 120 EUR bis zum 31.12. "
        "fällig ist. Bitte überweisen Sie den Betrag rechtzeitig. Vielen Dank.",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
