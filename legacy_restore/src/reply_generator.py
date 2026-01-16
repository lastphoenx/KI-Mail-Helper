"""
Reply Draft Generator Service (Phase G.1)
==========================================

Generiert KI-basierte Antwort-Entwürfe mit wählbarem Ton.

Features:
- Tone-Auswahl: formal, friendly, brief, decline
- Thread-Context Integration (Phase E)
- Automatische Anrede basierend auf Sender
- Deutsche Antworten für deutsche Emails

Usage:
    from src.reply_generator import ReplyGenerator
    
    generator = ReplyGenerator(ai_client)
    draft = generator.generate_reply(
        original_subject="Angebot Anfrage",
        original_body="Können Sie mir ein Angebot schicken?",
        original_sender="kunde@example.com",
        tone="formal",
        thread_context="..."  # Optional
    )
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

# 🔍 Debug-Logging System
from src.debug_logger import DebugLogger

# 🆕 Optimierte Prompts importieren (mit Fallback für Backward-Compatibility)
try:
    from src.optimized_reply_prompts import (
        REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED,
        TONE_PROMPTS_OPTIMIZED,
        build_optimized_user_prompt
    )
    OPTIMIZED_PROMPTS_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("✅ Optimierte Reply-Prompts geladen")
except ImportError as e:
    OPTIMIZED_PROMPTS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️ Optimierte Prompts nicht verfügbar (Fallback auf Standard): {e}")

logger = logging.getLogger(__name__)

# Tone-Definitions mit spezifischen Prompts
TONE_PROMPTS = {
    "formal": {
        "name": "Formell",
        "icon": "📜",
        "instructions": """
Schreibe eine FORMELLE geschäftliche Antwort:
- Verwende "Sie" (nicht "Du")
- Förmliche Anrede: "Sehr geehrte/r Frau/Herr [Name]" oder "Sehr geehrte Damen und Herren"
- Höflicher, professioneller Ton
- Vollständige Sätze, korrekte Grammatik
- Abschluss: "Mit freundlichen Grüßen"
- Keine Emojis, keine umgangssprachlichen Ausdrücke
"""
    },
    "friendly": {
        "name": "Freundlich",
        "icon": "😊",
        "instructions": """
Schreibe eine FREUNDLICHE, aber trotzdem professionelle Antwort:
- Verwende "Sie" oder "Du" je nach Kontext (wenn Original-Email "Du" nutzt)
- WICHTIG: Uni-Jargon verwenden - Anrede: "Liebe [Vorname]" oder "Lieber [Vorname]" (NICHT "Hallo"!)
- Warmer, persönlicher Ton
- Gerne ein Emoji verwenden (nicht übertreiben!)
- Abschluss: "Viele Grüße" oder "Beste Grüße"
- Natürlich und menschlich klingen
"""
    },
    "brief": {
        "name": "Kurz & Knapp",
        "icon": "⚡",
        "instructions": """
Schreibe eine KURZE, prägnante Antwort:
- Maximal 3-4 Sätze
- Direkt auf den Punkt kommen
- Keine ausschweifenden Erklärungen
- Einfache Anrede: "Hallo" oder nur Name
- Kurzer Abschluss: "Grüße" oder "VG"
- Effizienz über Höflichkeit (aber nicht unhöflich!)
"""
    },
    "decline": {
        "name": "Höfliche Ablehnung",
        "icon": "❌",
        "instructions": """
Schreibe eine HÖFLICHE ABLEHNUNG:
- Bedanke dich für die Anfrage/das Interesse
- Erkläre kurz (1 Satz), warum eine Absage nötig ist (z.B. "leider keine Kapazitäten")
- Biete ggf. Alternativen an (falls sinnvoll)
- Höflicher, entschuldigender Ton
- Verwende "Sie"
- Abschluss: "Mit freundlichen Grüßen"
- Lasse die Tür für zukünftige Zusammenarbeit offen
"""
    }
}

REPLY_GENERATION_SYSTEM_PROMPT = """
Du bist ein professioneller E-Mail-Assistent. Deine Aufgabe ist es, Antwort-Entwürfe auf E-Mails zu schreiben.

