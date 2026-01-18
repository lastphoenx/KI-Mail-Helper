"""
Mail Helper - Datenbankmodelle (SQLAlchemy + SQLite)
Phase 1: raw_emails, processed_emails
Phase 2: User, MailAccount, ServiceToken, RecoveryCode
"""

from datetime import datetime, timedelta, UTC
from enum import Enum
from typing import Optional
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    Date,
    Float,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
    LargeBinary,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash, check_password_hash
import secrets


Base = declarative_base()


class AIProvider(str, Enum):
    """KI-Provider für Email-Analyse"""

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MISTRAL = "mistral"


class EmailActionCategory(str, Enum):
    """Kategorien für Email-Aktionen"""

    ACTION_REQUIRED = "aktion_erforderlich"
    URGENT = "dringend"
    INFO_ONLY = "nur_information"


class EmailColor(str, Enum):
    """Farben für Email-Priorität/Scoring"""

    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"


class IMAPEncryption(str, Enum):
    """IMAP Verschlüsselungstypen"""

    SSL = "SSL"
    STARTTLS = "STARTTLS"
    NONE = "NONE"


class SMTPEncryption(str, Enum):
    """SMTP Verschlüsselungstypen"""

    STARTTLS = "STARTTLS"
    SSL = "SSL"
    NONE = "NONE"


class AuthType(str, Enum):
    """Authentifizierungs-Typen für Mail-Accounts"""

    IMAP = "imap"
    OAUTH = "oauth"


