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
from pathlib import Path

try:
    import joblib
except ImportError:
    joblib = None

from .known_newsletters import is_known_newsletter_sender, classify_newsletter_confidence

logger = logging.getLogger(__name__)


class AIClient(ABC):
    """Abstraktes Interface für KI-Backends"""

    @abstractmethod
    def analyze_email(self, subject: str, body: str, language: str = "de") -> Dict[str, Any]:
        """Analysiert eine Mail und liefert strukturierte Ergebnisse."""
        raise NotImplementedError


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
        "models": ["all-minilm:22m", "llama3.2", "llama3.2:1b", "llama3.2:3b", "phi3:mini", "mistral"],
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
            "gpt-4",
            "gpt-3.5-turbo",
        ],
        "requires_api_key": True,
        "env_key": "OPENAI_API_KEY",
        "needs_cloud_sanitization": True,
    },
    "anthropic": {
        "label": "Anthropic Claude (Cloud)",
        "is_cloud": True,
        "supports_base": True,
        "supports_optimize": True,
        "default_model_base": "claude-3-5-sonnet-20240620",
        "default_model_optimize": "claude-3-5-sonnet-20240620",
        "models_base": ["claude-3-5-sonnet-20240620", "claude-3-haiku-20240307"],
        "models_optimize": ["claude-3-5-sonnet-20240620", "claude-3-haiku-20240307"],
        "models": ["claude-3-5-sonnet-20240620", "claude-3-haiku-20240307"],
        "requires_api_key": True,
        "env_key": "ANTHROPIC_API_KEY",
        "needs_cloud_sanitization": True,
    },
}


def _build_user_payload(subject: str, body: str, language: str) -> str:
    return f"Betreff:\n{subject}\n\nText (Sprache: {language}):\n{body}"


def _build_standard_messages(subject: str, body: str, language: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_payload(subject, body, language)},
    ]


def _clamp(value: Any, min_val: int, max_val: int) -> int:
    try:
        return max(min_val, min(int(value), max_val))
    except (ValueError, TypeError):
        return 2


KNOWN_NEWSLETTER_SENDERS = {
    "gmx", "newsletter", "promo", "noreply", "no-reply", "news", "marketing",
    "info@", "updates@", "alerts@", "notifications@"
}

NEWSLETTER_KEYWORDS = {
    "newsletter", "unsubscribe", "abmelden", "subscription", "promotion",
    "offer", "angebot", "bestellen", "jetzt kostenlos", "spielen",
    "gewinn", "gratis", "trend", "trending", "top artikel", "highlight",
    "blog", "podcast", "magazin", "zeitschrift", "e-paper", "digest",
    "kuratiert", "handverlesene", "wöchentlich", "monatlich", "täglich",
    "jeden", "diese woche", "this week", "latest", "breaking"
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
        "spam_flag": bool(parsed.get("spam_flag", False)),
        "summary_de": parsed.get("summary_de", "Keine Zusammenfassung verfügbar"),
        "text_de": parsed.get("text_de", ""),
    }
    return validated


def _fallback_response() -> Dict[str, Any]:
    logger.warning("Nutze Fallback-Response (LLM nicht verfügbar oder Fehler bei der Analyse)")
    return {
        "dringlichkeit": 2,
        "wichtigkeit": 2,
        "kategorie_aktion": "aktion_erforderlich",
        "tags": ["Unbekannt"],
        "spam_flag": False,
        "summary_de": "Analyse fehlgeschlagen - LLM nicht verfügbar oder Fehler.",
        "text_de": "",
    }


