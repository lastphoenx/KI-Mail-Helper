"""
TranslatorService - Spracherkennung und Übersetzung
====================================================

Features:
- Spracherkennung via fastText (lid.176.bin Modell)
- Übersetzung via Cloud-LLM (OpenAI/Anthropic/Mistral)
- Lokale Übersetzung via Opus-MT (Helsinki-NLP)
- Chunking für lange Texte (Opus-MT 512 Token Limit)
- LRU-Cache für Opus-MT Modelle (RAM-Management)
- Sync-Wrapper für Celery-Integration

Version: 1.2.0
Datum: 2026-01-23
"""

import os
import logging
import asyncio
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from pathlib import Path
from collections import OrderedDict

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LanguageDetectionResult:
    """Ergebnis der Spracherkennung."""
    language: str           # ISO 639-1 Code (z.B. 'de', 'en', 'fr')
    confidence: float       # 0.0 - 1.0
    language_name: str      # Menschenlesbarer Name


@dataclass
class TranslationResult:
    """Ergebnis einer Übersetzung."""
    translated_text: str
    source_language: str
    target_language: str
    engine: str             # 'cloud' oder 'local'
    model_used: str         # z.B. 'gpt-4o', 'opus-mt-en-de'


# ═══════════════════════════════════════════════════════════════════════════════
# Language Mappings
# ═══════════════════════════════════════════════════════════════════════════════

LANGUAGE_NAMES = {
    'de': 'Deutsch',
    'en': 'English',
    'fr': 'Français',
    'it': 'Italiano',
    'es': 'Español',
    'pt': 'Português',
    'nl': 'Nederlands',
    'pl': 'Polski',
    'ru': 'Русский',
    'ja': '日本語',
    'zh': '中文',
    'ko': '한국어',
    'ar': 'العربية',
    'tr': 'Türkçe',
    'sv': 'Svenska',
    'da': 'Dansk',
    'no': 'Norsk',
    'fi': 'Suomi',
    'cs': 'Čeština',
    'hu': 'Magyar',
    'ro': 'Română',
    'el': 'Ελληνικά',
    'he': 'עברית',
    'uk': 'Українська',
}

# Unterstützte Zielsprachen für DACH-Kontext
SUPPORTED_TARGET_LANGUAGES = ['de', 'en', 'fr', 'it', 'es', 'pt', 'nl', 'pl']


# ═══════════════════════════════════════════════════════════════════════════════
# TranslatorService
# ═══════════════════════════════════════════════════════════════════════════════

