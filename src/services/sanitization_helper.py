# src/services/sanitization_helper.py
"""
Zentraler Helper für Sanitization/Anonymisierung.

Konsolidiert die redundante Logik aus:
- email_processing_tasks.py (reprocess_email_base, optimize_email_processing)
- reply_generation_tasks.py (generate_reply_draft)

Business-Logik:
1. Prüfe ob gespeicherte anonymisierte Version vorhanden
2. Wenn ja: Verwende sie (Cache-Hit)
3. Wenn nein: Erstelle on-the-fly und speichere für zukünftige Verwendung
4. Lade EntityMap für De-Anonymisierung (wichtig für Reply-Draft)
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class SanitizationResult:
    """Ergebnis der get_or_create_sanitized_content Funktion."""
    subject: str
    body: str
    was_anonymized: bool
    entities_count: int
    entity_map: Optional[Dict[str, Any]]  # Für De-Anonymisierung (reverse Map)
    was_cached: bool  # True wenn aus DB geladen, False wenn neu erstellt


def get_or_create_sanitized_content(
    raw_email,
    master_key: str,
    db_session: "Session",
    level: int = 3,
    *,
    with_roles: bool = False,
    sender: Optional[str] = None,
    recipient: Optional[str] = None,
    original_subject: Optional[str] = None,
    original_body: Optional[str] = None,
    logger_prefix: str = "Sanitize"
) -> SanitizationResult:
    """
    Zentrale Funktion für Anonymisierung mit Cache-Support.
    
    Prüft ob bereits anonymisierte Version in DB vorhanden ist.
    Wenn nicht: Erstellt on-the-fly und speichert für zukünftige Verwendung.
    
    Args:
        raw_email: RawEmail Model-Objekt
        master_key: DEK für Ver-/Entschlüsselung
        db_session: SQLAlchemy Session für Commit
        level: Sanitization-Level (1=Regex, 2=spaCy-Light, 3=spaCy-Full)
        with_roles: Wenn True, nutze sanitize_with_roles (für Reply-Draft)
        sender: Absender-Email (nur mit with_roles=True)
        recipient: Empfänger-Name (nur mit with_roles=True)
        original_subject: Entschlüsselter Original-Betreff (optional, wird sonst aus raw_email geladen)
        original_body: Entschlüsselter Original-Body (optional, wird sonst aus raw_email geladen)
        logger_prefix: Prefix für Log-Meldungen (z.B. "Reprocess", "Optimize", "Reply")
    
    Returns:
        SanitizationResult mit subject, body, entity_map, etc.
    
    Business-Logik (aus reply_generation_tasks.py übernommen):
    - Prüft encrypted_subject_sanitized UND encrypted_body_sanitized
    - Lädt entity_map für De-Anonymisierung
    - Speichert alle Metadaten (level, time_ms, entities_count)
    """
    import importlib
    encryption = importlib.import_module(".08_encryption", "src")
    
    entity_map = None
    was_cached = False
    
    # =========================================================================
    # SCHRITT 1: Prüfe ob gespeicherte Version vorhanden
    # =========================================================================
    if raw_email.encrypted_subject_sanitized and raw_email.encrypted_body_sanitized:
        try:
            sanitized_subject = encryption.EmailDataManager.decrypt_email_subject(
                raw_email.encrypted_subject_sanitized, master_key
            )
            sanitized_body = encryption.EmailDataManager.decrypt_email_body(
                raw_email.encrypted_body_sanitized, master_key
            )
            entities_count = raw_email.sanitization_entities_count or 0
            was_cached = True
            
            # EntityMap für De-Anonymisierung laden (wichtig für Reply-Draft!)
            if raw_email.encrypted_entity_map:
                try:
                    entity_map_json = encryption.EncryptionManager.decrypt_data(
                        raw_email.encrypted_entity_map, master_key
                    )
                    entity_map = json.loads(entity_map_json)
                    logger.debug(f"✅ Entity-Map geladen: {len(entity_map.get('reverse', {}))} Mappings")
                except Exception as em_err:
                    logger.warning(f"⚠️ Entity-Map Entschlüsselung fehlgeschlagen: {em_err}")
            
            logger.info(f"🛡️ {logger_prefix}: Verwende gespeicherte Anonymisierung (Entities={entities_count})")
            
            return SanitizationResult(
                subject=sanitized_subject,
                body=sanitized_body,
                was_anonymized=True,
                entities_count=entities_count,
                entity_map=entity_map,
                was_cached=True
            )
            
        except Exception as decrypt_err:
            logger.warning(f"⚠️ Gespeicherte Anonymisierung nicht lesbar: {decrypt_err}")
            # Markiere für Neu-Erstellung
            raw_email.encrypted_body_sanitized = None
            raw_email.encrypted_subject_sanitized = None
    
    # =========================================================================
    # SCHRITT 2: On-the-fly Anonymisierung
    # =========================================================================
    
    # Original-Content laden falls nicht übergeben
    if original_subject is None:
        original_subject = encryption.EmailDataManager.decrypt_email_subject(
            raw_email.encrypted_subject or "", master_key
        )
    if original_body is None:
        original_body = encryption.EmailDataManager.decrypt_email_body(
            raw_email.encrypted_body or "", master_key
        )
    
    try:
        from src.services.content_sanitizer import ContentSanitizer, get_sanitizer
        
        if with_roles and sender and recipient:
            # Reply-Draft Mode: Mit Rollen-Ersetzung (sender → [ABSENDER], etc.)
            sanitizer = ContentSanitizer()
            result = sanitizer.sanitize_with_roles(
                subject=original_subject,
                body=original_body,
                sender=sender,
                recipient=recipient,
                level=level
            )
        else:
            # Standard Mode: Normale Anonymisierung
            sanitizer = get_sanitizer()
            result = sanitizer.sanitize(
                subject=original_subject,
                body=original_body,
                level=level
            )
        
        sanitized_subject = result.subject
        sanitized_body = result.body
        entities_count = result.entities_found if hasattr(result, 'entities_found') else 0
        
        # EntityMap extrahieren
        if result.entity_map:
            if hasattr(result.entity_map, 'to_dict'):
                entity_map = result.entity_map.to_dict()
                entities_count = len(result.entity_map.forward) if hasattr(result.entity_map, 'forward') else entities_count
            else:
                entity_map = result.entity_map
        
        # =====================================================================
        # SCHRITT 3: In DB speichern für zukünftige Verwendung
        # =====================================================================
        try:
            raw_email.encrypted_subject_sanitized = encryption.EmailDataManager.encrypt_email_subject(
                sanitized_subject, master_key
            )
            raw_email.encrypted_body_sanitized = encryption.EmailDataManager.encrypt_email_body(
                sanitized_body, master_key
            )
            raw_email.sanitization_level = level
            raw_email.sanitization_entities_count = entities_count
            
            # Zeit speichern wenn vorhanden
            if hasattr(result, 'processing_time_ms') and result.processing_time_ms:
                raw_email.sanitization_time_ms = result.processing_time_ms
            
            # EntityMap für De-Anonymisierung speichern
            if entity_map:
                raw_email.encrypted_entity_map = encryption.EncryptionManager.encrypt_data(
                    json.dumps(entity_map), master_key
                )
            
            db_session.commit()
            logger.info(f"🛡️ {logger_prefix}: Anonymisiert & gespeichert mit Level {level} (Entities={entities_count})")
            
        except Exception as save_err:
            logger.error(f"❌ Anonymisierung speichern fehlgeschlagen: {save_err}")
            db_session.rollback()
        
        return SanitizationResult(
            subject=sanitized_subject,
            body=sanitized_body,
            was_anonymized=True,
            entities_count=entities_count,
            entity_map=entity_map,
            was_cached=False
        )
        
    except Exception as anon_err:
        logger.error(f"❌ {logger_prefix}: On-the-fly Anonymisierung fehlgeschlagen: {anon_err}")
        db_session.rollback()
        
        # Fallback: Original-Content ohne Anonymisierung
        return SanitizationResult(
            subject=original_subject,
            body=original_body,
            was_anonymized=False,
            entities_count=0,
            entity_map=None,
            was_cached=False
        )
