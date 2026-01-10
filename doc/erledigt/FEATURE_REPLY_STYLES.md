# Feature: Benutzerdefinierte Antwort-Stile

> **Version:** 1.0  
> **Status:** Konzept bereit für Implementierung  
> **Geschätzter Aufwand:** 6-8 Stunden  
> **Route:** `/reply-styles` (Top-Level)

---

## 🎯 Übersicht

Erweiterung des Reply-Generators um benutzerdefinierte Stil-Einstellungen:
- **Globale Einstellungen** (wirken auf alle 4 Stile)
- **Pro-Stil-Überschreibungen** (optional, für Feintuning)

### Beispiel

```
GLOBAL:
- Anrede-Form: "Du"
- Standard-Anrede: "Liebe/r"
- Standard-Gruss: "Beste Grüsse"
- Signatur: "Mike"

STIL "Formell" (überschreibt Global):
- Anrede-Form: "Sie"  ← Überschreibung!
- Anrede: "Sehr geehrte/r"
- Gruss: "Mit freundlichen Grüssen"

RESULTAT für "Formell":
→ "Sehr geehrte/r Frau Müller, ... Mit freundlichen Grüssen, Mike"

RESULTAT für "Freundlich" (nutzt Global):
→ "Liebe/r Max, ... Beste Grüsse, Mike"
```

---

## 🗄️ Datenbank-Schema

### Neue Tabelle: `reply_style_settings`

```python
# src/02_models.py - NEUE KLASSE

class ReplyStyleSettings(Base):
    """Benutzerdefinierte Einstellungen für Antwort-Stile
    
    Hybrid-Ansatz:
    - style_key = "global" → Wirkt auf alle Stile
    - style_key = "formal|friendly|brief|decline" → Überschreibt Global für diesen Stil
    """
    
    __tablename__ = "reply_style_settings"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Welcher Stil? "global" oder "formal", "friendly", "brief", "decline"
    style_key = Column(String(20), nullable=False, default="global")
    
    # Anrede-Einstellungen
    address_form = Column(String(10), nullable=True)  # "du", "sie", "auto"
    salutation = Column(String(100), nullable=True)   # z.B. "Liebe/r", "Sehr geehrte/r", "Hallo"
    
    # Gruss-Einstellungen
    closing = Column(String(100), nullable=True)      # z.B. "Beste Grüsse", "Mit freundlichen Grüssen"
    
    # Signatur
    signature_enabled = Column(Boolean, default=False)
    signature_text = Column(String(200), nullable=True)  # z.B. "Mike" oder "Mike Müller\nFirma GmbH"
    
    # Zusätzliche Anweisungen (Freitext für KI)
    custom_instructions = Column(Text, nullable=True)
    # z.B. "In unserer Firma ist es üblich, dass..."
    
    # Für Stil-spezifisch: Welche Felder überschreiben?
    # NULL = Global nutzen, Wert = Überschreiben
    # (implizit durch NULL-Werte in den Feldern oben)
    
    # Metadaten
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    # Relationships
    user = relationship("User", backref="reply_style_settings")
    
    # Constraints: Ein Setting pro User pro Style
    __table_args__ = (
        UniqueConstraint("user_id", "style_key", name="uq_user_style_key"),
        Index("ix_reply_style_user_id", "user_id"),
    )
```

### Datenbeispiele

```sql
-- User 1: Globale Einstellungen
INSERT INTO reply_style_settings (user_id, style_key, address_form, salutation, closing, signature_enabled, signature_text, custom_instructions)
VALUES (1, 'global', 'du', 'Liebe/r', 'Beste Grüsse', true, 'Mike', 'In unserer Firma duzen wir uns.');

-- User 1: Formell überschreibt teilweise
INSERT INTO reply_style_settings (user_id, style_key, address_form, salutation, closing, signature_enabled, signature_text, custom_instructions)
VALUES (1, 'formal', 'sie', 'Sehr geehrte/r', 'Mit freundlichen Grüssen', NULL, NULL, NULL);
-- signature_enabled=NULL bedeutet: Von Global übernehmen!

-- User 1: Kurz hat eigene Anweisungen
INSERT INTO reply_style_settings (user_id, style_key, address_form, salutation, closing, signature_enabled, signature_text, custom_instructions)
VALUES (1, 'brief', NULL, NULL, 'VG', false, NULL, 'Maximal 2 Sätze, keine Floskeln.');
```

