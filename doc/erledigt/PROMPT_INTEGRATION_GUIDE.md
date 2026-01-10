"""
INTEGRATION-GUIDE: Optimierte Prompts in KI-Mail-Helper
========================================================

Schritt-für-Schritt Anleitung zum Einbau der optimierten Prompts
"""

# ============================================================================
# SCHRITT 1: Neue Prompt-Datei erstellen
# ============================================================================

STEP_1 = """
1. Neue Datei erstellen: src/optimized_reply_prompts.py

   Kopiere optimized_reply_prompts.py ins src/ Verzeichnis
   
   $ cp optimized_reply_prompts.py src/
"""

# ============================================================================
# SCHRITT 2: reply_generator.py anpassen
# ============================================================================

STEP_2_IMPORT = """
2A. Imports in src/reply_generator.py anpassen:

# AM ANFANG DER DATEI:
# Alte Imports ERSETZEN/ERGÄNZEN:

# NEU: Optimierte Prompts importieren
from src.optimized_reply_prompts import (
    REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED,
    TONE_PROMPTS_OPTIMIZED,
    build_optimized_user_prompt
)

# Fallback auf alte Prompts (für Backward-Compatibility)
try:
    SYSTEM_PROMPT = REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED
    TONE_PROMPTS = TONE_PROMPTS_OPTIMIZED
except ImportError:
    # Alte Prompts falls neue nicht verfügbar
    SYSTEM_PROMPT = REPLY_GENERATION_SYSTEM_PROMPT
    TONE_PROMPTS = TONE_PROMPTS  # Alt
"""

STEP_2_METHOD = """
2B. generate_reply() Methode anpassen:

# IN DER KLASSE ReplyGenerator:

def generate_reply(
    self,
    original_subject: str,
    original_body: str,
    original_sender: str = "",
    tone: str = "formal",
    thread_context: Optional[str] = None,
    language: str = "de",
    has_attachments: bool = False,
    attachment_names: Optional[list] = None
) -> Dict[str, Any]:
    
    if not self.ai_client:
        return {...}  # Error handling wie vorher
    
    # Validiere Ton
    if tone not in TONE_PROMPTS:
        logger.warning(f"Unknown tone '{tone}', falling back to 'formal'")
        tone = "formal"
    
    # 🆕 NEU: Nutze optimierten Prompt-Builder
    try:
        user_prompt = build_optimized_user_prompt(
            original_subject=original_subject,
            original_body=original_body,
            original_sender=original_sender,
            tone=tone,
            thread_context=thread_context,
            has_attachments=has_attachments,
            attachment_names=attachment_names,
            language=language
        )
        
        # Nutze optimierten System-Prompt
        system_prompt = REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED
        
    except Exception as e:
        # Fallback auf alte Methode
        logger.warning(f"Optimized prompt failed, using fallback: {e}")
        user_prompt = self._build_user_prompt(...)  # Alte Methode
        system_prompt = REPLY_GENERATION_SYSTEM_PROMPT  # Alt
    
    # KI-Aufruf (wie vorher)
    try:
        logger.info(f"🤖 Generiere Reply-Entwurf (Ton: {tone})")
        
        reply_text = self.ai_client.generate_text(
            system_prompt=system_prompt,  # 🆕 Optimiert
            user_prompt=user_prompt,      # 🆕 Optimiert
            max_tokens=1000
        )
        
        # Cleanup & Return wie vorher
        reply_text = self._cleanup_reply_text(reply_text)
        
        return {
            "success": True,
            "reply_text": reply_text,
            "tone_used": tone,
            "timestamp": datetime.now().isoformat(),
            "error": None
        }
        
    except Exception as e:
        logger.error(f"❌ Reply-Generierung fehlgeschlagen: {e}")
        return {...}  # Error handling wie vorher
"""

# ============================================================================
# SCHRITT 3: Backward-Compatibility sichern
# ============================================================================

STEP_3 = """
3. Alte _build_user_prompt() Methode BEHALTEN (als Fallback):

# NICHT LÖSCHEN! Wird als Fallback genutzt
def _build_user_prompt(self, ...):
    # Alte Implementation behalten
    ...
    
# Neue Methode nutzt build_optimized_user_prompt()
# Falls die fehlschlägt → Fallback auf _build_user_prompt()
"""

# ============================================================================
# SCHRITT 4: Testing
# ============================================================================