class TranslatorService:
    """
    Service für Spracherkennung und Übersetzung.
    
    Usage:
        service = TranslatorService()
        
        # Spracherkennung
        result = service.detect_language("Ciao, come stai?")
        print(result.language)  # 'it'
        
        # Übersetzung
        translation = await service.translate("Hello!", target_lang='de')
        print(translation.translated_text)  # 'Hallo!'
    """
    
    _instance = None
    _model = None
    
    def __new__(cls):
        """Singleton Pattern für Model-Caching."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.model_path = Path(__file__).parent.parent.parent / 'models' / 'lid.176.bin'
        self._initialized = True
        logger.info("TranslatorService initialized")
    
    def _load_model(self):
        """Lazy-Load des fastText Modells (lädt automatisch herunter wenn nötig)."""
        if TranslatorService._model is not None:
            return TranslatorService._model
        
        import fasttext
        
        if not self.model_path.exists():
            self._download_model()
        
        # Suppress fastText warning about model type
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            TranslatorService._model = fasttext.load_model(str(self.model_path))
        
        logger.info(f"✅ fastText model loaded from {self.model_path}")
        return TranslatorService._model
    
    def _download_model(self):
        """Download lid.176.bin von fastText CDN."""
        import urllib.request
        import gzip
        import shutil
        
        url = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin"
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"📥 Downloading fastText language model (~126 MB)...")
        
        try:
            urllib.request.urlretrieve(url, str(self.model_path))
            logger.info(f"✅ Model downloaded to {self.model_path}")
        except Exception as e:
            raise RuntimeError(
                f"Failed to download fastText model: {e}. "
                f"Please download manually from {url} to {self.model_path}"
            )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Language Detection
    # ═══════════════════════════════════════════════════════════════════════════
    
    def detect_language(self, text: str) -> LanguageDetectionResult:
        """
        Erkennt die Sprache eines Textes.
        
        Args:
            text: Der zu analysierende Text
            
        Returns:
            LanguageDetectionResult mit Sprache, Confidence und Name
        """
        if not text or not text.strip():
            return LanguageDetectionResult(
                language='unknown',
                confidence=0.0,
                language_name='Unbekannt'
            )
        
        model = self._load_model()
        
        # HTML-Tags entfernen für bessere Spracherkennung
        sample = text
        if '<' in text[:500]:  # HTML-Check (großzügiger für DOCTYPE/Meta-Tags)
            try:
                from inscriptis import get_text
                from inscriptis.model.config import ParserConfig
                sample = get_text(text, ParserConfig(display_links=False))
            except Exception:
                # Fallback: einfaches Strip von Tags
                import re
                sample = re.sub(r'<[^>]+>', ' ', text)
        
        # 🧹 ROBUSTE TEXT-BEREINIGUNG für bessere Language Detection
        import re
        
        # 1. URLs entfernen (häufig in Newsletters, verwirren das Modell)
        sample = re.sub(r'https?://[^\s<>"]+', ' ', sample)
        
        # 2. Email-Adressen entfernen
        sample = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', ' ', sample)
        
        # 3. Base64-ähnliche lange Strings entfernen (Tracking-IDs, Inline-Bilder)
        sample = re.sub(r'\b[A-Za-z0-9+/=]{30,}\b', ' ', sample)
        
        # 4. Mehrfache Leerzeichen normalisieren
        sample = re.sub(r'\s+', ' ', sample).strip()
        
        # 5. Nehme mehr Text für bessere Analyse (2000 statt 1000)
        sample = sample[:2000]
        
        if not sample or len(sample) < 10:
            return LanguageDetectionResult(
                language='unknown',
                confidence=0.0,
                language_name='Unbekannt (zu wenig Text nach Bereinigung)'
            )
        
        predictions = model.predict(sample)
        lang_code = predictions[0][0].replace('__label__', '')
        confidence = float(predictions[1][0])
        
        # 🎯 HÖHERER CONFIDENCE-THRESHOLD: < 0.80 = unsichere Erkennung
        if confidence < 0.80:
            logger.warning(
                f"⚠️ Language detection unsicher: {lang_code} ({confidence:.2f}) - "
                f"Sample: '{sample[:100]}...'"
            )
        
        lang_name = LANGUAGE_NAMES.get(lang_code, lang_code.upper())
        
        return LanguageDetectionResult(
            language=lang_code,
            confidence=confidence,
            language_name=lang_name
        )
    
    def get_target_languages(self, source_lang: str) -> list:
        """
        Gibt verfügbare Zielsprachen basierend auf Quellsprache zurück.
        Filtert die Quellsprache aus der Liste.
        """
        return [
            {'code': lang, 'name': LANGUAGE_NAMES.get(lang, lang)}
            for lang in SUPPORTED_TARGET_LANGUAGES
            if lang != source_lang
        ]
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Translation - Cloud (LLM)
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
        engine: str = 'cloud',
        provider: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> TranslationResult:
        """
        Übersetzt einen Text in die Zielsprache.
        
        Args:
            text: Zu übersetzender Text
            target_lang: Zielsprache (ISO 639-1)
            source_lang: Quellsprache (auto-detect wenn None)
            engine: 'cloud' (LLM) oder 'local' (Opus-MT)
            provider: KI-Provider ('openai', 'anthropic', 'ollama', 'mistral')
            model_override: Optionales Modell-Override
            
        Returns:
            TranslationResult
        """
        # Auto-detect source language if not provided
        if not source_lang:
            detection = self.detect_language(text)
            source_lang = detection.language
        
        target_name = LANGUAGE_NAMES.get(target_lang, target_lang)
        source_name = LANGUAGE_NAMES.get(source_lang, source_lang)
        
        if engine == 'local':
            return await self._translate_local(text, source_lang, target_lang)
        else:
            return await self._translate_cloud(
                text, source_lang, target_lang, 
                source_name, target_name, provider, model_override
            )
    
    async def _translate_cloud(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        source_name: str,
        target_name: str,
        provider: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> TranslationResult:
        """Übersetzung via Cloud-LLM.
        
        Args:
            text: Zu übersetzender Text
            source_lang: Quellsprache (ISO 639-1)
            target_lang: Zielsprache (ISO 639-1)
            source_name: Quellsprache (Name)
            target_name: Zielsprache (Name)
            provider: KI-Provider ('openai', 'anthropic', 'ollama', 'mistral')
            model_override: Spezifisches Modell (optional)
        """
        import importlib
        
        # Dynamischer Import wegen numerischem Präfix im Dateinamen
        ai_client_module = importlib.import_module("src.03_ai_client")
        
        # Provider und Model ermitteln
        from flask import current_app
        
        if not provider:
            try:
                provider = current_app.config.get('OPTIMIZE_PROVIDER', 'openai')
            except RuntimeError:
                provider = 'openai'
        
        model = model_override
        if not model:
            try:
                model = current_app.config.get('OPTIMIZE_MODEL', 'gpt-4o-mini')
            except RuntimeError:
                model = 'gpt-4o-mini'
        
        # System-Prompt für reine Übersetzung
        system_prompt = f"""Du bist ein präziser Übersetzer. Übersetze den folgenden Text von {source_name} nach {target_name}.