---

## 📋 Migration

```python
# migrations/versions/xxx_add_reply_style_settings.py

"""Add reply style settings table

Revision ID: xxx
"""

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'reply_style_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('style_key', sa.String(20), nullable=False, server_default='global'),
        sa.Column('address_form', sa.String(10), nullable=True),
        sa.Column('salutation', sa.String(100), nullable=True),
        sa.Column('closing', sa.String(100), nullable=True),
        sa.Column('signature_enabled', sa.Boolean(), nullable=True),
        sa.Column('signature_text', sa.String(200), nullable=True),
        sa.Column('custom_instructions', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'style_key', name='uq_user_style_key')
    )
    op.create_index('ix_reply_style_user_id', 'reply_style_settings', ['user_id'])


def downgrade():
    op.drop_index('ix_reply_style_user_id')
    op.drop_table('reply_style_settings')
```

---

## 🔧 Service: ReplyStyleService

### Neue Datei: `src/services/reply_style_service.py`

```python
"""
Reply Style Service
===================

Verwaltet benutzerdefinierte Antwort-Stil-Einstellungen.
Hybrid-Ansatz: Globale Defaults + Pro-Stil-Überschreibungen.
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from src import models

logger = logging.getLogger(__name__)

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
    def get_user_settings(db: Session, user_id: int) -> Dict[str, Any]:
        """Holt alle Style-Settings eines Users
        
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
                for field in ["address_form", "salutation", "closing", 
                              "signature_enabled", "signature_text", "custom_instructions"]:
                    value = getattr(user_setting, field, None)
                    if value is not None:
                        result[style_key][field] = value
        
        return result
    
    @staticmethod
    def get_effective_settings(db: Session, user_id: int, style_key: str) -> Dict[str, Any]:
        """Holt die effektiven Settings für einen spezifischen Stil
        
        Merged: System-Defaults → User-Global → User-Style-Specific
        
        Args:
            db: Session
            user_id: User ID
            style_key: "formal", "friendly", "brief", "decline"
            
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
            for field in ["address_form", "salutation", "closing", 
                          "signature_enabled", "signature_text", "custom_instructions"]:
                value = getattr(user_global, field, None)
                if value is not None:
                    result[field] = value
        
        # 4. User Style-Specific überschreiben (höchste Priorität)
        user_style = db.query(models.ReplyStyleSettings).filter(
            models.ReplyStyleSettings.user_id == user_id,
            models.ReplyStyleSettings.style_key == style_key
        ).first()
        
        if user_style:
            for field in ["address_form", "salutation", "closing", 
                          "signature_enabled", "signature_text", "custom_instructions"]:
                value = getattr(user_style, field, None)
                if value is not None:
                    result[field] = value
        
        logger.debug(f"Effective settings for user {user_id}, style '{style_key}': {result}")
        return result
    
    @staticmethod
    def save_settings(
        db: Session, 
        user_id: int, 
        style_key: str, 
        settings: Dict[str, Any]
    ) -> models.ReplyStyleSettings:
        """Speichert Settings für einen Stil
        
        Args:
            db: Session
            user_id: User ID
            style_key: "global", "formal", "friendly", "brief", "decline"
            settings: Dict mit Feldern zum Speichern
            
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
            # Update
            for field in ["address_form", "salutation", "closing", 
                          "signature_enabled", "signature_text", "custom_instructions"]:
                if field in settings:
                    setattr(existing, field, settings[field])
            db.commit()
            logger.info(f"✅ Updated reply style '{style_key}' for user {user_id}")
            return existing
        else:
            # Create
            new_setting = models.ReplyStyleSettings(
                user_id=user_id,
                style_key=style_key,
                address_form=settings.get("address_form"),
                salutation=settings.get("salutation"),
                closing=settings.get("closing"),
                signature_enabled=settings.get("signature_enabled"),
                signature_text=settings.get("signature_text"),
                custom_instructions=settings.get("custom_instructions"),
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
```

---

## 🔄 Integration in ReplyGenerator

### Änderungen in `src/reply_generator.py`