WICHTIGE REGELN:
1. Schreibe NUR den E-Mail-Text (Body), KEINE Betreffzeile
2. Verwende die GLEICHE SPRACHE wie die Original-E-Mail (Deutsch für deutsche Mails)
3. Beziehe dich auf den Inhalt der Original-E-Mail
4. Halte dich an den vorgegebenen TON (formal/friendly/brief/decline)
5. Nutze Thread-Context falls vorhanden um bessere Antworten zu schreiben
6. Erfinde KEINE Fakten - bleibe bei dem was in der Original-Email steht
7. Formatiere den Text mit Absätzen (\\n\\n) für bessere Lesbarkeit

ANREDE-EXTRAKTION:
- Wenn Absender-Name vorhanden: Nutze "Frau/Herr [Nachname]" (formal) oder "Vorname" (friendly/brief)
- Wenn kein Name: Nutze "Sehr geehrte Damen und Herren" (formal) oder "Hallo" (friendly/brief)

LÄNGE:
- Formal: 4-6 Sätze
- Friendly: 4-6 Sätze
- Brief: 2-3 Sätze (maximal!)
- Decline: 3-5 Sätze

Gib NUR den E-Mail-Text zurück, keine Metadaten, keine Erklärungen!
""".strip()


class ReplyGenerator:
    """Service zum Generieren von Antwort-Entwürfen"""
    
    def __init__(self, ai_client=None):
        """
        Args:
            ai_client: AI Client mit chat/completion API (LocalOllama, OpenAI, Anthropic)
        """
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
        """
        Generiert einen Antwort-Entwurf.
        
        Args:
            original_subject: Betreff der Original-Email
            original_body: Body der Original-Email
            original_sender: Absender (für Anrede-Extraktion)
            tone: Ton der Antwort (formal/friendly/brief/decline)
            thread_context: Optional - Thread-Context aus Phase E
            language: Sprache (de/en)
            has_attachments: Ob Original-Email Anhänge hat
            attachment_names: Liste der Anhang-Namen (optional)
            
        Returns:
            Dict mit:
            - reply_text: Generierter Antwort-Text
            - tone_used: Verwendeter Ton
            - timestamp: Generierungs-Zeitpunkt
            - success: True/False
            - error: Fehlermeldung falls success=False
        """
        if not self.ai_client:
            return {
                "success": False,
                "error": "AI-Client nicht verfügbar",
                "reply_text": "",
                "tone_used": tone,
                "timestamp": datetime.now().isoformat()
            }
        
        # Validiere Ton
        if tone not in TONE_PROMPTS:
            logger.warning(f"Unknown tone '{tone}', falling back to 'formal'")
            tone = "formal"
        
        tone_config = TONE_PROMPTS[tone]
        
        # 🆕 Nutze optimierte Prompts falls verfügbar
        if OPTIMIZED_PROMPTS_AVAILABLE:
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
                system_prompt = REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED
                logger.debug(f"🎯 Using optimized prompts (Type detection enabled)")
            except Exception as e:
                # Fallback auf alte Methode
                logger.warning(f"Optimized prompt failed, using fallback: {e}")
                user_prompt = self._build_user_prompt(
                    original_subject=original_subject,
                    original_body=original_body,
                    original_sender=original_sender,
                    tone_instructions=tone_config["instructions"],
                    thread_context=thread_context,
                    language=language,
                    has_attachments=has_attachments,
                    attachment_names=attachment_names
                )
                system_prompt = REPLY_GENERATION_SYSTEM_PROMPT
        else:
            # Fallback: Alte Methode
            user_prompt = self._build_user_prompt(
                original_subject=original_subject,
                original_body=original_body,
                original_sender=original_sender,
                tone_instructions=tone_config["instructions"],
                thread_context=thread_context,
                language=language,
                has_attachments=has_attachments,
                attachment_names=attachment_names
            )
            system_prompt = REPLY_GENERATION_SYSTEM_PROMPT
        
        # Rufe AI auf
        try:
            logger.info(f"🤖 Generiere Reply-Entwurf (Ton: {tone})")
            
            # 🔍 DEBUG: Log AI Input um Anonymisierungs-Problem zu debuggen
            logger.debug(f"🔍 REPLY DEBUG - AI Input User Prompt (erste 500 Zeichen): {user_prompt[:500]}...")
            logger.debug(f"🔍 REPLY DEBUG - Original Body (erste 300 Zeichen): {original_body[:300]}...")
            
            # 🔍 Zentrales Debug-Logging
            if DebugLogger.is_enabled():
                session_id = f"reply_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                DebugLogger.log_ai_input(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=getattr(self.ai_client, 'model', 'unknown'),
                    session_id=session_id
                )
            
            # Nutze generate_text() - in Phase G.2 zu allen AI Clients hinzugefügt
            if hasattr(self.ai_client, 'generate_text'):
                reply_text = self.ai_client.generate_text(
                    system_prompt=system_prompt,  # 🆕 Dynamisch: optimiert oder standard
                    user_prompt=user_prompt,
                    max_tokens=1000
                )
            else:
                # Fallback für ältere Clients ohne generate_text()
                logger.warning("AI-Client hat keine generate_text() Methode, nutze Fallback")
                result = self.ai_client.analyze_email(
                    subject=original_subject,
                    body=f"GENERATE REPLY:\n{user_prompt}",
                    context=thread_context
                )
                reply_text = result.get("summary_de", "")
            
            # 🔍 DEBUG: Log AI Output um Anonymisierungs-Problem zu debuggen  
            logger.debug(f"🔍 REPLY DEBUG - AI Raw Output (erste 300 Zeichen): {reply_text[:300]}...")
            
            # 🔍 Zentrales Debug-Logging
            if DebugLogger.is_enabled():
                DebugLogger.log_ai_output(
                    response=reply_text,
                    model=getattr(self.ai_client, 'model', 'unknown'),
                    session_id=session_id
                )
            
            # Cleanup: Entferne mögliche Metadaten
            reply_text = self._cleanup_reply_text(reply_text)
            
            # 🆕 Normalisiere AI-generierte Platzhalter zu ContentSanitizer-Format
            reply_text = self._normalize_ai_placeholders(reply_text, original_body)
            
            # 🔍 DEBUG: Log nach Cleanup
            logger.debug(f"🔍 REPLY DEBUG - After Cleanup (erste 300 Zeichen): {reply_text[:300]}...")
            
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
    
    def _build_user_prompt(
        self,
        original_subject: str,
        original_body: str,
        original_sender: str,
        tone_instructions: str,
        thread_context: Optional[str],
        language: str,
        has_attachments: bool = False,
        attachment_names: Optional[list] = None
    ) -> str:
        """Baut den User-Prompt für die Reply-Generierung"""
        
        # Anhang-Hinweis
        attachment_hint = ""
        if has_attachments:
            if attachment_names:
                attachment_hint = f"\n📎 ANHÄNGE: {', '.join(attachment_names)}\n"
            else:
                attachment_hint = "\n📎 ANHÄNGE: Die Original-Email enthält Anhänge\n"
        
        prompt = f"""
{tone_instructions}