REGELN:
- Gib NUR die Übersetzung zurück, ohne Erklärungen oder Kommentare
- Behalte die Formatierung (Absätze, Aufzählungen) bei
- Übersetze idiomatisch, nicht wörtlich
- Bei Fachbegriffen: Verwende die gängige Übersetzung oder behalte den Begriff bei"""

        try:
            # Erstelle AI Client mit korrektem Provider
            ai_client = ai_client_module.build_client(provider=provider, model=model)
            
            # generate_text ist synchron - wir rufen es im Thread-Pool auf
            import asyncio
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: ai_client.generate_text(system_prompt, text, max_tokens=4000)
            )
            
            return TranslationResult(
                translated_text=translated.strip(),
                source_language=source_lang,
                target_language=target_lang,
                engine='cloud',
                model_used=f"{provider}/{model}"
            )
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            raise
    
    async def _translate_local(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> TranslationResult:
        """
        Lokale Übersetzung via Opus-MT (Helsinki-NLP).
        
        Modelle werden bei erstem Aufruf heruntergeladen (~300MB pro Sprachpaar).
        Cached in ~/.cache/huggingface/hub/
        """
        import asyncio
        
        # Mapping für Opus-MT Modell-Namen
        # Format: Helsinki-NLP/opus-mt-{src}-{tgt}
        model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"
        
        try:
            # Synchrone Transformers-Aufrufe in Thread-Pool
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: self._run_opus_translation(model_name, text)
            )
            
            return TranslationResult(
                translated_text=translated,
                source_language=source_lang,
                target_language=target_lang,
                engine='local',
                model_used=model_name.split('/')[-1]  # z.B. 'opus-mt-en-de'
            )
            
        except Exception as e:
            logger.error(f"Local translation error: {e}")
            # Fallback-Info für User
            if "does not appear to have a file named" in str(e):
                raise ValueError(
                    f"Kein Opus-MT Modell für {source_lang}→{target_lang} verfügbar. "
                    f"Bitte Cloud-Übersetzung verwenden."
                )
            raise
    
    def _run_opus_translation(self, model_name: str, text: str) -> str:
        """
        Führt Opus-MT Übersetzung synchron aus (für Thread-Pool).
        
        Mit LRU-Cache (max 2 Modelle) und Chunking für lange Texte.
        """
        if not text or not text.strip():
            return text

        from transformers import MarianMTModel, MarianTokenizer
        import os
        
        # KRITISCH: Trailing Spaces pro Zeile entfernen (inscriptis lässt die stehen)
        # Ohne dies: Leere Chunks → Opus-MT halluziniert "Es ist nicht bekannt, ob"
        lines = [line.rstrip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        # DEBUG: Log den EXACT Text der übersetzt wird
        logger.info(f"🔍 OPUS-MT Input ({len(text)} chars):\n{repr(text[:500])}\n")
        
        # LRU-Cache für Opus-MT Modelle (RAM-Management)
        MAX_CACHED_MODELS = 2  # Max 600MB RAM (300MB pro Modell)
        
        if not hasattr(self, '_opus_models'):
            self._opus_models = OrderedDict()
        
        # LRU: Wenn Cache voll, ältestes Modell entfernen
        if model_name not in self._opus_models:
            if len(self._opus_models) >= MAX_CACHED_MODELS:
                oldest = next(iter(self._opus_models))
                logger.info(f"🗑️ Entferne Opus-MT Modell aus Cache: {oldest}")
                del self._opus_models[oldest]
            
            logger.info(f"📥 Lade Opus-MT Modell: {model_name}")
            
            # FIX Phase 27: Timeout + Local-first + Error Handling
            try:
                # Prüfe ob Modell bereits lokal vorhanden (verhindert Download-Hänger)
                cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
                model_cache = f"models--{model_name.replace('/', '--')}"
                local_path = os.path.join(cache_dir, model_cache)
                
                # Local-first: Wenn vorhanden, erzwinge lokales Laden
                if os.path.exists(local_path):
                    logger.info(f"✅ Modell lokal gefunden: {local_path}")
                    tokenizer = MarianTokenizer.from_pretrained(model_name, local_files_only=True)
                    model = MarianMTModel.from_pretrained(model_name, local_files_only=True)
                else:
                    # Download mit Timeout (verhindert ewiges Hängen)
                    logger.warning(f"⚠️ Modell nicht lokal, Download nötig: {model_name}")
                    # transformers nutzt REQUESTS_TIMEOUT env var
                    os.environ['REQUESTS_TIMEOUT'] = '60'  # 60s Timeout
                    tokenizer = MarianTokenizer.from_pretrained(model_name, resume_download=True)
                    model = MarianMTModel.from_pretrained(model_name, resume_download=True)
                
                self._opus_models[model_name] = (tokenizer, model)
                logger.info(f"✅ Opus-MT Modell geladen: {model_name}")
                
            except Exception as e:
                logger.error(f"❌ Opus-MT Modell konnte nicht geladen werden: {model_name} - {e}")
                # Cleanup: Entferne .incomplete Files
                if os.path.exists(local_path):
                    incomplete_files = [f for f in os.listdir(os.path.join(local_path, 'blobs')) 
                                       if f.endswith('.incomplete')]
                    if incomplete_files:
                        logger.warning(f"🗑️ Entferne {len(incomplete_files)} .incomplete Files")
                        for f in incomplete_files:
                            os.remove(os.path.join(local_path, 'blobs', f))
                raise RuntimeError(f"Translation model {model_name} not available") from e
        
        # Move to end (LRU)
        self._opus_models.move_to_end(model_name)
        tokenizer, model = self._opus_models[model_name]
        
        # Prüfe Token-Count statt Zeichen-Count (präziser!)
        test_tokens = tokenizer(text, return_tensors='pt', padding=True, max_length=512)
        token_count = test_tokens['input_ids'].shape[1]
        
        if token_count <= 512:
            # Text passt in ein Chunk - DIREKT übersetzen!
            logger.debug(f"Text OK: {len(text)} chars = {token_count} tokens (< 512)")
            translated_tokens = model.generate(**test_tokens, max_length=512)
            return tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
        
        # Text zu lang: Chunking nötig
        logger.warning(f"Text zu lang: {len(text)} chars = {token_count} tokens - Chunking aktiviert")
        MAX_CHARS_PER_CHUNK = 350  # Konservativ für Chunking
        
        # Langer Text: In Absätze/Chunks aufteilen
        logger.debug(f"Text zu lang ({len(text)} Zeichen), Chunking aktiviert")
        
        # Strategie: An Absätzen trennen, große Paragraphen aufteilen
        paragraphs = text.split('\n\n')
        translated_chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            # Leere Absätze überspringen (verhindert Halluzinationen)
            if not para.strip():
                continue

            # Wenn Paragraph selbst zu lang, in Sätze aufteilen
            if len(para) > MAX_CHARS_PER_CHUNK:
                # Versuche an Satzenden zu trennen
                sentences = para.replace('. ', '.\n').split('\n')
                for sentence in sentences:
                    if not sentence.strip():
                        continue

                    # Falls einzelner Satz immer noch zu lang, hart trennen
                    if len(sentence) > MAX_CHARS_PER_CHUNK:
                        for i in range(0, len(sentence), MAX_CHARS_PER_CHUNK):
                            chunk_part = sentence[i:i+MAX_CHARS_PER_CHUNK]
                            if not chunk_part.strip():
                                continue

                            if current_chunk and len(current_chunk) + len(chunk_part) + 1 > MAX_CHARS_PER_CHUNK:
                                # Aktuellen Chunk übersetzen (OHNE truncation!)
                                if current_chunk.strip():
                                    tokens = tokenizer(current_chunk, return_tensors='pt', padding=True, max_length=512)
                                    translated_tokens = model.generate(**tokens, max_length=512)
                                    translated_chunks.append(
                                        tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
                                    )
                                current_chunk = chunk_part
                            else:
                                current_chunk += (" " if current_chunk else "") + chunk_part
                    else:
                        if current_chunk and len(current_chunk) + len(sentence) + 1 > MAX_CHARS_PER_CHUNK:
                            # Aktuellen Chunk übersetzen (OHNE truncation!)
                            if current_chunk.strip():
                                tokens = tokenizer(current_chunk, return_tensors='pt', padding=True, max_length=512)
                                translated_tokens = model.generate(**tokens, max_length=512)
                                translated_chunks.append(
                                    tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
                                )
                            current_chunk = sentence
                        else:
                            current_chunk += (" " if current_chunk else "") + sentence
                continue
            
            if len(current_chunk) + len(para) + 2 > MAX_CHARS_PER_CHUNK:
                # Chunk übersetzen (OHNE truncation!)
                if current_chunk and current_chunk.strip():
                    tokens = tokenizer(current_chunk, return_tensors='pt', padding=True, max_length=512)
                    translated_tokens = model.generate(**tokens, max_length=512)
                    translated_chunks.append(
                        tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
                    )
                current_chunk = para
            else:
                current_chunk += ("\n\n" if current_chunk else "") + para
        
        # Letzten Chunk übersetzen (OHNE truncation!)
        if current_chunk and current_chunk.strip():
            tokens = tokenizer(current_chunk, return_tensors='pt', padding=True, max_length=512)
            translated_tokens = model.generate(**tokens, max_length=512)
            translated_chunks.append(
                tokenizer.decode(translated_tokens[0], skip_special_tokens=True)
            )
        
        result = "\n\n".join(translated_chunks)
        logger.debug(f"Chunking abgeschlossen: {len(translated_chunks)} chunks → {len(result)} Zeichen")
        return result
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Sync Wrapper für Celery
    # ═══════════════════════════════════════════════════════════════════════════
    
    def translate_sync(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None,
        engine: str = 'local',
        provider: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> TranslationResult:
        """
        Synchroner Wrapper für translate() - für Celery-Tasks.
        
        Verwendet asyncio.run() um async-Funktion synchron auszuführen.
        """
        return asyncio.run(self.translate(
            text, target_lang, source_lang, engine, provider, model_override
        ))


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════════

def get_translator() -> TranslatorService:
    """Factory-Funktion für TranslatorService (Singleton)."""
    return TranslatorService()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Test
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio
    
    service = TranslatorService()
    
    # Test Detection
    print("=== Language Detection Test ===")
    tests = [
        "Ciao, come stai?",
        "Hello, how are you?",
        "Guten Tag, wie geht es Ihnen?",
        "Bonjour, comment allez-vous?",
    ]
    
    for text in tests:
        result = service.detect_language(text)
        print(f"{result.language} ({result.confidence:.1%}) [{result.language_name}]: {text}")
    
    print("\n=== Target Languages for 'it' ===")
    targets = service.get_target_languages('it')
    print([t['code'] for t in targets])