```python
# Am Anfang der Datei, nach Imports:
from src.services.reply_style_service import ReplyStyleService

# In der Klasse ReplyGenerator, neue Methode:

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
    attachment_names: Optional[list] = None
) -> Dict[str, Any]:
    """
    Generiert Antwort-Entwurf MIT User-spezifischen Stil-Einstellungen.
    
    Unterschied zu generate_reply():
    - Lädt User-Einstellungen aus DB
    - Merged mit Base-Tone-Instructions
    - Wendet Anrede, Gruss, Signatur, Custom Instructions an
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
    effective_settings = ReplyStyleService.get_effective_settings(db, user_id, tone)
    
    # 🆕 Kombinierte Instructions bauen
    base_instructions = TONE_PROMPTS[tone]["instructions"]
    enhanced_instructions = ReplyStyleService.build_style_instructions(
        effective_settings, 
        base_instructions
    )
    
    # User-Prompt bauen (wie bisher, aber mit enhanced_instructions)
    user_prompt = self._build_user_prompt(
        original_subject=original_subject,
        original_body=original_body,
        original_sender=original_sender,
        tone_instructions=enhanced_instructions,  # 🆕 Enhanced!
        thread_context=thread_context,
        language=language,
        has_attachments=has_attachments,
        attachment_names=attachment_names,
    )
    
    # KI-Aufruf (wie bisher)
    try:
        reply_text = self.ai_client.chat(
            system_prompt=REPLY_GENERATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=1000
        )
        
        # Cleanup
        reply_text = self._cleanup_reply_text(reply_text)
        
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
            },
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
```

---

## 🌐 API-Endpoints

### `src/01_web_app.py` - Neue Endpoints

```python
# ===== Reply Styles Settings API =====

@app.route("/api/reply-styles", methods=["GET"])
@login_required
def api_get_reply_styles():
    """Holt alle Reply-Style-Settings des Users
    
    Returns:
        {
            "global": {
                "address_form": "du",
                "salutation": "Liebe/r",
                "closing": "Beste Grüsse",
                "signature_enabled": true,
                "signature_text": "Mike",
                "custom_instructions": "In unserer Firma..."
            },
            "formal": {...},
            "friendly": {...},
            "brief": {...},
            "decline": {...}
        }
    """
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        from src.services.reply_style_service import ReplyStyleService
        settings = ReplyStyleService.get_user_settings(db, user.id)
        
        return jsonify(settings)
    finally:
        db.close()


@app.route("/api/reply-styles/<style_key>", methods=["GET"])
@login_required
def api_get_reply_style(style_key: str):
    """Holt effektive Settings für einen spezifischen Stil
    
    Merged: Defaults → Global → Style-Specific
    """
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        from src.services.reply_style_service import ReplyStyleService
        try:
            settings = ReplyStyleService.get_effective_settings(db, user.id, style_key)
            return jsonify({"style_key": style_key, "settings": settings})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    finally:
        db.close()


@app.route("/api/reply-styles/<style_key>", methods=["PUT"])
@login_required
def api_save_reply_style(style_key: str):
    """Speichert Settings für einen Stil
    
    Body:
        {
            "address_form": "du",
            "salutation": "Liebe/r",
            "closing": "Beste Grüsse",
            "signature_enabled": true,
            "signature_text": "Mike",
            "custom_instructions": "..."
        }
    
    Note: NULL-Werte werden übernommen (= "Von Global erben")
    """
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        data = request.get_json() or {}
        
        from src.services.reply_style_service import ReplyStyleService
        try:
            setting = ReplyStyleService.save_settings(db, user.id, style_key, data)
            return jsonify({
                "success": True,
                "style_key": style_key,
                "message": f"Einstellungen für '{style_key}' gespeichert"
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    finally:
        db.close()


@app.route("/api/reply-styles/<style_key>", methods=["DELETE"])
@login_required
def api_delete_reply_style_override(style_key: str):
    """Löscht Style-spezifische Überschreibung (setzt auf Global zurück)
    
    Note: "global" kann nicht gelöscht werden
    """
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        from src.services.reply_style_service import ReplyStyleService
        success = ReplyStyleService.delete_style_override(db, user.id, style_key)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Überschreibung für '{style_key}' gelöscht, nutze jetzt Global"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Konnte nicht löschen (evtl. 'global' oder nicht vorhanden)"
            }), 400
    finally:
        db.close()


@app.route("/api/reply-styles/preview", methods=["POST"])
@login_required
def api_preview_reply_style():
    """Generiert eine Vorschau mit den aktuellen Settings
    
    Body:
        {
            "style_key": "formal",
            "sample_sender": "Max Mustermann <max@example.com>"  // optional
        }
    
    Returns:
        {
            "preview_text": "Sehr geehrter Herr Mustermann,\n\n[Ihr Text hier]\n\nMit freundlichen Grüssen\nMike"
        }
    """
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        data = request.get_json() or {}
        style_key = data.get("style_key", "formal")
        sample_sender = data.get("sample_sender", "Max Mustermann <max@example.com>")
        
        from src.services.reply_style_service import ReplyStyleService
        
        try:
            settings = ReplyStyleService.get_effective_settings(db, user.id, style_key)
        except ValueError:
            return jsonify({"error": "Invalid style_key"}), 400
        
        # Einfache Vorschau bauen (ohne KI)
        preview_parts = []
        
        # Anrede
        salutation = settings.get("salutation", "Hallo")
        # Extrahiere Name aus Sender
        name = sample_sender.split("<")[0].strip() if "<" in sample_sender else sample_sender
        if name:
            preview_parts.append(f"{salutation} {name},")
        else:
            preview_parts.append(f"{salutation},")
        
        preview_parts.append("")
        preview_parts.append("[Ihr Antwort-Text wird hier erscheinen...]")
        preview_parts.append("")
        
        # Gruss
        closing = settings.get("closing", "Grüsse")
        preview_parts.append(closing)
        
        # Signatur
        if settings.get("signature_enabled") and settings.get("signature_text"):
            preview_parts.append(settings["signature_text"])
        
        return jsonify({
            "preview_text": "\n".join(preview_parts),
            "settings_used": settings
        })
        
    finally:
        db.close()
```

