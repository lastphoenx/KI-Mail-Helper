"""
Debug Logging System für Reply Generation & Anonymisierung
============================================================

Zentrales System zum Ein-/Ausschalten von detailliertem Debug-Logging.
Schreibt in separate Log-Files um den Datenfluss zu verfolgen.

⚠️ ACHTUNG: NUR FÜR ENTWICKLUNG/DEBUGGING!
   In Produktion DEAKTIVIEREN um keine sensiblen Daten zu loggen!

Usage:
    from src.debug_logger import DebugLogger
    
    if DebugLogger.is_enabled():
        DebugLogger.log_sanitizer_input(subject, body)
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class DebugLogger:
    """Zentrales Debug-Logging für Reply-Generation Pipeline"""
    
    # ⚠️ HIER EIN-/AUSSCHALTEN ⚠️
    # True = Logging aktiv (nur für Debugging!)
    # False = Logging deaktiviert (Produktion!)
    ENABLED = False  # 🔒 PRODUCTION: Debug-Logging deaktiviert
    
    # Log-Verzeichnis
    LOG_DIR = Path("logs/debug_reply")
    
    # Log-Dateien
    SANITIZER_INPUT = "sanitizer_input.log"
    SANITIZER_CLEANED = "sanitizer_input_cleaned_up_by_sanitizer.log"
    SANITIZER_OUTPUT = "sanitizer_output.log"
    SANITIZER_ANONYMIZED = "sanitizer_anonymized_output.log"
    AI_INPUT = "ai_input.log"
    AI_OUTPUT = "ai_output.log"
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Prüft ob Debug-Logging aktiviert ist"""
        return cls.ENABLED
    
    @classmethod
    def _ensure_log_dir(cls):
        """Erstellt Log-Verzeichnis falls nicht vorhanden"""
        if cls.ENABLED:
            cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def _write_log(cls, filename: str, content: str, session_id: Optional[str] = None):
        """
        Schreibt in Log-Datei
        
        Args:
            filename: Log-Dateiname
            content: Zu loggender Content
            session_id: Optional - Session-ID für Zuordnung
        """
        if not cls.ENABLED:
            return
        
        try:
            cls._ensure_log_dir()
            log_path = cls.LOG_DIR / filename
            
            timestamp = datetime.now().isoformat()
            session_marker = f" [Session: {session_id}]" if session_id else ""
            separator = "=" * 80
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{separator}\n")
                f.write(f"[{timestamp}]{session_marker}\n")
                f.write(f"{separator}\n")
                f.write(content)
                f.write(f"\n{separator}\n\n")
            
            logger.info(f"🔍 Debug-Log geschrieben: {log_path}")
            
        except Exception as e:
            logger.error(f"❌ Debug-Logging fehlgeschlagen: {e}")
    
    @classmethod
    def log_sanitizer_input(
        cls, 
        subject: str, 
        body: str, 
        sender: str = "",
        session_id: Optional[str] = None
    ):
        """
        Loggt Input für ContentSanitizer (Original-Daten vor Anonymisierung)
        
        Args:
            subject: Original Subject
            body: Original Body (decrypted)
            sender: Original Sender
            session_id: Optional - Session-ID für Zuordnung
        """
        if not cls.ENABLED:
            return
        
        content = f"""SANITIZER INPUT (Original-Daten VOR Anonymisierung)
═══════════════════════════════════════════════════════

SENDER: {sender}

SUBJECT: {subject}

BODY (erste 2000 Zeichen):
{body[:2000]}

BODY Länge: {len(body)} Zeichen
"""
        cls._write_log(cls.SANITIZER_INPUT, content, session_id)
    
    @classmethod
    def log_sanitizer_cleaned(
        cls,
        subject: str,
        body: str,
        session_id: Optional[str] = None
    ):
        """
        Loggt cleaned Input von ContentSanitizer (Nach HTML-Cleanup, VOR Anonymisierung)
        
        Args:
            subject: Cleaned Subject
            body: Cleaned Body (HTML entfernt)
            session_id: Optional - Session-ID für Zuordnung
        """
        if not cls.ENABLED:
            return
        
        content = f"""SANITIZER CLEANED INPUT (Nach HTML-Cleanup, VOR Anonymisierung)
═══════════════════════════════════════════════════════════════════════

SUBJECT (cleaned): {subject}

BODY (cleaned, erste 2000 Zeichen):
{body[:2000]}

BODY Länge: {len(body)} Zeichen
"""
        cls._write_log(cls.SANITIZER_CLEANED, content, session_id)
    
    @classmethod
    def log_sanitizer_anonymized(
        cls,
        result,  # SanitizationResult object
        session_id: Optional[str] = None
    ):
        """
        Loggt vollständigen anonymisierten Output von ContentSanitizer
        
        Args:
            result: SanitizationResult von ContentSanitizer
            session_id: Optional - Session-ID für Zuordnung
        """
        if not cls.ENABLED:
            return
        
        content = f"""SANITIZER ANONYMIZED OUTPUT (Vollständiger anonymisierter Content)
═════════════════════════════════════════════════════════════════════

SUBJECT (anonymisiert): {result.subject}

BODY (anonymisiert, erste 2000 Zeichen):
{result.body[:2000]}

BODY Länge: {len(result.body)} Zeichen

STATISTIK:
- Gefundene Entities: {result.entities_found}
- Verarbeitungszeit: {result.processing_time_ms}ms

ENTITY MAP (für De-Anonymisierung):
"""
        # Entity Map ausgeben
        if hasattr(result, 'entity_map') and result.entity_map:
            entity_map = result.entity_map
            for placeholder, original_value in entity_map.reverse.items():
                content += f"  {placeholder} → {original_value}\n"
        
        cls._write_log(cls.SANITIZER_ANONYMIZED, content, session_id)
    
    @classmethod
    def log_sanitizer_output(
        cls,
        result,  # SanitizationResult object
        session_id: Optional[str] = None
    ):
        """
        Loggt generellen Output von ContentSanitizer (Statistiken + Kurzfassung)
        
        Args:
            result: SanitizationResult von ContentSanitizer
            session_id: Optional - Session-ID für Zuordnung
        """
        if not cls.ENABLED:
            return
        
        content = f"""SANITIZER OUTPUT (Statistiken + Kurzfassung)
═════════════════════════════════════════════════

STATISTIK:
- Gefundene Entities: {result.entities_found}
- Verarbeitungszeit: {result.processing_time_ms}ms
- Level: {result.level}

ENTITY TYPES:
"""
        # Entity Types zählen
        for entity_type, count in result.entities_by_type.items():
            content += f"  {entity_type}: {count}\n"
        
        content += f"\nSUBJECT (erste 200 Zeichen): {result.subject[:200]}\n"
        content += f"\nBODY (erste 500 Zeichen): {result.body[:500]}\n"
        
        cls._write_log(cls.SANITIZER_OUTPUT, content, session_id)
    
    @classmethod
    def log_ai_input(
        cls,
        system_prompt: str,
        user_prompt: str,
        model: str = "",
        session_id: Optional[str] = None
    ):
        """
        Loggt Input für AI (Was an AI-Modell geschickt wird)
        
        Args:
            system_prompt: System-Prompt
            user_prompt: User-Prompt
            model: Modell-Name
            session_id: Optional - Session-ID für Zuordnung
        """
        if not cls.ENABLED:
            return
        
        content = f"""AI INPUT (Was an AI-Modell geschickt wird)
═══════════════════════════════════════════════

MODEL: {model}

SYSTEM PROMPT:
{system_prompt}

USER PROMPT (erste 3000 Zeichen):
{user_prompt[:3000]}

USER PROMPT Länge: {len(user_prompt)} Zeichen
"""
        cls._write_log(cls.AI_INPUT, content, session_id)
    
    @classmethod
    def log_ai_output(
        cls,
        response: str,
        model: str = "",
        session_id: Optional[str] = None
    ):
        """
        Loggt Output von AI (Was AI zurückgibt)
        
        Args:
            response: AI-Response
            model: Modell-Name
            session_id: Optional - Session-ID für Zuordnung
        """
        if not cls.ENABLED:
            return
        
        content = f"""AI OUTPUT (Was AI zurückgibt - RAW, ohne Cleanup)
════════════════════════════════════════════════════════

MODEL: {model}

RESPONSE (erste 2000 Zeichen):
{response[:2000]}

RESPONSE Länge: {len(response)} Zeichen
"""
        cls._write_log(cls.AI_OUTPUT, content, session_id)
    
    @classmethod
    def clear_logs(cls):
        """Löscht alle Debug-Logs (für neue Session)"""
        if not cls.ENABLED:
            return
        
        try:
            for log_file in [cls.SANITIZER_INPUT, cls.SANITIZER_CLEANED,
                           cls.SANITIZER_OUTPUT, cls.SANITIZER_ANONYMIZED,
                           cls.AI_INPUT, cls.AI_OUTPUT]:
                log_path = cls.LOG_DIR / log_file
                if log_path.exists():
                    log_path.unlink()
            logger.info("🧹 Debug-Logs gelöscht")
        except Exception as e:
            logger.error(f"❌ Fehler beim Löschen der Debug-Logs: {e}")
    
    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Gibt Status des Debug-Loggers zurück"""
        return {
            "enabled": cls.ENABLED,
            "log_dir": str(cls.LOG_DIR),
            "log_files": {
                "sanitizer_input": cls.SANITIZER_INPUT,
                "sanitizer_cleaned": cls.SANITIZER_CLEANED,
                "sanitizer_output": cls.SANITIZER_OUTPUT,
                "sanitizer_anonymized": cls.SANITIZER_ANONYMIZED,
                "ai_input": cls.AI_INPUT,
                "ai_output": cls.AI_OUTPUT,
            }
        }


if __name__ == "__main__":
    # Test
    print("Debug Logger Status:")
    print(DebugLogger.get_status())
    
    if DebugLogger.is_enabled():
        print("\n⚠️  DEBUG-LOGGING IST AKTIVIERT!")
        print("   Zum Deaktivieren: ENABLED = False setzen")
    else:
        print("\n✅ Debug-Logging ist deaktiviert")
