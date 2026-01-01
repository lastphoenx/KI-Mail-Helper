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
    ForeignKey,
    UniqueConstraint,
    Index,
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
    POP3 = "pop3"  # Future Support


class OptimizationStatus(str, Enum):
    """Status der Email-Optimierung (zweiter Pass)"""

    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class EmailTag(Base):
    """User-definierte Tags für Emails (Phase 10)"""

    __tablename__ = "email_tags"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    color = Column(String(20), nullable=False, default="#3B82F6")  # Tailwind blue-500
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    user = relationship("User", back_populates="email_tags")
    assignments = relationship("EmailTagAssignment", back_populates="tag", cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_tag_name"),)


class EmailTagAssignment(Base):
    """Verknüpfung zwischen Emails und Tags (Phase 10)"""

    __tablename__ = "email_tag_assignments"

    id = Column(Integer, primary_key=True)
    email_id = Column(Integer, ForeignKey("processed_emails.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(Integer, ForeignKey("email_tags.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Relationships
    email = relationship("ProcessedEmail", back_populates="tag_assignments")
    tag = relationship("EmailTag", back_populates="assignments")

    # Constraints
    __table_args__ = (UniqueConstraint("email_id", "tag_id", name="uq_email_tag"),)


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

    # KI-Präferenzen
    preferred_ai_provider = Column(String(20), default=AIProvider.OLLAMA.value)
    preferred_ai_model = Column(
        String(100), default="all-minilm:22m"
    )  # Base-Pass: schnelles Embedding-Modell
    preferred_ai_provider_optimize = Column(String(20), default=AIProvider.OLLAMA.value)
    preferred_ai_model_optimize = Column(
        String(100), default="llama3.2:1b"
    )  # Optimize-Pass: besseres LLM

    # Phase 13C Part 4: Fetch-Konfiguration (User-steuerbar)
    fetch_mails_per_folder = Column(Integer, default=100)  # Limit pro Ordner
    fetch_max_total = Column(Integer, default=0)  # 0 = unbegrenzt
    fetch_use_delta_sync = Column(Boolean, default=True)  # Nur neue Mails holen

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


class MailAccount(Base):
    """Mail-Account eines Benutzers (Phase 2 + Zero-Knowledge Phase)

    Unterstützt Multi-Auth:
    - auth_type="imap": Klassische IMAP/SMTP Authentifizierung
    - auth_type="oauth": OAuth 2.0 (Gmail, Outlook)
    - auth_type="pop3": POP3 (zukünftig)

    Zero-Knowledge:
    - E-Mail-Adressen und Server werden verschlüsselt gespeichert
    - Hash-Felder ermöglichen Suche ohne Klartext-Zugriff

    Felder-Mapping:
    - IMAP: encrypted_imap_server, encrypted_imap_username, encrypted_imap_password
    - OAuth: oauth_provider, encrypted_oauth_token, encrypted_oauth_refresh_token
    - POP3: encrypted_pop3_server, encrypted_pop3_username, encrypted_pop3_password
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

    # POP3-spezifische Felder (zukünftig, wenn auth_type="pop3", verschlüsselt)
    encrypted_pop3_server = Column(Text, nullable=True)
    pop3_port = Column(Integer, default=995)
    encrypted_pop3_username = Column(Text, nullable=True)
    encrypted_pop3_password = Column(Text)

    enabled = Column(Boolean, default=True)
    last_fetch_at = Column(DateTime)
    initial_sync_done = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # ===== PHASE 14A: UIDVALIDITY TRACKING =====
    folder_uidvalidity = Column(Text, nullable=True)  # JSON: {"INBOX": 1352540700, ...}

    # ===== PHASE 12: NICE-TO-HAVE (Server Metadata) =====
    detected_provider = Column(String(50), nullable=True)
    server_name = Column(String(255), nullable=True)
    server_version = Column(String(100), nullable=True)

    # Relationship
    user = relationship("User", back_populates="mail_accounts")
    raw_emails = relationship(
        "RawEmail", back_populates="mail_account", cascade="all, delete-orphan"
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

        elif self.auth_type == AuthType.POP3.value:
            if not all(
                [
                    self.encrypted_pop3_server,
                    self.encrypted_pop3_username,
                    self.encrypted_pop3_password,
                ]
            ):
                return False, "POP3 requires: server, username, password"

        return True, ""

    def __repr__(self):
        return f"<MailAccount(id={self.id}, user={self.user_id}, name='{self.name}', auth={self.auth_type})>"


class ServiceToken(Base):
    """Token für Background-Jobs (Phase 2)"""

    __tablename__ = "service_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    token_hash = Column(String(255), unique=True, nullable=False)
    master_key = Column(String(255), nullable=True)  # Encrypted DEK für Background-Jobs
    expires_at = Column(DateTime, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

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
        return datetime.now(UTC) < self.expires_at

    def __repr__(self):
        return f"<ServiceToken(id={self.id}, user={self.user_id})>"


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

    uid = Column(String(255), nullable=False)

    # Zero-Knowledge: Verschlüsselte persönliche Daten
    encrypted_sender = Column(Text, nullable=False)
    encrypted_subject = Column(Text)
    encrypted_body = Column(Text)

    received_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    deleted_at = Column(DateTime, nullable=True)
    deleted_verm = Column(Boolean, default=False)

    # ===== PHASE 14A: RFC-KONFORMER KEY (folder, uidvalidity, uid) =====
    imap_uid = Column(Integer, nullable=True, index=True)  # Phase 14a: String → Integer
    imap_folder = Column(String(200), nullable=False, default='INBOX')  # Phase 14a: NOT NULL
    imap_uidvalidity = Column(Integer, nullable=True, index=True)  # Phase 14a: RFC 3501
    imap_flags = Column(String(500), nullable=True)
    imap_last_seen_at = Column(DateTime, nullable=True)

    # ===== PHASE 12: MUST-HAVE (Threading & Query Optimization) =====
    message_id = Column(String(255), nullable=True, index=True)
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

    # Relationships
    user = relationship("User", back_populates="raw_emails")
    mail_account = relationship("MailAccount", back_populates="raw_emails")
    processed = relationship(
        "ProcessedEmail", back_populates="raw_email", uselist=False
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

    def __repr__(self):
        return f"<RawEmail(id={self.id}, user={self.user_id}, uid='{self.uid}')>"


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
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    deleted_at = Column(DateTime, nullable=True)
    deleted_verm = Column(Boolean, default=False)

    # Optimization (zweiter Pass für bessere Kategorisierung)
    optimization_status = Column(String(20), default=OptimizationStatus.PENDING.value)
    optimization_tried_at = Column(DateTime, nullable=True)
    optimization_completed_at = Column(DateTime, nullable=True)
    base_provider = Column(String(50), nullable=True)
    base_model = Column(String(100), nullable=True)
    optimize_provider = Column(String(50), nullable=True)
    optimize_model = Column(String(100), nullable=True)

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


if __name__ == "__main__":
    print("📊 Initialisiere Datenbank...")
    engine, Session = init_db()
    print(f"✅ Datenbank erstellt: {engine.url}")