### Änderung in bestehendem Endpoint

```python
# In api_generate_reply() - Zeile ändern:

# VORHER:
result = reply_gen.generate_reply(...)

# NACHHER:
result = reply_gen.generate_reply_with_user_style(
    db=db,
    user_id=user.id,
    original_subject=subject,
    original_body=body,
    original_sender=sender,
    tone=tone,
    thread_context=thread_context,
    language="de",
    has_attachments=has_attachments,
    attachment_names=attachment_names
)
```

---

## 🖼️ UI: Neue Seite `/reply-styles`

### Route in `src/01_web_app.py`

```python
@app.route("/reply-styles")
@login_required
def reply_styles_page():
    """Seite für Antwort-Stil-Einstellungen"""
    return render_template("reply_styles.html")
```

### Template: `templates/reply_styles.html`

```html
{% extends "base.html" %}

{% block title %}Antwort-Stile - KI-Mail-Helper{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-6 max-w-4xl">
    
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
        <div>
            <h1 class="text-2xl font-bold text-gray-900">✍️ Antwort-Stile</h1>
            <p class="text-gray-600 mt-1">Passe an, wie deine Antwort-Entwürfe generiert werden</p>
        </div>
        <a href="{{ url_for('settings_page') }}" class="btn btn-ghost">
            <i class="fas fa-arrow-left mr-2"></i> Zurück
        </a>
    </div>
    
    <!-- Globale Einstellungen -->
    <div class="card bg-blue-50 border-blue-200 mb-6">
        <div class="card-body">
            <h2 class="card-title text-blue-800">
                🌍 Globale Einstellungen
                <span class="badge badge-info">Wirken auf alle Stile</span>
            </h2>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                <!-- Anrede-Form -->
                <div class="form-control">
                    <label class="label">
                        <span class="label-text font-medium">Anrede-Form</span>
                    </label>
                    <select id="global-address-form" class="select select-bordered w-full" 
                            onchange="updateGlobal()">
                        <option value="auto">🔄 Automatisch (aus Email erkennen)</option>
                        <option value="du">👋 Du (informell)</option>
                        <option value="sie">🎩 Sie (formell)</option>
                    </select>
                </div>
                
                <!-- Standard-Anrede -->
                <div class="form-control">
                    <label class="label">
                        <span class="label-text font-medium">Standard-Anrede</span>
                    </label>
                    <input type="text" id="global-salutation" 
                           class="input input-bordered w-full"
                           placeholder="z.B. Liebe/r, Hallo, Guten Tag"
                           onchange="updateGlobal()">
                </div>
                
                <!-- Grussformel -->
                <div class="form-control">
                    <label class="label">
                        <span class="label-text font-medium">Grussformel</span>
                    </label>
                    <input type="text" id="global-closing" 
                           class="input input-bordered w-full"
                           placeholder="z.B. Beste Grüsse, Viele Grüsse"
                           onchange="updateGlobal()">
                </div>
                
                <!-- Signatur -->
                <div class="form-control">
                    <label class="label cursor-pointer justify-start gap-2">
                        <input type="checkbox" id="global-signature-enabled" 
                               class="checkbox checkbox-primary"
                               onchange="updateGlobal()">
                        <span class="label-text font-medium">Signatur anhängen</span>
                    </label>
                    <input type="text" id="global-signature-text" 
                           class="input input-bordered w-full mt-2"
                           placeholder="z.B. Mike, oder: Mike Müller | Firma GmbH"
                           onchange="updateGlobal()">
                </div>
            </div>
            
            <!-- Zusätzliche Anweisungen -->
            <div class="form-control mt-4">
                <label class="label">
                    <span class="label-text font-medium">Zusätzliche Anweisungen für die KI</span>
                </label>
                <textarea id="global-custom-instructions" 
                          class="textarea textarea-bordered w-full h-24"
                          placeholder="z.B. In unserer Firma ist es üblich, dass wir uns duzen. Wir verwenden nie Emojis in geschäftlichen Mails."
                          onchange="updateGlobal()"></textarea>
            </div>
        </div>
    </div>
    
    <!-- Stil-Tabs -->
    <div class="card">
        <div class="card-body">
            <h2 class="card-title mb-4">
                🎨 Stil-spezifische Einstellungen
                <span class="badge">Optional - überschreibt Global</span>
            </h2>
            
            <!-- Tab-Buttons -->
            <div class="tabs tabs-boxed mb-4">
                <a class="tab tab-active" data-style="formal" onclick="switchTab('formal')">
                    📜 Formell
                </a>
                <a class="tab" data-style="friendly" onclick="switchTab('friendly')">
                    😊 Freundlich
                </a>
                <a class="tab" data-style="brief" onclick="switchTab('brief')">
                    ⚡ Kurz
                </a>
                <a class="tab" data-style="decline" onclick="switchTab('decline')">
                    ❌ Ablehnung
                </a>
            </div>
            
            <!-- Tab-Content (wird per JS gefüllt) -->
            <div id="style-tab-content">
                <!-- Dynamisch generiert -->
            </div>
            
            <!-- Vorschau -->
            <div class="divider">Vorschau</div>
            
            <div class="bg-gray-50 rounded-lg p-4">
                <div class="flex items-center justify-between mb-2">
                    <span class="font-medium text-gray-700">👁️ So sieht eine Antwort aus:</span>
                    <button class="btn btn-sm btn-ghost" onclick="refreshPreview()">
                        <i class="fas fa-sync-alt mr-1"></i> Aktualisieren
                    </button>
                </div>
                <pre id="preview-text" class="whitespace-pre-wrap text-sm bg-white p-4 rounded border">
Lade Vorschau...
                </pre>
            </div>
        </div>
    </div>
    
    <!-- Action Buttons -->
    <div class="flex justify-end gap-4 mt-6">
        <button class="btn btn-ghost" onclick="resetToDefaults()">
            <i class="fas fa-undo mr-2"></i> Auf Standard zurücksetzen
        </button>
        <button class="btn btn-primary" onclick="saveAllSettings()">
            <i class="fas fa-save mr-2"></i> Alle Änderungen speichern
        </button>
    </div>
    
</div>

<script>
// State
let currentStyle = 'formal';
let settings = {};
let unsavedChanges = false;

// Load on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadSettings();
    switchTab('formal');
});

async function loadSettings() {
    try {
        const response = await fetch('/api/reply-styles');
        settings = await response.json();
        populateGlobalForm();
    } catch (error) {
        console.error('Error loading settings:', error);
        showToast('Fehler beim Laden der Einstellungen', 'error');
    }
}

function populateGlobalForm() {
    const global = settings.global || {};
    document.getElementById('global-address-form').value = global.address_form || 'auto';
    document.getElementById('global-salutation').value = global.salutation || '';
    document.getElementById('global-closing').value = global.closing || '';
    document.getElementById('global-signature-enabled').checked = global.signature_enabled || false;
    document.getElementById('global-signature-text').value = global.signature_text || '';
    document.getElementById('global-custom-instructions').value = global.custom_instructions || '';
}

function switchTab(styleKey) {
    currentStyle = styleKey;
    
    // Update tab styling
    document.querySelectorAll('.tabs .tab').forEach(tab => {
        tab.classList.remove('tab-active');
        if (tab.dataset.style === styleKey) {
            tab.classList.add('tab-active');
        }
    });
    
    // Render tab content
    renderStyleTab(styleKey);
    refreshPreview();
}

function renderStyleTab(styleKey) {
    const style = settings[styleKey] || {};
    const global = settings.global || {};
    
    const html = `
        <div class="alert alert-info mb-4">
            <i class="fas fa-info-circle"></i>
            <span>Leere Felder übernehmen die globalen Einstellungen</span>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="form-control">
                <label class="label">
                    <span class="label-text">Anrede-Form</span>
                    <span class="label-text-alt text-gray-400">Global: ${global.address_form || 'auto'}</span>
                </label>
                <select id="style-address-form" class="select select-bordered w-full"
                        onchange="markUnsaved()">
                    <option value="">— Von Global übernehmen —</option>
                    <option value="auto" ${style.address_form === 'auto' ? 'selected' : ''}>🔄 Automatisch</option>
                    <option value="du" ${style.address_form === 'du' ? 'selected' : ''}>👋 Du</option>
                    <option value="sie" ${style.address_form === 'sie' ? 'selected' : ''}>🎩 Sie</option>
                </select>
            </div>
            
            <div class="form-control">
                <label class="label">
                    <span class="label-text">Anrede</span>
                    <span class="label-text-alt text-gray-400">Global: ${global.salutation || '(KI entscheidet)'}</span>
                </label>
                <input type="text" id="style-salutation" 
                       class="input input-bordered w-full"
                       placeholder="Von Global übernehmen"
                       value="${style.salutation || ''}"
                       onchange="markUnsaved()">
            </div>
            
            <div class="form-control">
                <label class="label">
                    <span class="label-text">Grussformel</span>
                    <span class="label-text-alt text-gray-400">Global: ${global.closing || '(KI entscheidet)'}</span>
                </label>
                <input type="text" id="style-closing" 
                       class="input input-bordered w-full"
                       placeholder="Von Global übernehmen"
                       value="${style.closing || ''}"
                       onchange="markUnsaved()">
            </div>
            
            <div class="form-control">
                <label class="label">
                    <span class="label-text">Zusätzliche Anweisungen für diesen Stil</span>
                </label>
                <textarea id="style-custom-instructions" 
                          class="textarea textarea-bordered w-full h-20"
                          placeholder="z.B. Bei Ablehnungen immer eine Alternative anbieten"
                          onchange="markUnsaved()">${style.custom_instructions || ''}</textarea>
            </div>
        </div>
        
        <div class="flex justify-end mt-4">
            <button class="btn btn-sm btn-ghost text-red-500" onclick="resetStyleToGlobal('${styleKey}')">
                <i class="fas fa-trash mr-1"></i> Überschreibungen löschen
            </button>
        </div>
    `;
    
    document.getElementById('style-tab-content').innerHTML = html;
}

async function refreshPreview() {
    try {
        const response = await fetch('/api/reply-styles/preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                style_key: currentStyle,
                sample_sender: 'Max Mustermann <max@example.com>'
            })
        });
        
        const data = await response.json();
        document.getElementById('preview-text').textContent = data.preview_text;
    } catch (error) {
        console.error('Preview error:', error);
    }
}

function markUnsaved() {
    unsavedChanges = true;
}

function updateGlobal() {
    markUnsaved();
    // Speichere in lokalem State
    settings.global = {
        address_form: document.getElementById('global-address-form').value,
        salutation: document.getElementById('global-salutation').value || null,
        closing: document.getElementById('global-closing').value || null,
        signature_enabled: document.getElementById('global-signature-enabled').checked,
        signature_text: document.getElementById('global-signature-text').value || null,
        custom_instructions: document.getElementById('global-custom-instructions').value || null,
    };
    refreshPreview();
}

async function saveAllSettings() {
    try {
        // Global speichern
        await fetch('/api/reply-styles/global', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(settings.global)
        });
        
        // Aktuellen Stil speichern (falls geändert)
        const styleData = {
            address_form: document.getElementById('style-address-form')?.value || null,
            salutation: document.getElementById('style-salutation')?.value || null,
            closing: document.getElementById('style-closing')?.value || null,
            custom_instructions: document.getElementById('style-custom-instructions')?.value || null,
        };
        
        // Nur speichern wenn mindestens ein Wert gesetzt
        if (Object.values(styleData).some(v => v)) {
            await fetch(`/api/reply-styles/${currentStyle}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify(styleData)
            });
        }
        
        unsavedChanges = false;
        showToast('Einstellungen gespeichert!', 'success');
        
    } catch (error) {
        console.error('Save error:', error);
        showToast('Fehler beim Speichern', 'error');
    }
}