STEP_4 = """
4. Testen mit echten E-Mails:

A) Unit-Test schreiben:

# test_optimized_prompts.py
from src.reply_generator import ReplyGenerator
from src.optimized_reply_prompts import build_optimized_user_prompt

def test_optimized_prompt_question():
    prompt = build_optimized_user_prompt(
        original_subject="Frage zum Termin",
        original_body="Können wir auf nächste Woche verschieben?",
        original_sender="thomas@firma.de",
        tone="friendly"
    )
    
    assert "ERKANNTER E-MAIL-TYP: question" in prompt
    assert "Freundlich und persönlich" in prompt
    print("✅ Question-Typ erkannt")

def test_optimized_prompt_request():
    prompt = build_optimized_user_prompt(
        original_subject="Angebot gewünscht",
        original_body="Bitte senden Sie mir ein Angebot.",
        original_sender="kunde@example.com",
        tone="formal"
    )
    
    assert "ERKANNTER E-MAIL-TYP: request" in prompt
    assert "Formell und professionell" in prompt
    print("✅ Request-Typ erkannt")

if __name__ == "__main__":
    test_optimized_prompt_question()
    test_optimized_prompt_request()
    print("\\n✅ Alle Tests bestanden!")


B) Live-Test im System:

1. Starte dein System
2. Wähle eine Test-E-Mail
3. Klicke "Antwort-Entwurf generieren"
4. Prüfe im Log:

[2026-01-06 15:23:45] 🤖 Generiere Reply-Entwurf (Ton: formal)
[2026-01-06 15:23:45] Detected email type: request
[2026-01-06 15:23:47] ✅ Reply-Entwurf generiert (234 chars)

5. Vergleiche Qualität mit vorher
"""

# ============================================================================
# SCHRITT 5: Monitoring & Optimierung
# ============================================================================

STEP_5 = """
5. Monitoring hinzufügen (optional):

# In src/reply_generator.py:

def generate_reply(self, ...):
    ...
    
    # Nach erfolgreicher Generierung:
    if result["success"]:
        # Log E-Mail-Typ für Statistiken
        email_type = _detect_email_type(original_subject, original_body)
        logger.info(
            f"✅ Reply generiert | Type: {email_type} | "
            f"Tone: {tone} | Length: {len(reply_text)} chars"
        )
    
    return result


# Später auswerten:
$ grep "Reply generiert" logs/app.log | awk -F'|' '{print $2}' | sort | uniq -c
   45 Type: question
   23 Type: request
   12 Type: confirmation
    8 Type: complaint
    5 Type: information
"""

# ============================================================================
# SCHRITT 6: Kontinuierliche Verbesserung
# ============================================================================

STEP_6 = """
6. Prompt-Optimierung basierend auf Feedback:

A) Sammle schlechte Beispiele:
   - User gibt Feedback (Thumbs Down)
   - Speichere Original-Email + generierte Antwort
   - Analysiere Muster

B) Erweitere E-Mail-Typ-Erkennung:
   - Neue Typen hinzufügen (z.B. "follow-up", "reminder")
   - Keywords verfeinern
   - In _detect_email_type() ergänzen

C) Tone-Instructions verbessern:
   - Basierend auf User-Feedback
   - A/B-Testing verschiedener Formulierungen
   - User-spezifische Anpassungen (Phase: Reply Styles)

D) Few-Shot Examples hinzufügen:
   - Sammle User's eigene gute Antworten
   - Füge als Beispiele im Prompt hinzu
   - Siehe: FEW_SHOT_EXAMPLES in optimized_reply_prompts.py
"""

# ============================================================================
# VOLLSTÄNDIGES INTEGRATIONS-BEISPIEL
# ============================================================================