ORIGINAL E-MAIL:
Von: {original_sender or "Unbekannt"}
Betreff: {original_subject or "(Kein Betreff)"}{attachment_hint}

{original_body[:2000]}  
"""
        
        # Thread-Context hinzufügen falls vorhanden
        if thread_context:
            prompt += f"\n\nKONVERSATIONS-KONTEXT (frühere E-Mails im Thread):\n{thread_context[:1000]}\n"
        
        prompt += """

AUFGABE:
Schreibe JETZT die Antwort-E-Mail (nur Body-Text, keine Betreffzeile!).
Beziehe dich auf den Inhalt der Original-E-Mail und halte den vorgegebenen Ton ein.
"""
        
        return prompt.strip()
    
    def _cleanup_reply_text(self, text: str) -> str:
        """
        Bereinigt generierten Text von möglichen Metadaten oder Formatierungs-Artefakten.
        """
        if not text:
            return ""
        
        # Entferne mögliche "Subject:" oder "Betreff:" Zeilen (falls AI sie hinzufügt)
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_lower = line.lower().strip()
            # Skip Subject/Betreff Zeilen
            if line_lower.startswith('subject:') or line_lower.startswith('betreff:'):
                continue
            # Skip "Von:" oder "To:" Zeilen
            if line_lower.startswith('von:') or line_lower.startswith('to:') or line_lower.startswith('an:'):
                continue
            cleaned_lines.append(line)
        
        cleaned = '\n'.join(cleaned_lines).strip()
        
        # Entferne führende/trailing Quotes falls vorhanden
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        
        return cleaned
    
    def _normalize_ai_placeholders(self, reply_text: str, original_body: str) -> str:
        """
        Normalisiert AI-generierte Platzhalter zu ContentSanitizer-Format.
        
        Problem: AI erstellt manchmal eigene Platzhalter wie [23_2], [EMAIL_1] etc.
        statt die im Input vorhandenen [PERSON_X] zu verwenden.
        
        Diese Funktion ersetzt AI-generierte Platzhalter durch die korrekten
        ContentSanitizer-Platzhalter basierend auf dem Original-Content.
        
        Args:
            reply_text: AI-generierte Antwort (möglicherweise mit [23_2] etc.)
            original_body: Original anonymisierter Body mit [PERSON_X] Platzhaltern
        
        Returns:
            Reply-Text mit normalisierten Platzhaltern
        """
        import re
        
        # Extrahiere ContentSanitizer-Platzhalter aus Original-Body
        sanitizer_placeholders = re.findall(r'\[(?:PERSON|ORG|ADDRESS|EMAIL|PHONE|IBAN|URL)_\d+\]', original_body)
        
        # Finde AI-generierte Platzhalter im Reply-Text 
        # Muster: [Zahl_Zahl], [TEXT_Zahl], etc.
        ai_placeholders = re.findall(r'\[\w*\d+_?\d*\]', reply_text)
        
        # Wenn AI eigene Platzhalter erstellt hat
        if ai_placeholders and sanitizer_placeholders:
            logger.debug(f"🔄 Normalisiere AI-Platzhalter: {ai_placeholders} → ContentSanitizer Format")
            
            # Einfache Zuordnung: Ersetze AI-Platzhalter durch die ersten verfügbaren Sanitizer-Platzhalter
            for i, ai_placeholder in enumerate(set(ai_placeholders)):
                if i < len(sanitizer_placeholders):
                    # Verwende entsprechenden Sanitizer-Platzhalter
                    sanitizer_replacement = sanitizer_placeholders[i]
                    reply_text = reply_text.replace(ai_placeholder, sanitizer_replacement)
                    logger.debug(f"🔄 {ai_placeholder} → {sanitizer_replacement}")
                else:
                    # Fallback: Entferne überzählige AI-Platzhalter
                    reply_text = reply_text.replace(ai_placeholder, "[ANONYMIZED]")
                    logger.warning(f"⚠️ Überzähliger AI-Platzhalter entfernt: {ai_placeholder}")
        
        return reply_text
    
    @staticmethod
    def get_available_tones() -> Dict[str, Dict[str, str]]:
        """
        Gibt alle verfügbaren Töne zurück (für UI-Dropdown).
        
        Returns:
            Dict mit tone_key -> {name, icon}
        """
        return {
            key: {
                "name": config["name"],
                "icon": config["icon"]
            }
            for key, config in TONE_PROMPTS.items()
        }
    
    def generate_reply_with_user_style(
        self,
        db: Session,
        user_id: int,
        original_subject: str,
        original_body: str,
        original_sender: str = "",
        tone: str = "formal",
        thread_context: Optional[str] = None,
        language: str = "de",
        has_attachments: bool = False,
        attachment_names: Optional[list] = None,
        master_key: str = None,
        account_id: int = None
    ) -> Dict[str, Any]:
        """
        Generiert Antwort-Entwurf MIT User-spezifischen Stil-Einstellungen.
        
        Unterschied zu generate_reply():
        - Lädt User-Einstellungen aus DB
        - Merged mit Base-Tone-Instructions
        - Wendet Anrede, Gruss, Signatur, Custom Instructions an
        - Priorität: Account-Signatur > User-Style-Signatur
        
        Args:
            db: SQLAlchemy Session
            user_id: User ID für Style-Settings
            master_key: Zum Entschlüsseln von Signatur/Instructions
            account_id: Optional - Mail Account ID für Account-Signatur
            ... (rest wie generate_reply)
        
        Returns:
            Dict mit reply_text, tone_used, settings_applied, etc.
        """
        if not self.ai_client:
            return {
                "success": False,
                "error": "AI-Client nicht verfügbar",
                "reply_text": "",
                "tone_used": tone,
                "timestamp": datetime.now().isoformat()
            }
        
        # Validiere Ton
        if tone not in TONE_PROMPTS:
            logger.warning(f"Unknown tone '{tone}', falling back to 'formal'")
            tone = "formal"
        
        # 🆕 User-Style-Settings laden
        from src.services.reply_style_service import ReplyStyleService
        try:
            # get_effective_settings liefert bereits: Style > Global
            effective_settings = ReplyStyleService.get_effective_settings(
                db, user_id, tone, master_key
            )
            
            # 🆕 Phase I.2: Account-Signatur hat höchste Priorität (überschreibt Style + Global)
            if account_id and master_key:
                account_signature = ReplyStyleService.get_account_signature(
                    db, account_id, master_key
                )
                if account_signature:
                    effective_settings["signature_text"] = account_signature
                    effective_settings["signature_enabled"] = True
                    logger.info(f"✍️ Using account-specific signature for account {account_id} (Priority: Account > Style > Global)")
            
        except Exception as e:
            logger.error(f"Failed to load reply style settings: {e}")
            # Fallback auf Standard-Verhalten
            effective_settings = {}
        
        # 🆕 Kombinierte Instructions bauen
        base_instructions = TONE_PROMPTS[tone]["instructions"]
        if effective_settings:
            enhanced_instructions = ReplyStyleService.build_style_instructions(
                effective_settings, 
                base_instructions
            )
        else:
            enhanced_instructions = base_instructions
        
        # 🆕 User-Prompt bauen - mit optimierten Prompts falls verfügbar
        if OPTIMIZED_PROMPTS_AVAILABLE:
            try:
                # Bei User-Style: Erst optimierten Basis-Prompt bauen
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
                
                # Dann Style-Instructions einfügen (wenn vorhanden)
                if effective_settings:
                    # Ersetze die Ton-Instructions durch enhanced_instructions
                    # (enthält User-Styles wie Anrede, Gruss, Signatur)
                    base_tone_instructions = TONE_PROMPTS_OPTIMIZED.get(tone, TONE_PROMPTS_OPTIMIZED["formal"])["instructions"]
                    user_prompt = user_prompt.replace(base_tone_instructions, enhanced_instructions)
                    logger.debug(f"✍️ Style-Instructions in optimized prompt injected")
                
                system_prompt = REPLY_GENERATION_SYSTEM_PROMPT_OPTIMIZED
                logger.debug(f"🎯 Using optimized prompts with user-style (Type detection enabled)")
            except Exception as e:
                logger.warning(f"Optimized prompt with user-style failed, using fallback: {e}")
                user_prompt = self._build_user_prompt(
                    original_subject=original_subject,
                    original_body=original_body,
                    original_sender=original_sender,
                    tone_instructions=enhanced_instructions,
                    thread_context=thread_context,
                    language=language,
                    has_attachments=has_attachments,
                    attachment_names=attachment_names,
                )
                system_prompt = REPLY_GENERATION_SYSTEM_PROMPT
        else:
            # Fallback: Alte Methode mit enhanced_instructions
            user_prompt = self._build_user_prompt(
                original_subject=original_subject,
                original_body=original_body,
                original_sender=original_sender,
                tone_instructions=enhanced_instructions,
                thread_context=thread_context,
                language=language,
                has_attachments=has_attachments,
                attachment_names=attachment_names,
            )
            system_prompt = REPLY_GENERATION_SYSTEM_PROMPT
        
        # KI-Aufruf (wie bisher)
        try:
            logger.info(f"🤖 Generiere Reply-Entwurf mit User-Stil (Ton: {tone})")
            
            # 🔍 DEBUG: Log User-Style AI Input um Anonymisierungs-Problem zu debuggen
            logger.debug(f"🔍 USER-STYLE DEBUG - AI Input User Prompt (erste 500 Zeichen): {user_prompt[:500]}...")
            logger.debug(f"🔍 USER-STYLE DEBUG - Original Body (erste 300 Zeichen): {original_body[:300]}...")
            
            # 🔍 Zentrales Debug-Logging
            if DebugLogger.is_enabled():
                session_id = f"user_style_reply_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                DebugLogger.log_ai_input(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=getattr(self.ai_client, 'model', 'unknown'),
                    session_id=session_id
                )
            
            # Nutze generate_text() - in Phase G.2 zu allen AI Clients hinzugefügt
            if hasattr(self.ai_client, 'generate_text'):
                reply_text = self.ai_client.generate_text(
                    system_prompt=system_prompt,  # 🆕 Dynamisch: optimiert oder standard
                    user_prompt=user_prompt,
                    max_tokens=1000
                )
            else:
                # Fallback für ältere Clients ohne generate_text()
                logger.warning("AI-Client hat keine generate_text() Methode, nutze Fallback")
                result = self.ai_client.analyze_email(
                    subject=original_subject,
                    body=f"GENERATE REPLY:\n{user_prompt}",
                    context=thread_context
                )
                reply_text = result.get("summary_de", "")
            
            # 🔍 DEBUG: Log User-Style AI Output um Anonymisierungs-Problem zu debuggen
            logger.debug(f"🔍 USER-STYLE DEBUG - AI Raw Output (erste 300 Zeichen): {reply_text[:300]}...")
            
            # 🔍 Zentrales Debug-Logging
            if DebugLogger.is_enabled():
                DebugLogger.log_ai_output(
                    response=reply_text,
                    model=getattr(self.ai_client, 'model', 'unknown'),
                    session_id=session_id
                )
            
            # Cleanup
            reply_text = self._cleanup_reply_text(reply_text)
            
            # 🆕 Normalisiere AI-generierte Platzhalter zu ContentSanitizer-Format
            reply_text = self._normalize_ai_placeholders(reply_text, original_body)
            
            # 🔍 DEBUG: Log nach Cleanup
            logger.debug(f"🔍 USER-STYLE DEBUG - After Cleanup (erste 300 Zeichen): {reply_text[:300]}...")
            
            logger.info(f"✅ Reply-Entwurf mit User-Stil generiert ({len(reply_text)} chars)")
            
            return {
                "success": True,
                "reply_text": reply_text,
                "tone_used": tone,
                "tone_name": TONE_PROMPTS[tone]["name"],
                "tone_icon": TONE_PROMPTS[tone]["icon"],
                "timestamp": datetime.now().isoformat(),
                "settings_applied": {
                    "address_form": effective_settings.get("address_form"),
                    "salutation": effective_settings.get("salutation"),
                    "closing": effective_settings.get("closing"),
                    "has_signature": effective_settings.get("signature_enabled", False),
                } if effective_settings else None,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"❌ Reply-Generierung mit User-Stil fehlgeschlagen: {e}")
            return {
                "success": False,
                "error": str(e),
                "reply_text": "",
                "tone_used": tone,
                "timestamp": datetime.now().isoformat()
            }