async function resetStyleToGlobal(styleKey) {
    if (!confirm(`Alle Überschreibungen für "${styleKey}" löschen und auf Global zurücksetzen?`)) {
        return;
    }
    
    try {
        await fetch(`/api/reply-styles/${styleKey}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': getCsrfToken() }
        });
        
        delete settings[styleKey];
        renderStyleTab(styleKey);
        refreshPreview();
        showToast('Auf Global zurückgesetzt', 'success');
    } catch (error) {
        console.error('Reset error:', error);
    }
}

async function resetToDefaults() {
    if (!confirm('Alle Einstellungen auf Standard zurücksetzen?')) {
        return;
    }
    
    try {
        // Alle Stile löschen
        for (const style of ['formal', 'friendly', 'brief', 'decline']) {
            await fetch(`/api/reply-styles/${style}`, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': getCsrfToken() }
            });
        }
        
        // Global auf leer setzen (Defaults greifen)
        await fetch('/api/reply-styles/global', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                address_form: 'auto',
                salutation: null,
                closing: null,
                signature_enabled: false,
                signature_text: null,
                custom_instructions: null
            })
        });
        
        await loadSettings();
        switchTab(currentStyle);
        showToast('Auf Standard zurückgesetzt', 'success');
    } catch (error) {
        console.error('Reset error:', error);
    }
}

// Warn before leaving with unsaved changes
window.addEventListener('beforeunload', (e) => {
    if (unsavedChanges) {
        e.preventDefault();
        e.returnValue = '';
    }
});
</script>
{% endblock %}
```

---

## 🔗 Navigation: Link zu Reply-Styles

### In `templates/base.html` (Hauptmenü)

```html
<!-- Nach Tags, vor Tag-Vorschläge -->
<li>
    <a href="{{ url_for('reply_styles_page') }}" 
       class="{{ 'active' if request.endpoint == 'reply_styles_page' else '' }}">
        <i class="fas fa-pen-fancy mr-2"></i>
        Antwort-Stile
    </a>
</li>
```

### Im Reply-Modal (Link zu Einstellungen)

```html
<!-- In email_detail.html, im Reply-Modal, unter den Ton-Buttons -->
<div class="text-right mt-2">
    <a href="{{ url_for('reply_styles_page') }}" class="text-sm text-blue-600 hover:underline">
        <i class="fas fa-cog mr-1"></i> Stile anpassen
    </a>
</div>
```

---

## 📋 Implementierungs-Checkliste

### Phase 1: Datenbank (30 Min)
- [ ] `02_models.py`: `ReplyStyleSettings` Klasse hinzufügen
- [ ] Migration erstellen: `alembic revision --autogenerate -m "Add reply style settings"`
- [ ] Migration ausführen: `alembic upgrade head`

### Phase 2: Service (1.5h)
- [ ] Neue Datei: `src/services/reply_style_service.py`
- [ ] `get_user_settings()` implementieren
- [ ] `get_effective_settings()` implementieren
- [ ] `save_settings()` implementieren
- [ ] `delete_style_override()` implementieren
- [ ] `build_style_instructions()` implementieren

### Phase 3: ReplyGenerator Integration (1h)
- [ ] `reply_generator.py`: Import hinzufügen
- [ ] `generate_reply_with_user_style()` Methode hinzufügen
- [ ] Bestehenden API-Endpoint aktualisieren

### Phase 4: API-Endpoints (1h)
- [ ] `GET /api/reply-styles`
- [ ] `GET /api/reply-styles/<style_key>`
- [ ] `PUT /api/reply-styles/<style_key>`
- [ ] `DELETE /api/reply-styles/<style_key>`
- [ ] `POST /api/reply-styles/preview`

### Phase 5: UI (2h)
- [ ] Route `/reply-styles` hinzufügen
- [ ] Template `reply_styles.html` erstellen
- [ ] JavaScript für Tab-Switching, Save, Preview
- [ ] Navigation-Link in `base.html`
- [ ] Link im Reply-Modal

### Phase 6: Testing (1h)
- [ ] Globale Settings testen
- [ ] Pro-Stil-Überschreibungen testen
- [ ] Merge-Logik testen (Global → Style)
- [ ] Vorschau-Funktion testen
- [ ] Reply-Generierung mit Settings testen

**Gesamt: ~7-8 Stunden**

---

## 🎯 Beispiel-Konfigurationen

### Beispiel 1: Lockere Startup-Kultur

```json
{
    "global": {
        "address_form": "du",
        "salutation": "Hey",
        "closing": "Cheers",
        "signature_enabled": true,
        "signature_text": "Mike 🚀",
        "custom_instructions": "Wir sind ein lockeres Startup, Emojis sind willkommen!"
    },
    "formal": {
        "address_form": "sie",
        "salutation": "Guten Tag",
        "closing": "Mit besten Grüssen"
    }
}
```

### Beispiel 2: Traditionelles Unternehmen

```json
{
    "global": {
        "address_form": "sie",
        "salutation": "Sehr geehrte/r",
        "closing": "Mit freundlichen Grüssen",
        "signature_enabled": true,
        "signature_text": "Michael Müller\nAbteilungsleiter\nFirma GmbH",
        "custom_instructions": "Keine Emojis, keine Abkürzungen, immer höflich."
    },
    "brief": {
        "custom_instructions": "Maximal 3 Sätze, aber trotzdem höflich."
    }
}
```

### Beispiel 3: Schweizer Eigenheiten

```json
{
    "global": {
        "address_form": "auto",
        "salutation": "Liebe/r",
        "closing": "Beste Grüsse",
        "signature_enabled": true,
        "signature_text": "Mike",
        "custom_instructions": "Schreibe 'Grüsse' ohne ß (Schweizer Schreibweise). Verwende 'Freundliche Grüsse' statt 'Mit freundlichen Grüßen'."
    }
}
```

---

## 🔮 Zukünftige Erweiterungen

### 1. Benutzerdefinierte Stile erstellen

```python
# User kann eigene Stile erstellen (z.B. "Intern", "Kunde Premium")
class CustomReplyStyle(Base):
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String(50))  # z.B. "Kunde Premium"
    icon = Column(String(10))  # z.B. "⭐"
    base_style = Column(String(20))  # "formal", "friendly" als Basis
    # ... settings ...
```

### 2. Firmen-Templates (Multi-User)

```python
# Admin kann Firmen-weite Templates definieren
class CompanyReplyTemplate(Base):
    company_id = Column(Integer)
    style_key = Column(String(20))
    # ... settings ...
    is_locked = Column(Boolean)  # User kann nicht überschreiben
```

### 3. Kontext-basierte Stil-Auswahl

```python
# Automatische Stil-Auswahl basierend auf Sender/Kontext
# z.B. Emails von @bank.ch → automatisch "formal"
class StyleAutoRule(Base):
    user_id = Column(Integer)
    pattern = Column(String(100))  # z.B. "*@bank.ch"
    auto_style = Column(String(20))  # "formal"
```