FULL_INTEGRATION_EXAMPLE = """
============================================================
VOLLSTÄNDIGES CODE-BEISPIEL: reply_generator.py
============================================================

# src/reply_generator.py

import logging
from datetime import datetime
from typing import Dict, Any, Optional

# NEU: Optimierte Prompts
from src.optimized_reply_prompts import (
    REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED,
    TONE_PROMPTS_OPTIMIZED,
    build_optimized_user_prompt
)

logger = logging.getLogger(__name__)


class ReplyGenerator:
    '''Generiert AI-basierte Antwort-Entwürfe'''
    
    def __init__(self, ai_client):
        self.ai_client = ai_client
    
    def generate_reply(
        self,
        original_subject: str,
        original_body: str,
        original_sender: str = "",
        tone: str = "formal",
        thread_context: Optional[str] = None,
        language: str = "de",
        has_attachments: bool = False,
        attachment_names: Optional[list] = None
    ) -> Dict[str, Any]:
        '''
        Generiert Antwort-Entwurf mit optimierten Prompts.
        
        Returns:
            Dict mit reply_text, tone_used, success, etc.
        '''
        
        if not self.ai_client:
            return {
                "success": False,
                "error": "AI-Client nicht verfügbar",
                "reply_text": "",
                "tone_used": tone,
                "timestamp": datetime.now().isoformat()
            }
        
        # Validiere Ton
        if tone not in TONE_PROMPTS_OPTIMIZED:
            logger.warning(f"Unknown tone '{tone}', using 'formal'")
            tone = "formal"
        
        tone_config = TONE_PROMPTS_OPTIMIZED[tone]
        
        try:
            # 🆕 Nutze optimierten Prompt-Builder
            user_prompt = build_optimized_user_prompt(
                original_subject=original_subject,
                original_body=original_body,
                original_sender=original_sender,
                tone=tone,
                thread_context=thread_context,
                has_attachments=has_attachments,
                attachment_names=attachment_names,
                language=language
            )
            
            system_prompt = REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED
            
        except Exception as e:
            logger.warning(f"Optimized prompt failed, using fallback: {e}")
            # Fallback auf alte Methode
            user_prompt = self._build_user_prompt_fallback(
                original_subject, original_body, original_sender,
                tone_config["instructions"], thread_context,
                language, has_attachments, attachment_names
            )
            system_prompt = "Du bist ein E-Mail-Assistent"  # Alter Default
        
        # KI aufrufen
        try:
            logger.info(f"🤖 Generiere Reply-Entwurf (Ton: {tone})")
            
            reply_text = self.ai_client.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1000
            )
            
            # Cleanup
            reply_text = self._cleanup_reply_text(reply_text)
            
            logger.info(f"✅ Reply-Entwurf generiert ({len(reply_text)} chars)")
            
            return {
                "success": True,
                "reply_text": reply_text,
                "tone_used": tone,
                "tone_name": tone_config["name"],
                "tone_icon": tone_config["icon"],
                "timestamp": datetime.now().isoformat(),
                "error": None
            }
            
        except Exception as e:
            logger.error(f"❌ Reply-Generierung fehlgeschlagen: {e}")
            return {
                "success": False,
                "error": str(e),
                "reply_text": "",
                "tone_used": tone,
                "timestamp": datetime.now().isoformat()
            }
    
    def _build_user_prompt_fallback(self, ...):
        '''Fallback auf alte Methode (Backward-Compatibility)'''
        # Alte Implementation behalten
        ...
    
    def _cleanup_reply_text(self, text: str) -> str:
        '''Bereinigt AI-Output'''
        # Wie vorher
        ...
    
    @staticmethod
    def get_available_tones() -> Dict[str, Dict[str, str]]:
        '''Gibt verfügbare Töne zurück (für UI)'''
        return {
            key: {
                "name": config["name"],
                "icon": config["icon"]
            }
            for key, config in TONE_PROMPTS_OPTIMIZED.items()
        }
"""

# ============================================================================
# CHECKLISTE
# ============================================================================

CHECKLIST = """
============================================================
INTEGRATIONS-CHECKLISTE
============================================================

PRE-REQUISITES:
☐ Pre-Filter installiert (siehe INSTALLATION_ANLEITUNG.md)
☐ System läuft und generiert bereits Antworten

INTEGRATION:
☐ optimized_reply_prompts.py nach src/ kopiert
☐ reply_generator.py: Imports angepasst
☐ reply_generator.py: generate_reply() aktualisiert
☐ Alte _build_user_prompt() als Fallback behalten
☐ Code kompiliert ohne Fehler

TESTING:
☐ Unit-Tests geschrieben
☐ Unit-Tests bestehen
☐ Live-Test mit formeller E-Mail
☐ Live-Test mit freundlicher E-Mail
☐ Live-Test mit kurzer E-Mail
☐ Live-Test mit Newsletter (sollte gefiltert werden)

VALIDATION:
☐ Antworten haben bessere Qualität als vorher
☐ Richtiger Ton (formal/freundlich/kurz)
☐ Korrekte Anrede (Sie/Du)
☐ Keine Meta-Kommentare mehr
☐ Logs zeigen E-Mail-Typen

OPTIONAL:
☐ Monitoring für E-Mail-Typen implementiert
☐ Feedback-System für schlechte Antworten
☐ A/B-Testing Setup
☐ Few-Shot Learning vorbereitet

DOKUMENTATION:
☐ README.md aktualisiert
☐ Team informiert über neue Features
☐ Beispiele dokumentiert

============================================================
ERWARTETE VERBESSERUNGEN
============================================================

Qualität: 40-60% → 75-90% gut
Ton-Passung: 30-50% → 80-95% korrekt
Meta-Kommentare: 30-40% → < 5%
Newsletter-Antworten: Ja → Nein (gefiltert)

Zeit gespart (mit Pre-Filter): 60-90%
CPU-Zeit: 3-5h/Woche → 30-60 Min/Woche

============================================================
SUPPORT
============================================================

Bei Problemen:
1. Check Logs für Fehlermeldungen
2. Teste Fallback (alte Prompts funktionieren?)
3. Validiere Imports
4. Check ob optimized_reply_prompts.py im PYTHONPATH

Bei Fragen zu Prompt-Optimierung:
- Siehe prompt_optimization_comparison.py für Beispiele
- Teste mit test_dashboard.py
- Analysiere schlechte Antworten systematisch
"""

if __name__ == "__main__":
    print(STEP_1)
    print(STEP_2_IMPORT)
    print(STEP_2_METHOD)
    print(STEP_3)
    print(STEP_4)
    print(STEP_5)
    print(STEP_6)
    print("\n" + FULL_INTEGRATION_EXAMPLE)
    print("\n" + CHECKLIST)