class OptimizationStatus(str, Enum):
    """Status der Email-Optimierung (zweiter Pass)"""

    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class EmailTag(Base):
    """User-definierte Tags für Emails (Phase 10)
    
    Phase F.2 Enhanced:
    - description: Optional semantic description for better embeddings
    - learned_embedding: Aggregated embedding from assigned emails
    - embedding_updated_at: Last update timestamp for learned_embedding
    """

    __tablename__ = "email_tags"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    color = Column(String(20), nullable=False, default="#3B82F6")  # Tailwind blue-500
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # Phase F.2 Enhanced: Semantic tag description for better embeddings
    # If NULL: Fallback to name for embeddings
    description = Column(Text, nullable=True)
    
    # Phase F.2 Learning: Aggregated embedding from assigned emails
    # Recalculated after each tag assignment (mean of all email_embeddings)
    # If NULL: Fallback to description/name embedding
    learned_embedding = Column(LargeBinary, nullable=True)
    embedding_updated_at = Column(DateTime, nullable=True)
    
    # Phase NEGATIVE-FEEDBACK: Aggregated negative embedding (v2.0)
    # Mean of all rejected emails for this tag
    # Used to reduce false positive suggestions
    negative_embedding = Column(LargeBinary, nullable=True)
    negative_updated_at = Column(DateTime, nullable=True)
    negative_count = Column(Integer, default=0)

    # Relationships
    user = relationship("User", back_populates="email_tags")
    assignments = relationship("EmailTagAssignment", back_populates="tag", cascade="all, delete-orphan")
    negative_examples = relationship("TagNegativeExample", back_populates="tag", cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_tag_name"),)


class EmailTagAssignment(Base):
    """Verknüpfung zwischen Emails und Tags (Phase 10)"""

    __tablename__ = "email_tag_assignments"

    id = Column(Integer, primary_key=True)
    email_id = Column(Integer, ForeignKey("processed_emails.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(Integer, ForeignKey("email_tags.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # Phase F.3: Auto-Assignment Flag
    # True = Tag wurde automatisch zugewiesen (≥80% Similarity)
    # False = Tag wurde manuell zugewiesen
    auto_assigned = Column(Boolean, default=False, nullable=False)

    # Relationships
    email = relationship("ProcessedEmail", back_populates="tag_assignments")
    tag = relationship("EmailTag", back_populates="assignments")

    # Constraints
    __table_args__ = (UniqueConstraint("email_id", "tag_id", name="uq_email_tag"),)


class TagNegativeExample(Base):
    """Negativ-Beispiele für Tag-Learning (Phase NEGATIVE-FEEDBACK v2.0)
    
    Speichert Emails, die der User explizit als "passt nicht" für einen Tag
    markiert hat. Diese werden bei der Similarity-Berechnung als Penalty verwendet.
    
    Das System berechnet ein aggregiertes negative_embedding (Durchschnitt aller
    Rejections) und nutzt dies, um False Positives zu reduzieren.
    """
    
    __tablename__ = "tag_negative_examples"
    
    id = Column(Integer, primary_key=True)
    tag_id = Column(Integer, ForeignKey("email_tags.id", ondelete="CASCADE"), nullable=False)
    email_id = Column(Integer, ForeignKey("processed_emails.id", ondelete="CASCADE"), nullable=False)
    
    # Embedding-Kopie (da Email-Embedding sich ändern könnte)
    negative_embedding = Column(LargeBinary, nullable=False)
    
    # Metadaten
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # Woher kam die Ablehnung? ("suggestion" | "auto_assign")
    # NICHT "manual" - nur explizite Rejections!
    rejection_source = Column(String(20), default="suggestion")
    
    # Relationships
    tag = relationship("EmailTag", back_populates="negative_examples")
    email = relationship("ProcessedEmail", backref="negative_tag_examples")
    
    # Constraints: Eine Email kann nur einmal pro Tag als Negativ markiert werden
    __table_args__ = (
        UniqueConstraint("tag_id", "email_id", name="uq_tag_negative_email"),
        Index("ix_tag_negative_tag_id", "tag_id"),
    )


class TagSuggestionQueue(Base):
    """Warteschlange für KI-vorgeschlagene Tags (Phase TAG-QUEUE)
    
    Sammelt AI-Vorschläge für nicht-existierende Tags.
    User entscheidet: approve → Tag erstellen, reject → ignorieren, merge → zu existierendem Tag
    
    Status: pending, approved, rejected, merged
    """

    __tablename__ = "tag_suggestion_queue"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Was wurde vorgeschlagen
    suggested_name = Column(String(50), nullable=False)

    # Woher kam der Vorschlag (optional - kann später löschen wenn Email gelöscht wird)
    source_email_id = Column(Integer, ForeignKey("processed_emails.id", ondelete="SET NULL"), nullable=True)

    # Wann wurde es vorgeschlagen
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Status: pending, approved, rejected, merged
    status = Column(String(20), default="pending", nullable=False)

    # Falls zu existierendem Tag gemappt (bei merge oder approve)
    merged_into_tag_id = Column(Integer, ForeignKey("email_tags.id", ondelete="SET NULL"), nullable=True)

    # Wie oft wurde dieser Name vorgeschlagen (für Priorisierung)
    suggestion_count = Column(Integer, default=1)

    # Relationships
    user = relationship("User", backref="tag_suggestions")
    source_email = relationship("ProcessedEmail", backref="tag_suggestions")
    merged_into_tag = relationship("EmailTag", backref="merged_suggestions")

    # Constraints: Nur ein pending Vorschlag pro Name pro User
    __table_args__ = (
        UniqueConstraint("user_id", "suggested_name", name="uq_user_pending_suggestion"),
    )


class SenderPattern(Base):
    """
    Gelernte Muster für Absender-basierte Klassifizierung (Phase 11d).
    
    Speichert für jeden User, wie E-Mails von bestimmten Absendern
    typischerweise klassifiziert werden. Dies ermöglicht konsistente
    Klassifizierung für wiederkehrende Absender.
    
    Privacy: sender_hash ist ein SHA-256 Hash des normalisierten Absenders,
    sodass keine Klartextadressen gespeichert werden.
    """
    
    __tablename__ = "sender_patterns"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # SHA-256 Hash des normalisierten Absenders (lowercase, stripped)
    sender_hash = Column(String(64), nullable=False, index=True)
    
    # Gelernte Klassifizierung
    category = Column(String(50), nullable=True)  # Häufigste Kategorie
    priority = Column(Integer, nullable=True)  # Durchschnittliche Priorität (1-10)
    is_newsletter = Column(Boolean, nullable=True)  # Meist Newsletter?
    
    # Statistiken
    email_count = Column(Integer, default=1)  # Anzahl E-Mails von diesem Sender
    correction_count = Column(Integer, default=0)  # Anzahl User-Korrekturen
    confidence = Column(Integer, default=50)  # Konfidenz 0-100
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    # Relationships
    user = relationship("User", back_populates="sender_patterns")
    
    # Constraints: Ein Pattern pro User/Sender-Kombination
    __table_args__ = (UniqueConstraint("user_id", "sender_hash", name="uq_user_sender_pattern"),)


class User(Base):
    """Benutzer des Systems (Phase 2)"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # Account Security (Phase 9: Production Hardening)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)  # NULL = nicht gesperrt
    last_failed_login = Column(DateTime, nullable=True)

    # Key-Management (Phase 8: DEK/KEK Pattern)
    # Zero-Knowledge: KEK (Key Encryption Key) aus Passwort abgeleitet (PBKDF2)
    #                 DEK (Data Encryption Key) zufällig generiert, verschlüsselt alle E-Mails
    #                 encrypted_dek = AES-GCM(DEK, KEK) - ermöglicht Passwort-Wechsel ohne Neu-Verschlüsselung
    salt = Column(
        Text
    )  # base64(32 bytes) = 44 chars (TEXT für SQLite: keine Längen-Sorgen)
    encrypted_dek = Column(Text)  # DEK verschlüsselt mit KEK (aus Passwort)
    encrypted_master_key = Column(
        Text
    )  # DEPRECATED: Wird durch encrypted_dek ersetzt (für Migration behalten)

    # 2FA (TOTP)
    totp_secret = Column(String(32))
    totp_enabled = Column(Boolean, default=False)

    # KI-Präferenzen (3 Settings: EMBEDDING / BASE / OPTIMIZE)
    
    # 1. EMBEDDING Model (Vektorisierung für Semantic Search, Tags)
    preferred_embedding_provider = Column(String(20), default=AIProvider.OLLAMA.value)
    preferred_embedding_model = Column(
        String(100), default="all-minilm:22m"
    )  # Nur Embedding-Modelle: all-minilm, nomic-embed, bge, text-embedding-3-small
    
    # 2. BASE Model (Schnelle Klassifikation, erster Pass)
    preferred_ai_provider = Column(String(20), default=AIProvider.OLLAMA.value)
    preferred_ai_model = Column(
        String(100), default="llama3.2:1b"
    )  # Chat-Modelle: llama3.2:1b, gpt-4o-mini, haiku
    
    # 3. OPTIMIZE Model (Tiefe Analyse, zweiter Pass)
    preferred_ai_provider_optimize = Column(String(20), default=AIProvider.OLLAMA.value)
    preferred_ai_model_optimize = Column(
        String(100), default="llama3.2:3b"
    )  # Bessere Chat-Modelle: llama3.2:3b, gpt-4o, sonnet

    # Phase 13C Part 4: Fetch-Konfiguration (User-steuerbar)
    fetch_mails_per_folder = Column(Integer, default=100)  # Limit pro Ordner
    fetch_max_total = Column(Integer, default=0)  # 0 = unbegrenzt
    fetch_use_delta_sync = Column(Boolean, default=True)  # Nur neue Mails holen

    # Phase INV: Invite & Diagnostics Access
    imap_diagnostics_enabled = Column(Boolean, default=False)  # IMAP-Diagnostics Zugriff

    # Phase TAG-QUEUE: Tag Suggestion Queue (Default: AUS)
    # Wenn aktiviert: AI-Vorschläge für nicht-existierende Tags kommen in Queue
    # User kann dann approve/reject/merge mit eigenen Tags
    enable_tag_suggestion_queue = Column(Boolean, default=False)
    
    # Phase F.3: Auto-Assignment für bestehende Tags (Default: AUS)
    # Wenn aktiviert: Tags mit ≥80% Similarity werden automatisch zugewiesen
    # Unabhängig von enable_tag_suggestion_queue (verschiedene Features!)
    enable_auto_assignment = Column(Boolean, default=False)

    # Phase X: UrgencyBooster Setting
    urgency_booster_enabled = Column(Boolean, default=True, nullable=False)
    """Aktiviert Entity-basierte Klassifikation für Trusted Senders"""

    # Hybrid Score-Learning: Classifier-Präferenz
    prefer_personal_classifier = Column(Boolean, default=False, nullable=False)
    """Wenn True: Nutze persönliches ML-Modell statt globalem für Vorhersagen"""

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships
    mail_accounts = relationship(
        "MailAccount", back_populates="user", cascade="all, delete-orphan"
    )
    raw_emails = relationship(
        "RawEmail", back_populates="user", cascade="all, delete-orphan"
    )
    service_tokens = relationship(
        "ServiceToken", back_populates="user", cascade="all, delete-orphan"
    )
    recovery_codes = relationship(
        "RecoveryCode", back_populates="user", cascade="all, delete-orphan"
    )
    email_tags = relationship(
        "EmailTag", back_populates="user", cascade="all, delete-orphan"
    )
    sender_patterns = relationship(
        "SenderPattern", back_populates="user", cascade="all, delete-orphan"
    )
    reply_style_settings = relationship(
        "ReplyStyleSettings", back_populates="user", cascade="all, delete-orphan"
    )
    trusted_senders = relationship(
        "TrustedSender", back_populates="user", cascade="all, delete-orphan"
    )
    spacy_scoring_configs = relationship(
        "SpacyScoringConfig", back_populates="user", cascade="all, delete-orphan"
    )
    spacy_vip_senders = relationship(
        "SpacyVIPSender", back_populates="user", cascade="all, delete-orphan"
    )
    spacy_keyword_sets = relationship(
        "SpacyKeywordSet", back_populates="user", cascade="all, delete-orphan"
    )
    spacy_user_domains = relationship(
        "SpacyUserDomain", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password: str):
        """Hasht das Passwort (mit Längen-Validierung)"""
        if not password:
            raise ValueError("Passwort darf nicht leer sein")
        if len(password) < 8:
            raise ValueError("Passwort zu kurz (mind. 8 Zeichen)")
        if len(password) > 255:
            raise ValueError("Passwort zu lang (max. 255 Zeichen)")
        self.password_hash = generate_password_hash(password)

    def set_username(self, username: str):
        """Setzt Username mit Validierung"""
        if not username or len(username) < 3:
            raise ValueError("Username muss 3-80 Zeichen sein")
        if len(username) > 80:
            raise ValueError("Username zu lang (max. 80 Zeichen)")
        self.username = username

    def set_email(self, email: str):
        """Setzt Email mit Validierung"""
        if not email:
            raise ValueError("Email darf nicht leer sein")
        if len(email) > 255:
            raise ValueError("Email zu lang (max. 255 Zeichen)")
        self.email = email

    def check_password(self, password: str) -> bool:
        """Überprüft das Passwort"""
        return check_password_hash(self.password_hash, password)

    def is_locked(self) -> bool:
        """Prüft ob Account gesperrt ist"""
        if not self.locked_until:
            return False
        if datetime.now(UTC) >= self.locked_until:
            # Sperre abgelaufen - automatisch aufheben
            self.locked_until = None
            self.failed_login_attempts = 0
            return False
        return True

    def record_failed_login(self, session):
        """Fehlgeschlagenen Login-Versuch registrieren (Thread-safe)

        Phase 9f: Atomic SQL-Update verhindert Race Conditions bei Multi-Worker Setup
        OHNE session.commit() - Caller entscheidet über Transaction-Boundary
        """
        from sqlalchemy import text

        # Atomic increment direkt in DB (verhindert Read-Modify-Write Race)
        result = session.execute(
            text(
                "UPDATE users SET "
                "failed_login_attempts = failed_login_attempts + 1, "
                "last_failed_login = :now "
                "WHERE id = :id "
                "RETURNING failed_login_attempts"
            ),
            {"now": datetime.now(UTC), "id": self.id},
        )
        new_count = result.scalar()

        # Sync Python-Object mit DB-State (statt refresh!)
        self.failed_login_attempts = new_count
        self.last_failed_login = datetime.now(UTC)

        # Nach 5 Fehlversuchen: 15 Minuten Sperre
        if new_count >= 5:
            lockout_time = datetime.now(UTC) + timedelta(minutes=15)
            session.execute(
                text("UPDATE users SET locked_until = :locked WHERE id = :id"),
                {"locked": lockout_time, "id": self.id},
            )
            self.locked_until = lockout_time

    def reset_failed_logins(self, session):
        """Erfolgreicher Login - Counter zurücksetzen (Thread-safe)

        Phase 9f: Atomic SQL-Update verhindert Race Conditions
        """
        from sqlalchemy import text

        # Atomic reset direkt in DB
        session.execute(
            text(
                "UPDATE users SET "
                "failed_login_attempts = 0, "
                "last_failed_login = NULL, "
                "locked_until = NULL "
                "WHERE id = :id"
            ),
            {"id": self.id},
        )

        # Sync Python-Object mit DB-State
        self.failed_login_attempts = 0
        self.last_failed_login = None
        self.locked_until = None

    def __repr__(self):
        # Security: Mask sensitive data in logs
        return f"<User(id={self.id}, username='***')>"


# =============================================================================
# USER DELETION CLEANUP: Personal Classifier Files löschen
# =============================================================================

def _cleanup_personal_classifiers_on_delete(mapper, connection, target):
    """SQLAlchemy Event: Löscht Personal-Classifier-Dateien wenn User gelöscht wird.
    
    Wird VOR dem DELETE ausgeführt (before_delete), damit CASCADE noch funktioniert.
    
    Args:
        mapper: SQLAlchemy Mapper (nicht verwendet)
        connection: DB-Connection (nicht verwendet)
        target: User-Objekt das gelöscht wird
    """
    import shutil
    from pathlib import Path
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Lazy Import um Circular Imports zu vermeiden
        from src.services.personal_classifier_service import (
            get_classifier_dir,
            invalidate_classifier_cache
        )
        
        user_dir = get_classifier_dir() / "per_user" / f"user_{target.id}"
        
        if user_dir.exists():
            shutil.rmtree(user_dir)
            logger.info(f"🗑️ Personal classifiers gelöscht: user_{target.id}")
        
        # Cache invalidieren (für alle Classifier-Typen dieses Users)
        deleted_count = invalidate_classifier_cache(user_id=target.id)
        if deleted_count > 0:
            logger.debug(f"💾 Cache invalidiert: {deleted_count} Einträge für user_{target.id}")
            
    except Exception as e:
        # Fehler beim Cleanup sollte User-Löschung nicht blockieren
        logger.warning(f"⚠️ Cleanup für user_{target.id} fehlgeschlagen (non-blocking): {e}")


# Event Listener registrieren (wird beim Import von 02_models.py ausgeführt)
event.listen(User, 'before_delete', _cleanup_personal_classifiers_on_delete)


class MailAccount(Base):
    """Mail-Account eines Benutzers (Phase 2 + Zero-Knowledge Phase)

    Unterstützt Multi-Auth:
    - auth_type="imap": Klassische IMAP/SMTP Authentifizierung
    - auth_type="oauth": OAuth 2.0 (Gmail, Outlook)

    Zero-Knowledge:
    - E-Mail-Adressen und Server werden verschlüsselt gespeichert
    - Hash-Felder ermöglichen Suche ohne Klartext-Zugriff

    Felder-Mapping:
    - IMAP: encrypted_imap_server, encrypted_imap_username, encrypted_imap_password
    - OAuth: oauth_provider, encrypted_oauth_token, encrypted_oauth_refresh_token
    """

    __tablename__ = "mail_accounts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Allgemeine Felder
    name = Column(String(100), nullable=False)
    auth_type = Column(String(20), default=AuthType.IMAP.value, nullable=False)

    # IMAP-spezifische Felder (verschlüsselt für Zero-Knowledge)
    encrypted_imap_server = Column(Text, nullable=True)  # verschlüsselt
    imap_server_hash = Column(String(64), nullable=True, index=True)  # für Suche
    imap_port = Column(Integer, default=993)
    encrypted_imap_username = Column(Text, nullable=True)  # verschlüsselt
    imap_username_hash = Column(String(64), nullable=True, index=True)  # für Suche
    encrypted_imap_password = Column(Text)
    imap_encryption = Column(String(50), default=IMAPEncryption.SSL.value)

    # SMTP-spezifische Felder (optional für Versand, verschlüsselt)
    encrypted_smtp_server = Column(Text)
    smtp_port = Column(Integer, default=587)
    encrypted_smtp_username = Column(Text)
    encrypted_smtp_password = Column(Text)
    smtp_encryption = Column(String(50), default=SMTPEncryption.STARTTLS.value)

    # OAuth-spezifische Felder (wenn auth_type="oauth")
    oauth_provider = Column(String(20))  # "google", "microsoft"
    encrypted_oauth_token = Column(Text)
    encrypted_oauth_refresh_token = Column(Text)
    oauth_expires_at = Column(DateTime)

    # DEPRECATED: POP3-Felder (kept for schema compatibility, not functional)
    # POP3 support was removed - IMAP-only architecture
    encrypted_pop3_server = Column(Text, nullable=True)
    pop3_port = Column(Integer, default=995)
    encrypted_pop3_username = Column(Text, nullable=True)
    encrypted_pop3_password = Column(Text)

    enabled = Column(Boolean, default=True)
    last_fetch_at = Column(DateTime)
    initial_sync_done = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # ===== PHASE 13C PART 6: ACCOUNT-SPECIFIC FETCH FILTERS =====
    fetch_since_date = Column(Date, nullable=True)  # Nur Mails ab diesem Datum
    fetch_unseen_only = Column(Boolean, default=False)  # Nur ungelesene
    fetch_include_folders = Column(Text, nullable=True)  # JSON: ["INBOX", "Work"]
    fetch_exclude_folders = Column(Text, nullable=True)  # JSON: ["Spam", "Trash"]
    
    # ===== PHASE 14A: UIDVALIDITY TRACKING =====
    folder_uidvalidity = Column(Text, nullable=True)  # JSON: {"INBOX": 1352540700, ...}

    # ===== PHASE 12: NICE-TO-HAVE (Server Metadata) =====
    detected_provider = Column(String(50), nullable=True)
    server_name = Column(String(255), nullable=True)
    server_version = Column(String(100), nullable=True)
    
    # ===== PHASE I.2: ACCOUNT-SPECIFIC SIGNATURES =====
    signature_enabled = Column(Boolean, default=False, nullable=True)
    encrypted_signature_text = Column(Text, nullable=True)  # verschlüsselt mit Master-Key (wie andere Account-Daten)

    # ===== PHASE X: ACCOUNT-LEVEL URGENCY BOOSTER =====
    urgency_booster_enabled = Column(Boolean, default=True, nullable=False)
    
    # ===== PHASE X: ACCOUNT-LEVEL AI ANALYSIS CONTROL =====
    enable_ai_analysis_on_fetch = Column(Boolean, default=True, nullable=False)
    
    # ===== SERVER SYNC TRACKING =====
    last_server_sync_at = Column(DateTime, nullable=True)  # Letzter vollständiger Server-Scan
    
    # ===== ANALYSIS MODES (HIERARCHICAL TOGGLES) =====
    # 1️⃣ Anonymisierung (unabhängig vom Analyse-Modus)
    anonymize_with_spacy = Column(Boolean, default=False, nullable=False)
    
    # 3️⃣ AI-Analyse auf anonyme Daten
    ai_analysis_anon_enabled = Column(Boolean, default=False, nullable=False)
    
    # 4️⃣ AI-Analyse auf Original-Daten (ersetzt enable_ai_analysis_on_fetch langfristig)
    ai_analysis_original_enabled = Column(Boolean, default=False, nullable=False)

    # Relationship
    user = relationship("User", back_populates="mail_accounts")
    raw_emails = relationship(
        "RawEmail", back_populates="mail_account", cascade="all, delete-orphan"
    )
    
    # spaCy Hybrid Pipeline Relationships
    spacy_vip_senders = relationship(
        "SpacyVIPSender", back_populates="account", cascade="all, delete-orphan"
    )
    spacy_keyword_sets = relationship(
        "SpacyKeywordSet", back_populates="account", cascade="all, delete-orphan"
    )
    spacy_scoring_config = relationship(
        "SpacyScoringConfig", back_populates="account", cascade="all, delete-orphan", uselist=False
    )
    spacy_user_domains = relationship(
        "SpacyUserDomain", back_populates="account", cascade="all, delete-orphan"
    )


    def get_uidvalidity(self, folder: str) -> Optional[int]:
        """Gibt gespeicherte UIDVALIDITY für Ordner zurück
        
        Args:
            folder: IMAP Ordner (z.B. 'INBOX', 'Gesendet')
            
        Returns:
            UIDVALIDITY Integer oder None
        """
        if not self.folder_uidvalidity:
            return None
        try:
            import json
            data = json.loads(self.folder_uidvalidity)
            return data.get(folder)
        except (json.JSONDecodeError, AttributeError):
            return None
    
    def set_uidvalidity(self, folder: str, value: int) -> None:
        """Speichert UIDVALIDITY für Ordner
        
        Args:
            folder: IMAP Ordner (z.B. 'INBOX', 'Gesendet')
            value: UIDVALIDITY Integer vom Server
        """
        import json
        data = json.loads(self.folder_uidvalidity or "{}")
        data[folder] = int(value)
        self.folder_uidvalidity = json.dumps(data)
    
    @property
    def effective_ai_mode(self) -> str:
        """
        Berechnet effektiven Analyse-Modus unter Berücksichtigung aller Toggles.
        
        WICHTIG: Anonymisierung (anonymize_with_spacy) ist UNABHÄNGIG vom Analyse-Modus!
        - Anonymisierung läuft parallel (erzeugt Tab-Content)
        - Booster nutzt IMMER Original-Daten (lokal = sicher, beste Ergebnisse)
        - Nur AI-Anon nutzt anonymisierte Daten (Datenschutz für Cloud-LLMs)
        
        Priorität (höchste zuerst):
        1. Urgency Booster (spaCy lokal auf Original-Daten)
        2. AI auf anonyme Daten (benötigt anonymize_with_spacy)
        3. AI auf Original-Daten
        4. Keine Analyse
        
        Returns:
            "none" | "spacy_booster" | "llm_original" | "llm_anon"
        """
        # Priorität 1: Urgency Booster (nutzt Original, unabhängig von Anonymisierung)
        if self.urgency_booster_enabled:
            return "spacy_booster"
        
        # Priorität 2: AI auf anonyme Daten
        if self.ai_analysis_anon_enabled and self.anonymize_with_spacy:
            return "llm_anon"
        
        # Priorität 3: AI auf Original
        if self.ai_analysis_original_enabled:
            return "llm_original"
        
        # Priorität 4 (Legacy-Support): enable_ai_analysis_on_fetch
        if self.enable_ai_analysis_on_fetch:
            return "llm_original"
        
        # Fallback: Keine Analyse
        return "none"
    
    def validate_auth_fields(self) -> tuple[bool, str]:
        """Validiert ob die richtigen Felder für auth_type gesetzt sind

        Returns:
            (valid: bool, error_message: str)
        """
        if self.auth_type == AuthType.IMAP.value:
            if not all(
                [
                    self.encrypted_imap_server,
                    self.encrypted_imap_username,
                    self.encrypted_imap_password,
                ]
            ):
                return False, "IMAP requires: server, username, password"

        elif self.auth_type == AuthType.OAUTH.value:
            if not all([self.oauth_provider, self.encrypted_oauth_token]):
                return False, "OAuth requires: provider, token"

        return True, ""

    def __repr__(self):
        return f"<MailAccount(id={self.id}, user={self.user_id}, name='{self.name}', auth={self.auth_type})>"


class ServiceToken(Base):
    """
    Sichere Token-Verwaltung für Background-Jobs ohne längerer RAM-Speicher (Phase 2).
    
    Sicherheitsmodell:
    - Token wird mit 384-bit Entropie generiert (secrets.token_urlsafe)
    - token_hash wird bcrypt-gehasht (nicht reversible)
    - encrypted_dek wird nur gespeichert während Token valid ist
    - Nach Expiry wird DEK automatisch gelöscht
    
    Workflow:
    1. enqueue_fetch_job(): Erstellt ServiceToken, speichert encrypted_dek
    2. Job in Queue: speichert nur service_token_id (Integer)
    3. Worker: lädt Token, verifiziert gegen token_hash, holt DEK
    4. RAM-Cleanup: DEK mit Overwrites bereinigt nach Job
    
    Sicherheit vs. Alternativen:
    ✅ Token: RCE attacker kann Token + encrypted_dek lesen, aber token ist gehasht
    ✅ DEK: Nur valid wenn token_hash matched, nicht reversible
    ✅ Audit: last_verified_at logged Token-Verwendung
    ✅ TTL: Automatisches Expiry nach 7 Tagen (konfigurierbar)
    """

    __tablename__ = "service_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    token_hash = Column(String(255), unique=True, nullable=False)
    encrypted_dek = Column(Text, nullable=False)  # DEK für Email-Decryption
    expires_at = Column(DateTime, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    last_verified_at = Column(DateTime, nullable=True)

    # Relationship
    user = relationship("User", back_populates="service_tokens")

    @staticmethod
    def generate_token() -> str:
        """Generiert einen neuen Token mit 384 Bit Entropie (Phase 9: Security Hardening)"""
        return secrets.token_urlsafe(48)  # 48 bytes = 384 bit

    @staticmethod
    def hash_token(token: str) -> str:
        """Hasht einen Token"""
        return generate_password_hash(token)

    @staticmethod
    def verify_token(token: str, token_hash: str) -> bool:
        """Überprüft einen Token"""
        return check_password_hash(token_hash, token)

    def is_valid(self) -> bool:
        """Überprüft ob Token noch gültig ist"""
        # Handle both timezone-aware and naive datetimes (migration compatibility)
        now = datetime.now(UTC)
        expires = self.expires_at
        
        # If expires_at is naive, make it aware (assume UTC)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        
        return now < expires
    
    def mark_verified(self) -> None:
        """Markiert Token als gerade verwendet (für Audit-Logs)"""
        self.last_verified_at = datetime.now(UTC)

    def __repr__(self):
        return f"<ServiceToken(id={self.id}, user={self.user_id}, expires={self.expires_at.strftime('%Y-%m-%d %H:%M')})>"


class RecoveryCode(Base):
    """Recovery-Codes für Passwort-Reset (Phase 3)"""

    __tablename__ = "recovery_codes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    code_hash = Column(String(255), unique=True, nullable=False)
    used_at = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationship
    user = relationship("User", back_populates="recovery_codes")

    @staticmethod
    def generate_code() -> str:
        """Generiert einen Recovery-Code"""
        return secrets.token_hex(4).upper()

    @staticmethod
    def hash_code(code: str) -> str:
        """Hasht einen Code"""
        return generate_password_hash(code)

    @staticmethod
    def verify_code(code: str, code_hash: str) -> bool:
        """Überprüft einen Code"""
        return check_password_hash(code_hash, code)

    def is_unused(self) -> bool:
        """Überprüft ob Code noch nicht verwendet wurde"""
        return self.used_at is None

    def mark_used(self):
        """Markiert Code als verwendet"""
        self.used_at = datetime.now(UTC)

    def __repr__(self):
        return f"<RecoveryCode(id={self.id}, user={self.user_id}, used={'yes' if self.used_at else 'no'})>"


class MailServerState(Base):
    """Server-Zustand für ALLE Mails (auch nicht-gefetchte)
    
    Diese Tabelle hält den kompletten Zustand des Mail-Servers:
    - Ermöglicht Move-Detection (gleiche message_id, anderer folder)
    - Ermöglicht Delete-Detection (war in Tabelle, nicht mehr auf Server)
    - Ermöglicht echtes Delta (was wurde gefetcht vs. was existiert)
    
    Sync-Flow:
    1. SCAN SERVER → Alle ENVELOPEs holen → Hier speichern
    2. VERGLEICH → message_id/content_hash gegen bestehende Einträge
    3. DELTA-FETCH → Nur Mails mit raw_email_id IS NULL
    """
    __tablename__ = "mail_server_state"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    mail_account_id = Column(Integer, ForeignKey("mail_accounts.id"), nullable=False)
    
    # Server-Identifikation (ändert sich bei MOVE)
    folder = Column(Text, nullable=False)
    uid = Column(Integer, nullable=False)
    uidvalidity = Column(Integer, nullable=False)
    
    # Stabiler Identifier (bleibt bei MOVE gleich)
    message_id = Column(Text, nullable=True)  # Message-ID Header (kann NULL sein)
    content_hash = Column(Text, nullable=False)  # SHA256(date + from + subject)
    
    # Server-Metadaten (aus ENVELOPE, ohne Body zu laden)
    envelope_from = Column(Text, nullable=True)  # Absender (für Display ohne Fetch)
    envelope_subject = Column(Text, nullable=True)  # Betreff (für Display ohne Fetch)
    envelope_date = Column(DateTime, nullable=True)  # Datum
    flags = Column(Text, nullable=True)  # IMAP Flags als String
    
    # Referenz zu gefetchter Mail (NULL = noch nicht gefetcht)
    raw_email_id = Column(Integer, ForeignKey("raw_emails.id"), nullable=True)
    
    # Status
    is_deleted = Column(Boolean, default=False)  # Auf Server gelöscht
    
    # Timestamps
    first_seen_at = Column(DateTime, default=lambda: datetime.now(UTC))
    last_seen_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # Unique constraint: Ein UID pro Folder/UIDVALIDITY
    __table_args__ = (
        UniqueConstraint('user_id', 'mail_account_id', 'folder', 'uid', 'uidvalidity', 
                        name='uq_server_state_folder_uid'),
        Index('idx_server_state_hash', 'user_id', 'mail_account_id', 'content_hash'),
        Index('idx_server_state_msgid', 'user_id', 'mail_account_id', 'message_id'),
        Index('idx_server_state_not_fetched', 'user_id', 'mail_account_id', 'raw_email_id'),
    )
    
    # Relationships
    user = relationship("User", backref="mail_server_states")
    mail_account = relationship("MailAccount", backref="server_states")
    raw_email = relationship("RawEmail", backref="server_state")
    
    def __repr__(self):
        fetched = "✅" if self.raw_email_id else "❌"
        return f"<MailServerState({self.folder}/{self.uid} {fetched})>"


class RawEmail(Base):
    """Rohdaten der abgeholten E-Mails (Zero-Knowledge verschlüsselt)

    Alle persönlichen Daten (sender, subject, body) werden verschlüsselt gespeichert.
    """

    __tablename__ = "raw_emails"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mail_account_id = Column(
        Integer, ForeignKey("mail_accounts.id"), nullable=False, index=True
    )

    # Zero-Knowledge: Verschlüsselte persönliche Daten
    encrypted_sender = Column(Text, nullable=False)
    encrypted_subject = Column(Text)
    encrypted_body = Column(Text)

    received_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    # P1-002: deleted_verm entfernt - nur deleted_at nutzen
    deleted_at = Column(DateTime, nullable=True)

    # ===== PHASE 14A: RFC-KONFORMER KEY (folder, uidvalidity, uid) =====
    imap_uid = Column(Integer, nullable=True, index=True)  # Phase 14a: String → Integer
    imap_folder = Column(String(200), nullable=False, default='INBOX')  # Phase 14a: NOT NULL
    imap_uidvalidity = Column(Integer, nullable=True, index=True)  # Phase 14a: RFC 3501
    imap_flags = Column(String(500), nullable=True)
    imap_last_seen_at = Column(DateTime, nullable=True)

    # ===== PHASE 12: MUST-HAVE (Threading & Query Optimization) =====
    message_id = Column(String(512), nullable=True, index=True)  # 512 für Teams/Outlook lange IDs
    encrypted_in_reply_to = Column(Text, nullable=True)
    
    # BUG-003: parent_uid ist String (IMAP-UID), nicht ForeignKey
    # CAVEAT: UID ist nur eindeutig pro (user_id, mail_account_id, imap_folder)
    # TODO Phase 12b: Migriere zu parent_id (ForeignKey) für effiziente Joins
    parent_uid = Column(String(255), nullable=True, index=True)
    thread_id = Column(String(36), nullable=True, index=True)

    # Boolean Flags (replace imap_flags string, 200-300% faster queries)
    # Prefix 'imap_' used to distinguish from 'deleted_at' property
    imap_is_seen = Column(Boolean, default=False, nullable=True, index=True)
    imap_is_answered = Column(Boolean, default=False, nullable=True, index=True)
    imap_is_flagged = Column(Boolean, default=False, nullable=True, index=True)
    imap_is_deleted = Column(Boolean, default=False, nullable=True)
    imap_is_draft = Column(Boolean, default=False, nullable=True)

    # ===== PHASE 12: SHOULD-HAVE (Extended Envelope Data) =====
    encrypted_to = Column(Text, nullable=True)
    encrypted_cc = Column(Text, nullable=True)
    encrypted_bcc = Column(Text, nullable=True)
    encrypted_reply_to = Column(Text, nullable=True)

    message_size = Column(Integer, nullable=True)
    encrypted_references = Column(Text, nullable=True)

    # ===== PHASE 12: NICE-TO-HAVE (Content Info & Audit) =====
    content_type = Column(String(100), nullable=True)
    charset = Column(String(50), nullable=True)
    has_attachments = Column(Boolean, default=False, nullable=True)
    last_flag_sync_at = Column(DateTime, nullable=True)

    # ===== PHASE 17: SEMANTIC SEARCH =====
    # Embedding für semantische Suche (NICHT verschlüsselt!)
    # Embeddings sind nicht zu Klartext reversibel → Zero-Knowledge OK
    # 384 floats × 4 bytes = 1536 bytes pro Email (all-minilm:22m)
    email_embedding = Column(LargeBinary, nullable=True)
    embedding_model = Column(String(50), nullable=True)  # "all-minilm:22m"
    embedding_generated_at = Column(DateTime, nullable=True)

    # ===== PHASE G.2: AUTO-ACTION RULES =====
    # Flag ob Email bereits durch Auto-Rules verarbeitet wurde
    # Verhindert mehrfache Verarbeitung bei Background-Jobs
    auto_rules_processed = Column(Boolean, default=False, nullable=False, index=True)

    # ===== PHASE 22: SANITIZATION (ANONYMISIERUNG) =====
    # Pseudonymisierte Versionen (verschlüsselt wie Original)
    encrypted_subject_sanitized = Column(Text, nullable=True)
    encrypted_body_sanitized = Column(Text, nullable=True)
    
    # Sanitization Metadata
    sanitization_level = Column(Integer, nullable=True)  # 1=Regex, 2=spaCy-Light, 3=spaCy-Full
    sanitization_time_ms = Column(Float, nullable=True)
    sanitization_entities_count = Column(Integer, nullable=True)
    
    # EntityMap für De-Anonymisierung (verschlüsseltes JSON)
    encrypted_entity_map = Column(Text, nullable=True)

    # ===== INLINE ATTACHMENTS (CID-Bilder) =====
    # Verschlüsseltes JSON: {"cid1": {"mime_type": "image/png", "data": "base64..."}, ...}
    # Ermöglicht Anzeige von Inline-Bildern ohne externe Requests
    encrypted_inline_attachments = Column(Text, nullable=True)

    # ===== PHASE 24: STABLE IDENTIFIER (für Move-Detection) =====
    # stable_identifier = message_id wenn vorhanden, sonst "hash:<content_hash>"
    # Ermöglicht Move-Detection auch für Mails ohne message_id
    stable_identifier = Column(String(512), nullable=True, index=True)
    content_hash = Column(String(64), nullable=True, index=True)  # SHA256[:32]

    # ===== PHASE 25: CALENDAR INVITES =====
    # Erkennung von Termineinladungen (text/calendar MIME Part)
    is_calendar_invite = Column(Boolean, default=False, nullable=True, index=True)
    # REQUEST=Einladung, REPLY=Antwort, CANCEL=Absage (unverschlüsselt für Filter/Anzeige)
    calendar_method = Column(String(20), nullable=True)
    # JSON mit Event-Details: {method, uid, summary, dtstart, dtend, location, organizer, attendees[], status}
    encrypted_calendar_data = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="raw_emails")
    mail_account = relationship("MailAccount", back_populates="raw_emails")
    processed = relationship(
        "ProcessedEmail", back_populates="raw_email", uselist=False
    )
    attachments = relationship(
        "EmailAttachment", back_populates="raw_email", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Phase 14a: RFC-konformer Unique Key (RFC 3501 / RFC 9051)
        # "The combination of mailbox name, UIDVALIDITY, and UID must refer to
        #  a single, immutable message on that server forever."
        # EINDEUTIGER KEY: (user_id, account_id, folder, uidvalidity, uid)
        UniqueConstraint(
            "user_id", "mail_account_id", "imap_folder", "imap_uidvalidity", "imap_uid",
            name="uq_raw_emails_rfc_unique"
        ),
        # Performance-Index für Lookups
        Index(
            "ix_raw_emails_account_folder_uid",
            "mail_account_id", "imap_folder", "imap_uid"
        ),
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def has_sanitized_content(self) -> bool:
        """True wenn pseudonymisierte Version existiert"""
        return self.encrypted_subject_sanitized is not None or self.encrypted_body_sanitized is not None

    def __repr__(self):
        return f"<RawEmail(id={self.id}, user={self.user_id}, imap_uid={self.imap_uid})>"


class EmailAttachment(Base):
    """Klassische E-Mail-Anhänge (PDF, Word, Excel, Bilder, etc.)
    
    Speichert Anhänge verschlüsselt in der DB (Zero-Knowledge).
    Für große Dateien (>25MB) kann optional S3 verwendet werden.
    """
    
    __tablename__ = "email_attachments"
    
    id = Column(Integer, primary_key=True)
    raw_email_id = Column(Integer, ForeignKey("raw_emails.id", ondelete="CASCADE"), nullable=False)
    
    # Datei-Metadaten (unverschlüsselt für Suche/Anzeige)
    filename = Column(String(255), nullable=False)  # "rechnung.pdf"
    mime_type = Column(String(100), nullable=False)  # "application/pdf"
    size = Column(Integer, nullable=False)  # Bytes (unverschlüsselte Größe)
    content_id = Column(String(255), nullable=True)  # Falls inline (cid:...)
    
    # Verschlüsselter Inhalt (base64)
    encrypted_data = Column(Text, nullable=True)  # Für Dateien < 25MB
    
    # Optional: S3 für große Dateien
    s3_bucket = Column(String(100), nullable=True)
    s3_key = Column(String(512), nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # Relationship
    raw_email = relationship("RawEmail", back_populates="attachments")
    
    __table_args__ = (
        Index("ix_email_attachments_raw_email_id", "raw_email_id"),
    )
    
    @property
    def size_human(self) -> str:
        """Menschenlesbare Dateigröße"""
        if self.size < 1024:
            return f"{self.size} B"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} KB"
        else:
            return f"{self.size / (1024 * 1024):.1f} MB"
    
    @property
    def is_inline(self) -> bool:
        """True wenn Inline-Attachment (CID-Bild)"""
        return self.content_id is not None
    
    def __repr__(self):
        return f"<EmailAttachment(id={self.id}, filename={self.filename}, size={self.size_human})>"


class ProcessedEmail(Base):
    """Von der KI verarbeitete E-Mails mit Scoring"""

    __tablename__ = "processed_emails"

    id = Column(Integer, primary_key=True)
    raw_email_id = Column(
        Integer,
        ForeignKey("raw_emails.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # KI-Ergebnisse
    dringlichkeit = Column(Integer)
    wichtigkeit = Column(Integer)
    kategorie_aktion = Column(
        String(50), default=EmailActionCategory.ACTION_REQUIRED.value
    )
    spam_flag = Column(Boolean, default=False)

    # Zero-Knowledge: Verschlüsselte KI-Texte
    encrypted_summary_de = Column(Text)
    encrypted_text_de = Column(Text)
    encrypted_tags = Column(Text)
    encrypted_correction_note = Column(Text, nullable=True)

    # Scoring
    score = Column(Integer)
    matrix_x = Column(Integer)
    matrix_y = Column(Integer)
    farbe = Column(String(10), default=EmailColor.BLUE.value)

    # Status und Audit
    done = Column(Boolean, default=False)
    done_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, default=lambda: datetime.now(UTC))
    rebase_at = Column(DateTime, nullable=True)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    deleted_at = Column(DateTime, nullable=True)
    # P1-002: deleted_verm entfernt - nur deleted_at nutzen

    # Optimization (zweiter Pass für bessere Kategorisierung)
    optimization_status = Column(String(20), default=OptimizationStatus.PENDING.value)
    optimization_tried_at = Column(DateTime, nullable=True)
    optimization_completed_at = Column(DateTime, nullable=True)
    base_provider = Column(String(50), nullable=True)
    base_model = Column(String(100), nullable=True)
    optimize_provider = Column(String(50), nullable=True)
    optimize_model = Column(String(100), nullable=True)
    
    # ===== ANALYSIS METHOD TRACKING =====
    analysis_method = Column(String(50), nullable=True)
    # Werte: "none" | "spacy_booster" | "hybrid_booster" | "llm:ollama" | "llm:openai" | etc.
    
    # ===== AI CONFIDENCE TRACKING =====
    ai_confidence = Column(Float, nullable=True)
    # Konfidenz der AI-Analyse (0.0-1.0), z.B. 0.65-0.9 basierend auf Ensemble-Stats
    # NULL = keine Confidence verfügbar (alte Daten oder analysis_method='none')

    # Optimize-Pass Ergebnisse (separate Felder, überschreiben nicht die Initial-Analyse)
    optimize_dringlichkeit = Column(Integer, nullable=True)
    optimize_wichtigkeit = Column(Integer, nullable=True)
    optimize_kategorie_aktion = Column(String(50), nullable=True)
    optimize_spam_flag = Column(Boolean, nullable=True)
    optimize_encrypted_summary_de = Column(Text, nullable=True)
    optimize_encrypted_text_de = Column(Text, nullable=True)
    optimize_encrypted_tags = Column(Text, nullable=True)
    optimize_score = Column(Integer, nullable=True)
    optimize_matrix_x = Column(Integer, nullable=True)
    optimize_matrix_y = Column(Integer, nullable=True)
    optimize_farbe = Column(String(10), nullable=True)
    
    # ===== OPTIMIZE CONFIDENCE TRACKING =====
    optimize_confidence = Column(Float, nullable=True)
    # Konfidenz der Optimize-Pass Analyse (0.0-1.0)
    # NULL = keine Confidence verfügbar (alte Daten oder Standard-LLM ohne Confidence)

    # User-Korrektionen für ML-Training (Phase 8)
    # Diese Spalten speichern Nutzer-Feedback zur manuellen Korrektur von AI-Ergebnissen
    # Dienen als Trainingsdaten für die sklearn-Klassifikatoren (train_classifier.py)
    user_override_dringlichkeit = Column(
        Integer, nullable=True
    )  # Korrigierte Dringlichkeit (1-3)
    user_override_wichtigkeit = Column(
        Integer, nullable=True
    )  # Korrigierte Wichtigkeit (1-3)
    user_override_kategorie = Column(String(50), nullable=True)  # Korrigierte Kategorie
    user_override_spam_flag = Column(Boolean, nullable=True)  # Korrigiertes Spam-Flag
    user_override_tags = Column(
        String(500), nullable=True
    )  # Korrigierte Tags (Klartext für Suche)
    correction_timestamp = Column(DateTime, nullable=True)  # Zeitpunkt der Korrektur

    imap_flags_at_processing = Column(String(500), nullable=True)
    was_seen_at_processing = Column(Boolean, nullable=True)
    was_answered_at_processing = Column(Boolean, nullable=True)

    # Hybrid Score-Learning: Welches Modell wurde für Prediction genutzt?
    used_model_source = Column(String(20), default='global', nullable=False)
    """'global' = Globales Modell, 'personal' = Per-User Modell"""

    # Relationships
    raw_email = relationship("RawEmail", back_populates="processed")
    tag_assignments = relationship(
        "EmailTagAssignment", back_populates="email", cascade="all, delete-orphan"
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __repr__(self):
        return f"<ProcessedEmail(id={self.id}, raw_email_id={self.raw_email_id}, score={self.score})>"


class EmailFolder(Base):
    """IMAP-Ordnerstruktur für einen Mail-Account"""

    __tablename__ = "email_folders"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mail_account_id = Column(
        Integer,
        ForeignKey("mail_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(255), nullable=False)
    imap_path = Column(String(500), nullable=False)
    unread_count = Column(Integer, default=0)
    total_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # ===== PHASE 12: NICE-TO-HAVE (Folder Classification) =====
    is_special_folder = Column(Boolean, default=False, nullable=True)
    special_folder_type = Column(String(50), nullable=True)
    display_name_localized = Column(String(255), nullable=True)

    # Relationships
    user = relationship("User")
    mail_account = relationship("MailAccount")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "mail_account_id", "imap_path", name="uq_email_folders_path"
        ),
    )

    def __repr__(self):
        return f"<EmailFolder(id={self.id}, account={self.mail_account_id}, name='{self.name}')>"


class ReplyStyleSettings(Base):
    """Benutzerdefinierte Einstellungen für Antwort-Stile (Feature Reply Styles)
    
    Hybrid-Ansatz:
    - style_key = "global" → Wirkt auf alle Stile
    - style_key = "formal|friendly|brief|decline" → Überschreibt Global für diesen Stil
    
    Verschlüsselte Felder:
    - signature_text → encrypted_signature_text (Zero-Knowledge)
    - custom_instructions → encrypted_custom_instructions (Zero-Knowledge)
    """
    
    __tablename__ = "reply_style_settings"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Welcher Stil? "global" oder "formal", "friendly", "brief", "decline"
    style_key = Column(String(20), nullable=False, default="global")
    
    # Anrede-Einstellungen (Klartext, nicht sensibel)
    address_form = Column(String(10), nullable=True)  # "du", "sie", "auto"
    salutation = Column(String(100), nullable=True)   # z.B. "Liebe/r", "Sehr geehrte/r", "Hallo"
    
    # Gruss-Einstellungen (Klartext, nicht sensibel)
    closing = Column(String(100), nullable=True)      # z.B. "Beste Grüsse", "Mit freundlichen Grüssen"
    
    # Signatur (verschlüsselt)
    signature_enabled = Column(Boolean, default=False)
    encrypted_signature_text = Column(Text, nullable=True)  # Verschlüsselt (z.B. "Mike" oder "Mike\nFirma GmbH")
    
    # Zusätzliche Anweisungen für KI (verschlüsselt)
    encrypted_custom_instructions = Column(Text, nullable=True)  # Freitext für KI
    
    # Metadaten
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    # Relationships
    user = relationship("User", back_populates="reply_style_settings")
    
    # Constraints: Ein Setting pro User pro Style
    __table_args__ = (
        UniqueConstraint("user_id", "style_key", name="uq_user_style_key"),
        Index("ix_reply_style_user_id", "user_id"),
    )


class AutoRule(Base):
    """
    Auto-Action Rules für automatische E-Mail-Verarbeitung (Phase G.2)
    
    Ermöglicht Regeln wie:
    - "Alle Newsletter von X → Archiv-Ordner"
    - "Absender Y → Als gelesen + wichtig"
    - "Betreff enthält [SPAM] → Papierkorb"
    
    Beispiel-Regel:
    {
        "name": "Newsletter archivieren",
        "conditions": {
            "match_mode": "any",
            "sender_contains": "newsletter",
            "body_contains": "unsubscribe"
        },
        "actions": {
            "move_to_folder": "Archive",
            "mark_as_read": true,
            "apply_tag": "Newsletter"
        }
    }
    """
    __tablename__ = 'auto_rules'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Regel-Metadaten
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    priority = Column(Integer, default=100, nullable=False, index=True)  # Niedrigere = höhere Priorität
    
    # Bedingungen (JSON)
    # Mögliche Keys:
    # - match_mode: "all" (AND) oder "any" (OR)
    # - sender_equals: "exact@match.com"
    # - sender_contains: "newsletter"
    # - sender_domain: "marketing.com"
    # - subject_contains: "Newsletter"
    # - subject_regex: "\\[SPAM\\].*"
    # - has_attachment: true/false
    # - body_contains: "unsubscribe"
    conditions_json = Column(Text, nullable=False, default='{}')
    
    # Aktionen (JSON)
    # Mögliche Keys:
    # - move_to_folder: "Spam"
    # - mark_as_read: true
    # - mark_as_flagged: true
    # - apply_tag: "Newsletter"
    # - set_priority: "low"
    # - delete: true (VORSICHT!)
    # - stop_processing: false (stoppt weitere Regeln falls true)
    actions_json = Column(Text, nullable=False, default='{}')
    
    # Learning-Einstellung
    # Wenn True: Tag-Zuweisungen durch diese Regel werden als Lernbeispiele verwendet
    # Default: False (sicher, keine Verschmutzung des Tag-Learnings)
    enable_learning = Column(Boolean, default=False, nullable=False)
    
    # Statistiken
    times_triggered = Column(Integer, default=0, nullable=False)
    last_triggered_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
    
    # Relationships
    user = relationship('User', backref='auto_rules')
    
    @property
    def conditions(self) -> dict:
        """Gibt Bedingungen als dict zurück"""
        import json
        return json.loads(self.conditions_json) if self.conditions_json else {}
    
    @conditions.setter
    def conditions(self, value: dict):
        """Setzt Bedingungen aus dict"""
        import json
        self.conditions_json = json.dumps(value)
    
    @property
    def actions(self) -> dict:
        """Gibt Aktionen als dict zurück"""
        import json
        return json.loads(self.actions_json) if self.actions_json else {}
    
    @actions.setter
    def actions(self, value: dict):
        """Setzt Aktionen aus dict"""
        import json
        self.actions_json = json.dumps(value)
    
    def __repr__(self):
        return f'<AutoRule {self.id}: {self.name} (active={self.is_active})>'


# DB-Setup
def init_db(db_path="emails.db"):
    """Initialisiert die Datenbank"""
    if db_path == ":memory:":
        engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

    if engine.url.drivername.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            """Set SQLite pragmas for production use.

            - foreign_keys: Enable FK constraints (Phase 4)
            - journal_mode=WAL: Write-Ahead Logging für concurrent reads (Phase 9d)
            - busy_timeout: Retry statt sofort fail bei Lock-Conflicts (Phase 9d)
            - wal_autocheckpoint: Verhindert unbegrenzte .wal File-Größe

            Impact: Löst SQLite Deadlocks bei Multi-Worker + Background-Jobs
            """
            cursor = dbapi_conn.cursor()

            # Phase 4: Foreign Key Enforcement
            cursor.execute("PRAGMA foreign_keys=ON")

            # Phase 9d: WAL Mode für Multi-Worker Concurrency
            # Erlaubt parallele Reads während Write läuft (Writer blockiert Reader nicht!)
            cursor.execute("PRAGMA journal_mode=WAL")

            # Phase 9e: Synchronous NORMAL (balanced für WAL - schützt vor Datenverlust)
            # WICHTIG: NACH journal_mode setzen (WAL ändert default auf FULL)
            # FULL = jeder Commit fsync (langsam), NORMAL = nur Checkpoint fsync (optimal)
            cursor.execute("PRAGMA synchronous = NORMAL")

            # Phase 9d: Retry statt sofort fail bei SQLITE_BUSY
            # 5 Sekunden reichen (WAL reduziert Lock-Zeit drastisch)
            cursor.execute("PRAGMA busy_timeout = 5000")

            # Phase 9d: WAL Checkpoint (verhindert unbegrenzte .wal File-Größe)
            # Checkpoint alle 1000 Pages (~4MB)
            cursor.execute("PRAGMA wal_autocheckpoint = 1000")

            cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


class InvitedEmail(Base):
    """
    Phase INV: Email-Whitelist für Registration
    Nur eingetragene Email-Adressen dürfen sich registrieren (nach dem ersten User)
    """
    __tablename__ = "invited_emails"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    invited_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    invited_by = Column(String(255), nullable=True)  # CLI-Username oder "admin"
    used = Column(Boolean, default=False)  # Wurde die Einladung bereits genutzt?
    used_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<InvitedEmail {self.email} (used={self.used})>"


class TrustedSender(Base):
    """
    User-definierte vertrauenswürdige Absender (Phase X).
    
    Nur für Emails von diesen Sendern wird UrgencyBooster (spaCy) verwendet.
    Pattern wird normalisiert (lowercase) beim Speichern.
    
    Supports both user-level (global) and account-level (per-IMAP-account) whitelisting:
    - account_id = NULL: Global für alle Accounts des Users
    - account_id != NULL: Nur für dieses spezifische Account
    
    Pattern-Typen:
    - exact: Exakte Email-Adresse (chef@firma.de)
    - email_domain: Alle von Email-Domain (@firma.de)
    - domain: Alle von Domain (firma.de)
    """
    __tablename__ = "trusted_senders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=True)
    """Optional: Specific IMAP account. NULL = global for all accounts"""
    
    sender_pattern = Column(String(255), nullable=False)
    """Pattern: "chef@firma.de", "@firma.de", oder "firma.de" - normalisiert zu lowercase"""
    
    pattern_type = Column(String(20), nullable=False)
    """Pattern-Typ: 'exact', 'email_domain', oder 'domain'"""
    
    label = Column(String(100), nullable=True)
    """Optionales Label für UI: "Chef", "Kollegen", "Buchhaltung" """
    
    use_urgency_booster = Column(Boolean, default=True, nullable=False)
    """User kann spaCy pro Sender aktivieren/deaktivieren"""
    
    added_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    email_count = Column(Integer, default=0, nullable=False)
    """Wie viele Emails von diesem Sender wurden gesehen?"""
    
    # Relationships
    user = relationship("User", back_populates="trusted_senders")
    mail_account = relationship("MailAccount", foreign_keys=[account_id])
    
    __table_args__ = (
        UniqueConstraint('user_id', 'sender_pattern', name='uq_user_sender'),
    )
    
    def __init__(self, **kwargs):
        # Normalisiere Pattern beim Erstellen
        if 'sender_pattern' in kwargs:
            kwargs['sender_pattern'] = kwargs['sender_pattern'].lower().strip()
        super().__init__(**kwargs)
    
    def __repr__(self):
        return f"<TrustedSender(id={self.id}, pattern={self.sender_pattern}, type={self.pattern_type})>"


# ========================== SPACY HYBRID PIPELINE ==========================


class SpacyVIPSender(Base):
    """
    VIP-Absender für Hybrid Pipeline.
    Bestimmte Absender erhalten automatisch einen Wichtigkeits-Boost.
    
    Beispiele:
    - Chef-Email → importance_boost=+5
    - Vorstandsassistenz → importance_boost=+4
    - Team Lead → importance_boost=+2
    """
    __tablename__ = "spacy_vip_senders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=True)  # NULL = global für User
    sender_pattern = Column(String(255), nullable=False)  # email oder domain
    pattern_type = Column(String(20), nullable=False)  # "exact", "email_domain", "domain"
    
    # VIP-Konfiguration
    label = Column(String(100), nullable=True)  # "Chef", "CEO", "Wichtiger Kunde"
    importance_boost = Column(Integer, nullable=False, default=3)  # +1 bis +5
    urgency_boost = Column(Integer, nullable=False, default=0)  # Optional: Urgency-Boost
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="spacy_vip_senders")
    account = relationship("MailAccount", back_populates="spacy_vip_senders")

    __table_args__ = (
        Index("ix_spacy_vip_user_account", "user_id", "account_id"),
        UniqueConstraint("user_id", "sender_pattern", "account_id", name="uq_vip_user_pattern_account"),
    )

    def __repr__(self):
        return f"<SpacyVIPSender(pattern={self.sender_pattern}, boost=+{self.importance_boost})>"


class SpacyKeywordSet(Base):
    """
    Konfigurierbare Keyword-Sets für Hybrid Pipeline.
    Pro Account werden 12 Keyword-Sets gespeichert (als JSON).
    
    JSON-Format:
    {
        "imperative_verbs": ["prüfen", "freigeben", "bestätigen", ...],
        "urgency_time": ["heute", "morgen", "asap", ...],
        ...
    }
    """
    __tablename__ = "spacy_keyword_sets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=True)
    set_type = Column(String(50), nullable=False)  # 'urgency_high', 'urgency_low', etc.
    keywords_json = Column(Text, nullable=False)  # JSON-Array mit Keywords
    points_per_match = Column(Integer, nullable=False, default=2)
    max_points = Column(Integer, nullable=False, default=4)
    is_active = Column(Boolean, nullable=False, default=True)
    is_custom = Column(Boolean, nullable=False, default=False)  # TRUE = User-definiert
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="spacy_keyword_sets")
    account = relationship("MailAccount", back_populates="spacy_keyword_sets")

    __table_args__ = (
        Index("ix_spacy_keywords_user_account", "user_id", "account_id", "set_type"),
        UniqueConstraint("user_id", "account_id", "set_type", name="uq_keywords_user_account_type"),
    )

    def __repr__(self):
        return f"<SpacyKeywordSet(account={self.account_id}, set={self.set_type})>"


class SpacyScoringConfig(Base):
    """
    Scoring-Konfiguration für Hybrid Pipeline.
    Thresholds und Gewichte sind pro Account anpassbar.
    
    Beispiel:
    - imperative_weight=3 (Imperative sind wichtig)
    - deadline_weight=4 (Deadlines sind sehr wichtig)
    - question_threshold=0.3 (ab 30% Fragewörter → Niedriger Urgency)
    """
    __tablename__ = "spacy_scoring_config"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False)
    
    # Gewichte für verschiedene Detektoren
    imperative_weight = Column(Integer, nullable=False, default=3)
    deadline_weight = Column(Integer, nullable=False, default=4)
    keyword_weight = Column(Integer, nullable=False, default=2)
    vip_weight = Column(Integer, nullable=False, default=3)
    
    # Thresholds
    question_threshold = Column(Integer, nullable=False, default=3)  # Min. Anzahl Fragewörter
    negation_sensitivity = Column(Integer, nullable=False, default=2)  # Stärke der Negation
    
    # Ensemble-Gewichte (dynamisch basierend auf Anzahl Korrekturen)
    spacy_weight_initial = Column(Integer, nullable=False, default=100)  # <20 Korrekturen
    spacy_weight_learning = Column(Integer, nullable=False, default=30)  # 20-50 Korrekturen
    spacy_weight_trained = Column(Integer, nullable=False, default=15)   # 50+ Korrekturen
    
    last_modified = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="spacy_scoring_configs")
    account = relationship("MailAccount", back_populates="spacy_scoring_config")

    __table_args__ = (
        Index("idx_spacy_config_account", "account_id"),
        UniqueConstraint("user_id", "account_id", name="uq_scoring_user_account"),
    )

    def __repr__(self):
        return f"<SpacyScoringConfig(account={self.account_id})>"


class SpacyUserDomain(Base):
    """
    User-Domains für Hybrid Pipeline.
    Ermöglicht Erkennung von intern/extern bei Emails.
    
    Beispiele:
    - "example.com" → Interne Mails
    - "subsidiary.de" → Tochterunternehmen (auch intern)
    
    Externe Mails von Kunden/Partnern erhalten höhere Urgency.
    """
    __tablename__ = "spacy_user_domains"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("mail_accounts.id"), nullable=False)
    domain = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    user = relationship("User", back_populates="spacy_user_domains")
    account = relationship("MailAccount", back_populates="spacy_user_domains")

    __table_args__ = (
        Index("idx_spacy_domains_account", "account_id"),
        UniqueConstraint("account_id", "domain", name="uq_spacy_user_domain"),
    )

    def __repr__(self):
        return f"<SpacyUserDomain(domain={self.domain})>"


class RuleExecutionLog(Base):
    """
    P2-004: Logging für Auto-Rule Executions.
    Trackt Erfolg/Fehler beim Ausführen von Auto-Rules für Debugging und Monitoring.
    
    Beispiele:
    - success=True, action_type='move' → Rule erfolgreich ausgeführt
    - success=False, error_message='Folder not found' → Debugging-Info
    """
    __tablename__ = "rule_execution_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mail_account_id = Column(Integer, ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(Integer, ForeignKey("auto_rules.id", ondelete="CASCADE"), nullable=False)
    processed_email_id = Column(Integer, ForeignKey("processed_emails.id", ondelete="CASCADE"), nullable=False)
    executed_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    action_type = Column(String(50), nullable=False)  # 'move', 'mark_read', 'forward', etc.

    user = relationship("User")
    account = relationship("MailAccount")
    rule = relationship("AutoRule")
    email = relationship("ProcessedEmail")

    __table_args__ = (
        Index("idx_rule_exec_account_time", "mail_account_id", "executed_at"),
        Index("idx_rule_exec_rule", "rule_id"),
        Index("idx_rule_exec_email", "processed_email_id"),
    )

    def __repr__(self):
        status = "✅" if self.success else "❌"
        return f"<RuleExecutionLog({status} rule_id={self.rule_id} action={self.action_type})>"


class ClassifierMetadata(Base):
    """
    Hybrid Score-Learning: Metadata für trainierte Klassifikatoren.
    
    Trackt Trainings-Status, Accuracy und Fehler für:
    - Globale Modelle (user_id = NULL)
    - Per-User Modelle (user_id = User ID)
    
    Classifier-Typen: dringlichkeit, wichtigkeit, spam, kategorie
    """
    __tablename__ = "classifier_metadata"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=True,
        index=True
    )  # NULL für global, sonst User ID
    classifier_type = Column(String(50), nullable=False)
    # Werte: "dringlichkeit", "wichtigkeit", "spam", "kategorie"
    
    model_version = Column(Integer, default=1, nullable=False)
    training_samples = Column(Integer, default=0, nullable=False)
    # Wie viele Samples für Training genutzt
    
    last_trained_at = Column(DateTime, nullable=True)
    accuracy_score = Column(Float, nullable=True)
    # Optional: Validierungs-Score (0.0-1.0)
    
    error_count = Column(Integer, default=0, nullable=False)
    # Circuit-Breaker: Zählt Load-Fehler, bei >=3 kein Re-Training
    
    is_active = Column(Boolean, default=True, nullable=False)
    # False = Modell deaktiviert (zu viele Fehler oder manuell)
    
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime, 
        default=lambda: datetime.now(UTC), 
        onupdate=lambda: datetime.now(UTC),
        nullable=False
    )

    # Relationships
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint('user_id', 'classifier_type', name='uq_classifier_metadata'),
        CheckConstraint(
            "classifier_type IN ('dringlichkeit', 'wichtigkeit', 'spam', 'kategorie')",
            name='ck_classifier_type_valid'
        ),
        Index('idx_classifier_metadata_user_type', 'user_id', 'classifier_type'),
    )

    def __repr__(self):
        source = f"user_{self.user_id}" if self.user_id else "global"
        return f"<ClassifierMetadata({source}/{self.classifier_type} v{self.model_version} samples={self.training_samples})>"


if __name__ == "__main__":
    print("📊 Initialisiere Datenbank...")
    engine, Session = init_db()
    print(f"✅ Datenbank erstellt: {engine.url}")
