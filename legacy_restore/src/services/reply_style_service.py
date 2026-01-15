"""
Reply Style Service
===================

Verwaltet benutzerdefinierte Antwort-Stil-Einstellungen.
Hybrid-Ansatz: Globale Defaults + Pro-Stil-Überschreibungen.

Feature: FEATURE_REPLY_STYLES
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from importlib import import_module

logger = logging.getLogger(__name__)

# Import models module
models = import_module("src.02_models")

# Standard-Defaults (wenn User nichts konfiguriert hat)
DEFAULT_STYLE_SETTINGS = {
    "global": {
        "address_form": "auto",  # Automatisch aus Email erkennen
        "salutation": None,      # KI entscheidet
        "closing": None,         # KI entscheidet
        "signature_enabled": False,
        "signature_text": None,
        "custom_instructions": None,
    },
    "formal": {
        "address_form": "sie",
        "salutation": "Sehr geehrte/r",
        "closing": "Mit freundlichen Grüssen",
    },
    "friendly": {
        "address_form": "auto",
        "salutation": "Hallo",
        "closing": "Viele Grüsse",
    },
    "brief": {
        "address_form": "auto",
        "salutation": None,  # Kurz = keine lange Anrede
        "closing": "Grüsse",
    },
    "decline": {
        "address_form": "sie",
        "salutation": "Sehr geehrte/r",
        "closing": "Mit freundlichen Grüssen",
    },
}


class ReplyStyleService:
    """Service für Antwort-Stil-Einstellungen"""
    
    @staticmethod
    def get_account_signature(db: Session, account_id: int, master_key: str) -> Optional[str]:
        """Holt Account-spezifische Signatur
        
        Args:
            db: Session
            account_id: Mail Account ID
            master_key: Master-Key aus Session zum Entschlüsseln
        
        Returns:
            Signatur-Text oder None
        """
        account = db.query(models.MailAccount).filter(
            models.MailAccount.id == account_id
        ).first()
        
        if not account or not account.signature_enabled or not account.encrypted_signature_text:
            return None
        
        try:
            from src import encryption as enc
            return enc.EncryptionManager.decrypt_data(
                account.encrypted_signature_text, master_key
            )
        except Exception as e:
            logger.error(f"Failed to decrypt account signature: {e}")
            return None
    
    @staticmethod
    def get_user_settings(db: Session, user_id: int, master_key: str = None) -> Dict[str, Any]:
        """Holt alle Style-Settings eines Users
        
        Args:
            db: Session
            user_id: User ID
            master_key: Master key zum Entschlüsseln von signature/instructions
        
        Returns:
            {
                "global": {...},
                "formal": {...},
                "friendly": {...},
                "brief": {...},
                "decline": {...}
            }
        """
        settings = db.query(models.ReplyStyleSettings).filter(
            models.ReplyStyleSettings.user_id == user_id
        ).all()
        
        result = {}
        
        for style_key in ["global", "formal", "friendly", "brief", "decline"]:
            # Default-Werte
            result[style_key] = DEFAULT_STYLE_SETTINGS.get(style_key, {}).copy()
            
            # User-Überschreibungen anwenden
            user_setting = next((s for s in settings if s.style_key == style_key), None)
            if user_setting:
                for field in ["address_form", "salutation", "closing", "signature_enabled"]:
                    value = getattr(user_setting, field, None)
                    if value is not None:
                        result[style_key][field] = value
                
                # Verschlüsselte Felder entschlüsseln falls master_key vorhanden
                if master_key:
                    if user_setting.encrypted_signature_text:
                        try:
                            from src import encryption as enc
                            result[style_key]["signature_text"] = enc.EncryptionManager.decrypt_data(
                                user_setting.encrypted_signature_text, master_key
                            )
                        except Exception as e:
                            logger.error(f"Failed to decrypt signature_text for style '{style_key}': {e}")
                            result[style_key]["signature_text"] = "[FEHLER: Entschlüsselung fehlgeschlagen]"
                    
                    if user_setting.encrypted_custom_instructions:
                        try:
                            from src import encryption as enc
                            result[style_key]["custom_instructions"] = enc.EncryptionManager.decrypt_data(
                                user_setting.encrypted_custom_instructions, master_key
                            )
                        except Exception as e:
                            logger.error(f"Failed to decrypt custom_instructions for style '{style_key}': {e}")
                            result[style_key]["custom_instructions"] = "[FEHLER: Entschlüsselung fehlgeschlagen]"
                else:
                    # Ohne master_key: Felder als verschlüsselt markieren
                    result[style_key]["signature_text"] = None
                    result[style_key]["custom_instructions"] = None
        
        return result
    
    @staticmethod
    def get_effective_settings(
        db: Session, 
        user_id: int, 
        style_key: str,
        master_key: str = None
    ) -> Dict[str, Any]:
        """Holt die effektiven Settings für einen spezifischen Stil
        
        Merged: System-Defaults → User-Global → User-Style-Specific
        
        Args:
            db: Session
            user_id: User ID
            style_key: "formal", "friendly", "brief", "decline"
            master_key: Optional - zum Entschlüsseln
            
        Returns:
            Vollständige Settings für diesen Stil (alle Felder gefüllt)
        """
        if style_key not in ["formal", "friendly", "brief", "decline"]:
            raise ValueError(f"Invalid style_key: {style_key}")
        
        # 1. System-Defaults für diesen Stil
        result = DEFAULT_STYLE_SETTINGS.get(style_key, {}).copy()
        
        # 2. Global-Defaults für diesen Stil (falls vorhanden)
        for key, value in DEFAULT_STYLE_SETTINGS.get("global", {}).items():
            if key not in result or result[key] is None:
                result[key] = value
        
        # 3. User Global-Settings überschreiben
        user_global = db.query(models.ReplyStyleSettings).filter(
            models.ReplyStyleSettings.user_id == user_id,
            models.ReplyStyleSettings.style_key == "global"
        ).first()
        
        if user_global:
            for field in ["address_form", "salutation", "closing", "signature_enabled"]:
                value = getattr(user_global, field, None)
                if value is not None:
                    result[field] = value
            
            # Verschlüsselte Felder
            if master_key:
                if user_global.encrypted_signature_text:
                    try:
                        from src import encryption as enc
                        result["signature_text"] = enc.EncryptionManager.decrypt_data(
                            user_global.encrypted_signature_text, master_key
                        )
                    except Exception as e:
                        logger.error(f"Failed to decrypt global signature_text: {e}")
                        result["signature_text"] = "[FEHLER: Entschlüsselung fehlgeschlagen]"
                
                if user_global.encrypted_custom_instructions:
                    try:
                        from src import encryption as enc
                        result["custom_instructions"] = enc.EncryptionManager.decrypt_data(
                            user_global.encrypted_custom_instructions, master_key
                        )
                    except Exception as e:
                        logger.error(f"Failed to decrypt global custom_instructions: {e}")
                        result["custom_instructions"] = "[FEHLER: Entschlüsselung fehlgeschlagen]"
        
        # 4. User Style-Specific überschreiben (höchste Priorität)
        user_style = db.query(models.ReplyStyleSettings).filter(
            models.ReplyStyleSettings.user_id == user_id,
            models.ReplyStyleSettings.style_key == style_key
        ).first()
        
        if user_style:
            for field in ["address_form", "salutation", "closing", "signature_enabled"]:
                value = getattr(user_style, field, None)
                if value is not None:
                    result[field] = value
            
            # Verschlüsselte Felder
            if master_key:
                if user_style.encrypted_signature_text:
                    try:
                        from src import encryption as enc
                        result["signature_text"] = enc.EncryptionManager.decrypt_data(
                            user_style.encrypted_signature_text, master_key
                        )
                    except Exception as e:
                        logger.error(f"Failed to decrypt style signature_text: {e}")
                        result["signature_text"] = "[FEHLER: Entschlüsselung fehlgeschlagen]"
                
                if user_style.encrypted_custom_instructions:
                    try:
                        from src import encryption as enc
                        result["custom_instructions"] = enc.EncryptionManager.decrypt_data(
                            user_style.encrypted_custom_instructions, master_key
                        )
                    except Exception as e:
                        logger.error(f"Failed to decrypt style custom_instructions: {e}")
                        result["custom_instructions"] = "[FEHLER: Entschlüsselung fehlgeschlagen]"
        
        logger.debug(f"Effective settings for user {user_id}, style '{style_key}': {result}")
        return result
    
    @staticmethod
    def save_settings(
        db: Session, 
        user_id: int, 
        style_key: str, 
        settings: Dict[str, Any],
        master_key: str = None
    ) -> models.ReplyStyleSettings:
        """Speichert Settings für einen Stil
        
        Args:
            db: Session
            user_id: User ID
            style_key: "global", "formal", "friendly", "brief", "decline"
            settings: Dict mit Feldern zum Speichern
            master_key: Optional - zum Verschlüsseln
            
        Returns:
            ReplyStyleSettings Objekt
        """
        if style_key not in ["global", "formal", "friendly", "brief", "decline"]:
            raise ValueError(f"Invalid style_key: {style_key}")
        
        # Existierendes Setting holen oder neu erstellen
        existing = db.query(models.ReplyStyleSettings).filter(
            models.ReplyStyleSettings.user_id == user_id,
            models.ReplyStyleSettings.style_key == style_key
        ).first()
        
        if existing:
            # Validierung: signature_enabled=True erfordert signature_text
            if settings.get("signature_enabled") and not settings.get("signature_text", "").strip():
                raise ValueError("signature_enabled is True but signature_text is empty")
            
            # Update
            for field in ["address_form", "salutation", "closing", "signature_enabled"]:
                if field in settings:
                    setattr(existing, field, settings[field])
            
            # Verschlüsselte Felder
            if master_key:
                if "signature_text" in settings:
                    if settings["signature_text"]:
                        from src import encryption as enc
                        existing.encrypted_signature_text = enc.EncryptionManager.encrypt_data(
                            settings["signature_text"], master_key
                        )
                    else:
                        existing.encrypted_signature_text = None
                
                if "custom_instructions" in settings:
                    if settings["custom_instructions"]:
                        from src import encryption as enc
                        existing.encrypted_custom_instructions = enc.EncryptionManager.encrypt_data(
                            settings["custom_instructions"], master_key
                        )
                    else:
                        existing.encrypted_custom_instructions = None
            
            db.commit()
            logger.info(f"✅ Updated reply style '{style_key}' for user {user_id}")
            return existing
        else:
            # Validierung: signature_enabled=True erfordert signature_text
            if settings.get("signature_enabled") and not settings.get("signature_text", "").strip():
                raise ValueError("signature_enabled is True but signature_text is empty")
            
            # Create
            encrypted_signature = None
            encrypted_instructions = None
            
            if master_key:
                if settings.get("signature_text"):
                    from src import encryption as enc
                    encrypted_signature = enc.EncryptionManager.encrypt_data(
                        settings["signature_text"], master_key
                    )
                if settings.get("custom_instructions"):
                    from src import encryption as enc
                    encrypted_instructions = enc.EncryptionManager.encrypt_data(
                        settings["custom_instructions"], master_key
                    )
            
            new_setting = models.ReplyStyleSettings(
                user_id=user_id,
                style_key=style_key,
                address_form=settings.get("address_form"),
                salutation=settings.get("salutation"),
                closing=settings.get("closing"),
                signature_enabled=settings.get("signature_enabled"),
                encrypted_signature_text=encrypted_signature,
                encrypted_custom_instructions=encrypted_instructions,
            )
            db.add(new_setting)
            db.commit()
            db.refresh(new_setting)
            logger.info(f"✅ Created reply style '{style_key}' for user {user_id}")
            return new_setting
    
    @staticmethod
    def delete_style_override(db: Session, user_id: int, style_key: str) -> bool:
        """Löscht Style-spezifische Überschreibung (setzt auf Global zurück)
        
        Note: "global" kann nicht gelöscht werden (nur aktualisiert)
        """
        if style_key == "global":
            logger.warning("Cannot delete global settings, only update them")
            return False
        
        setting = db.query(models.ReplyStyleSettings).filter(
            models.ReplyStyleSettings.user_id == user_id,
            models.ReplyStyleSettings.style_key == style_key
        ).first()
        
        if setting:
            db.delete(setting)
            db.commit()
            logger.info(f"🗑️ Deleted reply style override '{style_key}' for user {user_id}")
            return True
        
        return False
    
    @staticmethod
    def build_style_instructions(settings: Dict[str, Any], base_tone_instructions: str) -> str:
        """Baut die kompletten Stil-Anweisungen für die KI
        
        Kombiniert:
        - Base tone instructions (aus TONE_PROMPTS)
        - User-spezifische Einstellungen
        
        Args:
            settings: Effective settings für den Stil
            base_tone_instructions: Original-Instructions aus TONE_PROMPTS
            
        Returns:
            Kombinierte Anweisungen für die KI
        """
        parts = [base_tone_instructions]
        
        # Anrede-Form
        address_form = settings.get("address_form", "auto")
        if address_form == "du":
            parts.append("\n\nWICHTIG - ANREDE-FORM: Verwende konsequent 'Du' (nicht 'Sie')!")
        elif address_form == "sie":
            parts.append("\n\nWICHTIG - ANREDE-FORM: Verwende konsequent 'Sie' (nicht 'Du')!")
        # "auto" = KI entscheidet basierend auf Original-Email
        
        # Spezifische Anrede
        salutation = settings.get("salutation")
        if salutation:
            parts.append(f"\n\nANREDE: Beginne die Email mit '{salutation}' gefolgt vom Namen.")
        
        # Grussformel
        closing = settings.get("closing")
        if closing:
            parts.append(f"\n\nGRUSSFORMEL: Beende die Email mit '{closing}'.")
        
        # Signatur
        if settings.get("signature_enabled") and settings.get("signature_text"):
            signature = settings["signature_text"]
            parts.append(f"\n\nSIGNATUR: Füge nach der Grussformel diese Signatur hinzu:\n{signature}")
        
        # Custom Instructions
        custom = settings.get("custom_instructions")
        if custom:
            parts.append(f"\n\nZUSÄTZLICHE ANWEISUNGEN VOM BENUTZER:\n{custom}")
        
        return "\n".join(parts)
