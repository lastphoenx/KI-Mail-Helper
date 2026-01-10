# 📘 PHASE X: Trusted Senders + UrgencyBooster - KORRIGIERTE Implementation

**Projekt:** KI-Mail-Helper  
**Phase:** X - Trusted Sender Whitelist + Entity-basierte Schnellklassifikation  
**Datum:** 2026-01-06  
**Status:** ✅ KORRIGIERT - Ready for Deployment  
**Review:** Beide Reviews berücksichtigt und Fehler behoben  

---

## 🔴 ÄNDERUNGEN GEGENÜBER ORIGINAL-DOKU

### Kritische Korrekturen:
1. ✅ **Import-Pattern korrigiert** - Nutzt jetzt `importlib.import_module()`
2. ✅ **Migration down_revision** - Muss manuell auf `ph_tag_queue` gesetzt werden
3. ✅ **analyze_email() statt classify_email_initial()** - Richtige Methode dokumentiert
4. ✅ **sender-Parameter hinzugefügt** - Signatur erweitert
5. ✅ **Performance-Erwartungen angepasst** - 100-300ms statt 50-100ms
6. ✅ **Validierung hinzugefügt** - Email/Domain-Format-Checks
7. ✅ **Limits implementiert** - Max 500 Trusted Senders pro User
8. ✅ **Newsletter Threshold** - Conditional Logic (0.45 mit Signalen, sonst 0.60)

---

## 📋 Inhaltsverzeichnis

