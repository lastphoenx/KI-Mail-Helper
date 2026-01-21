"""
Translator Blueprint - API-Endpoints für Übersetzung
=====================================================

Endpoints:
- GET  /translator           → UI Seite
- POST /api/translate/detect → Spracherkennung
- POST /api/translate/execute → Übersetzung durchführen

Version: 1.0.0
Datum: 2026-01-21
"""

import asyncio
import logging
from flask import Blueprint, render_template, request, jsonify, g
from functools import wraps

from src.services.translator_service import TranslatorService, LANGUAGE_NAMES, SUPPORTED_TARGET_LANGUAGES

logger = logging.getLogger(__name__)

translator_bp = Blueprint('translator', __name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: Async in Flask
# ═══════════════════════════════════════════════════════════════════════════════

def async_route(f):
    """Decorator um async Funktionen in Flask zu nutzen."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


# ═══════════════════════════════════════════════════════════════════════════════
# UI Route
# ═══════════════════════════════════════════════════════════════════════════════

@translator_bp.route('/translator')
def translator_page():
    """Translator UI Seite."""
    return render_template(
        'translator.html',
        supported_languages=SUPPORTED_TARGET_LANGUAGES,
        language_names=LANGUAGE_NAMES
    )


# ═══════════════════════════════════════════════════════════════════════════════
# API: Language Detection
# ═══════════════════════════════════════════════════════════════════════════════

@translator_bp.route('/api/translate/detect', methods=['POST'])
def detect_language():
    """
    Erkennt die Sprache eines Textes.
    
    Request:
        POST /api/translate/detect
        Content-Type: application/json
        {"text": "Ciao, come stai?"}
    
    Response:
        {
            "language": "it",
            "language_name": "Italiano",
            "confidence": 0.995,
            "target_languages": [
                {"code": "de", "name": "Deutsch"},
                {"code": "en", "name": "English"},
                ...
            ]
        }
    """
    try:
        data = request.get_json()
        text = data.get('text', '')
        
        if not text or len(text.strip()) < 3:
            return jsonify({
                'language': 'unknown',
                'language_name': 'Unbekannt',
                'confidence': 0.0,
                'target_languages': []
            })
        
        service = TranslatorService()
        result = service.detect_language(text)
        targets = service.get_target_languages(result.language)
        
        return jsonify({
            'language': result.language,
            'language_name': result.language_name,
            'confidence': round(result.confidence, 3),
            'target_languages': targets
        })
        
    except Exception as e:
        logger.exception(f"Language detection error: {e}")
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# API: Translation
# ═══════════════════════════════════════════════════════════════════════════════

@translator_bp.route('/api/translate/execute', methods=['POST'])
@async_route
async def execute_translation():
    """
    Übersetzt einen Text.
    
    Request:
        POST /api/translate/execute
        Content-Type: application/json
        {
            "text": "Hello, how are you?",
            "target_lang": "de",
            "source_lang": "en",  // optional, auto-detect wenn nicht angegeben
            "engine": "cloud",    // 'cloud' oder 'local'
            "model": "gpt-4o"     // optional, Model-Override
        }
    
    Response:
        {
            "translated_text": "Hallo, wie geht es Ihnen?",
            "source_language": "en",
            "target_language": "de",
            "engine": "cloud",
            "model_used": "gpt-4o"
        }
    """
    try:
        data = request.get_json()
        text = data.get('text', '')
        target_lang = data.get('target_lang')
        source_lang = data.get('source_lang')  # Optional
        engine = data.get('engine', 'cloud')
        provider = data.get('provider')  # 'openai', 'anthropic', 'ollama', 'mistral'
        model_override = data.get('model')
        
        if not text:
            return jsonify({'error': 'Text ist erforderlich'}), 400
        
        if not target_lang:
            return jsonify({'error': 'Zielsprache ist erforderlich'}), 400
        
        if target_lang not in SUPPORTED_TARGET_LANGUAGES:
            return jsonify({
                'error': f'Zielsprache {target_lang} wird nicht unterstützt. '
                         f'Unterstützt: {", ".join(SUPPORTED_TARGET_LANGUAGES)}'
            }), 400
        
        service = TranslatorService()
        
        result = await service.translate(
            text=text,
            target_lang=target_lang,
            source_lang=source_lang,
            engine=engine,
            provider=provider,
            model_override=model_override
        )
        
        return jsonify({
            'translated_text': result.translated_text,
            'source_language': result.source_language,
            'source_language_name': LANGUAGE_NAMES.get(result.source_language, result.source_language),
            'target_language': result.target_language,
            'target_language_name': LANGUAGE_NAMES.get(result.target_language, result.target_language),
            'engine': result.engine,
            'model_used': result.model_used
        })
        
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        logger.exception(f"Translation error: {e}")
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# API: Available Languages
# ═══════════════════════════════════════════════════════════════════════════════

@translator_bp.route('/api/translate/languages', methods=['GET'])
def get_languages():
    """
    Gibt alle unterstützten Sprachen zurück.
    
    Response:
        {
            "languages": [
                {"code": "de", "name": "Deutsch"},
                {"code": "en", "name": "English"},
                ...
            ]
        }
    """
    languages = [
        {'code': code, 'name': name}
        for code, name in LANGUAGE_NAMES.items()
        if code in SUPPORTED_TARGET_LANGUAGES
    ]
    return jsonify({'languages': languages})