class LocalOllamaClient(AIClient):
    """Lokales LLM via Ollama (Standard-Backend)"""

    DEFAULT_MODEL = "llama3.2"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "600"))
        self.model = (model or os.getenv("OLLAMA_MODEL") or self.DEFAULT_MODEL).strip()
        self._available_models = self._fetch_available_models()
        normalized_model = self.model.split(":", 1)[0].strip()
        if self._available_models and normalized_model not in self._available_models:
            logger.warning(
                "⚠️ Modell %s ist in Ollama nicht installiert. Bitte mit 'ollama pull %s' bereitstellen.",
                self.model,
                self.model
            )
        self._is_embedding_model = self._detect_model_type()
        if self._is_embedding_model:
            logger.info("🔍 Embedding-Modell erkannt: %s → nutze Heuristiken für Analyse", self.model)
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
            response = requests.post(
                show_url,
                json={"name": self.model},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                details = data.get("details", {})
                family = details.get("family", "").lower()
                is_embedding = family == "bert" or "embedding" in family.lower()
                return is_embedding
        except Exception as e:
            logger.debug("Fehler beim Erkennen des Modelltyps für %s: %s", self.model, e)
        return False

    def _load_classifiers(self) -> None:
        """Lädt trainierte sklearn-Klassifikatoren aus src/classifiers/*.pkl (optional)."""
        if not joblib:
            logger.debug("joblib nicht verfügbar - Klassifikatoren können nicht geladen werden")
            return

        classifier_dir = Path(__file__).resolve().parent / "classifiers"
        self._classifiers = {}
        self._label_encoders = {}

        classifier_files = {
            "dringlichkeit": "dringlichkeit_clf.pkl",
            "wichtigkeit": "wichtigkeit_clf.pkl",
            "kategorie": "kategorie_clf.pkl",
            "spam": "spam_clf.pkl",
        }

        for key, filename in classifier_files.items():
            clf_path = classifier_dir / filename
            encoder_path = classifier_dir / f"{key}_encoder.pkl"

            if clf_path.exists():
                try:
                    self._classifiers[key] = joblib.load(clf_path)
                    if encoder_path.exists():
                        self._label_encoders[key] = joblib.load(encoder_path)
                    logger.debug(f"✅ Klassifikator geladen: {key}")
                except Exception as e:
                    logger.warning(f"Fehler beim Laden von {clf_path}: {e}")
            else:
                logger.debug(f"Klassifikator nicht gefunden: {clf_path} → Heuristiken als Fallback")

    def _fetch_available_models(self) -> set[str]:
        """Fragt verfügbare Modelle ab und meldet die Erreichbarkeit des Servers."""
        tags_url = f"{self.base_url}/api/tags"
        try:
            response = requests.get(tags_url, timeout=2)
            if response.status_code != 200:
                logger.warning("⚠️ Ollama-Server antwortet mit Status %s", response.status_code)
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
        Kürzt Text auf max. 512 Zeichen um Kontext-Limits zu respektieren.
        """
        if not text or not text.strip():
            return None
        
        truncated = text.strip()[:512]
        
        try:
            response = requests.post(
                self.embeddings_url,
                json={"model": self.model, "prompt": truncated},
                timeout=30,
            )
            if response.status_code != 200:
                logger.debug("Embedding API Error (%s): %s", response.status_code, response.text[:100])
                return None
            data = response.json()
            embedding = data.get("embedding")
            if embedding and isinstance(embedding, list):
                return embedding
        except Exception as e:
            logger.debug("Fehler beim Embedding: %s", e)
        return None

    def _analyze_with_embeddings(self, subject: str, body: str, sender: str = "") -> Dict[str, Any]:
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
                logger.debug(f"Newsletter erkannt (Konfidenz={newsletter_confidence:.1%}): {sender} - {subject[:50]}")
                embedding = None
            return {
                "dringlichkeit": _clamp(dringlichkeit, 1, 3),
                "wichtigkeit": _clamp(wichtigkeit, 1, 3),
                "kategorie_aktion": kategorie_aktion,
                "tags": tags,
                "spam_flag": spam_flag,
                "summary_de": subject[:100] if subject else "Keine Zusammenfassung",
                "text_de": body[:500] if body else "",
            }
        
        if embedding and self._classifiers:
            import numpy as np
            embedding_array = np.array(embedding).reshape(1, -1)
            
            if "dringlichkeit" in self._classifiers:
                try:
                    pred = self._classifiers["dringlichkeit"].predict(embedding_array)[0]
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
        
        if not self._classifiers or not embedding:
            keywords_spam_high = ["unsubscribe", "no-reply", "newsletter", "promotion", "angebot", "gmx games", "gewinn", "spielen"]
            keywords_spam_medium = ["bestfans", "game", "kostenlos"]
            keywords_dringend = ["urgent", "sofort", "deadline"]
            keywords_aktion_required = ["bezahle", "überweise", "zahlung erforderlich", "payment required"]
            keywords_rechnung = ["rechnung", "invoice", "rechnungsbetrag"]
            keywords_sicherheit_critical = ["passwort ändern", "password reset", "account locked", "verify now", "konto gesperrt"]
            
            newsletter_keyword_count = sum(1 for kw in NEWSLETTER_KEYWORDS if kw in text)
            has_unsubscribe = "unsubscribe" in text or "abmelden" in text
            
            if any(kw in text for kw in keywords_spam_high) or has_unsubscribe:
                spam_flag = True
                tags.append("Newsletter/Promotion")
                dringlichkeit = 1
                wichtigkeit = 1
                kategorie_aktion = "nur_information"
            elif newsletter_keyword_count >= 2 or has_unsubscribe:
                spam_flag = True
                tags.append("Newsletter/Promotion")
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
            "spam_flag": spam_flag,
            "summary_de": subject[:100] if subject else "Keine Zusammenfassung",
            "text_de": body[:500] if body else "",
        }

    def analyze_email(self, subject: str, body: str, language: str = "de", sender: str = "") -> Dict[str, Any]:
        """Dispatcher: nutzt Embedding-Heuristiken oder Chat-LLM je nach Modelltyp."""
        if self._is_embedding_model:
            return self._analyze_with_embeddings(subject, body, sender=sender)
        return self._analyze_with_chat(subject, body, language)

    def _analyze_with_chat(self, subject: str, body: str, language: str = "de") -> Dict[str, Any]:
        """Analysiert eine Mail mit Chat-LLM (Standard)."""
        messages = _build_standard_messages(subject=subject, body=body, language=language)

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
            logger.error("Ollama-Request timed out")
            return self._get_fallback_response()
        except Exception as e:
            logger.error("Fehler bei Ollama-Aufruf (%s): %s", self.model, e)
            return self._get_fallback_response()

        if response.status_code == 404:
            logger.error(
                "Ollama meldet 404 für Modell %s. Bitte 'ollama pull %s' ausführen und den Dienst erneut probieren.",
                self.model,
                self.model
            )
            return self._get_fallback_response()

        if response.status_code != 200:
            logger.error(
                "Ollama API Error (%s): %s - %s",
                self.model,
                response.status_code,
                response.text[:200],
            )
            return self._get_fallback_response()

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error("Antwort von Ollama ist kein JSON (subject=%r, model=%s): %s", subject, self.model, e)
            return self._get_fallback_response()

        content = (data.get("message") or {}).get("content", "").strip()
        if not content:
            logger.error("Ollama-Antwort enthält keinen Content (subject=%r, model=%s)", subject, self.model)
            return self._get_fallback_response()

        parsed = _parse_model_json(content)
        if not parsed:
            return self._get_fallback_response()

        return _validate_ai_payload(parsed)

    def _get_fallback_response(self) -> Dict[str, Any]:
        """Fallback-Response wenn LLM nicht verfügbar oder Antwort unbrauchbar."""
        return _fallback_response()


class OpenAIClient(AIClient):
    """OpenAI Chat Completions API."""

    API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise ValueError("OpenAI API Key fehlt")
        self.api_key = api_key
        self.model = model or PROVIDER_REGISTRY["openai"]["default_model"]
        self.timeout = int(os.getenv("OPENAI_TIMEOUT", "300"))

    def analyze_email(self, subject: str, body: str, language: str = "de") -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": _build_standard_messages(subject, body, language),
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(self.API_URL, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error("OpenAI-Request timed out (%s)", self.model)
            return _fallback_response()
        except Exception as exc:
            logger.error("OpenAI Fehler (%s): %s", self.model, exc)
            return _fallback_response()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            logger.error("OpenAI lieferte kein JSON (subject=%r): %s", subject, exc)
            return _fallback_response()

        choices = data.get("choices") or []
        if not choices:
            logger.error("OpenAI Antwort ohne choices (subject=%r)", subject)
            return _fallback_response()

        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not content:
            logger.error("OpenAI Antwort ohne Content (subject=%r)", subject)
            return _fallback_response()

        parsed = _parse_model_json(content)
        if not parsed:
            return _fallback_response()

        return _validate_ai_payload(parsed)


class AnthropicClient(AIClient):
    """Anthropic Claude Messages API."""

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20240620"):
        if not api_key:
            raise ValueError("Anthropic API Key fehlt")
        self.api_key = api_key
        self.model = model or PROVIDER_REGISTRY["anthropic"]["default_model"]
        self.timeout = int(os.getenv("ANTHROPIC_TIMEOUT", "300"))

    def analyze_email(self, subject: str, body: str, language: str = "de") -> Dict[str, Any]:
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
                            "text": _build_user_payload(subject, body, language)
                        }
                    ]
                }
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        try:
            response = requests.post(self.API_URL, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error("Anthropic-Request timed out (%s)", self.model)
            return _fallback_response()
        except Exception as exc:
            logger.error("Anthropic Fehler (%s): %s", self.model, exc)
            return _fallback_response()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            logger.error("Anthropic lieferte kein JSON (subject=%r): %s", subject, exc)
            return _fallback_response()

        content_blocks = data.get("content") or []
        text_parts: List[str] = []
        for block in content_blocks:
            if block.get("type") == "text" and block.get("text"):
                text_parts.append(block["text"])
        content = "\n".join(text_parts).strip()
        if not content:
            logger.error("Anthropic Antwort ohne Content (subject=%r)", subject)
            return _fallback_response()

        parsed = _parse_model_json(content)
        if not parsed:
            return _fallback_response()

        return _validate_ai_payload(parsed)


def resolve_model(provider: str, requested_model: Optional[str]) -> str:
    """
    Resolves das Modell für einen Provider.
    WICHTIG: Kein ENFORCED_MODEL mehr! Gibt angeforderte Modelle durch.
    """
    provider_key = (provider or "ollama").lower()
    config = PROVIDER_REGISTRY.get(provider_key) or {}
    
    if requested_model and requested_model.strip():
        return requested_model.strip()
    
    return config.get("default_model", LocalOllamaClient.DEFAULT_MODEL)


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
        options.append({
            "id": provider_key,
            "label": cfg["label"],
            "default_model": cfg.get("default_model"),
            "models": cfg.get("models", []),
            "requires_api_key": cfg.get("requires_api_key", False),
            "env_key": env_key,
            "available": available,
        })
    return options


def build_client(provider: str = "ollama", model: Optional[str] = None, **kwargs) -> AIClient:
    provider_key = (provider or "ollama").lower()
    if provider_key not in PROVIDER_REGISTRY:
        raise ValueError(f"Unbekanntes Backend: {provider}")

    resolved_model = resolve_model(provider_key, model)

    if provider_key == "ollama":
        return LocalOllamaClient(model=resolved_model, base_url=kwargs.get("base_url"))

    if provider_key == "openai":
        api_key = kwargs.get("api_key") or os.getenv(PROVIDER_REGISTRY["openai"]["env_key"], "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY ist nicht gesetzt")
        return OpenAIClient(api_key=api_key, model=resolved_model)

    if provider_key == "anthropic":
        api_key = kwargs.get("api_key") or os.getenv(PROVIDER_REGISTRY["anthropic"]["env_key"], "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt")
        return AnthropicClient(api_key=api_key, model=resolved_model)

    raise ValueError(f"Provider {provider} wird nicht unterstützt")


def get_ai_client(backend: str = "ollama", **kwargs) -> AIClient:
    model = kwargs.pop("model", None)
    return build_client(backend, model=model, **kwargs)


def validate_provider_choice(provider: str, model: Optional[str], kind: Optional[str] = None) -> tuple[bool, Optional[str], Optional[str]]:
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
    
    if kind and kind.lower() in ('base', 'optimize'):
        key = f"models_{kind.lower()}"
        allowed_models = config.get(key, [])
        
        if allowed_models and resolved_model not in allowed_models:
            return False, None, f"Modell '{resolved_model}' ist für {kind}-Pass nicht erlaubt. Erlaubte: {', '.join(allowed_models)}"
    
    return True, resolved_model, None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    client = build_client("ollama")
    result = client.analyze_email(
        subject="Wichtig: Rechnung begleichen",
        body="Hallo, dies ist eine Erinnerung, dass Ihre Rechnung über 120 EUR bis zum 31.12. "
             "fällig ist. Bitte überweisen Sie den Betrag rechtzeitig. Vielen Dank.",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    client = get_ai_client("ollama")
    result = client.analyze_email(
        subject="Wichtig: Rechnung begleichen",
        body="Hallo, dies ist eine Erinnerung, dass Ihre Rechnung über 120 EUR bis zum 31.12. "
             "fällig ist. Bitte überweisen Sie den Betrag rechtzeitig. Vielen Dank.",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