1. [Pre-Flight Checks](#pre-flight-checks)
2. [Dependencies](#schritt-1-dependencies)
3. [Database Migration](#schritt-2-database-migration)
4. [Models erweitern](#schritt-3-models-erweitern)
5. [Newsletter-Classifier erweitern](#schritt-4-newsletter-classifier-erweitern)
6. [Trusted Sender Service](#schritt-5-trusted-sender-service-korrigiert)
7. [UrgencyBooster Service](#schritt-6-urgencybooster-service)
8. [AI Client Integration](#schritt-7-ai-client-integration-korrigiert)
9. [Processing Integration](#schritt-8-processing-integration-korrigiert)
10. [API Endpoints](#schritt-9-api-endpoints)
11. [UI Settings](#schritt-10-ui-settings)
12. [Deployment](#deployment-anleitung)
13. [Testing](#testing)

---

## Pre-Flight Checks

**WICHTIG:** Diese Checks MÜSSEN vor Implementation ausgeführt werden!

```bash
cd /home/mailhelper/projects/KI-Mail-Helper
source venv/bin/activate

# 1. Check aktuelle Migration
alembic current
alembic heads
# Notiere die letzte Migration ID!

# 2. Check spaCy
python -c "import spacy; print('✅ spaCy installed')" || pip install spacy
python -c "import spacy; spacy.load('de_core_news_sm'); print('✅ Model OK')" || \
    python -m spacy download de_core_news_sm

# 3. Backup erstellen
cp -r . ../KI-Mail-Helper-backup-$(date +%Y%m%d)
cp app.db app.db.backup

# 4. Check services directory
ls -la src/services/__init__.py || touch src/services/__init__.py

echo "✅ Pre-Flight Checks complete"
```

---

## Schritt 1: Dependencies

### 1.1 requirements.txt erweitern

**Datei:** `requirements.txt`

**ÄNDERUNG:** Am Ende hinzufügen:

```txt
# Phase X: UrgencyBooster - Entity-based Classification
spacy>=3.7.0
```

### 1.2 Startup-Code für spaCy Model Download

**Datei:** `src/01_web_app.py` (am Anfang, nach Imports)

```python
# Phase X: Ensure spaCy model is available
def ensure_spacy_model():
    """Stellt sicher dass spaCy Model verfügbar ist"""
    try:
        import spacy
        spacy.load("de_core_news_sm")
        logger.info("✅ spaCy Model (de_core_news_sm) verfügbar")
    except OSError:
        logger.warning("⚠️ spaCy Model nicht gefunden, versuche Download...")
        try:
            import os
            os.system("python -m spacy download de_core_news_sm")
            import spacy
            spacy.load("de_core_news_sm")
            logger.info("✅ spaCy Model erfolgreich heruntergeladen")
        except Exception as e:
            logger.error(f"❌ spaCy Model Download fehlgeschlagen: {e}")
            logger.error("   Bitte manuell installieren: python -m spacy download de_core_news_sm")

# Call beim Startup
ensure_spacy_model()
```

---

## Schritt 2: Database Migration

### 2.1 Migration erstellen

**Datei:** `migrations/versions/ph18_trusted_senders.py` **(NEU)**

**⚠️ KRITISCH:** `down_revision` MUSS manuell angepasst werden!

```python
"""Add trusted_senders table and urgency_booster_enabled setting

Revision ID: ph18_trusted_senders
Revises: <MANUAL_CHECK_REQUIRED>
Create Date: 2026-01-06

⚠️ WICHTIG: Setze down_revision auf die LETZTE Migration!
Führe aus: alembic current
Dann ersetze <MANUAL_CHECK_REQUIRED> mit dem Ergebnis.

Wahrscheinlich: 'ph_tag_queue' (basierend auf Review 2)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'ph18_trusted_senders'
down_revision = 'ph_tag_queue'  # ⚠️ PRÜFE MIT: alembic current
branch_labels = None
depends_on = None


def upgrade():
    """Add trusted_senders table and user setting"""
    
    # 1. Add urgency_booster_enabled to users table
    op.add_column(
        'users',
        sa.Column(
            'urgency_booster_enabled',
            sa.Boolean(),
            nullable=False,
            server_default='1'
        )
    )
    
    # 2. Create trusted_senders table
    op.create_table(
        'trusted_senders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_pattern', sa.String(255), nullable=False),
        sa.Column('pattern_type', sa.String(20), nullable=False),
        sa.Column('label', sa.String(100), nullable=True),
        sa.Column('use_urgency_booster', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.Column('email_count', sa.Integer(), nullable=False, server_default='0'),
        
        sa.UniqueConstraint('user_id', 'sender_pattern', name='uq_user_sender')
    )
    
    # 3. Create indexes (Composite index für Performance!)
    op.create_index('ix_trusted_senders_user_pattern', 'trusted_senders', 
                    ['user_id', 'sender_pattern'])  # ✅ Review 1 Empfehlung
    
    print("✅ Migration ph18: trusted_senders table created")
    print("✅ Migration ph18: urgency_booster_enabled added to users")


def downgrade():
    """Rollback changes"""
    op.drop_table('trusted_senders')
    op.drop_column('users', 'urgency_booster_enabled')
    print("⬇️ Rollback ph18: Changes reverted")
```

### 2.2 Migration ausführen

```bash
# PRE-CHECK
alembic current
# Notiere Output und passe down_revision an!

# Migration ausführen
alembic upgrade head

# Verifizieren
alembic current
# Should show: ph18_trusted_senders (head)

# Check Database
sqlite3 app.db "SELECT name FROM sqlite_master WHERE type='table' AND name='trusted_senders';"
# Should output: trusted_senders
```

---

## Schritt 3: Models erweitern

### 3.1 src/02_models.py

**ÄNDERUNG 1:** Import erweitern (falls nicht vorhanden)

```python
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, 
    ForeignKey, Enum, UniqueConstraint
)
```

**ÄNDERUNG 2:** User Model erweitern

**FINDE:**
```python
class User(Base):
    __tablename__ = "users"
    
    # ... existing fields ...
    preferred_embedding_provider = Column(String(50), default="ollama")
    preferred_embedding_model = Column(String(100), default="all-minilm:22m")
```

**FÜGE NACH preferred_embedding_model HINZU:**

```python
    # Phase X: UrgencyBooster Setting
    urgency_booster_enabled = Column(Boolean, default=True, nullable=False)
    """Aktiviert Entity-basierte Klassifikation für Trusted Senders"""
```

**ÄNDERUNG 3:** User Relationships erweitern

**FINDE:**
```python
    # Relationships
    mail_accounts = relationship("MailAccount", back_populates="user", cascade="all, delete-orphan")
    raw_emails = relationship("RawEmail", back_populates="user", cascade="all, delete-orphan")
    email_tags = relationship("EmailTag", back_populates="user", cascade="all, delete-orphan")
```

**FÜGE HINZU:**

```python
    trusted_senders = relationship("TrustedSender", back_populates="user", cascade="all, delete-orphan")
```

**ÄNDERUNG 4:** Neues Model hinzufügen (am Ende der Datei)

```python
class TrustedSender(Base):
    """
    User-definierte vertrauenswürdige Absender.
    
    Nur für Emails von diesen Sendern wird UrgencyBooster (spaCy) verwendet.
    Pattern wird normalisiert (lowercase) beim Speichern.
    """
    __tablename__ = "trusted_senders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    sender_pattern = Column(String(255), nullable=False)
    pattern_type = Column(String(20), nullable=False)
    label = Column(String(100), nullable=True)
    use_urgency_booster = Column(Boolean, default=True, nullable=False)
    
    added_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    email_count = Column(Integer, default=0, nullable=False)
    
    user = relationship("User", back_populates="trusted_senders")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'sender_pattern', name='uq_user_sender'),
    )
    
    def __init__(self, **kwargs):
        # ✅ Review 2: Normalisiere Pattern beim Erstellen
        if 'sender_pattern' in kwargs:
            kwargs['sender_pattern'] = kwargs['sender_pattern'].lower().strip()
        super().__init__(**kwargs)
    
    def __repr__(self):
        return f"<TrustedSender(id={self.id}, pattern={self.sender_pattern})>"
```

---

## Schritt 4: Newsletter-Classifier erweitern

### 4.1 src/known_newsletters.py

**ÄNDERUNG:** Siehe Original-Doku (bleibt unverändert), aber **PLUS:**

**Nach classify_newsletter_confidence() hinzufügen:**

```python
def should_treat_as_newsletter(sender: str, subject: str, body: str = "") -> bool:
    """
    Entscheidungs-Logik mit conditional Threshold (Review 1 Empfehlung).
    
    Returns:
        True wenn Email als Newsletter behandelt werden soll
    """
    confidence = classify_newsletter_confidence(sender, subject, body)
    
    # High confidence mit starken Signalen
    if confidence >= 0.45:
        # Prüfe auf starke Signale
        strong_signals = (
            "unsubscribe" in body.lower() or
            "abmelden" in body.lower() or
            count_urgency_tricks(f"{subject} {body[:500]}") >= 2 or
            count_scam_indicators(f"{subject} {body[:500]}") >= 1
        )
        
        if strong_signals:
            return True
    
    # Medium confidence ohne starke Signale
    if confidence >= 0.60:
        return True
    
    return False
```

---

## Schritt 5: Trusted Sender Service (KORRIGIERT)

### 5.1 src/services/trusted_senders.py (NEU)

**✅ KORRIGIERT:** Import-Pattern, Validierung, Limits, Transaktionale Updates

```python
"""
Trusted Sender Management

Verwaltet User-definierte vertrauenswürdige Absender.
Phase X - Korrigierte Version nach Reviews.
"""

import logging
import re
import importlib
from typing import Optional, List, Dict
from datetime import datetime, UTC
from sqlalchemy import func, update

logger = logging.getLogger(__name__)

# ✅ Review 2: Limits definieren
MAX_TRUSTED_SENDERS_PER_USER = 500

# ✅ Review 2: Validierungs-Regex
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
DOMAIN_REGEX = r'^([a-zA-Z0-9](-?[a-zA-Z0-9])*\.)+[a-zA-Z]{2,}$'


class TrustedSenderManager:
    """Verwaltet Trusted Sender für User"""
    
    @staticmethod
    def is_trusted_sender(db, user_id: int, sender_email: str) -> Optional[Dict]:
        """
        Prüft ob Sender vertrauenswürdig ist.
        
        Returns:
            None wenn nicht trusted
            dict mit {'id', 'label', 'use_urgency_booster', 'pattern'} wenn trusted
        """
        # ✅ Review 1: Korrektes Import-Pattern
        models = importlib.import_module(".02_models", "src")
        
        sender_lower = sender_email.lower().strip()
        
        if '@' in sender_lower:
            domain = sender_lower.split('@')[1]
            email_domain = '@' + domain
        else:
            domain = sender_lower
            email_domain = None
        
        # Hole alle Trusted Sender für User
        trusted_senders = db.query(models.TrustedSender).filter_by(
            user_id=user_id
        ).all()
        
        # ✅ Pattern ist bereits normalisiert (siehe Model __init__)
        for ts in trusted_senders:
            pattern = ts.sender_pattern  # Bereits lowercase
            
            if ts.pattern_type == 'exact':
                if pattern == sender_lower:
                    return {
                        'id': ts.id,
                        'label': ts.label,
                        'use_urgency_booster': ts.use_urgency_booster,
                        'pattern': ts.sender_pattern,
                        'pattern_type': 'exact'
                    }
            
            elif ts.pattern_type == 'email_domain' and email_domain:
                if pattern == email_domain:
                    return {
                        'id': ts.id,
                        'label': ts.label,
                        'use_urgency_booster': ts.use_urgency_booster,
                        'pattern': ts.sender_pattern,
                        'pattern_type': 'email_domain'
                    }
            
            elif ts.pattern_type == 'domain':
                if pattern == domain or sender_lower.endswith('.' + pattern) or sender_lower.endswith('@' + pattern):
                    return {
                        'id': ts.id,
                        'label': ts.label,
                        'use_urgency_booster': ts.use_urgency_booster,
                        'pattern': ts.sender_pattern,
                        'pattern_type': 'domain'
                    }
        
        return None
    
    @staticmethod
    def add_trusted_sender(
        db,
        user_id: int,
        sender_pattern: str,
        pattern_type: str,
        label: Optional[str] = None
    ) -> Dict:
        """
        Fügt vertrauenswürdigen Sender hinzu.
        
        ✅ Mit Validierung und Limits (Review 2)
        """
        models = importlib.import_module(".02_models", "src")
        
        # Validate pattern_type
        if pattern_type not in ['exact', 'email_domain', 'domain']:
            return {'success': False, 'error': f'Ungültiger pattern_type: {pattern_type}'}
        
        # Normalize
        sender_pattern = sender_pattern.lower().strip()
        
        # ✅ Review 2: Validierung
        if pattern_type == 'exact':
            if not re.match(EMAIL_REGEX, sender_pattern):
                return {'success': False, 'error': 'Ungültiges Email-Format'}
        
        elif pattern_type == 'email_domain':
            if not sender_pattern.startswith('@'):
                return {'success': False, 'error': 'Email-Domain muss mit @ beginnen'}
            domain_part = sender_pattern[1:]
            if not re.match(DOMAIN_REGEX, domain_part):
                return {'success': False, 'error': 'Ungültiges Domain-Format'}
        
        elif pattern_type == 'domain':
            if not re.match(DOMAIN_REGEX, sender_pattern):
                return {'success': False, 'error': 'Ungültiges Domain-Format'}
        
        # ✅ Review 2: Check Limit
        current_count = db.query(models.TrustedSender).filter_by(user_id=user_id).count()
        if current_count >= MAX_TRUSTED_SENDERS_PER_USER:
            return {
                'success': False,
                'error': f'Limit erreicht ({MAX_TRUSTED_SENDERS_PER_USER} Sender maximum)'
            }
        
        # Check if exists
        existing = db.query(models.TrustedSender).filter_by(
            user_id=user_id,
            sender_pattern=sender_pattern
        ).first()
        
        if existing:
            return {
                'success': False,
                'error': 'Sender bereits in Liste',
                'existing_id': existing.id
            }
        
        # Create (Pattern wird im Model __init__ normalisiert)
        trusted = models.TrustedSender(
            user_id=user_id,
            sender_pattern=sender_pattern,
            pattern_type=pattern_type,
            label=label,
            use_urgency_booster=True,
            added_at=datetime.now(UTC),
            email_count=0
        )
        
        db.add(trusted)
        db.commit()
        
        logger.info(f"✅ User {user_id} added trusted sender: {sender_pattern} ({pattern_type})")
        
        return {
            'success': True,
            'id': trusted.id,
            'sender_pattern': trusted.sender_pattern,
            'pattern_type': trusted.pattern_type,
            'label': trusted.label
        }
    
    @staticmethod
    def update_last_seen(db, trusted_sender_id: int):
        """
        Aktualisiert last_seen_at und email_count.
        
        ✅ Review 2: Transaktionales Update statt Python increment
        """
        models = importlib.import_module(".02_models", "src")
        
        try:
            db.execute(
                update(models.TrustedSender)
                .where(models.TrustedSender.id == trusted_sender_id)
                .values(
                    last_seen_at=datetime.now(UTC),
                    email_count=models.TrustedSender.email_count + 1
                )
            )
            db.commit()
        except Exception as e:
            logger.error(f"Failed to update trusted sender {trusted_sender_id}: {e}")
            db.rollback()
    
    @staticmethod
    def get_suggestions_from_emails(
        db,
        user_id: int,
        master_key: str,
        limit: int = 10
    ) -> List[Dict]:
        """Schlägt Sender vor basierend auf Email-Historie."""
        models = importlib.import_module(".02_models", "src")
        encryption = importlib.import_module(".08_encryption", "src")
        
        frequent_senders = db.query(
            models.RawEmail.encrypted_sender,
            func.count(models.RawEmail.id).label('count')
        ).filter(
            models.RawEmail.user_id == user_id,
            models.RawEmail.deleted_at.is_(None)
        ).group_by(
            models.RawEmail.encrypted_sender
        ).having(
            func.count(models.RawEmail.id) >= 3
        ).order_by(
            func.count(models.RawEmail.id).desc()
        ).limit(limit * 3).all()
        
        suggestions = []
        trusted_patterns = {
            ts.sender_pattern
            for ts in db.query(models.TrustedSender).filter_by(user_id=user_id).all()
        }
        
        decryption_errors = 0  # ✅ Review 2: Zähle Fehler
        
        for encrypted_sender, count in frequent_senders:
            try:
                sender = encryption.EmailDataManager.decrypt_sender(encrypted_sender, master_key)
                sender_lower = sender.lower()
                
                if sender_lower in trusted_patterns:
                    continue
                
                if '@' in sender_lower:
                    domain = sender_lower.split('@')[1]
                    email_domain = '@' + domain
                    
                    if email_domain in trusted_patterns or domain in trusted_patterns:
                        continue
                
                suggestions.append({
                    'sender': sender,
                    'email_count': count,
                    'suggested_pattern_type': 'exact'
                })
                
                if len(suggestions) >= limit:
                    break
            
            except Exception as e:
                decryption_errors += 1
                logger.error(f"Decryption failed for sender suggestion: {e}")
                
                # ✅ Review 2: Abort if too many errors
                if decryption_errors > 10:
                    logger.warning("Too many decryption errors, aborting suggestions")
                    break
        
        return suggestions
```

---

## Schritt 6: UrgencyBooster Service

*Dieser Teil bleibt wie in der Original-Doku, außer:*

**Performance-Dokumentation anpassen:**

```python
class UrgencyBooster:
    """
    Entity-basierte Dringlichkeits-Erkennung mit spaCy NER.
    
    Performance (CPU-only):
    - Erste Email: ~500ms (Model-Loading)
    - Folgende Emails: 100-300ms (je nach Textlänge)
    - Kurze Emails (<500 chars): ~100-150ms ✅
    - Lange Emails (>1000 chars): ~200-300ms
    
    ✅ Review 2: Performance-Erwartungen realistic
    """
```

---

## Schritt 7: AI Client Integration (KORRIGIERT)

### 7.1 src/03_ai_client.py

**✅ KRITISCH:** Integration erfolgt in `analyze_email()`, NICHT in `classify_email_initial()`!

**ÄNDERUNG 1:** Import hinzufügen (oben)

```python
# Phase X: UrgencyBooster
URGENCY_BOOSTER_AVAILABLE = False
try:
    from services.urgency_booster import get_urgency_booster
    from services.trusted_senders import TrustedSenderManager
    URGENCY_BOOSTER_AVAILABLE = True
    logger.info("✅ UrgencyBooster verfügbar")
except ImportError as e:
    logger.warning(f"⚠️ UrgencyBooster nicht verfügbar: {e}")
```

**ÄNDERUNG 2:** analyze_email() Signatur erweitern

**FINDE in LocalOllamaClient:**
```python
def analyze_email(
    self,
    subject: str,
    body: str,
    language: str = "de",
    context: Optional[str] = None
) -> Dict[str, Any]:
```

**ERSETZE mit:**

```python
def analyze_email(
    self,
    subject: str,
    body: str,
    sender: str = "",  # ✅ NEU
    language: str = "de",
    context: Optional[str] = None,
    user_id: Optional[int] = None,  # ✅ NEU
    db = None,  # ✅ NEU
    user_enabled_booster: bool = True  # ✅ NEU
) -> Dict[str, Any]:
    """
    Analysiert Email mit optionalem UrgencyBooster für Trusted Senders.
    
    Workflow (Phase X):
    1. Newsletter-Check (Heuristik)
    2. Trusted Sender Check
       → UrgencyBooster (100-300ms)
       → High Confidence → Return
    3. Standard-Analyse (Embedding/Chat)
    """
```

**ÄNDERUNG 3:** Newsletter-Check mit conditional Threshold

**FINDE:**
```python
# Irgendwo in analyze_email() - Newsletter Check
```

**ERSETZE/FÜGE EIN:**

```python
    # === Newsletter-Check (Phase X: Improved) ===
    from known_newsletters import should_treat_as_newsletter
    
    if should_treat_as_newsletter(sender, subject, body):
        logger.debug(f"Newsletter erkannt: {sender}")
        return {
            "dringlichkeit": 1,
            "wichtigkeit": 1,
            "kategorie_aktion": "nur_information",
            "spam_flag": True,
            "tags": ["Newsletter"],
            "summary_de": subject[:100] if subject else "",
            "text_de": body[:500] if body else ""
        }
```

**ÄNDERUNG 4:** UrgencyBooster Integration NACH Newsletter-Check

**FÜGE EIN (NACH Newsletter-Check, VOR Standard-Analyse):**

```python
    # === Phase X: Trusted Sender Check + UrgencyBooster ===
    if (
        user_id is not None
        and db is not None
        and sender
        and user_enabled_booster
        and URGENCY_BOOSTER_AVAILABLE
    ):
        try:
            trusted = TrustedSenderManager.is_trusted_sender(db, user_id, sender)
            
            if trusted and trusted['use_urgency_booster']:
                logger.info(f"✅ Trusted sender: {sender} ({trusted.get('label', 'None')})")
                
                booster = get_urgency_booster()
                booster_result = booster.analyze_urgency(subject, body, sender)
                
                logger.info(
                    f"🚀 UrgencyBooster: "
                    f"urgency={booster_result['urgency_score']:.2f}, "
                    f"confidence={booster_result['confidence']:.2f}"
                )
                
                # ✅ Review 1: Confidence 0.6 ist OK für Trusted Senders
                if booster_result['confidence'] >= 0.6:
                    
                    TrustedSenderManager.update_last_seen(db, trusted['id'])
                    
                    # Map Score → Dringlichkeit/Wichtigkeit
                    if booster_result['urgency_score'] >= 0.7:
                        dringlichkeit = 3
                    elif booster_result['urgency_score'] >= 0.4:
                        dringlichkeit = 2
                    else:
                        dringlichkeit = 1
                    
                    if booster_result['importance_score'] >= 0.6:
                        wichtigkeit = 3
                    elif booster_result['importance_score'] >= 0.3:
                        wichtigkeit = 2
                    else:
                        wichtigkeit = 1
                    
                    kategorie_aktion = booster_result['category']
                    
                    tags = []
                    if booster_result['signals'].get('invoice_detected'):
                        tags.append("Rechnung")
                    if booster_result['signals'].get('time_pressure'):
                        tags.append("Deadline")
                    if not tags:
                        tags.append("Klassifiziert")
                    
                    return {
                        "dringlichkeit": dringlichkeit,
                        "wichtigkeit": wichtigkeit,
                        "kategorie_aktion": kategorie_aktion,
                        "tags": tags,
                        "suggested_tags": tags,
                        "spam_flag": False,
                        "summary_de": subject[:100] if subject else "",
                        "text_de": body[:500] if body else ""
                    }
                else:
                    logger.info(f"⚡ UrgencyBooster LOW CONFIDENCE → Fallback")
        
        except Exception as e:
            logger.warning(f"⚠️ UrgencyBooster Fehler: {e}")
    
    # === Standard-Analyse (Embedding oder Chat) ===
    # ... existing code ...
```

---

## Schritt 8: Processing Integration (KORRIGIERT)

### 8.1 src/12_processing.py

**FINDE die Stelle wo analyze_email() aufgerufen wird:**

```bash
# Suche nach:
grep -n "analyze_email" src/12_processing.py
```

**TYPISCHERWEISE sowas wie:**
```python
ai_result = ai_client.analyze_email(
    subject=decrypted_subject,
    body=decrypted_body,
    language=language
)
```

**ERSETZE mit:**

```python
# Phase X: Mit Trusted Sender Support
user = session.query(models.User).filter_by(id=raw_email.user_id).first()

ai_result = ai_client.analyze_email(
    subject=decrypted_subject,
    body=decrypted_body,
    sender=decrypted_sender,  # ✅ NEU
    language=language,
    user_id=raw_email.user_id,  # ✅ NEU
    db=session,  # ✅ NEU
    user_enabled_booster=user.urgency_booster_enabled if user else True  # ✅ NEU
)
```

---

## Schritt 9: API Endpoints

*Bleibt wie in Original-Doku, keine Änderungen nötig.*

---

## Schritt 10: UI Settings

*Bleibt wie in Original-Doku, keine Änderungen nötig.*

---

## Deployment-Anleitung

### 1. Vorbereitung

```bash
cd /home/mailhelper/projects/KI-Mail-Helper
source venv/bin/activate

# Backup
cp -r . ../KI-Mail-Helper-backup-$(date +%Y%m%d)
cp app.db app.db.backup

# Git
git status
git add .
git commit -m "Phase X: Trusted Senders + UrgencyBooster (Corrected)"
```

### 2. Pre-Flight Checks ausführen

```bash
# Siehe oben - ALLE Checks durchführen!
```

### 3. Migration anpassen & ausführen

```bash
# ✅ KRITISCH: down_revision prüfen
alembic current
# Notiere Output!

# Editiere migrations/versions/ph18_trusted_senders.py
# Setze down_revision = '<output_von_oben>'

# Migration ausführen
alembic upgrade head

# Verifizieren
alembic current
sqlite3 app.db "SELECT name FROM sqlite_master WHERE type='table' AND name='trusted_senders';"
```

### 4. Code deployen

**Checklist:**
- [ ] Migration `ph18_trusted_senders.py` mit korrektem down_revision
- [ ] `src/02_models.py` erweitert
- [ ] `src/known_newsletters.py` erweitert + `should_treat_as_newsletter()`
- [ ] `src/services/trusted_senders.py` mit importlib-Pattern
- [ ] `src/services/urgency_booster.py` erstellt
- [ ] `src/03_ai_client.py` - `analyze_email()` erweitert
- [ ] `src/12_processing.py` - Aufruf angepasst
- [ ] `src/01_web_app.py` - API-Endpoints + spaCy Startup-Code
- [ ] `templates/settings.html` erweitert
- [ ] `src/services/__init__.py` vorhanden

### 5. Server neustarten & testen

```bash
# Stop Server
# (Ctrl+C)

# Start Server
python src/01_web_app.py

# Check Logs - sollte zeigen:
# ✅ spaCy Model (de_core_news_sm) verfügbar
# ✅ UrgencyBooster verfügbar
```

---

## Testing

### Test 1: Trusted Sender hinzufügen

```
1. Browser → http://localhost:5000/settings
2. Scrolle zu "Vertrauenswürdige Absender"
3. Klicke "Vorschläge laden"
4. ✓ Mind. 1 Vorschlag erscheint
5. Klicke "Hinzufügen"
6. ✓ Sender erscheint in Liste mit Email-Count
```

### Test 2: Email Fetch mit Trusted Sender

```
1. Fetch Emails
2. Check Logs:
   "✅ Trusted sender: xyz@example.com"
   "🚀 UrgencyBooster: urgency=..."
   "✅ UrgencyBooster HIGH CONFIDENCE → D=..."
3. ✓ Email hat korrekte Scores
4. ✓ Processing-Zeit ~100-300ms (nicht 5-10 Min!)
```

### Test 3: Newsletter Erkennung

```
1. Fetch Marketing-Email
2. Check Logs:
   "Newsletter erkannt: marketing@shop.com"
3. ✓ spam_flag=True
4. ✓ Dringlichkeit=1
5. ✓ UrgencyBooster wurde NICHT aufgerufen
```

### Test 4: Unknown Sender Fallback

```
1. Fetch Email von unbekanntem Sender
2. Check Logs:
   Kein "✅ Trusted sender" Log
   Standard-Analyse läuft
3. ✓ Classification funktioniert normal
```

### Test 5: Performance Benchmark

```bash
# Vor Implementation
time python -c "from src import processing; processing.process_pending_raw_emails(session)"
# Notiere Zeit

# Nach Implementation (mit 5 Trusted Senders hinzugefügt)
time python -c "from src import processing; processing.process_pending_raw_emails(session)"
# Notiere Zeit

# Erwartung: 3-4x schneller wenn 50% Trusted Senders
```

---

## Troubleshooting

### Problem 1: ImportError in trusted_senders.py

**Symptom:**
```
ImportError: No module named 'models_02'
```

**Lösung:**
```python
# ✅ Korrekt (bereits in korrigierter Version):
models = importlib.import_module(".02_models", "src")

# ❌ NICHT:
from models_02 import TrustedSender
```

### Problem 2: Migration down_revision Konflikt

**Symptom:**
```
Multiple heads detected
```

**Lösung:**
```bash
alembic heads
alembic merge -m "merge heads before ph18"
alembic upgrade head
```

### Problem 3: analyze_email() missing sender parameter

**Symptom:**
```
TypeError: analyze_email() got an unexpected keyword argument 'sender'
```

**Lösung:**
Prüfe ob Signatur in **ALLEN** AI-Client-Klassen erweitert wurde:
- LocalOllamaClient
- OpenAIChatClient
- AnthropicChatClient

### Problem 4: spaCy Model nicht gefunden

**Symptom:**
```
OSError: [E050] Can't find model 'de_core_news_sm'
```

**Lösung:**
```bash
python -m spacy download de_core_news_sm
# Oder nutze Startup-Code in 01_web_app.py
```

---

## 🎯 Zusammenfassung der Korrekturen

| Fehler in Original-Doku | Korrektur | Review |
|-------------------------|-----------|--------|
| **Import-Pattern falsch** | importlib.import_module() | Review 1 & 2 ✅ |
| **down_revision statisch** | Manuell prüfen mit alembic | Review 1 & 2 ✅ |
| **classify_email_initial()** | analyze_email() | Review 1 ✅ |
| **sender-Parameter fehlt** | Signatur erweitert | Review 1 ✅ |
| **Performance 50-100ms** | 100-300ms realistic | Review 2 ✅ |
| **Keine Validierung** | Regex + Limits hinzugefügt | Review 2 ✅ |
| **Newsletter Threshold fix** | Conditional 0.45/0.60 | Review 1 ✅ |
| **Case-Sensitivity** | Model normalisiert Pattern | Review 2 ✅ |
| **Race Condition** | Transaktionales Update | Review 2 ✅ |

---

## ✅ Ready for Deployment!

Diese korrigierte Version adressiert **ALLE kritischen Punkte** aus beiden Reviews.

**Geschätzte Zeit:** 6-8 Stunden (mit Korrekturen)

Viel Erfolg! 🚀
