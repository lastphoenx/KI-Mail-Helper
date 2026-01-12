"""
Mail Helper - Web-App (Flask) mit Multi-User & 2FA
Phase 2: Login, Register, 2FA Setup, Mail-Accounts
"""

from dotenv import load_dotenv

load_dotenv()

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    session,
    flash,
    make_response,
)
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import check_password_hash
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, UTC
import logging
import importlib
import os
import threading
from werkzeug.serving import make_server

try:
    from flask_talisman import Talisman

    TALISMAN_AVAILABLE = True
except ImportError:
    TALISMAN_AVAILABLE = False

env_validator = importlib.import_module(".00_env_validator", "src")
env_validator.validate_environment()

models = importlib.import_module(".02_models", "src")
scoring = importlib.import_module(".05_scoring", "src")
auth = importlib.import_module(".07_auth", "src")
encryption = importlib.import_module(".08_encryption", "src")
google_oauth = importlib.import_module(".10_google_oauth", "src")
sanitizer = importlib.import_module(".04_sanitizer", "src")
ai_client = importlib.import_module(".03_ai_client", "src")
processing = importlib.import_module(".12_processing", "src")
background_jobs = importlib.import_module(".14_background_jobs", "src")
provider_utils = importlib.import_module(".15_provider_utils", "src")
password_validator = importlib.import_module(".09_password_validator", "src")
mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")
mail_sync = importlib.import_module(".16_mail_sync", "src")
semantic_search = importlib.import_module(".semantic_search", "src")
smtp_sender = importlib.import_module(".19_smtp_sender", "src")

# 🔍 Debug-Logging System
from src.debug_logger import DebugLogger

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="../templates")

# SECRET_KEY from System Environment (NOT from .env file for production security)
# Development: Set in .env file (not committed to git)
# Production: Set in systemd service or /etc/environment
secret_key = os.getenv("FLASK_SECRET_KEY")
if not secret_key:
    raise ValueError(
        "FLASK_SECRET_KEY environment variable must be set!\n"
        "Development: Add to .env file (see .env.example)\n"
        "Production: Set in systemd service or /etc/environment\n"
        "Generate with: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
    )
app.config["SECRET_KEY"] = secret_key

app.config["WTF_CSRF_ENABLED"] = True  # CSRF Protection aktivieren
app.config["WTF_CSRF_TIME_LIMIT"] = None  # Kein Timeout (Session-basiert)

# Reverse Proxy Support (nginx, caddy, traefik, etc.)
# Verarbeitet X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Host, X-Forwarded-Prefix
if os.getenv("BEHIND_REVERSE_PROXY", "false").lower() == "true":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,  # X-Forwarded-For (Client IP)
        x_proto=1,  # X-Forwarded-Proto (http/https)
        x_host=1,  # X-Forwarded-Host (Domain)
        x_prefix=1,  # X-Forwarded-Prefix (URL Prefix)
    )
    logger.info("🔄 ProxyFix aktiviert - App läuft hinter Reverse Proxy")

# Server-Side Sessions für Zero-Knowledge Security
# Master-Keys werden NUR auf dem Server gespeichert, NICHT im Browser-Cookie
app.config["SESSION_TYPE"] = "filesystem"

# Create session directory if it doesn't exist (prevent runtime errors)
session_dir = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), ".flask_sessions"
)
os.makedirs(session_dir, mode=0o700, exist_ok=True)

app.config["SESSION_FILE_DIR"] = session_dir

# Session Timeout (Phase 9: Production Hardening)
app.config["SESSION_PERMANENT"] = True  # Enable permanent sessions with timeout
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    minutes=30
)  # 30min inactivity timeout
app.config[
    "SESSION_USE_SIGNER"
] = False  # EMPFOHLEN: Deprecated seit Flask-Session 0.7.0 (server-side irrelevant, 256-bit Session-ID = ausreichend)

# Security Note: Session files contain DEK/Master-Keys. Ensure:
# - Restrictive file permissions (0o700 above)
# - Regular cleanup of expired sessions
# - Backup software excludes .flask_sessions/
# - For high-security: Consider encrypted filesystem or Redis with TLS
app.config["SESSION_KEY_PREFIX"] = "mail_helper_"
app.config[
    "SESSION_ID_LENGTH"
] = 32  # 256-bit Entropie für Session-ID (default, explizit dokumentiert)

# Session-Cookie Security (OWASP Best Practices)
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
)  # True für HTTPS
app.config["SESSION_COOKIE_HTTPONLY"] = True  # Kein JavaScript-Zugriff
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # CSRF-Schutz

Session(app)

# CSRF Protection mit Flask-WTF (Phase 8d: Security Hardening)
from flask_wtf.csrf import CSRFProtect, generate_csrf, validate_csrf
from werkzeug.exceptions import BadRequest

csrf = CSRFProtect(app)

import secrets
from flask import g


# Generate CSP nonce for this request
@app.before_request
def generate_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)


# Make csrf_token and csp_nonce available in all templates
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf, csp_nonce=lambda: g.get("csp_nonce", ""))


# Security Fix (Layer 1): CSRF Protection for AJAX Endpoints
@app.before_request
def csrf_protect_ajax():
    """Validates CSRF tokens for all POST/PUT/DELETE AJAX requests."""
    if request.method in ["POST", "PUT", "DELETE"] and request.is_json:
        token = request.headers.get("X-CSRFToken")
        if not token:
            logger.warning(
                "⚠️ CSRF token missing in AJAX request from %s", request.remote_addr
            )
            return jsonify({"error": "CSRF token missing"}), 403
        try:
            validate_csrf(token)
        except BadRequest:
            logger.warning(
                "⚠️ CSRF token invalid in AJAX request from %s", request.remote_addr
            )
            return jsonify({"error": "CSRF token invalid"}), 403


# Security Fix (Layer 5): Content Security Policy via HTTP Header (not meta tag)
@app.after_request
def set_security_headers(response):
    """Sets CSP and other security headers for all responses.

    CSP uses nonce for inline scripts (no 'unsafe-inline' needed).
    Security headers are set for ALL responses (including errors).

    Exception: /email/<id>/render-html endpoint has relaxed CSP for email content.
    """
    # Exception: Email rendering endpoint sets its own headers
    if g.get("skip_security_headers", False):
        return response

    # Security Headers für ALLE anderen Responses (inkl. Errors) - Defense-in-Depth
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # P2-006: Nur einmal HSTS setzen (Duplikat entfernt)
    response.headers[
        "Strict-Transport-Security"
    ] = "max-age=31536000; includeSubDomains"

    # CSP nur bei erfolgreichen Responses (< 400) - benötigt Nonce aus g
    if response.status_code < 400:
        nonce = g.get("csp_nonce", "")
        # Content Security Policy (strict, with nonce for inline scripts)
        csp = (
            "default-src 'self'; "
            f"script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response.headers["Content-Security-Policy"] = csp

    return response


logger.info("🛡️  CSRF Protection aktiviert (Flask-WTF + AJAX)")
logger.info("🔒 Security Headers aktiviert (CSP + X-Frame-Options + Referrer-Policy)")

# Rate Limiting (Phase 9: Production Hardening)
from flask_limiter import Limiter
from src.thread_api import thread_api
from flask_limiter.util import get_remote_address

# Auto-detect Redis availability for multi-worker setups
RATE_LIMIT_STORAGE = os.getenv("RATE_LIMIT_STORAGE", "memory://")
if RATE_LIMIT_STORAGE == "auto":
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, db=1, socket_connect_timeout=1)
        r.ping()
        RATE_LIMIT_STORAGE = "redis://localhost:6379/1"
        logger.info("🟢 Redis detected - using for rate limiting (multi-worker safe)")
    except (ImportError, ConnectionError):
        RATE_LIMIT_STORAGE = "memory://"
        logger.warning(
            "🟡 Redis not available - using memory storage (single-worker only)"
        )

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=RATE_LIMIT_STORAGE,
)

logger.info("🛡️  Rate Limiting aktiviert (Flask-Limiter)")

# HTTPS Enforcement mit Flask-Talisman wird dynamisch in start_server() aktiviert
talisman = None


@app.before_request
def check_dek_in_session():
    """Überprüft ob DEK in Session vorhanden ist (für Zero-Knowledge Encryption)

    Falls User authentifiziert ist aber DEK fehlt (z.B. nach Session-Expire),
    wird der User zur Passwort-Reauth weitergeleitet.

    Phase 8c: Security Hardening - Mandatory 2FA Check
    User ohne aktivierte 2FA werden automatisch zu /2fa/setup weitergeleitet.
    """
    # Skip für Login/Logout/Static-Routes + 2FA-Setup
    if request.endpoint in [
        "login",
        "register",
        "logout",
        "static",
        "verify_2fa",
        "setup_2fa",
    ]:
        return None

    # DEK-Check (Zero-Knowledge)
    if current_user.is_authenticated and not session.get("master_key"):
        logger.warning(
            f"⚠️ User {current_user.user_model.id} authenticated aber DEK in Session fehlt - Reauth erforderlich"
        )
        session.clear()
        logout_user()
        flash("Sitzung abgelaufen - bitte erneut anmelden", "warning")
        return redirect(url_for("login"))

    # Mandatory 2FA Check (Phase 8c Security Hardening)
    if current_user.is_authenticated and not current_user.user_model.totp_enabled:
        logger.warning(
            f"⚠️ User {current_user.user_model.id} hat 2FA nicht aktiviert - Redirect zu Setup"
        )
        flash("2FA ist Pflicht - bitte jetzt einrichten", "warning")
        return redirect(url_for("setup_2fa"))

    return None


DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emails.db")

# SQLite mit WAL-Mode und Timeout für Concurrency
engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30.0}  # 30 Sekunden Timeout
)

# SQLite Pragmas für Concurrency (WAL-Mode)
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """SQLite Pragmas für Multi-Worker Concurrency"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")  # 30 Sekunden
    cursor.execute("PRAGMA wal_autocheckpoint=1000")
    cursor.close()

SessionLocal = sessionmaker(bind=engine)
job_queue = background_jobs.BackgroundJobQueue(DATABASE_PATH)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


def decrypt_raw_email(raw_email, master_key):
    """Zero-Knowledge Helper: Entschlüsselt RawEmail-Felder

    Args:
        raw_email: RawEmail Model mit verschlüsselten Feldern
        master_key: User's Master-Key aus Session

    Returns:
        dict mit entschlüsselten Werten: sender, subject, body
    """
    try:
        return {
            "sender": encryption.EmailDataManager.decrypt_email_sender(
                raw_email.encrypted_sender or "", master_key
            )
            if raw_email.encrypted_sender
            else "",
            "subject": encryption.EmailDataManager.decrypt_email_subject(
                raw_email.encrypted_subject or "", master_key
            )
            if raw_email.encrypted_subject
            else "",
            "body": encryption.EmailDataManager.decrypt_email_body(
                raw_email.encrypted_body or "", master_key
            )
            if raw_email.encrypted_body
            else "",
        }
    except (ValueError, KeyError, Exception) as e:
        logger.error(
            f"Entschlüsselung fehlgeschlagen für RawEmail {raw_email.id}: {type(e).__name__}"
        )
        return {
            "sender": "***Entschlüsselung fehlgeschlagen***",
            "subject": "***Entschlüsselung fehlgeschlagen***",
            "body": "***Entschlüsselung fehlgeschlagen***",
        }


class UserWrapper(UserMixin):
    """Wrapper für SQLAlchemy User-Model für Flask-Login"""

    def __init__(self, user_model):
        self.user_model = user_model
        self.id = user_model.id

    def get_id(self):
        return str(self.user_model.id)


@login_manager.user_loader
def load_user(user_id):
    """Lädt User aus DB für Flask-Login"""
    db = get_db_session()
    try:
        user = db.query(models.User).filter_by(id=int(user_id)).first()
        if user:
            return UserWrapper(user)
    finally:
        db.close()
    return None


def get_db_session():
    """Get database session from shared pool"""
    return SessionLocal()


def get_current_user_model(db):
    """Holt das aktuelle User-Model aus DB"""
    if not current_user.is_authenticated:
        return None
    return db.query(models.User).filter_by(id=current_user.id).first()


# ============================================================================
# P1-003: API Input-Validation Helpers
# ============================================================================

def validate_string(value, field_name, min_len=1, max_len=1000, allow_empty=False):
    """Validiert String-Input für API-Endpoints
    
    Args:
        value: Zu validierender Wert
        field_name: Feldname für Fehlermeldung
        min_len: Minimale Länge (default: 1)
        max_len: Maximale Länge (default: 1000)
        allow_empty: Leere Strings erlauben (default: False)
        
    Returns:
        Bereinigter String oder None wenn allow_empty=True
        
    Raises:
        ValueError: Bei ungültigem Input
    """
    if value is None:
        if allow_empty:
            return None
        raise ValueError(f"{field_name} ist erforderlich")
    
    if not isinstance(value, str):
        raise ValueError(f"{field_name} muss ein String sein")
    
    value = value.strip()
    
    if len(value) == 0 and not allow_empty:
        raise ValueError(f"{field_name} darf nicht leer sein")
    
    if len(value) < min_len:
        raise ValueError(f"{field_name} muss mindestens {min_len} Zeichen lang sein")
    
    if len(value) > max_len:
        raise ValueError(f"{field_name} darf maximal {max_len} Zeichen lang sein")
    
    return value


def validate_integer(value, field_name, min_val=None, max_val=None):
    """Validiert Integer-Input für API-Endpoints
    
    Args:
        value: Zu validierender Wert
        field_name: Feldname für Fehlermeldung
        min_val: Minimalwert (optional)
        max_val: Maximalwert (optional)
        
    Returns:
        Integer-Wert
        
    Raises:
        ValueError: Bei ungültigem Input
    """
    if value is None:
        raise ValueError(f"{field_name} ist erforderlich")
    
    if not isinstance(value, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise ValueError(f"{field_name} muss eine Zahl sein")
    
    if min_val is not None and value < min_val:
        raise ValueError(f"{field_name} muss mindestens {min_val} sein")
    
    if max_val is not None and value > max_val:
        raise ValueError(f"{field_name} darf maximal {max_val} sein")
    
    return value


def validate_email(value, field_name):
    """Validiert E-Mail-Adresse
    
    Args:
        value: Zu validierender Wert
        field_name: Feldname für Fehlermeldung
        
    Returns:
        Normalisierte E-Mail-Adresse (lowercase)
        
    Raises:
        ValueError: Bei ungültiger E-Mail
    """
    if value is None or not isinstance(value, str):
        raise ValueError(f"{field_name} ist erforderlich")
    
    value = value.strip().lower()
    
    if len(value) == 0:
        raise ValueError(f"{field_name} darf nicht leer sein")
    
    if len(value) > 320:  # RFC 5321 Maximum
        raise ValueError(f"{field_name} ist zu lang (max. 320 Zeichen)")
    
    # Simple email pattern check
    if "@" not in value or "." not in value.split("@")[1]:
        raise ValueError(f"{field_name} hat kein gültiges E-Mail-Format")
    
    return value


# ============================================================================
# P1-005: API Response Helpers (Standardisiertes Format)
# ============================================================================

def api_success(data=None, message=None, status_code=200):
    """Standardisierte Erfolgs-Response
    
    Args:
        data: Response-Daten (optional)
        message: Erfolgs-Nachricht (optional)
        status_code: HTTP-Statuscode (default: 200)
        
    Returns:
        JSON-Response mit standardisiertem Format
    """
    response = {"success": True}
    
    if data is not None:
        response["data"] = data
    
    if message:
        response["message"] = message
    
    return jsonify(response), status_code


def api_error(message, code=None, status_code=400, details=None):
    """Standardisierte Fehler-Response
    
    Args:
        message: Fehlermeldung (required)
        code: Fehlercode wie "VALIDATION_ERROR", "NOT_FOUND" (optional)
        status_code: HTTP-Statuscode (default: 400)
        details: Zusätzliche Details (optional)
        
    Returns:
        JSON-Response mit standardisiertem Fehler-Format
    """
    error_data = {"message": message}
    
    if code:
        error_data["code"] = code
    
    if details:
        error_data["details"] = details
    
    return jsonify({"success": False, "error": error_data}), status_code


def ensure_master_key_in_session():
    """Stellt sicher, dass Master-Key in Session vorhanden ist"""
    if not session.get("master_key"):
        logger.error(f"Master-Key nicht in Session für User {current_user.id}")
        return False
    return True


# ============================================================================
# P2-008: Phase Y Auto-Config Helper
# ============================================================================

def initialize_phase_y_config(db, user_id, account_id, account_email_domain=None):
    """Erstellt automatisch Phase Y Default-Config für neuen Account
    
    P2-008: Learning-First Approach - Neue Accounts können sofort lernen.
    
    Erstellt:
    - SpacyScoringConfig mit Default-Gewichten
    - SpacyUserDomain basierend auf Account-Email-Domain
    
    Args:
        db: SQLAlchemy Session
        user_id: User ID
        account_id: MailAccount ID
        account_email_domain: Domain der Email-Adresse (optional, z.B. "company.com")
    """
    try:
        # 1. SpacyScoringConfig mit Defaults
        existing_config = db.query(models.SpacyScoringConfig).filter_by(
            user_id=user_id, account_id=account_id
        ).first()
        
        if not existing_config:
            config = models.SpacyScoringConfig(
                user_id=user_id,
                account_id=account_id,
                # Default-Gewichte aus Migration
                imperative_weight=3,
                deadline_weight=4,
                keyword_weight=2,
                vip_weight=3,
                question_threshold=3,
                negation_sensitivity=2,
                # Ensemble Learning Weights (start mit 100% spaCy)
                spacy_weight_initial=100,
                spacy_weight_learning=30,
                spacy_weight_trained=15
            )
            db.add(config)
            logger.info(f"✅ Phase Y Scoring Config erstellt für Account {account_id}")
        
        # 2. SpacyUserDomain wenn Email-Domain bekannt
        if account_email_domain:
            existing_domain = db.query(models.SpacyUserDomain).filter_by(
                account_id=account_id, domain=account_email_domain
            ).first()
            
            if not existing_domain:
                user_domain = models.SpacyUserDomain(
                    user_id=user_id,
                    account_id=account_id,
                    domain=account_email_domain,
                    is_active=True
                )
                db.add(user_domain)
                logger.info(f"✅ Phase Y User-Domain '{account_email_domain}' für Account {account_id}")
        
        db.commit()
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Initialisieren von Phase Y Config: {e}")
        db.rollback()
        return False


# Register Thread API Blueprint
app.register_blueprint(thread_api)


@app.route("/")
def index():
    """Hauptseite: Redirect zu Dashboard oder Login"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")  # Rate limit: 5 login attempts per minute per IP
def login():
    """Login-Seite mit optional 2FA"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    db = get_db_session()

    try:
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")

            user = db.query(models.User).filter_by(username=username).first()

            # Timing-Attack Protection: Dummy password check für constant-time behavior
            if not user:
                # Dummy bcrypt check to normalize timing (prevent user enumeration)
                dummy_hash = "$2b$12$" + "0" * 53  # Valid bcrypt format
                try:
                    check_password_hash(dummy_hash, password)
                except:
                    pass
                logger.warning(
                    f"SECURITY[LOGIN_FAILED]: user={username} ip={request.remote_addr} "
                    f"reason=user_not_found"
                )
                return (
                    render_template("login.html", error="Ungültige Anmeldedaten"),
                    401,
                )

            # Account Lockout Check (Phase 9)
            if user.is_locked():
                remaining = (user.locked_until - datetime.now(UTC)).total_seconds() / 60
                # Audit Log für Fail2Ban
                logger.warning(
                    f"SECURITY[LOCKOUT]: user={username} ip={request.remote_addr} "
                    f"remaining={int(remaining)}min reason=account_locked"
                )
                return (
                    render_template(
                        "login.html",
                        error=f"Account gesperrt. Bitte versuche es in {int(remaining)} Minuten erneut.",
                    ),
                    403,
                )

            if not user.check_password(password):
                # Phase 9f: Atomic SQL-Update (Race Condition Protection)
                user.record_failed_login(db)
                db.commit()
                # Audit Log für Fail2Ban
                logger.warning(
                    f"SECURITY[LOGIN_FAILED]: user={username} ip={request.remote_addr} "
                    f"attempts={user.failed_login_attempts}/5 reason=invalid_credentials"
                )
                return (
                    render_template("login.html", error="Ungültige Anmeldedaten"),
                    401,
                )

            # Erfolgreicher Login - Failed Counter zurücksetzen
            # Phase 9f: Atomic SQL-Update (Race Condition Protection)
            user.reset_failed_logins(db)
            db.commit()

            # Phase 8: DEK/KEK Pattern - DEK entschlüsseln
            dek = auth.MasterKeyManager.decrypt_dek_from_password(user, password)
            if not dek:
                logger.error("❌ DEK-Entschlüsselung fehlgeschlagen")
                return (
                    render_template(
                        "login.html", error="Entschlüsselung fehlgeschlagen"
                    ),
                    401,
                )

            if user.totp_enabled:
                # Security: DEK statt Passwort in Session (2FA-Zwischenschritt)
                session["pending_user_id"] = user.id
                session["pending_dek"] = dek
                session["pending_remember"] = bool(request.form.get("remember"))
                session["pending_auth_time"] = str(
                    __import__("datetime").datetime.utcnow()
                )
                return redirect(url_for("verify_2fa"))

            # DEK in Session speichern
            session[
                "master_key"
            ] = dek  # Session-Key heißt "master_key" aus Kompatibilität
            logger.info("✅ DEK erfolgreich in Session geladen")

            # Zero-Knowledge: Disable remember-me (verhindert DEK-Loss nach Session-Expire)
            login_user(UserWrapper(user), remember=False)
            # Audit Log für erfolgreichen Login
            logger.info(
                f"SECURITY[LOGIN_SUCCESS]: user={user.username} ip={request.remote_addr} "
                f"2fa=disabled method=password"
            )
            return redirect(url_for("dashboard"))

        return render_template("login.html")

    finally:
        db.close()


@app.route("/register", methods=["GET", "POST"])
def register():
    """Registrierungs-Seite"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    db = get_db_session()

    try:
        if request.method == "POST":
            username = request.form.get("username")
            email = request.form.get("email")
            password = request.form.get("password")
            password_confirm = request.form.get("password_confirm")

            if not all([username, email, password, password_confirm]):
                return (
                    render_template(
                        "register.html", error="Alle Felder sind erforderlich"
                    ),
                    400,
                )

            if password != password_confirm:
                return (
                    render_template(
                        "register.html",
                        error="Passwörter stimmen nicht überein",
                        username=username,
                        email=email,
                    ),
                    400,
                )

            # Phase INV: Whitelist-Check (außer für ersten User)
            user_count = db.query(models.User).count()
            if user_count > 0:  # Nicht der erste User
                invite = db.query(models.InvitedEmail).filter_by(email=email, used=False).first()
                if not invite:
                    return (
                        render_template(
                            "register.html",
                            error="Registration ist nur mit Einladung möglich. Kontaktiere den Administrator.",
                            username=username,
                        ),
                        403,
                    )

            # Phase 8c: Security Hardening - OWASP Password Policy
            is_valid, error_msg = password_validator.PasswordValidator.validate(
                password
            )
            if not is_valid:
                return (
                    render_template(
                        "register.html", error=error_msg, username=username, email=email
                    ),
                    400,
                )

            if db.query(models.User).filter_by(username=username).first():
                return (
                    render_template(
                        "register.html",
                        error="Benutzername existiert bereits",
                        email=email,
                    ),
                    400,
                )

            if db.query(models.User).filter_by(email=email).first():
                return (
                    render_template(
                        "register.html",
                        error="E-Mail existiert bereits",
                        username=username,
                    ),
                    400,
                )

            user = models.User()
            user.set_username(username)
            user.set_email(email)
            user.set_password(password)

            db.add(user)
            db.commit()

            # Phase INV: Markiere Invite als verwendet
            if user_count > 0:
                invite.used = True
                invite.used_at = datetime.now(UTC)
                db.commit()

            # Phase 8: DEK/KEK Pattern - DEK erstellen und in Session speichern
            salt, encrypted_dek, dek = auth.MasterKeyManager.setup_dek_for_user(
                user.id, password, db
            )
            session[
                "master_key"
            ] = dek  # Session-Key heißt "master_key" aus Kompatibilität

            logger.info(f"✅ User registriert (ID: {user.id}, DEK/KEK erstellt)")

            # Phase 8c: Security Hardening - Mandatory 2FA Setup
            # User wird automatisch zu 2FA-Setup weitergeleitet
            session["mandatory_2fa_setup"] = True
            session["new_user_id"] = user.id
            flash(
                "Registrierung erfolgreich! Bitte richte jetzt 2FA ein (Pflichtfeld).",
                "success",
            )
            return redirect(url_for("setup_2fa"))

        return render_template("register.html")

    finally:
        db.close()


@app.route("/2fa/verify", methods=["GET", "POST"])
@limiter.limit("5 per minute")  # Rate limit: 5 2FA attempts per minute per IP
def verify_2fa():
    """2FA-Verifikation"""
    user_id = session.get("pending_user_id")

    if not user_id:
        return redirect(url_for("login"))

    db = get_db_session()

    try:
        user = db.query(models.User).filter_by(id=user_id).first()

        if not user or not user.totp_enabled:
            return redirect(url_for("login"))

        if request.method == "POST":
            token = request.form.get("token", "").strip()
            recovery_code = request.form.get("recovery_code", "").strip()

            verified = False

            if token and len(token) == 6:
                verified = auth.AuthManager.verify_totp(user.totp_secret, token)

            elif recovery_code:
                verified = auth.RecoveryCodeManager.verify_recovery_code(
                    user.id, recovery_code, db
                )

            if verified:
                # Extract pending data BEFORE session operations
                dek = session.get("pending_dek")
                remember = session.get("pending_remember", False)

                # Clear pending 2FA data
                session.pop("pending_user_id", None)
                session.pop("pending_dek", None)
                session.pop("pending_remember", None)
                session.pop("pending_auth_time", None)

                # Phase 8: DEK/KEK Pattern
                if not dek:
                    logger.error("❌ Kein DEK für 2FA gefunden")
                    flash("Session abgelaufen - bitte erneut einloggen", "danger")
                    return redirect(url_for("login"))

                session["master_key"] = dek
                logger.info("✅ DEK nach 2FA in Session geladen")

                login_user(UserWrapper(user), remember=remember)
                # Audit Log für erfolgreichen Login mit 2FA
                logger.info(
                    f"SECURITY[LOGIN_SUCCESS]: user={user.username} ip={request.remote_addr} "
                    f"2fa=verified method=totp"
                )
                return redirect(url_for("dashboard"))

            # Fehlgeschlagener 2FA-Versuch
            logger.warning(
                f"SECURITY[2FA_FAILED]: user={user.username} ip={request.remote_addr} "
                f"reason=invalid_token"
            )
            return render_template("verify_2fa.html", error="Ungültiger Code"), 401

        return render_template("verify_2fa.html")

    finally:
        db.close()


@app.route("/logout")
@login_required
def logout():
    """Logout"""
    username = (
        current_user.user_model.username
        if hasattr(current_user, "user_model")
        else "User"
    )
    ip = request.remote_addr

    # Audit Log für Logout
    logger.info(f"SECURITY[LOGOUT]: user={username} ip={ip}")

    # Zero-Knowledge: Komplette Session löschen (DEK + pending_* + oauth-state etc.)
    session.clear()

    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Hauptseite: 3x3-Prioritäten-Matrix mit Statistiken"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        # Account-Filter (optional)
        filter_account_id = None
        account_id_str = request.args.get("mail_account")
        if account_id_str:
            try:
                filter_account_id = int(account_id_str)
            except (ValueError, TypeError):
                filter_account_id = None

        # Alle Mail-Accounts des Users (für Dropdown)
        user_accounts = (
            db.query(models.MailAccount)
            .filter(models.MailAccount.user_id == user.id)
            .order_by(models.MailAccount.name)
            .all()
        )

        # Zero-Knowledge: Entschlüssele Email-Adressen für Anzeige
        master_key = session.get("master_key")
        if master_key and user_accounts:
            for account in user_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = (
                            encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_username, master_key
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            f"Fehler beim Entschlüsseln der Account-Email: {e}"
                        )
                        account.decrypted_imap_username = None

        matrix_data = {}
        total_mails = 0
        high_priority_count = 0

        # Filtere nach Account falls gewählt
        query_filter = [
            models.RawEmail.user_id == user.id,
            models.RawEmail.deleted_at == None,
            models.ProcessedEmail.done == False,
            models.ProcessedEmail.deleted_at == None,
        ]
        if filter_account_id:
            query_filter.append(models.RawEmail.mail_account_id == filter_account_id)

        # Alle unerledigten Mails des Users (optional gefiltert nach Account)
        processed_mails = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(*query_filter)
            .all()
        )

        total_mails = len(processed_mails)

        for mail in processed_mails:
            key = f"{mail.matrix_x}_{mail.matrix_y}"
            if key not in matrix_data:
                matrix_data[key] = {"count": 0, "color": mail.farbe}

            matrix_data[key]["count"] += 1

            if mail.farbe == "rot":
                high_priority_count += 1

        amp_colors = {
            "rot": sum(
                m["count"] for m in matrix_data.values() if m.get("color") == "rot"
            ),
            "gelb": sum(
                m["count"] for m in matrix_data.values() if m.get("color") == "gelb"
            ),
            "grün": sum(
                m["count"] for m in matrix_data.values() if m.get("color") == "grün"
            ),
        }

        matrix = {}
        for x in range(1, 4):
            for y in range(1, 4):
                key = f"{x}_{y}"
                matrix_key = f"{x}{y}"
                matrix[matrix_key] = matrix_data.get(key, {}).get("count", 0)

        # Erledigte Mails (mit Account-Filter)
        done_query_filter = [
            models.RawEmail.user_id == user.id,
            models.RawEmail.deleted_at == None,
            models.ProcessedEmail.done == True,
            models.ProcessedEmail.deleted_at == None,
        ]
        if filter_account_id:
            done_query_filter.append(models.RawEmail.mail_account_id == filter_account_id)

        done_mails = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(*done_query_filter)
            .count()
        )

        stats = {
            "total": total_mails + done_mails,
            "open": total_mails,
            "done": done_mails,
        }

        # Gewählter Account (für Anzeige)
        selected_account = None
        if filter_account_id:
            selected_account = (
                db.query(models.MailAccount)
                .filter(models.MailAccount.id == filter_account_id)
                .first()
            )

        return render_template(
            "dashboard.html",
            matrix=matrix,
            ampel=amp_colors,
            stats=stats,
            top_tags=[],
            user_accounts=user_accounts,
            filter_account_id=filter_account_id,
            selected_account=selected_account,
        )

    finally:
        db.close()


@app.route("/list")
@login_required
def list_view():
    """Listen-Ansicht: alle Mails mit erweiterten Filtern"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        # Legacy-Filter
        filter_color = request.args.get("farbe") or None
        filter_done = (request.args.get("done") or "").lower()
        search_term = (request.args.get("search", "") or "").strip()

        # Account-Filter
        filter_account_id = None
        account_id_str = request.args.get("mail_account")
        if account_id_str:
            try:
                filter_account_id = int(account_id_str)
            except (ValueError, TypeError):
                filter_account_id = None

        # Phase 10: Tag-Filter
        filter_tag_ids = []
        tag_id_str = request.args.get("tags")
        if tag_id_str:
            try:
                filter_tag_ids = [int(tag_id_str)]
            except (ValueError, TypeError):
                filter_tag_ids = []

        # Phase 13: Neue Filter
        filter_folder = request.args.get("folder") or None
        filter_seen = (request.args.get("seen") or "").lower()
        filter_flagged = (request.args.get("flagged") or "").lower()
        filter_attachments = (request.args.get("attach") or "").lower()

        # Datums-Filter
        filter_date_from = request.args.get("date_from") or None
        filter_date_to = request.args.get("date_to") or None

        # Sortierung
        sort_by = request.args.get("sort", "score")  # date/score/size/sender
        sort_order = request.args.get("order", "desc").lower()  # asc/desc
        if sort_order not in ("asc", "desc"):
            sort_order = "desc"

        query = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
        )

        if filter_done in ("true", "false"):
            query = query.filter(models.ProcessedEmail.done == (filter_done == "true"))

        if filter_color:
            query = query.filter(models.ProcessedEmail.farbe == filter_color)

        if filter_account_id:
            query = query.filter(models.RawEmail.mail_account_id == filter_account_id)

        # Phase 10: Filter nach Tags
        if filter_tag_ids:
            query = query.join(models.EmailTagAssignment).filter(
                models.EmailTagAssignment.tag_id.in_(filter_tag_ids)
            )

        # Phase 13: Ordner-Filter
        if filter_folder:
            query = query.filter(models.RawEmail.imap_folder == filter_folder)

        # Phase 13: Gelesen/Ungelesen-Filter
        if filter_seen == "true":
            query = query.filter(models.RawEmail.imap_is_seen == True)
        elif filter_seen == "false":
            query = query.filter(models.RawEmail.imap_is_seen == False)

        # Phase 13: Geflaggt/Nicht-Filter
        if filter_flagged == "true":
            query = query.filter(models.RawEmail.imap_is_flagged == True)
        elif filter_flagged == "false":
            query = query.filter(models.RawEmail.imap_is_flagged == False)

        # Phase 13: Anhang-Filter
        if filter_attachments == "true":
            query = query.filter(models.RawEmail.has_attachments == True)
        elif filter_attachments == "false":
            query = query.filter(models.RawEmail.has_attachments == False)

        # Phase 13: Datums-Filter
        if filter_date_from:
            try:
                from_date = datetime.fromisoformat(filter_date_from)
                query = query.filter(models.RawEmail.received_at >= from_date)
            except (ValueError, TypeError):
                pass

        if filter_date_to:
            try:
                to_date = datetime.fromisoformat(filter_date_to)
                to_date = to_date.replace(hour=23, minute=59, second=59)
                query = query.filter(models.RawEmail.received_at <= to_date)
            except (ValueError, TypeError):
                pass

        # Phase 13: Sortierung anwenden
        if sort_by == "date":
            sort_col = models.RawEmail.received_at
        elif sort_by == "size":
            sort_col = models.RawEmail.message_size
        elif sort_by == "sender":
            sort_col = models.RawEmail.encrypted_sender
        else:  # "score" (default)
            sort_col = models.ProcessedEmail.score

        # P2-007: Server-Pagination
        page = int(request.args.get('page', 1))
        per_page = 50
        
        # Count total for pagination
        total_count = query.count()
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        
        # Boundary checks
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        
        # Apply pagination
        if sort_order == "asc":
            mails = query.order_by(sort_col.asc()).limit(per_page).offset((page - 1) * per_page).all()
        else:
            mails = query.order_by(sort_col.desc()).limit(per_page).offset((page - 1) * per_page).all()

        # Lade alle User-Accounts für Filter-Dropdown
        user_accounts = (
            db.query(models.MailAccount)
            .filter(models.MailAccount.user_id == user.id)
            .all()
        )

        # Phase 13C: Lade Server-Ordner via IMAP (für Dropdown-Autocomplete)
        server_folders = []
        if filter_account_id:
            try:
                account = db.query(models.MailAccount).filter_by(
                    id=filter_account_id, user_id=user.id
                ).first()
                if account and account.auth_type == "imap":
                    master_key_temp = session.get("master_key")
                    if master_key_temp:
                        imap_server = encryption.CredentialManager.decrypt_server(
                            account.encrypted_imap_server, master_key_temp
                        )
                        imap_username = encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_imap_username, master_key_temp
                        )
                        imap_password = encryption.CredentialManager.decrypt_imap_password(
                            account.encrypted_imap_password, master_key_temp
                        )
                        fetcher = mail_fetcher_mod.MailFetcher(
                            server=imap_server,
                            username=imap_username,
                            password=imap_password,
                            port=account.imap_port,
                        )
                        fetcher.connect()
                        try:
                            # IMAPClient.list_folders() returns (flags, delimiter, folder_name) tuples
                            folders = fetcher.connection.list_folders()
                            for flags, delimiter, folder_name in folders:
                                # Skip \Noselect folders
                                if b'\\Noselect' in flags or '\\Noselect' in [f.decode() if isinstance(f, bytes) else f for f in flags]:
                                    continue
                                # folder_name is bytes, decode UTF-7 to UTF-8
                                folder_display = mail_fetcher_mod.decode_imap_folder_name(folder_name)
                                server_folders.append(folder_display)
                            server_folders.sort()
                        finally:
                            fetcher.disconnect()
            except Exception as e:
                logger.warning(f"Konnte Server-Ordner nicht laden: {e}")

        # Phase 10: Lade alle User-Tags für Filter-Dropdown
        all_tags = []
        tag_manager_mod = None
        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            all_tags = tag_manager_mod.TagManager.get_user_tags(db, user.id)
        except ImportError:
            logger.warning("TagManager nicht verfügbar")

        # Phase 10 Fix: Eager load alle Tags für alle Emails (verhindert n+1)
        email_ids = [mail.id for mail in mails]
        email_tags_map = {}
        if email_ids and tag_manager_mod:
            try:
                # Single query für alle Email-Tag-Assignments
                tag_assignments = (
                    db.query(models.EmailTagAssignment, models.EmailTag)
                    .join(
                        models.EmailTag,
                        models.EmailTagAssignment.tag_id == models.EmailTag.id,
                    )
                    .filter(
                        models.EmailTagAssignment.email_id.in_(email_ids),
                        models.EmailTag.user_id == user.id,
                    )
                    .all()
                )

                # Group by email_id
                for assignment, tag in tag_assignments:
                    if assignment.email_id not in email_tags_map:
                        email_tags_map[assignment.email_id] = []
                    email_tags_map[assignment.email_id].append(tag)
            except Exception as e:
                logger.warning(f"Tag eager loading fehlgeschlagen: {e}")

        # Zero-Knowledge: Entschlüsselung für Anzeige und Suche
        master_key = session.get("master_key")
        decrypted_mails = []

        # Dekryptiere Mail-Adressen der Accounts für Dropdown
        if master_key and user_accounts:
            for account in user_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = (
                            encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_username, master_key
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            f"Fehler beim Entschlüsseln der Account-Email: {e}"
                        )
                        account.decrypted_imap_username = None

        if master_key:
            for mail in mails:
                try:
                    # RawEmail entschlüsseln
                    decrypted_subject = (
                        encryption.EmailDataManager.decrypt_email_subject(
                            mail.raw_email.encrypted_subject or "", master_key
                        )
                    )
                    decrypted_sender = encryption.EmailDataManager.decrypt_email_sender(
                        mail.raw_email.encrypted_sender or "", master_key
                    )

                    # ProcessedEmail entschlüsseln
                    decrypted_summary_de = encryption.EmailDataManager.decrypt_summary(
                        mail.encrypted_summary_de or "", master_key
                    )
                    decrypted_tags = encryption.EmailDataManager.decrypt_summary(
                        mail.encrypted_tags or "", master_key
                    )

                    # Suche anwenden (falls nötig)
                    if search_term:
                        if not (
                            search_term.lower() in decrypted_subject.lower()
                            or search_term.lower() in decrypted_sender.lower()
                        ):
                            continue  # Skip diese Mail bei Suche

                    # Mail-Objekt mit entschlüsselten Daten erweitern
                    mail._decrypted_subject = decrypted_subject
                    mail._decrypted_sender = decrypted_sender
                    mail._decrypted_summary_de = decrypted_summary_de
                    mail._decrypted_tags = decrypted_tags

                    # Phase 10 Fix: Tags aus pre-loaded map holen (kein n+1)
                    mail.email_tags = email_tags_map.get(mail.id, [])

                    decrypted_mails.append(mail)

                except (ValueError, KeyError, Exception) as e:
                    logger.error(
                        f"Entschlüsselung fehlgeschlagen für RawEmail {mail.raw_email.id}: {type(e).__name__}"
                    )
                    continue
        else:
            # Ohne master_key können wir nichts anzeigen
            decrypted_mails = []

        # Phase 13: Sammle verfügbare Ordner aus ALLEN RawEmails des Users (nicht nur sichtbare)
        available_folders_query = (
            db.query(models.RawEmail.imap_folder)
            .filter(
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.RawEmail.imap_folder != None,
            )
            .distinct()
        )
        available_folders = sorted([f for (f,) in available_folders_query.all()])

        return render_template(
            "list_view.html",
            user=user,
            mails=decrypted_mails,
            filter_color=filter_color,
            filter_done=filter_done,
            search_term=search_term,
            user_accounts=user_accounts,
            filter_account_id=filter_account_id,
            all_tags=all_tags,
            filter_tag_ids=filter_tag_ids,
            # Phase 13: Neue Filter-Parameter
            filter_folder=filter_folder,
            available_folders=available_folders,
            server_folders=server_folders,
            filter_seen=filter_seen,
            filter_flagged=filter_flagged,
            filter_attachments=filter_attachments,
            filter_date_from=filter_date_from,
            filter_date_to=filter_date_to,
            sort_by=sort_by,
            sort_order=sort_order,
            # P2-007: Pagination
            page=page,
            total_pages=total_pages,
            total_count=total_count,
            per_page=per_page,
        )

    finally:
        db.close()


@app.route("/threads")
@login_required
def threads_view():
    """Thread-basierte Conversations-Ansicht (Phase 12)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        # Lade User-Accounts für Filter-Dropdown (wie bei /list)
        user_accounts = (
            db.query(models.MailAccount)
            .filter(models.MailAccount.user_id == user.id)
            .all()
        )
        
        # Dekryptiere Account-Email-Adressen für Dropdown
        master_key = session.get("master_key")
        if master_key and user_accounts:
            for account in user_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = (
                            encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_username, master_key
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Fehler beim Entschlüsseln der Account-Email: {e}")
                        account.decrypted_imap_username = None

        # Account-Filter aus Query-Parameter
        filter_account_id = request.args.get("mail_account")

        return render_template(
            "threads_view.html", 
            user=user, 
            user_accounts=user_accounts,
            filter_account_id=filter_account_id
        )

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>")
@login_required
def email_detail(raw_email_id):
    """Detailansicht einer einzelnen Mail (via raw_email_id)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not processed:
            return redirect(url_for("list_view"))

        raw = processed.raw_email
        priority_label = scoring.get_priority_label(processed.score)

        # Zero-Knowledge: Entschlüssele E-Mail für Anzeige
        master_key = session.get("master_key")
        decrypted_subject = ""
        decrypted_sender = ""
        decrypted_to = ""
        decrypted_cc = ""
        decrypted_bcc = ""
        decrypted_body = ""
        decrypted_summary_de = ""
        decrypted_text_de = ""
        decrypted_tags = ""
        decrypted_subject_sanitized = ""  # Phase 22
        decrypted_body_sanitized = ""     # Phase 22

        if master_key:
            # RawEmail entschlüsseln (mit individuellen try-except pro Feld!)
            try:
                decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                    raw.encrypted_subject or "", master_key
                )
            except Exception as e:
                logger.warning(f"Subject decryption failed for email {raw.id}: {e}")
                decrypted_subject = "(Entschlüsselung fehlgeschlagen)"
            
            try:
                decrypted_sender = encryption.EmailDataManager.decrypt_email_sender(
                    raw.encrypted_sender or "", master_key
                )
            except Exception as e:
                logger.warning(f"Sender decryption failed for email {raw.id}: {e}")
                decrypted_sender = "Unbekannt"
            
            # To/Cc/Bcc sind JSON: [{"name": "...", "email": "..."}]
            try:
                to_encrypted = raw.encrypted_to or ""
                if to_encrypted:
                    to_decrypted = encryption.EmailDataManager.decrypt_email_sender(to_encrypted, master_key)
                    if to_decrypted:
                        import json
                        to_list = json.loads(to_decrypted)
                        decrypted_to = ", ".join([f"{item.get('name', '')} <{item.get('email', '')}>" if item.get('name') else item.get('email', '') for item in to_list])
            except Exception as e:
                logger.warning(f"To decryption/parsing failed for email {raw.id}: {e}")
            
            try:
                cc_encrypted = raw.encrypted_cc or ""
                if cc_encrypted:
                    cc_decrypted = encryption.EmailDataManager.decrypt_email_sender(cc_encrypted, master_key)
                    if cc_decrypted:
                        import json
                        cc_list = json.loads(cc_decrypted)
                        decrypted_cc = ", ".join([f"{item.get('name', '')} <{item.get('email', '')}>" if item.get('name') else item.get('email', '') for item in cc_list])
            except Exception as e:
                logger.warning(f"Cc decryption/parsing failed for email {raw.id}: {e}")
            
            try:
                bcc_encrypted = raw.encrypted_bcc or ""
                if bcc_encrypted:
                    bcc_decrypted = encryption.EmailDataManager.decrypt_email_sender(bcc_encrypted, master_key)
                    if bcc_decrypted:
                        import json
                        bcc_list = json.loads(bcc_decrypted)
                        decrypted_bcc = ", ".join([f"{item.get('name', '')} <{item.get('email', '')}>" if item.get('name') else item.get('email', '') for item in bcc_list])
            except Exception as e:
                logger.warning(f"Bcc decryption/parsing failed for email {raw.id}: {e}")
            
            try:
                decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                    raw.encrypted_body or "", master_key
                )
            except Exception as e:
                logger.warning(f"Body decryption failed for email {raw.id}: {e}")
                decrypted_body = "(Entschlüsselung fehlgeschlagen)"

            # ProcessedEmail entschlüsseln
            try:
                decrypted_summary_de = encryption.EmailDataManager.decrypt_summary(
                    processed.encrypted_summary_de or "", master_key
                )
            except Exception as e:
                logger.warning(f"Summary decryption failed for email {processed.id}: {e}")
                
            try:
                decrypted_text_de = encryption.EmailDataManager.decrypt_summary(
                    processed.encrypted_text_de or "", master_key
                )
            except Exception as e:
                logger.warning(f"Text decryption failed for email {processed.id}: {e}")
                
            try:
                decrypted_tags = encryption.EmailDataManager.decrypt_summary(
                    processed.encrypted_tags or "", master_key
                )
            except Exception as e:
                logger.warning(f"Tags decryption failed for email {processed.id}: {e}")
            
            # Phase 22: Anonymisierte Version entschlüsseln (wenn vorhanden)
            try:
                if raw.encrypted_subject_sanitized:
                    decrypted_subject_sanitized = encryption.EmailDataManager.decrypt_email_subject(
                        raw.encrypted_subject_sanitized, master_key
                    )
            except Exception as e:
                logger.warning(f"Sanitized subject decryption failed for email {raw.id}: {e}")
            
            try:
                if raw.encrypted_body_sanitized:
                    decrypted_body_sanitized = encryption.EmailDataManager.decrypt_email_body(
                        raw.encrypted_body_sanitized, master_key
                    )
            except Exception as e:
                logger.warning(f"Sanitized body decryption failed for email {raw.id}: {e}")

        # Phase 10: Lade Email-Tags
        email_tags = []
        all_user_tags = []
        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            email_tags = tag_manager_mod.TagManager.get_email_tags(
                db, processed.id, user.id  # processed.id für Tag-Zuordnung
            )
            all_user_tags = tag_manager_mod.TagManager.get_user_tags(db, user.id)
        except ImportError:
            logger.warning("TagManager nicht verfügbar")

        return render_template(
            "email_detail.html",
            user=user,
            email=processed,
            raw=raw,
            raw_email=raw,  # Phase 22: Alias für Template-Kompatibilität
            decrypted_subject=decrypted_subject,
            decrypted_sender=decrypted_sender,
            decrypted_to=decrypted_to,
            decrypted_cc=decrypted_cc,
            decrypted_bcc=decrypted_bcc,
            decrypted_body=decrypted_body,
            decrypted_summary_de=decrypted_summary_de,
            decrypted_text_de=decrypted_text_de,
            decrypted_tags=decrypted_tags,
            decrypted_subject_sanitized=decrypted_subject_sanitized,  # Phase 22
            decrypted_body_sanitized=decrypted_body_sanitized,        # Phase 22
            priority_label=priority_label,
            email_tags=email_tags,
            all_user_tags=all_user_tags,
        )

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/render-html")
@login_required
def render_email_html(raw_email_id: int):
    """Rendert E-Mail-HTML mit lockerer CSP (Fonts/Bilder erlaubt, Scripts blockiert)

    Dieser Endpoint wird von <iframe> in email_detail.html verwendet.
    CSP erlaubt externe Ressourcen für korrektes E-Mail-Rendering,
    blockiert aber alle Scripts (XSS-Schutz).

    Setzt eigene CSP-Header (g.skip_security_headers umgeht globalen Hook).
    """
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            logger.error(f"render_email_html: User not found (raw_email_id={raw_email_id})")
            return "Unauthorized", 403

        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not processed:
            logger.error(
                f"render_email_html: Email {raw_email_id} not found for user {user.id}"
            )
            return "Email not found", 404

        # Zero-Knowledge: Entschlüssele E-Mail-Body
        master_key = session.get("master_key")
        if not master_key:
            logger.error(f"render_email_html: master_key missing in session")
            return "Session expired", 401

        try:
            decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                processed.raw_email.encrypted_body or "", master_key
            )
        except Exception as e:
            logger.error(
                f"render_email_html: Entschlüsselung fehlgeschlagen für Email {raw_email_id}: {type(e).__name__}: {e}"
            )
            return "Decryption failed", 500

        # Marker für after_request Hook: Überschreibe Headers nicht (MUSS VOR make_response!)
        g.skip_security_headers = True

        # Wrap email body with proper HTML structure to prevent Quirks Mode
        html_content = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 10px; }}
        img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
{decrypted_body}
</body>
</html>"""

        # Response mit lockerer CSP nur für E-Mail-Content
        response = make_response(html_content)
        response.headers["Content-Type"] = "text/html; charset=utf-8"

        # CSP für E-Mail-Rendering: Erlaube externe Fonts/Bilder (PayPal, etc.)
        # WICHTIG: Scripts IMMER blockiert (XSS-Schutz)
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "style-src 'unsafe-inline'; "
            "img-src https: data:; "
            "font-src https: data:; "
            "script-src 'none'"
        )

        # Security Headers (ohne X-Frame-Options für iframe embedding)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response

    except Exception as e:
        logger.error(f"render_email_html: Unhandled exception: {type(e).__name__}: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return "Internal Server Error", 500

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/done", methods=["POST"])
@login_required
def mark_done(raw_email_id):
    """Markiert eine Mail als erledigt"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if email:
            email.done = True
            email.done_at = datetime.now(UTC)
            db.commit()
            logger.info(f"✅ Mail {raw_email_id} als erledigt markiert")

        return redirect(request.referrer or url_for("list_view"))

    except Exception as e:
        db.rollback()  # Rollback bei Fehler
        # Security: Log details internally, show generic message to user
        logger.error(f"Fehler bei mark_done: {type(e).__name__}")
        flash("Fehler beim Markieren der E-Mail. Bitte versuche es erneut.", "error")
        return redirect(url_for("list_view"))

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/undo", methods=["POST"])
@login_required
def mark_undone(raw_email_id):
    """Macht 'erledigt'-Markierung rückgängig"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if email:
            email.done = False
            email.done_at = None
            db.commit()
            logger.info(f"↩️  Mail {raw_email_id} zurückgesetzt")

        return redirect(request.referrer or url_for("list_view"))

    except Exception as e:
        db.rollback()  # Rollback bei Fehler
        logger.error(f"Fehler bei mark_undone: {type(e).__name__}")
        return redirect(url_for("list_view"))

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/reprocess", methods=["POST"])
@login_required
def reprocess_email(raw_email_id):
    """Reprocessed eine fehlgeschlagene Email"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        provider = (user.preferred_ai_provider or "ollama").lower()
        resolved_model = ai_client.resolve_model(provider, user.preferred_ai_model)
        use_cloud = ai_client.provider_requires_cloud(provider)
        sanitize_level = sanitizer.get_sanitization_level(use_cloud)

        raw_email = email.raw_email
        if not raw_email:
            return jsonify({"error": "RawEmail nicht gefunden"}), 404

        # Zero-Knowledge: Entschlüssele E-Mail-Daten
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Session abgelaufen. Bitte neu einloggen."}), 401

        decrypted = decrypt_raw_email(raw_email, master_key)

        try:
            client = ai_client.build_client(provider, model=resolved_model)
            sanitized_body = sanitizer.sanitize_email(
                decrypted["body"], level=sanitize_level
            )

            # Phase E: analyze_email() hat keinen sender Parameter mehr
            result = client.analyze_email(
                subject=decrypted["subject"],
                body=sanitized_body,
                language="de"
            )

            priority = scoring.analyze_priority(
                result["dringlichkeit"], result["wichtigkeit"]
            )

            # Zero-Knowledge: Verschlüssele KI-Ergebnisse
            encrypted_summary = encryption.EmailDataManager.encrypt_summary(
                result["summary_de"], master_key
            )
            encrypted_text = encryption.EmailDataManager.encrypt_summary(
                result["text_de"], master_key
            )
            encrypted_tags = encryption.EmailDataManager.encrypt_summary(
                ",".join(result.get("tags", [])), master_key
            )

            email.dringlichkeit = result["dringlichkeit"]
            email.wichtigkeit = result["wichtigkeit"]
            email.kategorie_aktion = result["kategorie_aktion"]
            email.encrypted_tags = encrypted_tags
            email.spam_flag = result["spam_flag"]
            email.encrypted_summary_de = encrypted_summary
            email.encrypted_text_de = encrypted_text
            email.score = priority["score"]
            email.matrix_x = priority["matrix_x"]
            email.matrix_y = priority["matrix_y"]
            email.farbe = priority["farbe"]
            email.base_model = resolved_model
            email.base_provider = provider
            email.processed_at = datetime.now(UTC)  # Aktualisiere Analyse-Zeit
            email.rebase_at = datetime.now(UTC)  # Neue Verarbeitung = Rebase
            email.updated_at = datetime.now(UTC)
            email.optimization_status = models.OptimizationStatus.PENDING.value

            db.commit()
            logger.info(f"✅ Mail {raw_email_id} erneut verarbeitet: Score={email.score}")

            return jsonify(
                {
                    "status": "success",
                    "message": "Email erfolgreich neu verarbeitet",
                    "score": email.score,
                    "farbe": email.farbe,
                }
            )

        except Exception as proc_err:
            db.rollback()  # Rollback bei Verarbeitungsfehler
            logger.error(f"❌ Fehler bei Reprocessing von Email {raw_email_id}: {proc_err}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Verarbeitung fehlgeschlagen: {str(proc_err)}",
                    }
                ),
                500,
            )

    except Exception as e:
        db.rollback()  # Rollback bei allgemeinem Fehler
        logger.error(f"Fehler bei reprocess_email: {type(e).__name__}")
        return jsonify({"error": "Verarbeitung fehlgeschlagen"}), 500

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/optimize", methods=["POST"])
@login_required
def optimize_email(raw_email_id):
    """Triggert Optimize-Pass für Email (bessere Kategorisierung mit optimize-Provider)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        provider_optimize = (user.preferred_ai_provider_optimize or "ollama").lower()
        resolved_model = ai_client.resolve_model(
            provider_optimize, user.preferred_ai_model_optimize
        )
        use_cloud = ai_client.provider_requires_cloud(provider_optimize)
        sanitize_level = sanitizer.get_sanitization_level(use_cloud)

        raw_email = email.raw_email
        if not raw_email:
            return jsonify({"error": "RawEmail nicht gefunden"}), 404

        # Zero-Knowledge: Entschlüssele E-Mail-Daten
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Session abgelaufen. Bitte neu einloggen."}), 401

        decrypted = decrypt_raw_email(raw_email, master_key)

        try:
            client = ai_client.build_client(provider_optimize, model=resolved_model)
            logger.info(f"🤖 Optimize-Pass mit {provider_optimize.upper()}/{resolved_model}")
            sanitized_body = sanitizer.sanitize_email(
                decrypted["body"], level=sanitize_level
            )

            # Phase E: analyze_email() hat keinen sender Parameter mehr
            result = client.analyze_email(
                subject=decrypted["subject"],
                body=sanitized_body,
                language="de"
            )

            priority = scoring.analyze_priority(
                result["dringlichkeit"], result["wichtigkeit"]
            )

            # Zero-Knowledge: Verschlüssele KI-Ergebnisse
            encrypted_summary = encryption.EmailDataManager.encrypt_summary(
                result["summary_de"], master_key
            )
            encrypted_text = encryption.EmailDataManager.encrypt_summary(
                result["text_de"], master_key
            )
            encrypted_tags = encryption.EmailDataManager.encrypt_summary(
                ",".join(result.get("tags", [])), master_key
            )

            email.optimize_dringlichkeit = result["dringlichkeit"]
            email.optimize_wichtigkeit = result["wichtigkeit"]
            email.optimize_kategorie_aktion = result["kategorie_aktion"]
            email.optimize_encrypted_tags = encrypted_tags
            email.optimize_spam_flag = result["spam_flag"]
            email.optimize_encrypted_summary_de = encrypted_summary
            email.optimize_encrypted_text_de = encrypted_text
            email.optimize_score = priority["score"]
            email.optimize_matrix_x = priority["matrix_x"]
            email.optimize_matrix_y = priority["matrix_y"]
            email.optimize_farbe = priority["farbe"]
            # Phase Y2: Extract optimize confidence if available
            email.optimize_confidence = result.get("_phase_y_confidence") if result else None
            email.optimize_model = resolved_model
            email.optimize_provider = provider_optimize
            email.optimization_status = models.OptimizationStatus.DONE.value
            email.optimization_completed_at = datetime.now(UTC)
            email.updated_at = datetime.now(UTC)

            db.commit()
            logger.info(f"✅ Mail {raw_email_id} optimiert: Score={email.optimize_score}")

            return jsonify(
                {
                    "status": "success",
                    "message": "Email erfolgreich optimiert",
                    "score": email.optimize_score,
                    "farbe": email.optimize_farbe,
                    "kategorie_aktion": email.optimize_kategorie_aktion,
                    "dringlichkeit": email.optimize_dringlichkeit,
                    "wichtigkeit": email.optimize_wichtigkeit,
                }
            )

        except Exception as proc_err:
            db.rollback()  # Rollback bei Optimierungsfehler
            email.optimization_status = models.OptimizationStatus.FAILED.value
            email.optimization_tried_at = datetime.now(UTC)
            db.commit()
            logger.error(f"❌ Fehler bei Optimize von Email {email_id}: {proc_err}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Optimierung fehlgeschlagen: {str(proc_err)}",
                    }
                ),
                500,
            )

    except Exception as e:
        db.rollback()  # Rollback bei allgemeinem Fehler
        logger.error(f"Fehler bei optimize_email: {type(e).__name__}")
        return jsonify({"error": "Optimierung fehlgeschlagen"}), 500

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/correct", methods=["POST"])
def correct_email(raw_email_id: int):
    """Speichert User-Korrektionen für eine Email (für Training)."""
    if not current_user:
        return jsonify({"error": "Nicht authentifiziert"}), 401

    db = get_db_session()
    try:
        user = db.query(models.User).filter(models.User.id == current_user.id).first()
        if not user:
            return jsonify({"error": "User nicht gefunden"}), 404

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        data = request.get_json() or {}

        email.user_override_dringlichkeit = data.get("dringlichkeit")
        email.user_override_wichtigkeit = data.get("wichtigkeit")
        email.user_override_kategorie = data.get("kategorie")
        email.user_override_spam_flag = data.get("spam_flag")
        email.user_override_tags = (
            ",".join(data.get("tags", [])) if data.get("tags") else None
        )
        # Note: Korrektur-Notiz wird verschlüsselt gespeichert (encrypted_correction_note)
        # Frontend sendet Klartext, Backend verschlüsselt vor DB-Speicherung
        email.encrypted_correction_note = data.get("note")
        email.correction_timestamp = datetime.now(UTC)
        email.updated_at = datetime.now(UTC)

        db.commit()

        logger.info(f"✅ Mail {raw_email_id} korrigiert durch User {user.id}")

        # Phase 11b: Online-Learning - Inkrementelles Lernen aus Korrektur
        _trigger_online_learning(email, data)

        return jsonify(
            {
                "status": "success",
                "message": "Korrektur gespeichert! Diese wird beim nächsten Training berücksichtigt.",
                "correction_count": db.query(models.ProcessedEmail)
                .filter(models.ProcessedEmail.user_override_dringlichkeit != None)
                .count(),
            }
        )

    except Exception as e:
        db.rollback()  # Rollback bei Fehler
        logger.error(f"Fehler beim Speichern der Korrektur: {type(e).__name__}")
        return jsonify({"error": "Speichern fehlgeschlagen"}), 500
    finally:
        db.close()


@app.route("/api/email/<int:raw_email_id>/flags", methods=["GET"])
@login_required
def get_email_flags(raw_email_id):
    """Holt aktuelle IMAP-Flags einer Email vom Server"""
    if not current_user:
        return jsonify({"error": "Nicht authentifiziert"}), 401

    db = get_db_session()
    try:
        imap_flags_mod = importlib.import_module("src.16_imap_flags")

        user = db.query(models.User).filter(models.User.id == current_user.id).first()
        if not user:
            return jsonify({"error": "User nicht gefunden"}), 404

        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not processed:
            return jsonify({"error": "Email nicht gefunden"}), 404

        raw_email = processed.raw_email

        parser = imap_flags_mod.IMAPFlagParser()

        return jsonify(
            {
                "status": "success",
                "imap_flags": raw_email.imap_flags or "",
                "is_seen": parser.is_seen(raw_email.imap_flags or ""),
                "is_answered": parser.is_answered(raw_email.imap_flags or ""),
                "is_flagged": parser.is_flagged(raw_email.imap_flags or ""),
                "is_deleted": parser.is_deleted(raw_email.imap_flags or ""),
                "imap_uid": raw_email.imap_uid,
                "imap_folder": raw_email.imap_folder,
                "imap_last_seen_at": raw_email.imap_last_seen_at.isoformat()
                if raw_email.imap_last_seen_at
                else None,
            }
        )

    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Flags: {type(e).__name__}")
        return jsonify({"error": "Abrufen fehlgeschlagen"}), 500
    finally:
        db.close()


@app.route("/retrain", methods=["POST"])
def retrain_models():
    """Trainiert ML-Klassifikatoren aus User-Korrektionen."""
    if not current_user:
        return jsonify({"error": "Nicht authentifiziert"}), 401

    try:
        from train_classifier import train_from_corrections

        trained_count = train_from_corrections()

        if trained_count == 0:
            return (
                jsonify(
                    {
                        "status": "no_data",
                        "message": "Keine ausreichenden Korrektionen zum Trainieren vorhanden. Mindestens 5 Korrektionen pro Klassifikator erforderlich.",
                        "trained": 0,
                    }
                ),
                200,
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"✅ {trained_count} Klassifikator(en) erfolgreich trainiert. System nutzt jetzt Ihre Feedback-Labels!",
                    "trained": trained_count,
                }
            ),
            200,
        )

    except ImportError:
        return (
            jsonify(
                {
                    "error": "scikit-learn nicht installiert. Bitte: pip install scikit-learn"
                }
            ),
            500,
        )

    except Exception as e:
        logger.error(f"Fehler beim Retraining: {type(e).__name__}")
        return jsonify({"error": "Retraining fehlgeschlagen"}), 500


@app.route("/api/training-stats", methods=["GET"])
def get_training_stats():
    """Gibt Statistiken über Training für UI-Dashboard."""
    if not current_user:
        return jsonify({"error": "Nicht authentifiziert"}), 401

    db = get_db_session()
    try:
        ProcessedEmail = models.ProcessedEmail

        total_emails = db.query(ProcessedEmail).count()
        corrections_count = (
            db.query(ProcessedEmail)
            .filter(ProcessedEmail.user_override_dringlichkeit != None)
            .count()
        )

        last_correction = (
            db.query(ProcessedEmail)
            .filter(ProcessedEmail.correction_timestamp != None)
            .order_by(ProcessedEmail.correction_timestamp.desc())
            .first()
        )

        last_correction_date = None
        if last_correction and last_correction.correction_timestamp:
            last_correction_date = last_correction.correction_timestamp.isoformat()

        from pathlib import Path

        classifier_dir = Path(__file__).resolve().parent / "classifiers"
        trained_models = []
        if classifier_dir.exists():
            for f in classifier_dir.glob("*_clf.pkl"):
                model_name = f.stem.replace("_clf", "")
                trained_models.append(
                    {"name": model_name, "exists": True, "modified": f.stat().st_mtime}
                )

        return (
            jsonify(
                {
                    "total_emails": total_emails,
                    "corrections_count": corrections_count,
                    "trained_models_count": len(trained_models),
                    "trained_models": trained_models,
                    "last_correction_date": last_correction_date,
                    "ready_for_training": corrections_count >= 5,
                }
            ),
            200,
        )

    finally:
        db.close()


@app.route("/api/models/<provider>")
@login_required
def api_get_models_for_provider(provider: str):
    """
    API: Dynamische Model-Abfrage für Provider.
    
    Returns:
        JSON: {
            "provider": "ollama",
            "models": [
                {"id": "llama3.2:1b", "name": "Llama 3.2 1B", "type": "chat"},
                {"id": "all-minilm:22m", "name": "All-MiniLM 22M", "type": "embedding"},
                ...
            ]
        }
    """
    try:
        # Nummerierte Module brauchen importlib!
        model_discovery = importlib.import_module('.04_model_discovery', 'src')
        
        # Modelle dynamisch von Provider abrufen
        models_list = model_discovery.get_available_models(provider)
        
        return jsonify({
            "provider": provider,
            "models": models_list
        }), 200
        
    except Exception as e:
        logger.error(f"Model discovery failed for {provider}: {e}")
        return jsonify({
            "provider": provider,
            "models": [],
            "error": str(e)
        }), 500


@app.route("/reply-styles")
@login_required
def reply_styles_page():
    """Seite für Antwort-Stil-Einstellungen (Feature: FEATURE_REPLY_STYLES)"""
    return render_template("reply_styles.html")


@app.route("/settings")
@login_required
def settings():
    """Settings-Seite: Mail-Accounts, 2FA, AI-Provider (Base + Optimize), etc."""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        mail_accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()

        # Zero-Knowledge: Entschlüssele Mail-Account-Daten für Anzeige
        master_key = session.get("master_key")
        if master_key:
            for account in mail_accounts:
                try:
                    if account.encrypted_imap_server:
                        account.imap_server = (
                            encryption.CredentialManager.decrypt_server(
                                account.encrypted_imap_server, master_key
                            )
                        )
                    if account.encrypted_imap_username:
                        account.imap_username = (
                            encryption.CredentialManager.decrypt_email_address(
                                account.encrypted_imap_username, master_key
                            )
                        )
                    if account.encrypted_smtp_server:
                        account.smtp_server = (
                            encryption.CredentialManager.decrypt_server(
                                account.encrypted_smtp_server, master_key
                            )
                        )
                    if account.encrypted_smtp_username:
                        account.smtp_username = (
                            encryption.CredentialManager.decrypt_email_address(
                                account.encrypted_smtp_username, master_key
                            )
                        )
                except Exception as e:
                    logger.warning(
                        f"Konnte Account {account.id} nicht entschlüsseln: {e}"
                    )
                    account.imap_server = "***verschlüsselt***"
                    account.imap_username = "***verschlüsselt***"

        # 3 AI Settings (Embedding / Base / Optimize)
        selected_provider_embedding = (user.preferred_embedding_provider or "ollama").lower()
        selected_model_embedding = user.preferred_embedding_model or "all-minilm:22m"
        
        selected_provider_base = (user.preferred_ai_provider or "ollama").lower()
        selected_model_base = user.preferred_ai_model or "llama3.2:1b"

        selected_provider_optimize = (
            user.preferred_ai_provider_optimize or "ollama"
        ).lower()
        selected_model_optimize = user.preferred_ai_model_optimize or "llama3.2:3b"

        # Phase 13C Part 4: User Fetch Preferences (global)
        user_prefs = {
            'mails_per_folder': getattr(user, 'fetch_mails_per_folder', 100),
            'max_total_mails': getattr(user, 'fetch_max_total', 0),
            'use_delta_sync': getattr(user, 'fetch_use_delta_sync', True),
        }

        from datetime import datetime
        
        return render_template(
            "settings.html",
            user=user,
            mail_accounts=mail_accounts,
            totp_enabled=user.totp_enabled,
            ai_selected_provider_embedding=selected_provider_embedding,
            ai_selected_model_embedding=selected_model_embedding,
            ai_selected_provider_base=selected_provider_base,
            ai_selected_model_base=selected_model_base,
            ai_selected_provider_optimize=selected_provider_optimize,
            ai_selected_model_optimize=selected_model_optimize,
            user_prefs=user_prefs,
            now=datetime.now,
        )

    finally:
        db.close()


@app.route("/mail-fetch-config")
@login_required
def mail_fetch_config():
    """Mail Fetch Configuration: AI Analysis & Anonymization Settings"""
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))
        
        # Get mail accounts for configuration
        mail_accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()
        
        # Zero-Knowledge: Entschlüssele Email-Adressen für Anzeige
        master_key = session.get("master_key")
        if master_key and mail_accounts:
            for account in mail_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = (
                            encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_username, master_key
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Fehler beim Entschlüsseln der Account-Email: {e}")
                        account.decrypted_imap_username = None
        
        return render_template(
            "mail_fetch_config.html",
            user=user,
            mail_accounts=mail_accounts
        )
    finally:
        db.close()


@app.route("/whitelist")
@login_required
def whitelist():
    """Whitelist/Trusted Senders Management Page"""
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))
        
        # Get mail accounts for dropdown
        mail_accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()
        
        # Zero-Knowledge: Entschlüssele Email-Adressen für Anzeige
        master_key = session.get("master_key")
        if master_key and mail_accounts:
            for account in mail_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = (
                            encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_username, master_key
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Fehler beim Entschlüsseln der Account-Email: {e}")
                        account.decrypted_imap_username = None
        
        return render_template(
            "whitelist.html",
            user=user,
            mail_accounts=mail_accounts
        )
    finally:
        db.close()


@app.route("/ki-prio")
@login_required
def ki_prio():
    """KI-gestützte E-Mail Priorisierung: Konfiguration für spaCy Hybrid Pipeline"""
    return render_template("phase_y_config.html")


@app.route("/settings/fetch-config", methods=["POST"])
@login_required
def save_fetch_config():
    """Speichert Fetch-Präferenzen für einen spezifischen Account
    
    Phase 13C Part 6: Account-spezifische Filter (statt User-global)
    """
    import json
    from datetime import datetime
    
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        # Part 6: Account-ID ist erforderlich
        account_id = request.form.get('account_id')
        if not account_id:
            flash("❌ Bitte Account auswählen", "error")
            return redirect(url_for("settings"))
        
        account = db.query(models.MailAccount).filter(
            models.MailAccount.id == account_id,
            models.MailAccount.user_id == user.id
        ).first()
        
        if not account:
            flash("❌ Account nicht gefunden", "error")
            return redirect(url_for("settings"))

        # Part 4: Basis-Einstellungen (bleiben beim User)
        mails_per_folder = int(request.form.get('mails_per_folder', 100))
        max_total_mails = int(request.form.get('max_total_mails', 0))
        use_delta_sync = request.form.get('use_delta_sync') == 'on'

        # Part 5: Erweiterte Filter (jetzt pro Account)
        since_date_str = request.form.get('since_date', '').strip()
        unseen_only = request.form.get('unseen_only') == 'on'
        include_folders = request.form.getlist('include_folders')  # Mehrfachauswahl
        exclude_folders = request.form.getlist('exclude_folders')

        # Validierung Part 4
        if mails_per_folder < 10 or mails_per_folder > 1000:
            flash("❌ Mails pro Ordner muss zwischen 10 und 1000 liegen", "error")
            return redirect(url_for("settings"))
        
        if max_total_mails < 0 or max_total_mails > 10000:
            flash("❌ Max. Gesamt muss zwischen 0 und 10000 liegen", "error")
            return redirect(url_for("settings"))

        # Part 5: Datum parsen
        since_date = None
        if since_date_str:
            try:
                since_date = datetime.strptime(since_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("❌ Ungültiges Datum-Format (YYYY-MM-DD erwartet)", "error")
                return redirect(url_for("settings"))

        # Speichern: Part 4 beim User
        user.fetch_mails_per_folder = mails_per_folder
        user.fetch_max_total = max_total_mails
        user.fetch_use_delta_sync = use_delta_sync
        
        # Part 6: Filter beim Account
        account.fetch_since_date = since_date
        account.fetch_unseen_only = unseen_only
        account.fetch_include_folders = json.dumps(include_folders) if include_folders else None
        account.fetch_exclude_folders = json.dumps(exclude_folders) if exclude_folders else None
        
        db.commit()

        # Feedback
        filters = []
        if since_date:
            filters.append(f"ab {since_date}")
        if unseen_only:
            filters.append("nur ungelesene")
        if include_folders:
            filters.append(f"Ordner: {', '.join(include_folders)}")
        
        filter_str = f" | Filter: {', '.join(filters)}" if filters else ""
        flash(f"✅ Filter für '{account.name}' gespeichert{filter_str}", "success")
        return redirect(url_for("settings") + f"#fetch_config_account_{account_id}")

    except Exception as e:
        logger.error(f"Fehler beim Speichern der Fetch-Config: {e}")
        flash("❌ Fehler beim Speichern", "error")
        return redirect(url_for("settings"))

    finally:
        db.close()


@app.route("/account/<int:account_id>/fetch-filters", methods=["GET"])
@login_required
def get_account_fetch_filters(account_id):
    """Lade die Fetch-Filter für einen bestimmten Account
    
    Phase 13C Part 6: Account-spezifische Filter
    """
    import json
    
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        account = db.query(models.MailAccount).filter(
            models.MailAccount.id == account_id,
            models.MailAccount.user_id == user.id
        ).first()
        
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        # Parse JSON Felder
        include_folders = []
        exclude_folders = []
        
        if account.fetch_include_folders:
            try:
                include_folders = json.loads(account.fetch_include_folders)
            except:
                pass
        
        if account.fetch_exclude_folders:
            try:
                exclude_folders = json.loads(account.fetch_exclude_folders)
            except:
                pass
        
        return jsonify({
            "account_id": account_id,
            "account_name": account.name,
            "since_date": account.fetch_since_date.strftime('%Y-%m-%d') if account.fetch_since_date else None,
            "unseen_only": account.fetch_unseen_only or False,
            "include_folders": include_folders,
            "exclude_folders": exclude_folders,
            "has_filters": bool(account.fetch_since_date or account.fetch_unseen_only or include_folders or exclude_folders)
        })
    
    except Exception as e:
        logger.error(f"Fehler beim Laden der Account-Filter {account_id}: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        db.close()


@app.route("/tags")
@login_required
def tags_view():
    """Tag-Management-Seite"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        # Lade TagManager dynamisch
        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            TagManager = tag_manager_mod.TagManager
        except ImportError as e:
            logger.error(f"TagManager konnte nicht geladen werden: {e}")
            return render_template("tags.html", user=user, tags=[])

        # Hole alle Tags des Users
        tags = TagManager.get_user_tags(db, user.id)

        # Zähle E-Mails pro Tag
        tags_with_counts = []
        for tag in tags:
            email_count = (
                db.query(models.EmailTagAssignment)
                .filter(models.EmailTagAssignment.tag_id == tag.id)
                .count()
            )
            tags_with_counts.append(
                {
                    "id": tag.id,
                    "name": tag.name,
                    "color": tag.color,
                    "description": tag.description,  # Phase F.2: Description für Edit-Modal
                    "email_count": email_count,
                }
            )

        return render_template(
            "tags.html", user=user, tags=tags_with_counts
        )

    finally:
        db.close()


@app.route("/api/accounts", methods=["GET"])
@login_required
def api_get_accounts():
    """API: Alle Mail-Accounts des Users abrufen"""
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()
        
        # Zero-Knowledge: Entschlüssele Email-Adressen für Anzeige
        master_key = session.get("master_key")
        result_accounts = []
        
        for acc in accounts:
            email = acc.name  # Fallback
            
            if master_key and acc.auth_type == "imap" and acc.encrypted_imap_username:
                try:
                    email = encryption.EmailDataManager.decrypt_email_sender(
                        acc.encrypted_imap_username, master_key
                    )
                except Exception as e:
                    logger.warning(f"Fehler beim Entschlüsseln der Account-Email: {e}")
            
            result_accounts.append({
                "id": acc.id,
                "name": acc.name,
                "email": email,
                "auth_type": acc.auth_type
            })
        
        return jsonify({"accounts": result_accounts}), 200
    
    except Exception as e:
        logger.error(f"Fehler beim Laden der Accounts: {e}")
        return jsonify({"error": "Fehler beim Laden"}), 500
    
    finally:
        db.close()


@app.route("/api/tags", methods=["GET"])
@login_required
def api_get_tags():
    """API: Alle User-Tags abrufen (für Learning-Modal)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            TagManager = tag_manager_mod.TagManager
        except ImportError:
            return jsonify([]), 200

        tags = TagManager.get_user_tags(db, user.id)

        return (
            jsonify(
                [{"id": tag.id, "name": tag.name, "color": tag.color} for tag in tags]
            ),
            200,
        )

    finally:
        db.close()


@app.route("/api/tags", methods=["POST"])
@login_required
def api_create_tag():
    """API: Tag erstellen (Phase F.2: mit description)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        
        # P1-003: Input-Validation
        try:
            name = validate_string(data.get("name"), "Tag-Name", min_len=1, max_len=50)
            color = validate_string(data.get("color", "#3B82F6"), "Farbe", min_len=4, max_len=20)
            description = validate_string(
                data.get("description"), "Beschreibung", 
                min_len=0, max_len=500, allow_empty=True
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            tag = tag_manager_mod.TagManager.create_tag(
                db, user.id, name, color, description=description
            )

            return jsonify({
                "id": tag.id, 
                "name": tag.name, 
                "color": tag.color,
                "description": tag.description
            }), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    finally:
        db.close()


@app.route("/api/tags/<int:tag_id>", methods=["PUT"])
@login_required
def api_update_tag(tag_id):
    """API: Tag aktualisieren (Phase F.2: mit description)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        
        # P1-003: Input-Validation
        try:
            name = validate_string(data.get("name"), "Tag-Name", min_len=1, max_len=50) if data.get("name") else None
            color = validate_string(data.get("color"), "Farbe", min_len=4, max_len=20) if data.get("color") else None
            description = validate_string(
                data.get("description"), "Beschreibung", 
                min_len=0, max_len=500, allow_empty=True
            ) if "description" in data else None
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            tag = tag_manager_mod.TagManager.update_tag(
                db, tag_id, user.id, name=name, color=color, description=description
            )

            if not tag:
                return jsonify({"error": "Tag nicht gefunden"}), 404

            return jsonify({"id": tag.id, "name": tag.name, "color": tag.color})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    finally:
        db.close()


@app.route("/api/tags/<int:tag_id>", methods=["DELETE"])
@login_required
def api_delete_tag(tag_id):
    """API: Tag löschen"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            success = tag_manager_mod.TagManager.delete_tag(db, tag_id, user.id)

            if not success:
                return jsonify({"error": "Tag nicht gefunden"}), 404

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    finally:
        db.close()


@app.route("/api/emails/<int:raw_email_id>/tags", methods=["GET"])
@login_required
def api_get_email_tags(raw_email_id):
    """API: Tags einer E-Mail abrufen (für Learning-Modal)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        try:
            # Hole processed_email.id via raw_email.id
            processed = (
                db.query(models.ProcessedEmail)
                .join(models.RawEmail)
                .filter(
                    models.RawEmail.id == raw_email_id,
                    models.RawEmail.user_id == user.id,
                    models.RawEmail.deleted_at == None
                )
                .first()
            )
            
            if not processed:
                return jsonify([]), 200
            
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            tags = tag_manager_mod.TagManager.get_email_tags(db, processed.id, user.id)

            return (
                jsonify(
                    [
                        {"id": tag.id, "name": tag.name, "color": tag.color}
                        for tag in tags
                    ]
                ),
                200,
            )
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Email-Tags: {e}")
            return jsonify([]), 200

    finally:
        db.close()


@app.route("/api/emails/<int:raw_email_id>/tag-suggestions", methods=["GET"])
@login_required
def api_get_tag_suggestions(raw_email_id):
    """
    API: Tag-Vorschläge für eine E-Mail abrufen (Phase F.2).

    Phase F.2: Verwendet Email-Embeddings direkt statt Text zu re-embedden.
    Schneller und effizienter da Embeddings bereits beim Fetch generiert wurden.
    """
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            
            # Phase F.2: Nutze Email-Embeddings direkt
            # 1. Hole RawEmail mit Embedding
            processed = (
                db.query(models.ProcessedEmail)
                .join(models.RawEmail)
                .filter(
                    models.RawEmail.id == raw_email_id,
                    models.RawEmail.user_id == user.id,
                    models.RawEmail.deleted_at == None
                )
                .first()
            )
            
            if not processed or not processed.raw_email:
                return jsonify({"suggestions": [], "email_id": raw_email_id, "method": "none"}), 200
            
            raw_email = processed.raw_email
            
            # 2. Wenn Email-Embedding vorhanden: Nutze Phase F.2 Methode
            if raw_email.email_embedding:
                # Bereits zugewiesene Tags holen
                assigned_tag_ids = [
                    assignment.tag_id 
                    for assignment in db.query(models.EmailTagAssignment)
                    .filter_by(email_id=processed.id).all()
                ]
                
                logger.info(f"Phase F.2: Email raw_id={raw_email_id} (processed_id={processed.id}) - Assigned tags: {assigned_tag_ids}")
                
                # Phase F.2 Enhanced: Email-Embedding-basierte Suggestions mit dynamischen Thresholds
                # min_similarity=None → Nutzt get_suggestion_threshold() (70-80% basierend auf Tag-Anzahl)
                tag_suggestions = tag_manager_mod.TagManager.suggest_tags_by_email_embedding(
                    db=db,
                    user_id=user.id,
                    email_embedding_bytes=raw_email.email_embedding,
                    top_k=5,
                    min_similarity=None,  # Dynamisch: 70% bei <= 5 Tags, 75% bei 6-15, 80% bei >= 16
                    exclude_tag_ids=assigned_tag_ids
                )
                
                suggestions = [
                    {
                        "id": tag.id,
                        "name": tag.name,
                        "color": tag.color,
                        "similarity": round(similarity, 3)
                    }
                    for tag, similarity in tag_suggestions
                ]
                
                logger.info(f"Phase F.2: Email raw_id={raw_email_id} - Found {len(suggestions)} suggestions")
                if suggestions:
                    logger.info(f"Phase F.2: Top suggestion: {suggestions[0]['name']} ({suggestions[0]['similarity']})")
                
                return jsonify({
                    "suggestions": suggestions, 
                    "email_id": raw_email_id,
                    "method": "embedding",  # Phase F.2
                    "embedding_available": True
                }), 200
            
            else:
                # Fallback: Alte text-basierte Methode (Phase 11c)
                # Für Emails ohne Embedding (z.B. alte Daten vor Phase F.1)
                suggestions = tag_manager_mod.TagManager.get_tag_suggestions_for_email(
                    db, processed.id, user.id, top_k=5
                )
                
                return jsonify({
                    "suggestions": suggestions, 
                    "email_id": raw_email_id,
                    "method": "text-fallback",  # Legacy
                    "embedding_available": False
                }), 200
                
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Tag-Vorschläge: {e}")
            return jsonify({"suggestions": [], "email_id": raw_email_id}), 200

    finally:
        db.close()


@app.route("/api/emails/<int:raw_email_id>/tags", methods=["POST"])
@login_required
def api_assign_tag_to_email(raw_email_id):
    """API: Tag zu E-Mail zuweisen"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        # Hole processed_email.id via raw_email.id
        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id
            )
            .first()
        )
        
        if not processed:
            return jsonify({"error": "Email nicht gefunden"}), 404

        data = request.get_json()
        tag_id = data.get("tag_id")

        if not tag_id:
            return jsonify({"error": "tag_id erforderlich"}), 400

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            success = tag_manager_mod.TagManager.assign_tag(
                db, processed.id, tag_id, user.id
            )

            if not success:
                return (
                    jsonify({"error": "Tag bereits zugewiesen oder nicht gefunden"}),
                    400,
                )

            # Learning: Update user_override_tags für ML-Training
            _update_user_override_tags(db, processed.id, user.id, tag_manager_mod)

            return jsonify({"success": True})
        except ValueError as e:
            return jsonify({"error": str(e)}), 404

    finally:
        db.close()


@app.route("/api/emails/<int:raw_email_id>/tags/<int:tag_id>", methods=["DELETE"])
@login_required
def api_remove_tag_from_email(raw_email_id, tag_id):
    """API: Tag von E-Mail entfernen"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        # Hole processed_email.id via raw_email.id
        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id
            )
            .first()
        )
        
        if not processed:
            return jsonify({"error": "Email nicht gefunden"}), 404

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            success = tag_manager_mod.TagManager.remove_tag(
                db, processed.id, tag_id, user.id
            )

            if not success:
                return jsonify({"error": "Tag-Verknüpfung nicht gefunden"}), 404

            # Learning: Update user_override_tags für ML-Training
            _update_user_override_tags(db, processed.id, user.id, tag_manager_mod)

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    finally:
        db.close()


@app.route("/api/emails/<int:raw_email_id>/tags/<int:tag_id>/reject", methods=["POST"])
@login_required
def api_reject_tag_for_email(raw_email_id, tag_id):
    """🚫 Phase F.3: Tag-Vorschlag ablehnen und als negatives Beispiel speichern"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        # Hole processed_email.id via raw_email.id
        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id
            )
            .first()
        )
        
        if not processed:
            return jsonify({"error": "Email nicht gefunden"}), 404

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            
            # Negative example hinzufügen
            success = tag_manager_mod.add_negative_example(
                db, tag_id, processed.id, rejection_source="ui"
            )

            if not success:
                return jsonify({"error": "Konnte negatives Beispiel nicht speichern"}), 500

            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"Fehler beim Ablehnen von Tag {tag_id} für Email raw_id={raw_email_id}: {e}")
            return jsonify({"error": str(e)}), 500

    finally:
        db.close()


@app.route("/api/tags/<int:tag_id>/negative-examples", methods=["GET"])
@login_required
def api_get_negative_examples(tag_id):
    """📊 Phase F.3: Liste negativer Beispiele für ein Tag abrufen"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        try:
            models_mod = importlib.import_module("src.02_models")
            
            # Tag validieren (gehört User?)
            tag = db.query(models_mod.EmailTag).filter_by(
                id=tag_id, user_id=user.id
            ).first()
            
            if not tag:
                return jsonify({"error": "Tag nicht gefunden"}), 404
            
            # Negative examples holen
            negative_examples = db.query(models_mod.TagNegativeExample).filter_by(
                tag_id=tag_id
            ).all()
            
            result = []
            for example in negative_examples:
                email = db.query(models_mod.ProcessedEmail).filter_by(
                    id=example.email_id
                ).first()
                
                if email:
                    result.append({
                        "email_id": example.email_id,
                        "subject": email.subject,
                        "created_at": example.created_at.isoformat() if example.created_at else None,
                        "rejection_source": example.rejection_source
                    })
            
            return jsonify({
                "tag_id": tag_id,
                "tag_name": tag.name,
                "negative_count": tag.negative_count or 0,
                "examples": result
            })
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen negativer Beispiele für Tag {tag_id}: {e}")
            return jsonify({"error": str(e)}), 500

    finally:
        db.close()


# ============================================================================
# Phase TAG-QUEUE: Tag Suggestion Queue Endpoints
# ============================================================================

@app.route("/tag-suggestions")
@login_required
def tag_suggestions_page():
    """UI: Tag-Vorschläge Seite"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return redirect("/login")

        suggestion_mod = importlib.import_module("src.services.tag_suggestion_service")
        tag_manager_mod = importlib.import_module("src.services.tag_manager")

        # Holt pending Vorschläge + User-Tags
        suggestions = suggestion_mod.TagSuggestionService.get_pending_suggestions(db, user.id)
        user_tags = tag_manager_mod.TagManager.get_user_tags(db, user.id)
        stats = suggestion_mod.TagSuggestionService.get_suggestion_stats(db, user.id)

        return render_template(
            "tag_suggestions.html",
            suggestions=suggestions,
            user_tags=user_tags,
            stats=stats,
            queue_enabled=user.enable_tag_suggestion_queue,
            auto_assignment_enabled=user.enable_auto_assignment  # NEW
        )

    finally:
        db.close()


@app.route("/api/tag-suggestions", methods=["GET"], endpoint="api_get_pending_tag_suggestions")
@login_required
def api_get_pending_tag_suggestions():
    """API: Pending Vorschläge abrufen"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        suggestion_mod = importlib.import_module("src.services.tag_suggestion_service")
        suggestions = suggestion_mod.TagSuggestionService.get_pending_suggestions(db, user.id)

        return jsonify(
            [
                {
                    "id": s.id,
                    "name": s.suggested_name,
                    "count": s.suggestion_count,
                    "source_email_subject": (
                        s.source_email.subject if s.source_email else None
                    ),
                    "source_email_id": s.source_email_id,
                    "created_at": s.created_at.isoformat(),
                }
                for s in suggestions
            ]
        )

    finally:
        db.close()


@app.route("/api/tag-suggestions/<int:id>/approve", methods=["POST"])
@login_required
def api_approve_suggestion(id):
    """API: Vorschlag annehmen → Tag erstellen"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json() or {}
        color = data.get("color", "#3B82F6")

        suggestion_mod = importlib.import_module("src.services.tag_suggestion_service")
        tag = suggestion_mod.TagSuggestionService.approve_suggestion(db, id, user.id, color)

        if not tag:
            return jsonify({"error": "Suggestion not found"}), 404

        return jsonify(
            {"success": True, "tag_id": tag.id, "tag_name": tag.name, "color": tag.color}
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        db.close()


@app.route("/api/tag-suggestions/<int:id>/reject", methods=["POST"])
@login_required
def api_reject_suggestion(id):
    """API: Vorschlag ablehnen"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        suggestion_mod = importlib.import_module("src.services.tag_suggestion_service")
        success = suggestion_mod.TagSuggestionService.reject_suggestion(db, id, user.id)

        return jsonify({"success": success})

    finally:
        db.close()


@app.route("/api/tag-suggestions/<int:id>/merge", methods=["POST"])
@login_required
def api_merge_suggestion(id):
    """API: Vorschlag zu existierendem Tag mergen"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        target_tag_id = data.get("target_tag_id")

        if not target_tag_id:
            return jsonify({"error": "target_tag_id required"}), 400

        suggestion_mod = importlib.import_module("src.services.tag_suggestion_service")
        success = suggestion_mod.TagSuggestionService.merge_suggestion(
            db, id, target_tag_id, user.id
        )

        return jsonify({"success": success})

    finally:
        db.close()


@app.route("/api/tag-suggestions/batch-reject", methods=["POST"])
@login_required
def api_batch_reject_suggestions():
    """API: Alle Vorschläge ablehnen"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        suggestion_mod = importlib.import_module("src.services.tag_suggestion_service")
        count = suggestion_mod.TagSuggestionService.batch_reject_by_user(db, user.id)

        return jsonify({"success": True, "count": count})

    finally:
        db.close()


@app.route("/api/tag-suggestions/batch-approve", methods=["POST"])
@login_required
def api_batch_approve_suggestions():
    """API: Alle Vorschläge annehmen"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json() or {}
        color = data.get("color", "#3B82F6")

        suggestion_mod = importlib.import_module("src.services.tag_suggestion_service")
        count = suggestion_mod.TagSuggestionService.batch_approve_by_user(db, user.id, color)

        return jsonify({"success": True, "count": count})

    finally:
        db.close()


@app.route("/api/tag-suggestions/settings", methods=["GET", "POST"])
@login_required
def api_tag_suggestion_settings():
    """API: Tag-Suggestion & Auto-Assignment Einstellungen lesen/setzen"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        if request.method == "GET":
            return jsonify({
                "enable_tag_suggestion_queue": user.enable_tag_suggestion_queue,
                "enable_auto_assignment": user.enable_auto_assignment
            })

        # POST: Update settings
        data = request.get_json()
        
        if "enable_tag_suggestion_queue" in data:
            user.enable_tag_suggestion_queue = data["enable_tag_suggestion_queue"]
        
        if "enable_auto_assignment" in data:
            user.enable_auto_assignment = data["enable_auto_assignment"]
        
        db.commit()

        return jsonify({
            "success": True, 
            "enable_tag_suggestion_queue": user.enable_tag_suggestion_queue,
            "enable_auto_assignment": user.enable_auto_assignment
        })

    except Exception as e:
        db.rollback()  # Rollback bei Fehler
        logger.error(f"Fehler bei tag_suggestion_settings: {type(e).__name__}")
        return jsonify({"error": "Einstellungen konnten nicht gespeichert werden"}), 500
    finally:
        db.close()


def _update_user_override_tags(db, email_id: int, user_id: int, tag_manager_mod):
    """Helper: Aktualisiert user_override_tags für ML-Training

    Wenn User Tags manuell ändert, speichern wir die finalen Tag-Namen
    in user_override_tags (comma-separated) für sklearn-Training.
    """
    try:
        from datetime import datetime, UTC

        # Hole aktuelle Tags der Email
        current_tags = tag_manager_mod.TagManager.get_email_tags(db, email_id, user_id)
        tag_names = [tag.name for tag in current_tags]
        tag_string = ",".join(tag_names) if tag_names else ""

        # Update ProcessedEmail
        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.ProcessedEmail.id == email_id, models.RawEmail.user_id == user_id
            )
            .first()
        )

        if processed:
            processed.user_override_tags = tag_string
            processed.correction_timestamp = datetime.now(UTC)
            db.commit()
            logger.debug(
                f"📚 user_override_tags updated für Email {email_id}: {tag_string}"
            )
    except Exception as e:
        logger.warning(f"⚠️  Fehler beim Update von user_override_tags: {e}")
        db.rollback()


# ===== Phase Y: spaCy Hybrid Pipeline Configuration APIs =====


@app.route("/api/phase-y/vip-senders", methods=["GET"])
@login_required
def api_get_vip_senders():
    """API: Alle VIP-Absender für Account abrufen"""
    db = get_db_session()
    try:
        account_id = request.args.get("account_id", type=int)
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        user = get_current_user_model(db)
        account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        vips = db.query(models.SpacyVIPSender).filter_by(account_id=account_id).all()
        
        return jsonify({
            "vips": [
                {
                    "id": vip.id,
                    "sender_pattern": vip.sender_pattern,
                    "pattern_type": vip.pattern_type,
                    "importance_boost": vip.importance_boost,
                    "label": vip.label,
                    "is_active": vip.is_active
                }
                for vip in vips
            ]
        }), 200
    finally:
        db.close()


@app.route("/api/phase-y/vip-senders", methods=["POST"])
@login_required
def api_create_vip_sender():
    """API: VIP-Absender erstellen"""
    db = get_db_session()
    try:
        data = request.get_json()
        
        # P1-003: Input-Validation
        try:
            account_id = validate_integer(data.get("account_id"), "Account-ID", min_val=1)
            sender_pattern = validate_string(data.get("sender_pattern"), "Absender-Pattern", min_len=1, max_len=255).lower()
            pattern_type = validate_string(data.get("pattern_type", "email"), "Pattern-Typ", min_len=1, max_len=20)
            importance_boost = validate_integer(data.get("importance_boost", 2), "Importance-Boost", min_val=0, max_val=10)
            label = validate_string(data.get("label", ""), "Label", min_len=0, max_len=100, allow_empty=True) or ""
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        
        user = get_current_user_model(db)
        account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        vip = models.SpacyVIPSender(
            user_id=user.id,
            account_id=account_id,
            sender_pattern=sender_pattern,
            pattern_type=pattern_type,
            importance_boost=importance_boost,
            label=label,
            is_active=data.get("is_active", True)
        )
        db.add(vip)
        db.commit()
        
        return jsonify({"success": True, "vip_id": vip.id}), 201
    except Exception as e:
        db.rollback()
        logger.error(f"Fehler beim Erstellen von VIP: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/phase-y/vip-senders/<int:vip_id>", methods=["PUT"])
@login_required
def api_update_vip_sender(vip_id):
    """API: VIP-Absender aktualisieren"""
    db = get_db_session()
    try:
        data = request.get_json()
        user = get_current_user_model(db)
        
        vip = db.query(models.SpacyVIPSender).join(models.MailAccount).filter(
            models.SpacyVIPSender.id == vip_id,
            models.MailAccount.user_id == user.id
        ).first()
        
        if not vip:
            return jsonify({"error": "VIP nicht gefunden"}), 404
        
        vip.sender_pattern = data.get("sender_pattern", vip.sender_pattern).lower()
        vip.pattern_type = data.get("pattern_type", vip.pattern_type)
        vip.importance_boost = data.get("importance_boost", vip.importance_boost)
        vip.label = data.get("label", vip.label)
        vip.is_active = data.get("is_active", vip.is_active)
        
        db.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Fehler beim Aktualisieren von VIP: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/phase-y/vip-senders/<int:vip_id>", methods=["DELETE"])
@login_required
def api_delete_vip_sender(vip_id):
    """API: VIP-Absender löschen"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        
        vip = db.query(models.SpacyVIPSender).join(models.MailAccount).filter(
            models.SpacyVIPSender.id == vip_id,
            models.MailAccount.user_id == user.id
        ).first()
        
        if not vip:
            return jsonify({"error": "VIP nicht gefunden"}), 404
        
        db.delete(vip)
        db.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Fehler beim Löschen von VIP: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/phase-y/keyword-sets", methods=["GET"])
@login_required
def api_get_keyword_sets():
    """API: Alle Keyword-Sets für Account abrufen"""
    db = get_db_session()
    try:
        account_id = request.args.get("account_id", type=int)
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        user = get_current_user_model(db)
        account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        keyword_sets = db.query(models.SpacyKeywordSet).filter_by(user_id=user.id, account_id=account_id).all()
        
        # Wenn keine Custom-Sets existieren, Default-Sets laden
        if not keyword_sets:
            from src.services.spacy_config_manager import SpacyConfigManager
            config_manager = SpacyConfigManager(db)
            default_sets = config_manager._get_default_keyword_sets()
            
            return jsonify({
                "keyword_sets": [
                    {
                        "id": None,
                        "keyword_set_name": name,
                        "keywords": keywords,
                        "is_active": True,
                        "is_default": True
                    }
                    for name, keywords in default_sets.items()
                ]
            }), 200
        
        import json
        return jsonify({
            "keyword_sets": [
                {
                    "id": ks.id,
                    "keyword_set_name": ks.set_type,  # Frontend erwartet "keyword_set_name"
                    "keywords": json.loads(ks.keywords_json),
                    "is_active": ks.is_active,
                    "is_default": False
                }
                for ks in keyword_sets
            ]
        }), 200
    finally:
        db.close()


@app.route("/api/phase-y/keyword-sets", methods=["POST"])
@login_required
def api_save_keyword_set():
    """API: Keyword-Set speichern/aktualisieren"""
    db = get_db_session()
    try:
        data = request.get_json()
        account_id = int(data.get("account_id"))  # Convert to int!
        
        user = get_current_user_model(db)
        account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        set_type = data.get("keyword_set_name")  # Frontend sendet "keyword_set_name"
        keywords = data.get("keywords", [])
        
        # Prüfe ob Set bereits existiert
        existing = db.query(models.SpacyKeywordSet).filter_by(
            user_id=user.id,
            account_id=account_id,
            set_type=set_type
        ).first()
        
        import json
        if existing:
            existing.keywords_json = json.dumps(keywords)
            existing.is_active = data.get("is_active", True)
            existing.points_per_match = data.get("points_per_match", 2)
            existing.max_points = data.get("max_points", 4)
        else:
            new_set = models.SpacyKeywordSet(
                user_id=user.id,
                account_id=account_id,
                set_type=set_type,
                keywords_json=json.dumps(keywords),
                is_active=data.get("is_active", True),
                points_per_match=data.get("points_per_match", 2),
                max_points=data.get("max_points", 4),
                is_custom=data.get("is_custom", False)
            )
            db.add(new_set)
        
        db.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Fehler beim Speichern von Keyword-Set: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/phase-y/scoring-config", methods=["GET"])
@login_required
def api_get_scoring_config():
    """API: Scoring-Konfiguration für Account abrufen"""
    db = get_db_session()
    try:
        account_id = request.args.get("account_id", type=int)
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        user = get_current_user_model(db)
        account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        config = db.query(models.SpacyScoringConfig).filter_by(account_id=account_id).first()
        
        if not config:
            # Default-Werte
            from src.services.spacy_config_manager import SpacyConfigManager
            config_manager = SpacyConfigManager(db)
            default_config = config_manager._get_default_scoring_config()
            return jsonify({"config": default_config, "is_default": True}), 200
        
        return jsonify({
            "config": {
                "imperative_weight": config.imperative_weight,
                "deadline_weight": config.deadline_weight,
                "keyword_weight": config.keyword_weight,
                "vip_weight": config.vip_weight,
                "question_threshold": config.question_threshold,
                "negation_sensitivity": config.negation_sensitivity,
                "spacy_weight_initial": config.spacy_weight_initial,
                "spacy_weight_learning": config.spacy_weight_learning,
                "spacy_weight_trained": config.spacy_weight_trained
            },
            "is_default": False
        }), 200
    finally:
        db.close()


@app.route("/api/phase-y/scoring-config", methods=["POST"])
@login_required
def api_save_scoring_config():
    """API: Scoring-Konfiguration speichern"""
    db = get_db_session()
    try:
        data = request.get_json()
        account_id = int(data.get("account_id"))  # Convert to int!
        
        user = get_current_user_model(db)
        account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        config = db.query(models.SpacyScoringConfig).filter_by(account_id=account_id).first()
        
        if config:
            # Update
            config.imperative_weight = data.get("imperative_weight", config.imperative_weight)
            config.deadline_weight = data.get("deadline_weight", config.deadline_weight)
            config.keyword_weight = data.get("keyword_weight", config.keyword_weight)
            config.vip_weight = data.get("vip_weight", config.vip_weight)
            config.question_threshold = data.get("question_threshold", config.question_threshold)
            config.negation_sensitivity = data.get("negation_sensitivity", config.negation_sensitivity)
            config.spacy_weight_initial = data.get("spacy_weight_initial", config.spacy_weight_initial)
            config.spacy_weight_learning = data.get("spacy_weight_learning", config.spacy_weight_learning)
            config.spacy_weight_trained = data.get("spacy_weight_trained", config.spacy_weight_trained)
        else:
            # Create
            config = models.SpacyScoringConfig(
                user_id=user.id,
                account_id=account_id,
                imperative_weight=data.get("imperative_weight", 3),
                deadline_weight=data.get("deadline_weight", 4),
                keyword_weight=data.get("keyword_weight", 2),
                vip_weight=data.get("vip_weight", 3),
                question_threshold=data.get("question_threshold", 3),
                negation_sensitivity=data.get("negation_sensitivity", 2),
                spacy_weight_initial=data.get("spacy_weight_initial", 100),
                spacy_weight_learning=data.get("spacy_weight_learning", 30),
                spacy_weight_trained=data.get("spacy_weight_trained", 15)
            )
            db.add(config)
        
        db.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Fehler beim Speichern von Scoring-Config: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/phase-y/user-domains", methods=["GET"])
@login_required
def api_get_user_domains():
    """API: User-Domains für Account abrufen"""
    db = get_db_session()
    try:
        account_id = request.args.get("account_id", type=int)
        if not account_id:
            return jsonify({"error": "account_id erforderlich"}), 400
        
        user = get_current_user_model(db)
        account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        domains = db.query(models.SpacyUserDomain).filter_by(account_id=account_id).all()
        
        return jsonify({
            "domains": [
                {
                    "id": domain.id,
                    "domain": domain.domain,
                    "is_active": domain.is_active
                }
                for domain in domains
            ]
        }), 200
    finally:
        db.close()


@app.route("/api/phase-y/user-domains", methods=["POST"])
@login_required
def api_create_user_domain():
    """API: User-Domain erstellen"""
    db = get_db_session()
    try:
        data = request.get_json()
        account_id = int(data.get("account_id"))  # Convert to int!
        
        user = get_current_user_model(db)
        account = db.query(models.MailAccount).filter_by(id=account_id, user_id=user.id).first()
        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404
        
        domain = models.SpacyUserDomain(
            user_id=user.id,
            account_id=account_id,
            domain=data.get("domain", "").lower(),
            is_active=data.get("is_active", True)
        )
        db.add(domain)
        db.commit()
        
        return jsonify({"success": True, "domain_id": domain.id}), 201
    except Exception as e:
        db.rollback()
        logger.error(f"Fehler beim Erstellen von Domain: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/phase-y/user-domains/<int:domain_id>", methods=["DELETE"])
@login_required
def api_delete_user_domain(domain_id):
    """API: User-Domain löschen"""
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        
        domain = db.query(models.SpacyUserDomain).join(models.MailAccount).filter(
            models.SpacyUserDomain.id == domain_id,
            models.MailAccount.user_id == user.id
        ).first()
        
        if not domain:
            return jsonify({"error": "Domain nicht gefunden"}), 404
        
        db.delete(domain)
        db.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        db.rollback()
        logger.error(f"Fehler beim Löschen von Domain: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ===== Phase F.1: Semantic Search API Endpoints =====


@app.route("/api/search/semantic", methods=["GET"])
@login_required
@limiter.limit("30 per minute")  # 🐛 BUG-012 FIX: Rate Limit für rechenintensive Semantic Search
def api_semantic_search():
    """
    API: Semantische E-Mail-Suche (Phase F.1)
    
    Query Parameters:
    - q: Suchbegriff (required)
    - limit: Max. Anzahl Ergebnisse (default: 20)
    - threshold: Min. Similarity Score 0-1 (default: 0.25)
    
    Returns:
    {
        "results": [
            {
                "email_id": 123,
                "subject": "Budget Q4",
                "from": "boss@company.com",
                "date": "2024-01-15T10:30:00Z",
                "similarity_score": 0.87,
                "snippet": "...text excerpt..."
            }
        ],
        "query": "Budget",
        "total": 5,
        "has_embeddings": true
    }
    """
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
            
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"error": "Query parameter 'q' is required"}), 400
            
        try:
            limit = int(request.args.get("limit", 20))
            threshold = float(request.args.get("threshold", 0.25))
            account_id = request.args.get("account_id")  # Optional: Filter nach Account
            if account_id:
                try:
                    account_id = int(account_id)
                except ValueError:
                    account_id = None
        except ValueError:
            return jsonify({"error": "Invalid limit or threshold parameter"}), 400
            
        # Semantic Search durchführen
        try:
            # AI-Client für Query-Embedding generieren (Ollama mit all-minilm:22m)
            query_ai_client = ai_client.LocalOllamaClient(model="all-minilm:22m")
            
            search_service = semantic_search.SemanticSearchService(db, query_ai_client)
            results = search_service.search(
                query=query,
                user_id=user.id,
                limit=limit,
                threshold=threshold,
                account_id=account_id  # Übergebe Account-Filter
            )
            
            # Ergebnisse formatieren (mit Decryption)
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master key not in session"}), 401
                
            formatted_results = []
            for result in results:
                # Decrypt Subject
                try:
                    subject_plain = encryption.EmailDataManager.decrypt_email_subject(
                        result["encrypted_subject"], master_key
                    ) if result.get("encrypted_subject") else ""
                    
                    # Sender ist unverschlüsselt (encrypted_sender ist ein Misnomer)
                    sender = result.get("encrypted_sender", "")
                    
                    # Datum formatieren
                    date_str = result["received_at"].isoformat() if result.get("received_at") else None
                    
                    formatted_results.append({
                        "email_id": result["id"],
                        "subject": subject_plain,
                        "from": sender,
                        "date": date_str,
                        "similarity_score": result["similarity_score"],
                        "snippet": subject_plain[:150] + "..." if len(subject_plain) > 150 else subject_plain
                    })
                except Exception as decrypt_err:
                    logger.warning(f"Decryption failed for email {result['id']}: {decrypt_err}")
                    continue
                    
            return jsonify({
                "results": formatted_results,
                "query": query,
                "total": len(formatted_results),
                "has_embeddings": len(results) > 0
            }), 200
            
        except Exception as search_err:
            logger.error(f"Semantic search failed: {search_err}")
            return jsonify({
                "results": [],
                "query": query,
                "total": 0,
                "error": "Search service unavailable"
            }), 500
            
    finally:
        db.close()


@app.route("/api/emails/<int:raw_email_id>/similar", methods=["GET"])
@login_required
@limiter.limit("40 per minute")  # 🐛 BUG-012 FIX: Rate Limit für Embedding-Vergleiche
def api_find_similar_emails(raw_email_id):
    """
    API: Ähnliche E-Mails finden (Phase F.1)
    
    Query Parameters:
    - limit: Max. Anzahl Ergebnisse (default: 5)
    
    Returns:
    {
        "similar_emails": [
            {
                "email_id": 456,
                "subject": "Budget Q3",
                "from": "cfo@company.com",
                "date": "2023-12-10T14:20:00Z",
                "similarity_score": 0.92
            }
        ],
        "reference_email_id": 123,
        "total": 3
    }
    """
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
            
        try:
            limit = int(request.args.get("limit", 5))
            account_id = request.args.get("account_id")
            if account_id:
                try:
                    account_id = int(account_id)
                except ValueError:
                    account_id = None  # Default: nur gleicher Account
        except ValueError:
            return jsonify({"error": "Invalid limit parameter"}), 400
            
        # Ownership Check: User muss die Email besitzen
        ref_email = db.query(models.RawEmail).filter_by(
            id=raw_email_id,
            user_id=user.id
        ).first()
        
        if not ref_email:
            return jsonify({"error": "Email not found or access denied"}), 404
            
        # Similar Emails finden
        try:
            search_service = semantic_search.SemanticSearchService(db)
            results = search_service.find_similar(
                email_id=raw_email_id,
                limit=limit,
                account_id=account_id  # Übergebe Account-Filter (None = gleicher Account)
            )
            
            # Ergebnisse formatieren (mit Decryption)
            master_key = session.get("master_key")
            if not master_key:
                return jsonify({"error": "Master key not in session"}), 401
                
            formatted_results = []
            for result in results:
                try:
                    subject_plain = encryption.EmailDataManager.decrypt_email_subject(
                        result["encrypted_subject"], master_key
                    ) if result.get("encrypted_subject") else ""
                    
                    sender = result.get("encrypted_sender", "")
                    date_str = result["received_at"].isoformat() if result.get("received_at") else None
                    
                    formatted_results.append({
                        "email_id": result["id"],
                        "subject": subject_plain,
                        "from": sender,
                        "date": date_str,
                        "similarity_score": result["similarity_score"]
                    })
                except Exception as decrypt_err:
                    logger.warning(f"Decryption failed for email {result['id']}: {decrypt_err}")
                    continue
                    
            return jsonify({
                "similar_emails": formatted_results,
                "reference_email_id": raw_email_id,
                "total": len(formatted_results)
            }), 200
            
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 404
        except Exception as search_err:
            logger.error(f"Similar search failed: {search_err}")
            return jsonify({
                "similar_emails": [],
                "reference_email_id": raw_email_id,
                "total": 0,
                "error": "Search service unavailable"
            }), 500
            
    finally:
        db.close()


@app.route("/api/embeddings/stats", methods=["GET"])
@login_required
def api_embedding_stats():
    """
    API: Embedding Coverage Statistics (Phase F.1)
    
    Returns:
    {
        "total_emails": 150,
        "emails_with_embeddings": 120,
        "coverage_percent": 80.0,
        "embedding_model": "all-minilm:22m"
    }
    """
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
            
        try:
            search_service = semantic_search.SemanticSearchService(db)
            stats = search_service.get_embedding_stats(user_id=user.id)
            
            return jsonify(stats), 200
            
        except Exception as stats_err:
            logger.error(f"Stats retrieval failed: {stats_err}")
            return jsonify({
                "total_emails": 0,
                "emails_with_embeddings": 0,
                "coverage_percent": 0.0,
                "error": "Stats unavailable"
            }), 500
            
    finally:
        db.close()


# ===== End Phase F.1 Semantic Search =====


# ===== Phase G.1: Reply Draft Generator =====

@app.route("/api/emails/<int:raw_email_id>/generate-reply", methods=["POST"])
@login_required
def api_generate_reply(raw_email_id):
    """
    API: Generiert Antwort-Entwurf auf eine Email (Phase G.1 + Provider/Anonymization)
    
    Request Body:
    {
        "tone": "formal|friendly|brief|decline",     // Optional, default: "formal"
        "provider": "ollama|openai|anthropic",       // Optional, default: User-Settings
        "model": "llama3.2|gpt-4o|claude-sonnet",   // Optional, default: User-Settings
        "use_anonymization": true|false              // Optional, auto: Cloud=true, Local=false
    }
    
    Returns:
    {
        "success": true,
        "reply_text": "Sehr geehrte Frau Müller,\n\n...",
        "tone_used": "formal",
        "tone_name": "Formell",
        "tone_icon": "📜",
        "timestamp": "2026-01-02T10:30:00",
        "was_anonymized": true,                      // Neu: Ob anonymisiert wurde
        "entity_map": {...},                         // Neu: Für De-Anonymisierung
        "provider_used": "anthropic",                // Neu: Welcher Provider genutzt
        "model_used": "claude-3.5-sonnet"           // Neu: Welches Modell genutzt
    }
    """
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        
        # Parse request body
        data = request.get_json() or {}
        tone = data.get("tone", "formal")
        
        # 🆕 Neue Parameter: Provider/Model Selection
        requested_provider = data.get("provider")  # Optional: User-Wahl
        requested_model = data.get("model")        # Optional: User-Wahl
        use_anonymization = data.get("use_anonymization")  # Optional: Auto oder User-Wahl
        
        # 🔍 DEBUG: Session-ID für Debug-Logging (MUSS am Anfang definiert werden!)
        session_id = f"reply_{raw_email_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        
        # Validiere Email-Zugriff
        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None
            )
            .first()
        )
        
        if not processed or not processed.raw_email:
            return jsonify({
                "success": False,
                "error": "Email nicht gefunden"
            }), 404
        
        raw_email = processed.raw_email
        
        # Zero-Knowledge: Entschlüssele Email-Daten
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({
                "success": False,
                "error": "Master-Key nicht verfügbar"
            }), 401
        
        try:
            decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                raw_email.encrypted_subject or "", master_key
            )
            decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                raw_email.encrypted_body or "", master_key
            )
            decrypted_sender = encryption.EmailDataManager.decrypt_email_sender(
                raw_email.encrypted_sender or "", master_key
            )
        except Exception as e:
            logger.error(f"Decryption failed for email raw_id={raw_email_id}: {e}")
            return jsonify({
                "success": False,
                "error": "Entschlüsselung fehlgeschlagen"
            }), 500
        
        # Phase E: Build Thread-Context für bessere Antworten
        thread_context = ""
        try:
            processing_mod = importlib.import_module(".12_processing", "src")
            thread_context = processing_mod.build_thread_context(
                session=db,
                raw_email=raw_email,
                master_key=master_key,
                max_context_emails=3  # Nur 3 für Reply (nicht 5 wie bei Processing)
            )
        except Exception as ctx_err:
            logger.warning(f"Thread-Context build failed: {ctx_err}")
            # Nicht kritisch, fahre ohne Context fort
        
        # Generate Reply
        try:
            reply_generator_mod = importlib.import_module("src.reply_generator")
            
            # 🆕 Provider/Model Selection mit intelligenten Defaults
            if requested_provider and requested_model:
                # User hat explizit gewählt
                provider = requested_provider.lower()
                resolved_model = ai_client.resolve_model(provider, requested_model, kind="optimize")
                logger.info(f"🎯 User-selected Reply-Generator: {provider}/{resolved_model}")
            else:
                # Fallback auf User-Settings
                provider = (user.preferred_ai_provider_optimize or user.preferred_ai_provider or "ollama").lower()
                optimize_model = user.preferred_ai_model_optimize or user.preferred_ai_model
                resolved_model = ai_client.resolve_model(provider, optimize_model, kind="optimize")
                logger.info(f"🤖 Default Reply-Generator: {provider}/{resolved_model}")
            
            client = ai_client.build_client(provider, model=resolved_model)
            
            # 🆕 Anonymisierungs-Logik mit pragmatischem Fallback
            cloud_providers = ["openai", "anthropic", "google"]
            is_cloud_provider = provider in cloud_providers
            
            # Auto-Anonymisierung: Cloud = default true, Lokal = default false
            if use_anonymization is None:
                use_anonymization = is_cloud_provider
                if is_cloud_provider:
                    logger.info(f"🔒 Auto-enabling anonymization for cloud provider: {provider}")
            
            # Bestimme welchen Content wir nutzen
            content_for_ai_subject = decrypted_subject
            content_for_ai_body = decrypted_body
            entity_map = None
            was_anonymized = False
            
            if use_anonymization:
                # Nutze sanitized Content (Phase 22: encrypted_*_sanitized)
                if raw_email.encrypted_subject_sanitized and raw_email.encrypted_body_sanitized:
                    # ✅ Ideal: Bereits anonymisiert (Phase 22)
                    try:
                        content_for_ai_subject = encryption.EmailDataManager.decrypt_email_subject(
                            raw_email.encrypted_subject_sanitized, master_key
                        )
                        content_for_ai_body = encryption.EmailDataManager.decrypt_email_body(
                            raw_email.encrypted_body_sanitized, master_key
                        )
                        was_anonymized = True
                        
                        # EntityMap aus DB laden für De-Anonymisierung
                        if raw_email.encrypted_entity_map:
                            try:
                                import json
                                entity_map_json = encryption.EncryptionManager.decrypt_data(
                                    raw_email.encrypted_entity_map, master_key
                                )
                                entity_map = json.loads(entity_map_json)
                                logger.info(f"🔒 Loaded EntityMap from DB ({len(entity_map.get('reverse', {}))} entries)")
                            except Exception as e:
                                logger.warning(f"⚠️ EntityMap decryption failed: {e}")
                                entity_map = None
                        
                        logger.info(f"🔒 Using pre-sanitized content from Phase 22")
                    except Exception as decrypt_err:
                        logger.warning(f"⚠️ Sanitized content decryption failed: {decrypt_err}")
                        # Fallback auf Original
                        content_for_ai_body = decrypted_body
                else:
                    # 🔐 SECURITY FIX: ON-THE-FLY Anonymisierung + DB-Speicherung
                    logger.info(
                        f"⏳ Email raw_id={raw_email_id} (processed_id={processed.id}) has no sanitized content yet. "
                        f"Running ContentSanitizer on-the-fly and STORING to DB..."
                    )
                    
                    try:
                        # Import ContentSanitizer
                        from src.services.content_sanitizer import ContentSanitizer
                        sanitizer = ContentSanitizer()
                        
                        # 🔍 DEBUG: Log Sanitizer Input
                        if DebugLogger.is_enabled():
                            DebugLogger.log_sanitizer_input(
                                subject=decrypted_subject,
                                body=decrypted_body,
                                sender=decrypted_sender,
                                session_id=session_id
                            )
                        
                        # Anonymisiere Subject + Body (Level 2 = Regex + spaCy Light)
                        result = sanitizer.sanitize_with_roles(
                            subject=decrypted_subject,
                            body=decrypted_body,
                            sender=decrypted_sender,
                            recipient=user.username,
                            level=2,
                            session_id=session_id
                        )
                        
                        # 🔍 DEBUG: Log Sanitizer Output (Statistiken)
                        if DebugLogger.is_enabled():
                            DebugLogger.log_sanitizer_output(
                                result=result,
                                session_id=session_id
                            )
                            # Log auch vollständigen anonymisierten Content
                            DebugLogger.log_sanitizer_anonymized(
                                result=result,
                                session_id=session_id
                            )
                        
                        # Verschlüssele und speichere in DB
                        raw_email.encrypted_subject_sanitized = encryption.EmailDataManager.encrypt_email_subject(
                            result.subject, master_key
                        )
                        raw_email.encrypted_body_sanitized = encryption.EmailDataManager.encrypt_email_body(
                            result.body, master_key
                        )
                        raw_email.sanitization_entities_count = result.entities_found
                        raw_email.sanitization_level = 2
                        raw_email.sanitization_time_ms = result.processing_time_ms
                        
                        # EntityMap für De-Anonymisierung verschlüsselt speichern
                        entity_map = result.entity_map.to_dict()
                        import json
                        raw_email.encrypted_entity_map = encryption.EncryptionManager.encrypt_data(
                            json.dumps(entity_map), master_key
                        )
                        
                        db.commit()
                        
                        # Nutze anonymisierte Daten
                        content_for_ai_subject = result.subject
                        content_for_ai_body = result.body
                        was_anonymized = True
                        
                        # 🔍 DEBUG: Log Sanitizer Output
                        if DebugLogger.is_enabled():
                            DebugLogger.log_sanitizer_output(
                                result=result,
                                session_id=session_id
                            )
                        
                        logger.info(
                            f"✅ On-the-fly anonymization completed and STORED to DB. "
                            f"Entities: {raw_email.sanitization_entities_count}"
                        )
                        
                    except Exception as anon_err:
                        logger.error(f"❌ On-the-fly anonymization FAILED: {anon_err}")
                        db.rollback()
                        return jsonify({
                            "success": False,
                            "error": f"Anonymisierung fehlgeschlagen: {str(anon_err)}"
                        }), 500
            else:
                # Original-Content gewünscht (z.B. lokale Modelle)
                if is_cloud_provider:
                    logger.warning(f"⚠️ Using original content with cloud provider {provider} - User explicitly disabled anonymization")
            
            generator = reply_generator_mod.ReplyGenerator(ai_client=client)
            
            # 🔍 DEBUG: Zentrales Debug-Logging System
            if DebugLogger.is_enabled():
                logger.warning("⚠️ DEBUG-LOGGING IST AKTIV - Sensible Daten werden geloggt!")
            
            # Old debug logs
            logger.debug(f"🔍 REPLY API DEBUG - content_for_ai_subject: {content_for_ai_subject}")
            logger.debug(f"🔍 REPLY API DEBUG - content_for_ai_body (erste 400 Zeichen): {content_for_ai_body[:400]}...")
            logger.debug(f"🔍 REPLY API DEBUG - was_anonymized: {was_anonymized}")
            logger.debug(f"🔍 REPLY API DEBUG - entity_map keys: {list(entity_map.keys()) if entity_map else 'None'}")
            
            # 🔐 SECURITY FIX: Sender auch anonymisieren wenn use_anonymization aktiv
            if was_anonymized:
                sender_for_ai = "[ABSENDER]"
            else:
                sender_for_ai = decrypted_sender
            
            # 🆕 Use generate_reply_with_user_style() for personalized replies
            # Phase I.2: Pass account_id für Account-spezifische Signaturen
            result = generator.generate_reply_with_user_style(
                db=db,
                user_id=user.id,
                original_subject=content_for_ai_subject,   # 🆕 Ggf. anonymisiert
                original_body=content_for_ai_body,         # 🆕 Ggf. anonymisiert
                original_sender=sender_for_ai,             # ✅ JETZT AUCH ANONYMISIERT!
                tone=tone,
                thread_context=thread_context if thread_context else None,
                has_attachments=raw_email.has_attachments or False,
                master_key=master_key,
                account_id=raw_email.mail_account_id
            )
            
            # 🆕 Erweitere Response um neue Felder
            if result["success"]:
                result["was_anonymized"] = was_anonymized
                result["entity_map"] = entity_map  # Für Frontend De-Anonymisierung
                result["provider_used"] = provider
                result["model_used"] = resolved_model
                
                logger.info(
                    f"✅ Reply-Entwurf generiert für Email raw_id={raw_email_id} (processed_id={processed.id}) "
                    f"(Ton: {result['tone_used']}, Provider: {provider}/{resolved_model}, "
                    f"Anonymisiert: {was_anonymized}, {len(result['reply_text'])} chars)"
                )
            
            return jsonify(result), 200 if result["success"] else 500
            
        except Exception as gen_err:
            logger.error(f"Reply generation failed: {gen_err}")
            return jsonify({
                "success": False,
                "error": f"Generierung fehlgeschlagen: {str(gen_err)}",
                "reply_text": "",
                "tone_used": tone,
                "timestamp": datetime.now(UTC).isoformat()
            }), 500
            
    finally:
        db.close()


@app.route("/api/reply-tones", methods=["GET"])
@login_required
def api_get_reply_tones():
    """
    API: Gibt verfügbare Reply-Töne zurück (Phase G.1)
    
    Returns:
    {
        "tones": {
            "formal": {"name": "Formell", "icon": "📜"},
            "friendly": {"name": "Freundlich", "icon": "😊"},
            ...
        }
    }
    """
    try:
        reply_generator_mod = importlib.import_module("src.reply_generator")
        tones = reply_generator_mod.ReplyGenerator.get_available_tones()
        
        return jsonify({"tones": tones}), 200
    except Exception as e:
        logger.error(f"Failed to get reply tones: {e}")
        return jsonify({"tones": {}}), 500


# ===== End Phase G.1 =====


# ===== Reply Styles Settings API (Feature: FEATURE_REPLY_STYLES) =====

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
        
        # Zero-Knowledge: Brauchen master_key zum Entschlüsseln
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key nicht verfügbar"}), 401
        
        from src.services.reply_style_service import ReplyStyleService
        settings = ReplyStyleService.get_user_settings(db, user.id, master_key)
        
        return jsonify(settings)
    except Exception as e:
        logger.error(f"Failed to get reply styles: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@app.route("/api/reply-styles/<style_key>", methods=["GET"])
@login_required
def api_get_reply_style(style_key: str):
    """Holt effektive Settings für einen spezifischen Stil
    
    Merged: Defaults → Global → Style-Specific
    
    Returns:
        {
            "style_key": "formal",
            "settings": {
                "address_form": "sie",
                "salutation": "Sehr geehrte/r",
                ...
            }
        }
    """
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key nicht verfügbar"}), 401
        
        from src.services.reply_style_service import ReplyStyleService
        try:
            settings = ReplyStyleService.get_effective_settings(
                db, user.id, style_key, master_key
            )
            return jsonify({"style_key": style_key, "settings": settings})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to get reply style: {e}")
        return jsonify({"error": str(e)}), 500
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
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key nicht verfügbar"}), 401
        
        data = request.get_json() or {}
        
        from src.services.reply_style_service import ReplyStyleService
        try:
            setting = ReplyStyleService.save_settings(
                db, user.id, style_key, data, master_key
            )
            return jsonify({
                "success": True,
                "style_key": style_key,
                "message": f"Einstellungen für '{style_key}' gespeichert"
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to save reply style: {e}")
        return jsonify({"error": str(e)}), 500
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
    except Exception as e:
        logger.error(f"Failed to delete reply style override: {e}")
        return jsonify({"error": str(e)}), 500
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
            "preview_text": "Sehr geehrter Herr Mustermann,\n\n[Ihr Text hier]\n\nMit freundlichen Grüssen\nMike",
            "settings_used": {...}
        }
    """
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key nicht verfügbar"}), 401
        
        data = request.get_json() or {}
        style_key = data.get("style_key", "formal")
        sample_sender = data.get("sample_sender", "Max Mustermann <max@example.com>")
        
        from src.services.reply_style_service import ReplyStyleService
        
        try:
            settings = ReplyStyleService.get_effective_settings(
                db, user.id, style_key, master_key
            )
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
        
    except Exception as e:
        logger.error(f"Failed to preview reply style: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ===== End Reply Styles API =====



# ===== Phase G.2: Auto-Action Rules Engine =====

@app.route("/rules")
@login_required
def rules_management():
    """Rules Management Page - Übersicht über alle Auto-Rules"""
    db_session = get_db_session()
    
    try:
        user = get_current_user_model(db_session)
        if not user:
            return redirect(url_for("login"))
        
        # Lade alle Regeln des Users
        rules = db_session.query(models.AutoRule).filter_by(
            user_id=user.id
        ).order_by(models.AutoRule.priority.asc()).all()
        
        return render_template(
            "rules_management.html",
            user=user,
            rules=rules
        )
    
    finally:
        db_session.close()


@app.route("/api/rules", methods=["GET"])
@login_required
def api_get_rules():
    """API: Alle Regeln des Users abrufen"""
    db_session = get_db_session()
    
    try:
        user = get_current_user_model(db_session)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        rules = db_session.query(models.AutoRule).filter_by(
            user_id=user.id
        ).order_by(models.AutoRule.priority.asc()).all()
        
        return jsonify({
            "rules": [
                {
                    "id": rule.id,
                    "name": rule.name,
                    "description": rule.description,
                    "is_active": rule.is_active,
                    "priority": rule.priority,
                    "conditions": rule.conditions,
                    "actions": rule.actions,
                    "times_triggered": rule.times_triggered,
                    "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
                    "created_at": rule.created_at.isoformat() if rule.created_at else None
                }
                for rule in rules
            ]
        }), 200
    
    finally:
        db_session.close()


@app.route("/api/rules", methods=["POST"])
@login_required
def api_create_rule():
    """API: Neue Regel erstellen"""
    db_session = get_db_session()
    
    try:
        user = get_current_user_model(db_session)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        data = request.get_json()
        
        # Validierung
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name erforderlich"}), 400
        
        conditions = data.get("conditions", {})
        actions = data.get("actions", {})
        
        if not conditions:
            return jsonify({"error": "Mindestens eine Bedingung erforderlich"}), 400
        
        if not actions:
            return jsonify({"error": "Mindestens eine Aktion erforderlich"}), 400
        
        # Regel erstellen
        rule = models.AutoRule(
            user_id=user.id,
            name=name,
            description=data.get("description"),
            priority=data.get("priority", 100),
            is_active=data.get("is_active", True),
            conditions=conditions,
            actions=actions
        )
        
        db_session.add(rule)
        db_session.commit()
        
        logger.info(f"✅ Regel erstellt: '{rule.name}' (ID: {rule.id}) für User {user.id}")
        
        return jsonify({
            "success": True,
            "rule": {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "is_active": rule.is_active,
                "priority": rule.priority,
                "conditions": rule.conditions,
                "actions": rule.actions
            }
        }), 201
    
    except Exception as e:
        db_session.rollback()
        logger.error(f"Fehler beim Erstellen der Regel: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        db_session.close()


@app.route("/api/rules/<int:rule_id>", methods=["PUT"])
@login_required
def api_update_rule(rule_id):
    """API: Regel aktualisieren"""
    db_session = get_db_session()
    
    try:
        user = get_current_user_model(db_session)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        rule = db_session.query(models.AutoRule).filter_by(
            id=rule_id,
            user_id=user.id
        ).first()
        
        if not rule:
            return jsonify({"error": "Regel nicht gefunden"}), 404
        
        data = request.get_json()
        
        # Update Felder
        if "name" in data:
            rule.name = data["name"].strip()
        if "description" in data:
            rule.description = data["description"]
        if "is_active" in data:
            rule.is_active = data["is_active"]
        if "priority" in data:
            rule.priority = data["priority"]
        if "conditions" in data:
            rule.conditions = data["conditions"]
        if "actions" in data:
            rule.actions = data["actions"]
        
        db_session.commit()
        
        logger.info(f"✅ Regel aktualisiert: '{rule.name}' (ID: {rule.id})")
        
        return jsonify({
            "success": True,
            "rule": {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "is_active": rule.is_active,
                "priority": rule.priority,
                "conditions": rule.conditions,
                "actions": rule.actions
            }
        }), 200
    
    except Exception as e:
        db_session.rollback()
        logger.error(f"Fehler beim Aktualisieren der Regel: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        db_session.close()


@app.route("/api/rules/<int:rule_id>", methods=["DELETE"])
@login_required
def api_delete_rule(rule_id):
    """API: Regel löschen"""
    db_session = get_db_session()
    
    try:
        user = get_current_user_model(db_session)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        rule = db_session.query(models.AutoRule).filter_by(
            id=rule_id,
            user_id=user.id
        ).first()
        
        if not rule:
            return jsonify({"error": "Regel nicht gefunden"}), 404
        
        rule_name = rule.name
        db_session.delete(rule)
        db_session.commit()
        
        logger.info(f"🗑️  Regel gelöscht: '{rule_name}' (ID: {rule_id})")
        
        return jsonify({"success": True}), 200
    
    except Exception as e:
        db_session.rollback()
        logger.error(f"Fehler beim Löschen der Regel: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        db_session.close()


@app.route("/api/rules/<int:rule_id>/test", methods=["POST"])
@login_required
def api_test_rule(rule_id):
    """
    API: Regel auf E-Mail testen (Dry-Run)
    
    Request Body:
    {
        "email_id": 123  # Optional - wenn nicht angegeben, teste gegen alle
    }
    
    Returns:
    {
        "success": true,
        "matches": [
            {
                "email_id": 123,
                "matched": true,
                "matched_conditions": ["sender_contains", "subject_contains"],
                "actions_would_execute": ["move_to:Archive", "mark_as_read"]
            }
        ],
        "total_tested": 1,
        "total_matches": 1
    }
    """
    db_session = get_db_session()
    
    try:
        user = get_current_user_model(db_session)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        rule = db_session.query(models.AutoRule).filter_by(
            id=rule_id,
            user_id=user.id
        ).first()
        
        if not rule:
            return jsonify({"error": "Regel nicht gefunden"}), 404
        
        data = request.get_json() or {}
        email_id = data.get("email_id")
        
        # Master-Key aus Session
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key nicht verfügbar"}), 401
        
        # Rules Engine initialisieren
        from src.auto_rules_engine import AutoRulesEngine
        engine = AutoRulesEngine(user.id, master_key, db_session)
        
        matches = []
        
        if email_id:
            # Teste eine spezifische E-Mail
            results = engine.process_email(email_id, dry_run=True, rule_id=rule_id)
            
            for result in results:
                matches.append({
                    "email_id": result.email_id,
                    "matched": result.success,
                    "actions_would_execute": result.actions_executed
                })
        else:
            # Teste gegen die letzten 20 E-Mails
            recent_emails = db_session.query(models.RawEmail).filter_by(
                user_id=user.id,
                deleted_at=None
            ).order_by(models.RawEmail.received_at.desc()).limit(20).all()
            
            for email in recent_emails:
                results = engine.process_email(email.id, dry_run=True, rule_id=rule_id)
                
                if results and results[0].success:
                    matches.append({
                        "email_id": email.id,
                        "matched": True,
                        "actions_would_execute": results[0].actions_executed
                    })
        
        logger.info(f"🧪 Regel '{rule.name}' getestet: {len(matches)} Matches")
        
        return jsonify({
            "success": True,
            "matches": matches,
            "total_tested": 1 if email_id else 20,
            "total_matches": len(matches),
            "rule_name": rule.name
        }), 200
    
    except Exception as e:
        logger.error(f"Fehler beim Testen der Regel: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        db_session.close()


@app.route("/api/rules/apply", methods=["POST"])
@login_required
def api_apply_rules():
    """
    API: Regeln manuell auf E-Mails anwenden
    
    Request Body:
    {
        "email_ids": [123, 456],  # Optional - wenn leer, alle unverarbeiteten
        "rule_ids": [1, 2]        # Optional - wenn leer, alle aktiven Regeln
    }
    
    Returns:
    {
        "success": true,
        "stats": {
            "emails_processed": 2,
            "rules_triggered": 3,
            "actions_executed": 5
        }
    }
    """
    db_session = get_db_session()
    
    try:
        user = get_current_user_model(db_session)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        data = request.get_json() or {}
        email_ids = data.get("email_ids", [])
        
        # Master-Key aus Session
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key nicht verfügbar"}), 401
        
        # Rules Engine initialisieren
        from src.auto_rules_engine import AutoRulesEngine
        engine = AutoRulesEngine(user.id, master_key, db_session)
        
        stats = {
            "emails_processed": 0,
            "rules_triggered": 0,
            "actions_executed": 0,
            "errors": 0
        }
        
        if email_ids:
            # Spezifische E-Mails verarbeiten
            for email_id in email_ids:
                try:
                    results = engine.process_email(email_id, dry_run=False)
                    
                    for result in results:
                        if result.success:
                            stats["rules_triggered"] += 1
                            stats["actions_executed"] += len(result.actions_executed)
                        else:
                            stats["errors"] += 1
                    
                    stats["emails_processed"] += 1
                    
                except Exception as e:
                    logger.error(f"Fehler bei E-Mail {email_id}: {e}")
                    stats["errors"] += 1
        else:
            # Alle unverarbeiteten E-Mails
            batch_stats = engine.process_new_emails(since_minutes=10080, limit=500)  # 1 Woche
            stats.update(batch_stats)
            stats["emails_processed"] = batch_stats["emails_checked"]
        
        logger.info(
            f"✅ Auto-Rules angewendet: {stats['emails_processed']} E-Mails, "
            f"{stats['rules_triggered']} Regeln ausgelöst"
        )
        
        return jsonify({
            "success": True,
            "stats": stats
        }), 200
    
    except Exception as e:
        logger.error(f"Fehler beim Anwenden der Regeln: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        db_session.close()


@app.route("/api/rules/templates", methods=["GET"])
@login_required
def api_get_rule_templates():
    """API: Vordefinierte Regel-Templates abrufen"""
    try:
        from src.auto_rules_engine import RULE_TEMPLATES
        
        return jsonify({
            "templates": [
                {
                    "id": key,
                    "name": template["name"],
                    "description": template["description"],
                    "priority": template.get("priority", 100),
                    "conditions": template["conditions"],
                    "actions": template["actions"]
                }
                for key, template in RULE_TEMPLATES.items()
            ]
        }), 200
    
    except Exception as e:
        logger.error(f"Fehler beim Laden der Templates: {e}")
        return jsonify({"templates": []}), 500


@app.route("/api/rules/templates/<template_name>", methods=["POST"])
@login_required
def api_create_rule_from_template(template_name):
    """
    API: Regel aus Template erstellen
    
    Request Body:
    {
        "overrides": {
            "name": "Meine angepasste Regel",
            "conditions": {...},
            "actions": {...}
        }
    }
    """
    db_session = get_db_session()
    
    try:
        user = get_current_user_model(db_session)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        
        data = request.get_json() or {}
        overrides = data.get("overrides", {})
        
        from src.auto_rules_engine import create_rule_from_template
        
        rule = create_rule_from_template(
            db_session=db_session,
            user_id=user.id,
            template_name=template_name,
            overrides=overrides
        )
        
        if not rule:
            return jsonify({"error": "Template nicht gefunden"}), 404
        
        return jsonify({
            "success": True,
            "rule": {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "is_active": rule.is_active,
                "priority": rule.priority,
                "conditions": rule.conditions,
                "actions": rule.actions
            }
        }), 201
    
    except Exception as e:
        db_session.rollback()
        logger.error(f"Fehler beim Erstellen der Regel aus Template: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        db_session.close()


@app.route("/rules/execution-log")
@login_required
def rules_execution_log():
    """
    Issue 3: RuleExecutionLog-UI
    Zeigt Verlauf aller Regel-Ausführungen für Debugging und Monitoring
    """
    db_session = get_db_session()
    
    try:
        user = get_current_user_model(db_session)
        if not user:
            return redirect(url_for("login"))
        
        # Query parameters für Filterung
        limit = int(request.args.get('limit', 100))
        rule_id = request.args.get('rule_id')
        success_filter = request.args.get('success')  # 'true', 'false', or None (all)
        
        # Base query
        query = db_session.query(
            models.RuleExecutionLog,
            models.AutoRule,
            models.ProcessedEmail,
            models.RawEmail
        ).join(
            models.AutoRule,
            models.RuleExecutionLog.rule_id == models.AutoRule.id
        ).join(
            models.ProcessedEmail,
            models.RuleExecutionLog.processed_email_id == models.ProcessedEmail.id
        ).join(
            models.RawEmail,
            models.ProcessedEmail.raw_email_id == models.RawEmail.id
        ).filter(
            models.RuleExecutionLog.user_id == user.id
        )
        
        # Apply filters
        if rule_id:
            query = query.filter(models.RuleExecutionLog.rule_id == int(rule_id))
        
        if success_filter == 'true':
            query = query.filter(models.RuleExecutionLog.success == True)
        elif success_filter == 'false':
            query = query.filter(models.RuleExecutionLog.success == False)
        
        # Order by most recent first
        logs = query.order_by(
            models.RuleExecutionLog.executed_at.desc()
        ).limit(limit).all()
        
        # Get all rules for filter dropdown
        all_rules = db_session.query(models.AutoRule).filter_by(
            user_id=user.id
        ).order_by(models.AutoRule.name.asc()).all()
        
        # Decrypt email subjects for display
        master_key = session.get("master_key")
        decrypted_logs = []
        
        if master_key:
            for log, rule, processed, raw in logs:
                try:
                    subject = encryption.EmailDataManager.decrypt_email_subject(
                        raw.encrypted_subject or "", master_key
                    )
                except:
                    subject = "(Entschlüsselung fehlgeschlagen)"
                
                decrypted_logs.append({
                    'log': log,
                    'rule': rule,
                    'subject': subject,
                    'email_id': raw.id  # raw_email_id für konsistente URLs
                })
        
        return render_template(
            "rules_execution_log.html",
            user=user,
            logs=decrypted_logs,
            all_rules=all_rules,
            limit=limit,
            rule_id=rule_id,
            success_filter=success_filter
        )
    
    finally:
        db_session.close()


# ===== End Phase G.2 =====


# ============================================================================
# ===== Phase H: SMTP Mail-Versand =====
# ============================================================================

@app.route('/api/account/<int:account_id>/smtp-status', methods=['GET'])
@login_required
def api_smtp_status(account_id):
    """
    Prüft ob SMTP für einen Account konfiguriert ist.
    
    Returns:
    {
        "configured": true,
        "server": "smtp.example.com",
        "port": 587,
        "encryption": "STARTTLS"
    }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    db = get_db_session()
    try:
        account = db.query(models.MailAccount).get(account_id)
        if not account or account.user_id != current_user.id:
            return jsonify({
                "success": False,
                "error": "Account nicht gefunden"
            }), 404
        
        # Prüfen ob SMTP konfiguriert
        has_smtp = bool(
            account.encrypted_smtp_server and 
            (account.encrypted_smtp_password or account.encrypted_imap_password)
        )
        
        if has_smtp:
            sender = smtp_sender.SMTPSender(account, master_key)
            is_valid, error = sender.validate_configuration()
            
            return jsonify({
                "success": True,
                "configured": is_valid,
                "server": sender.credentials.get("smtp_server") if is_valid else None,
                "port": account.smtp_port,
                "encryption": account.smtp_encryption,
                "error": error if not is_valid else None
            })
        else:
            return jsonify({
                "success": True,
                "configured": False,
                "error": "SMTP nicht konfiguriert"
            })
    finally:
        db.close()


@app.route('/api/account/<int:account_id>/test-smtp', methods=['POST'])
@login_required
def api_test_smtp(account_id):
    """
    Testet die SMTP-Verbindung eines Mail-Accounts.
    
    Returns:
        {
            "success": true,
            "message": "SMTP-Verbindung erfolgreich"
        }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    db = get_db_session()
    try:
        # Account laden und Berechtigung prüfen
        account = db.query(models.MailAccount).get(account_id)
        if not account or account.user_id != current_user.id:
            return jsonify({
                "success": False,
                "error": "Account nicht gefunden"
            }), 404
        
        # SMTP testen
        sender = smtp_sender.SMTPSender(account, master_key)
        success, message = sender.test_connection()
        
        return jsonify({
            "success": success,
            "message": message
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    finally:
        db.close()


@app.route('/api/emails/<int:raw_email_id>/send-reply', methods=['POST'])
@login_required
def api_send_reply(raw_email_id):
    """
    Sendet eine Antwort auf eine Email.
    
    POST Body:
    {
        "reply_text": "Danke für Ihre Nachricht...",
        "reply_html": "<p>Danke für Ihre Nachricht...</p>",  // optional
        "include_quote": true,  // optional, default: true
        "cc": ["cc@example.com"],  // optional
        "attachments": [  // optional
            {
                "filename": "dokument.pdf",
                "content_base64": "...",
                "mime_type": "application/pdf"
            }
        ]
    }
    
    Returns:
    {
        "success": true,
        "message_id": "<abc123@example.com>",
        "saved_to_sent": true,
        "sent_folder": "Gesendet",
        "saved_to_db": true,
        "db_email_id": 123
    }
    """
    import base64
    
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    db = get_db_session()
    try:
        # Email laden
        raw_email = db.query(models.RawEmail).get(email_id)
        if not raw_email or raw_email.user_id != current_user.id:
            return jsonify({
                "success": False,
                "error": "Email nicht gefunden"
            }), 404
        
        # Mail-Account prüfen
        account = db.query(models.MailAccount).get(raw_email.mail_account_id)
        if not account:
            return jsonify({
                "success": False,
                "error": "Mail-Account nicht gefunden"
            }), 404
        
        # Request-Body parsen
        data = request.get_json() or {}
        
        reply_text = data.get('reply_text')
        if not reply_text:
            return jsonify({
                "success": False,
                "error": "reply_text ist erforderlich"
            }), 400
        
        reply_html = data.get('reply_html')
        include_quote = data.get('include_quote', True)
        
        # CC-Empfänger parsen
        cc_recipients = None
        if data.get('cc'):
            cc_recipients = [smtp_sender.EmailRecipient.from_string(addr) for addr in data['cc']]
        
        # Anhänge parsen (Base64 → Bytes)
        attachments = None
        if data.get('attachments'):
            attachments = []
            for att in data['attachments']:
                try:
                    content = base64.b64decode(att['content_base64'])
                    attachments.append(smtp_sender.EmailAttachment(
                        filename=att['filename'],
                        content=content,
                        mime_type=att.get('mime_type', 'application/octet-stream')
                    ))
                except Exception as e:
                    return jsonify({
                        "success": False,
                        "error": f"Ungültiger Anhang: {e}"
                    }), 400
        
        # SMTP Sender erstellen und Antwort senden
        sender = smtp_sender.SMTPSender(account, master_key)
        result = sender.send_reply(
            original_email=raw_email,
            reply_text=reply_text,
            reply_html=reply_html,
            include_quote=include_quote,
            cc=cc_recipients,
            attachments=attachments
        )
        
        if result.success:
            return jsonify({
                "success": True,
                "message_id": result.message_id,
                "saved_to_sent": result.saved_to_sent,
                "sent_folder": result.sent_folder,
                "imap_uid": result.imap_uid,
                "saved_to_db": result.saved_to_db,
                "db_email_id": result.db_email_id
            })
        else:
            return jsonify({
                "success": False,
                "error": result.error
            }), 500
            
    except Exception as e:
        logger.error(f"Send-Reply Fehler: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    finally:
        db.close()


@app.route('/api/account/<int:account_id>/send', methods=['POST'])
@login_required
def api_send_email(account_id):
    """
    Sendet eine neue Email (nicht als Antwort).
    
    POST Body:
    {
        "to": ["empfaenger@example.com"],
        "cc": ["cc@example.com"],  // optional
        "bcc": ["bcc@example.com"],  // optional
        "subject": "Betreff",
        "body_text": "Hallo...",
        "body_html": "<p>Hallo...</p>",  // optional
        "attachments": [...]  // optional, wie bei send-reply
    }
    
    Returns:
    {
        "success": true,
        "message_id": "<abc123@example.com>",
        ...
    }
    """
    import base64
    
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    db = get_db_session()
    try:
        # Account laden
        account = db.query(models.MailAccount).get(account_id)
        if not account or account.user_id != current_user.id:
            return jsonify({
                "success": False,
                "error": "Account nicht gefunden"
            }), 404
        
        # Request-Body parsen
        data = request.get_json() or {}
        
        # Pflichtfelder validieren
        if not data.get('to'):
            return jsonify({
                "success": False,
                "error": "Mindestens ein Empfänger (to) erforderlich"
            }), 400
        
        if not data.get('subject'):
            return jsonify({
                "success": False,
                "error": "Betreff (subject) erforderlich"
            }), 400
        
        if not data.get('body_text'):
            return jsonify({
                "success": False,
                "error": "Nachrichtentext (body_text) erforderlich"
            }), 400
        
        # Empfänger parsen
        to_recipients = [smtp_sender.EmailRecipient.from_string(addr) for addr in data['to']]
        cc_recipients = [smtp_sender.EmailRecipient.from_string(addr) for addr in data.get('cc', [])]
        bcc_recipients = [smtp_sender.EmailRecipient.from_string(addr) for addr in data.get('bcc', [])]
        
        # Anhänge parsen
        attachments = []
        if data.get('attachments'):
            for att in data['attachments']:
                try:
                    content = base64.b64decode(att['content_base64'])
                    attachments.append(smtp_sender.EmailAttachment(
                        filename=att['filename'],
                        content=content,
                        mime_type=att.get('mime_type', 'application/octet-stream')
                    ))
                except Exception as e:
                    return jsonify({
                        "success": False,
                        "error": f"Ungültiger Anhang: {e}"
                    }), 400
        
        # OutgoingEmail erstellen
        email = smtp_sender.OutgoingEmail(
            to=to_recipients,
            cc=cc_recipients,
            bcc=bcc_recipients,
            subject=data['subject'],
            body_text=data['body_text'],
            body_html=data.get('body_html'),
            attachments=attachments
        )
        
        # Senden
        sender = smtp_sender.SMTPSender(account, master_key)
        result = sender.send_email(email)
        
        if result.success:
            return jsonify({
                "success": True,
                "message_id": result.message_id,
                "saved_to_sent": result.saved_to_sent,
                "sent_folder": result.sent_folder,
                "imap_uid": result.imap_uid,
                "saved_to_db": result.saved_to_db,
                "db_email_id": result.db_email_id
            })
        else:
            return jsonify({
                "success": False,
                "error": result.error
            }), 500
            
    except Exception as e:
        logger.error(f"Send-Email Fehler: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    finally:
        db.close()


@app.route('/api/emails/<int:raw_email_id>/generate-and-send', methods=['POST'])
@login_required
def api_generate_and_send_reply(raw_email_id):
    """
    Generiert einen KI-Entwurf UND sendet ihn optional direkt.
    
    POST Body:
    {
        "tone": "formal",
        "custom_instructions": "Termine vorschlagen",
        "include_quote": true,
        "send_immediately": false  // false = nur generieren, nicht senden
    }
    
    Returns:
    {
        "success": true,
        "draft_text": "...",  // Der generierte Text
        "sent": true,         // Wurde gesendet?
        "message_id": "...",  // Falls gesendet
        ...
    }
    """
    from src.reply_generator import generate_reply_draft
    
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert"
        }), 401
    
    db = get_db_session()
    try:
        # Email laden
        raw_email = db.query(models.RawEmail).get(raw_email_id)
        if not raw_email or raw_email.user_id != current_user.id:
            return jsonify({
                "success": False,
                "error": "Email nicht gefunden"
            }), 404
        
        data = request.get_json() or {}
        tone = data.get('tone', 'formal')
        custom_instructions = data.get('custom_instructions')
        include_quote = data.get('include_quote', True)
        send_immediately = data.get('send_immediately', False)
        
        # 1. Draft generieren
        draft = generate_reply_draft(
            email_id=raw_email_id,
            master_key=master_key,
            tone=tone,
            custom_instructions=custom_instructions
        )
        
        if not draft:
            return jsonify({
                "success": False,
                "error": "Draft-Generierung fehlgeschlagen"
            }), 500
        
        response = {
            "success": True,
            "draft_text": draft['draft_text'],
            "subject": draft['subject'],
            "recipient": draft['recipient'],
            "tone": draft['tone'],
            "generation_time_ms": draft['generation_time_ms'],
            "sent": False
        }
        
        # 2. Optional: Direkt senden
        if send_immediately:
            account = db.query(models.MailAccount).get(raw_email.mail_account_id)
            if not account:
                response["send_error"] = "Mail-Account nicht gefunden"
                return jsonify(response)
            
            sender = smtp_sender.SMTPSender(account, master_key)
            result = sender.send_reply(
                original_email=raw_email,
                reply_text=draft['draft_text'],
                include_quote=include_quote
            )
            
            if result.success:
                response["sent"] = True
                response["message_id"] = result.message_id
                response["saved_to_sent"] = result.saved_to_sent
                response["saved_to_db"] = result.saved_to_db
            else:
                response["send_error"] = result.error
        
        return jsonify(response)
    except Exception as e:
        logger.error(f"Generate-and-send Fehler: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    finally:
        db.close()


# ===== End Phase H =====
# ===== End Phase G.1 =====


@app.route("/api/emails/<int:raw_email_id>/check-embedding-compatibility", methods=["GET"])
@login_required
def api_check_embedding_compatibility(raw_email_id):
    """
    Pre-Check: Prüft ob Email-Embedding mit GEWÄHLTEM Model kompatibel ist
    
    Vergleicht: current_email_dim VS selected_embedding_model_dim (aus Settings)
    
    Returns:
        {
            "compatible": bool,
            "current_dim": int,
            "expected_dim": int,
            "message": str
        }
    """
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"compatible": False, "error": "Unauthorized"}), 401
        
        # Hole Email
        raw_email = (
            db.query(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None
            )
            .first()
        )
        
        if not raw_email:
            return jsonify({"compatible": False, "error": "Email nicht gefunden"}), 404
        
        # WICHTIG: Prüfe gegen GEWÄHLTES Embedding Model (aus Settings!)
        from src.semantic_search import get_embedding_dim_from_bytes
        
        current_dim = get_embedding_dim_from_bytes(raw_email.email_embedding) if raw_email.email_embedding else 0
        
        # Hole erwartete Dimension vom GEWÄHLTEN Model
        provider_embedding = (user.preferred_embedding_provider or "ollama").lower()
        model_embedding = user.preferred_embedding_model or "all-minilm:22m"
        
        # Model-spezifische Dimensionen (hardcoded für bekannte Modelle)
        MODEL_DIMENSIONS = {
            "all-minilm:22m": 384,
            "nomic-embed-text": 768,
            "bge-large": 1024,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
            "mistral-embed": 1024,
        }
        
        expected_dim = MODEL_DIMENSIONS.get(model_embedding, 384)  # Default 384
        
        compatible = (current_dim == expected_dim) if current_dim > 0 else True
        
        return jsonify({
            "compatible": compatible,
            "current_dim": current_dim,
            "expected_dim": expected_dim,
            "selected_model": model_embedding,
            "message": f"Embedding-Dimension {current_dim} weicht vom gewählten Model ({model_embedding}: {expected_dim}) ab. "
                      f"Bitte nutze 'Alle Emails neu embedden' in den Settings!"
                      if not compatible else "Embedding kompatibel"
        }), 200
        
    except Exception as e:
        logger.error(f"Compatibility check failed: {e}")
        return jsonify({"compatible": True, "error": str(e)}), 200  # Allow on error
    finally:
        db.close()


@app.route("/api/emails/<int:raw_email_id>/reprocess", methods=["POST"])
@login_required
@limiter.limit("10 per minute")  # 🐛 BUG-012 FIX: Rate Limit für AI-Reprocessing
def api_reprocess_email(raw_email_id):
    """
    API: Email neu verarbeiten (Phase F.2 Enhanced)
    
    Regeneriert:
    - Email-Embedding (mit aktuellem Base Model aus Settings)
    - AI-Score + Kategorie
    - Tag-Suggestions (automatisch mit neuem Embedding)
    
    Use Case: Model-Wechsel (z.B. all-minilm → bge-large)
    """
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"success": False, "error": "Master-Key nicht verfügbar"}), 401
        
        # Validiere Email-Zugriff
        raw_email = (
            db.query(models.RawEmail)
            .filter(
                models.RawEmail.id == email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None
            )
            .first()
        )
        
        if not raw_email:
            return jsonify({"success": False, "error": "Email nicht gefunden"}), 404
        
        # Entschlüssele für Reprocessing
        try:
            decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                raw_email.encrypted_subject or "", master_key
            )
            decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                raw_email.encrypted_body or "", master_key
            )
        except Exception as e:
            logger.error(f"Decryption failed for email {email_id}: {e}")
            return jsonify({"success": False, "error": "Entschlüsselung fehlgeschlagen"}), 500
        
        # 1. EMBEDDING neu generieren (mit EMBEDDING Model aus Settings!)
        try:
            from src.semantic_search import generate_embedding_for_email
            
            # WICHTIG: Nutze EMBEDDING Settings (nicht BASE!)
            provider_embedding = (user.preferred_embedding_provider or "ollama").lower()
            model_embedding = user.preferred_embedding_model or "all-minilm:22m"
            resolved_model_embedding = ai_client.resolve_model(provider_embedding, model_embedding)
            
            embedding_client = ai_client.build_client(provider_embedding, model=resolved_model_embedding)
            
            embedding_bytes, model_name, timestamp = generate_embedding_for_email(
                subject=decrypted_subject,
                body=decrypted_body,
                ai_client=embedding_client,
                model_name=resolved_model_embedding  # Übergebe explizit das Model
            )
            
            if embedding_bytes:
                raw_email.email_embedding = embedding_bytes
                raw_email.embedding_model = model_name or resolved_model_embedding
                raw_email.embedding_generated_at = timestamp
                logger.info(f"✅ Embedding regenerated: {model_name} ({len(embedding_bytes)} bytes)")
            else:
                logger.warning("⚠️  Embedding regeneration failed")
        except Exception as emb_err:
            logger.error(f"Embedding regeneration error: {emb_err}")
            # Nicht kritisch, fahre fort
        
        # 2. AI-SCORE + KATEGORIE neu berechnen
        ai_score = None
        try:
            processing_mod = importlib.import_module(".12_processing", "src")
            
            # Build Thread-Context
            thread_context = processing_mod.build_thread_context(
                session=db,
                raw_email=raw_email,
                master_key=master_key,
                max_context_emails=5
            )
            
            # Nutze Optimize Model für Processing (nicht Base Model!)
            provider_optimize = (user.preferred_ai_provider_optimize or "ollama").lower()
            model_optimize = user.preferred_ai_model_optimize or "llama3.2:1b"
            resolved_model_optimize = ai_client.resolve_model(provider_optimize, model_optimize)
            
            optimize_client = ai_client.build_client(provider_optimize, model=resolved_model_optimize)
            
            result = optimize_client.analyze_email(
                subject=decrypted_subject,
                body=decrypted_body,
                language="de",
                context=thread_context if thread_context else None
            )
            
            # Update ProcessedEmail
            processed = db.query(models.ProcessedEmail).filter_by(
                raw_email_id=raw_email.id
            ).first()
            
            if processed and result:
                processed.score = result.get("score", processed.score)
                processed.farbe = result.get("farbe", processed.farbe)
                processed.kategorie_aktion = result.get("kategorie_aktion", processed.kategorie_aktion)
                ai_score = processed.score
                logger.info(f"✅ Score regenerated: {processed.score} ({processed.farbe})")
            
        except Exception as score_err:
            logger.error(f"Score regeneration error: {score_err}")
        
        # 3. TAG-SUGGESTIONS werden automatisch neu berechnet (via neues Embedding)
        # → Keine extra Action nötig, Frontend reload holt neue Suggestions
        
        db.commit()
        
        return jsonify({
            "success": True,
            "message": "Email erfolgreich neu verarbeitet",
            "embedding_model": raw_email.embedding_model,
            "ai_score": ai_score,
            "timestamp": datetime.now(UTC).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Reprocess failed for email {email_id}: {e}")
        db.rollback()
        return jsonify({
            "success": False,
            "error": f"Neuverarbeitung fehlgeschlagen: {str(e)}"
        }), 500
    finally:
        db.close()


@app.route("/api/batch-reprocess-embeddings", methods=["POST"])
@login_required
@limiter.limit("5 per minute")  # 🐛 BUG-012 FIX: Strenge Rate Limit - sehr rechenintensiv!
def api_batch_reprocess_embeddings():
    """
    Batch-Reprocess: Regeneriert Embeddings für ALLE Emails (async mit Progress)
    
    Use Case: User wechselt Embedding-Model (z.B. all-minilm → bge-large)
    → Alle Emails müssen neu embedded werden für konsistente Semantic Search!
    
    Returns job_id für Progress-Tracking
    """
    db = get_db_session()
    
    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"success": False, "error": "Master-Key nicht verfügbar"}), 401
        
        # Hole aktuelles Embedding-Model aus Settings
        provider_embedding = (user.preferred_embedding_provider or "ollama").lower()
        model_embedding = user.preferred_embedding_model or "all-minilm:22m"
        
        # Enqueue async job
        job_id = job_queue.enqueue_batch_reprocess_job(
            user_id=user.id,
            master_key=master_key,
            provider=provider_embedding,
            model=model_embedding
        )
        
        return jsonify({
            "success": True,
            "status": "queued",
            "job_id": job_id,
            "message": "Batch-Reprocess gestartet"
        }), 200
        
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Batch-Reprocess enqueue failed: {e}")
        return jsonify({
            "success": False,
            "error": f"Batch-Reprocess fehlgeschlagen: {str(e)}"
        }), 500
    finally:
        db.close()


# ===== End Phase F.2 Enhanced =====


def _trigger_online_learning(email, data: dict):
    """Phase 11b: Online-Learning nach User-Korrektur.

    Trainiert SGD-Klassifikatoren inkrementell mit der neuen Korrektur.
    Aktualisiert auch Sender-Patterns für konsistente Klassifizierung (Phase 11d).
    Läuft async im Hintergrund um Response nicht zu verzögern.
    """
    try:
        # Import hier um circular imports zu vermeiden
        train_mod = importlib.import_module("src.train_classifier")

        # Hole Original-Mail-Daten
        subject = ""
        body = ""
        sender = ""
        user_id = None

        if email.raw_email:
            subject = email.raw_email.subject or ""
            body = email.raw_email.body or ""
            sender = email.raw_email.sender or ""
            user_id = email.raw_email.user_id

        if not subject and not body:
            logger.debug("Online-Learning übersprungen: Keine Mail-Daten")
            return

        # Initialisiere OnlineLearner
        learner = train_mod.OnlineLearner()

        # Lerne aus jeder Korrektur
        learned_count = 0

        if data.get("dringlichkeit") is not None:
            if learner.learn_from_correction(
                subject, body, "dringlichkeit", data["dringlichkeit"]
            ):
                learned_count += 1

        if data.get("wichtigkeit") is not None:
            if learner.learn_from_correction(
                subject, body, "wichtigkeit", data["wichtigkeit"]
            ):
                learned_count += 1

        if data.get("spam_flag") is not None:
            if learner.learn_from_correction(subject, body, "spam", data["spam_flag"]):
                learned_count += 1

        if data.get("kategorie") is not None:
            if learner.learn_from_correction(subject, body, "kategorie", data["kategorie"]):
                learned_count += 1

        if learned_count > 0:
            logger.info(
                f"📚 Online-Learning: {learned_count} Klassifikator(en) aktualisiert"
            )

        # Phase 11d: Sender-Pattern aktualisieren
        if sender and user_id:
            try:
                sender_patterns_mod = importlib.import_module(
                    "src.services.sender_patterns"
                )
                db = get_db_session()
                try:
                    sender_patterns_mod.SenderPatternManager.update_from_classification(
                        db=db,
                        user_id=user_id,
                        sender=sender,
                        category=data.get("kategorie"),
                        priority=data.get("dringlichkeit"),
                        is_newsletter=data.get("spam_flag"),
                        is_correction=True,  # User-Korrektur hat höheres Gewicht
                    )
                    logger.debug(f"📊 Sender-Pattern aktualisiert für User {user_id}")
                finally:
                    db.close()
            except Exception as e:
                logger.debug(f"Sender-Pattern Update übersprungen: {e}")

    except ImportError:
        logger.debug("Online-Learning nicht verfügbar (scikit-learn nicht installiert)")
    except Exception as e:
        # Online-Learning ist optional - Fehler sollten Korrektur nicht blockieren
        logger.warning(f"Online-Learning Fehler (nicht kritisch): {e}")


@app.route("/settings/ai", methods=["POST"])
@login_required
def save_ai_preferences():
    """Speichert KI-Provider- und Modellpräferenzen für Embedding + Base + Optimize Pass."""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        # 1. EMBEDDING Settings
        provider_embedding = (request.form.get("ai_provider_embedding") or "ollama").lower()
        model_embedding = (request.form.get("ai_model_embedding") or "").strip()
        
        # 2. BASE Settings
        provider_base = (request.form.get("ai_provider_base") or "ollama").lower()
        model_base = (request.form.get("ai_model_base") or "").strip()

        # 3. OPTIMIZE Settings
        provider_optimize = (
            request.form.get("ai_provider_optimize") or "ollama"
        ).lower()
        model_optimize = (request.form.get("ai_model_optimize") or "").strip()

        # Validierung (basic - kann erweitert werden)
        if not model_embedding:
            flash("Embedding-Model ist erforderlich!", "danger")
            return redirect(url_for("settings"))
        
        if not model_base:
            flash("Base-Model ist erforderlich!", "danger")
            return redirect(url_for("settings"))
            
        if not model_optimize:
            flash("Optimize-Model ist erforderlich!", "danger")
            return redirect(url_for("settings"))

        # Speichern
        user.preferred_embedding_provider = provider_embedding
        user.preferred_embedding_model = model_embedding
        user.preferred_ai_provider = provider_base
        user.preferred_ai_model = model_base
        user.preferred_ai_provider_optimize = provider_optimize
        user.preferred_ai_model_optimize = model_optimize
        db.commit()

        flash("✅ KI-Präferenzen gespeichert (Embedding + Base + Optimize).", "success")
    except Exception as exc:
        db.rollback()
        logger.error(f"Fehler beim Speichern der KI-Präferenz: {type(exc).__name__}")
        flash("Speichern fehlgeschlagen. Bitte Log prüfen.", "danger")
    finally:
        db.close()

    return redirect(url_for("settings"))


@app.route("/settings/password", methods=["GET", "POST"])
@login_required
def change_password():
    """Passwort-Änderung mit KEK-Neuableitung (Phase 8c Security Hardening)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        if request.method == "POST":
            old_password = request.form.get("old_password", "").strip()
            new_password = request.form.get("new_password", "").strip()
            new_password_confirm = request.form.get("new_password_confirm", "").strip()

            # 1. Validierung: Alle Felder ausgefüllt
            if not all([old_password, new_password, new_password_confirm]):
                flash("Alle Felder sind erforderlich", "danger")
                return render_template("change_password.html")

            # 2. Validierung: Neue Passwörter stimmen überein
            if new_password != new_password_confirm:
                flash("Neue Passwörter stimmen nicht überein", "danger")
                return render_template("change_password.html")

            # 3. Validierung: Altes Passwort korrekt
            if not user.check_password(old_password):
                flash("Altes Passwort ist falsch", "danger")
                return render_template("change_password.html")

            # 4. Validierung: Password Policy (OWASP)
            is_valid, error_msg = password_validator.PasswordValidator.validate(
                new_password
            )
            if not is_valid:
                flash(error_msg, "danger")
                return render_template("change_password.html")

            # 5. KEK-Neuableitung + DEK-Re-Encryption
            try:
                # Entschlüssele DEK mit altem Passwort
                old_dek = auth.MasterKeyManager.decrypt_dek_from_password(
                    user, old_password
                )
                if not old_dek:
                    flash("DEK-Entschlüsselung fehlgeschlagen", "danger")
                    return render_template("change_password.html")

                # Generiere neuen Salt + KEK aus neuem Passwort
                new_salt = encryption.EncryptionManager.generate_salt()
                new_kek = encryption.EncryptionManager.generate_master_key(
                    new_password, new_salt
                )

                # Verschlüssele DEK mit neuem KEK
                new_encrypted_dek = encryption.EncryptionManager.encrypt_dek(
                    old_dek, new_kek
                )

                # Speichere neuen Salt + encrypted_dek
                user.salt = new_salt
                user.encrypted_dek = new_encrypted_dek
                user.set_password(new_password)
                db.commit()

                logger.info(
                    f"✅ Passwort geändert für User {user.id} - KEK neu abgeleitet, DEK re-encrypted"
                )

                # 6. Session-Invalidierung (Sicherheit)
                session.clear()
                logout_user()

                flash("Passwort erfolgreich geändert! Bitte neu anmelden.", "success")
                return redirect(url_for("login"))

            except Exception as e:
                db.rollback()
                logger.error(f"❌ Fehler bei Passwort-Änderung: {type(e).__name__}")
                flash(
                    "Passwort-Änderung fehlgeschlagen. Bitte erneut versuchen.",
                    "danger",
                )
                return render_template("change_password.html")

        return render_template("change_password.html")

    finally:
        db.close()


@app.route("/api/available-models/<provider>")
@login_required
def get_available_models(provider):
    """Gibt verfügbare Modelle für einen Provider zurück, gefiltert nach kind=base/optimize"""
    try:
        kind = request.args.get('kind', None)  # 'base', 'optimize', oder None
        models_list = provider_utils.get_available_models(provider, kind=kind)
        return jsonify({"models": models_list})
    except Exception as exc:
        logger.error(f"Fehler beim Abrufen von Modellen für {provider}: {exc}")
        return jsonify({"error": "Modelle konnten nicht abgerufen werden"}), 500


@app.route("/api/available-providers")
@login_required
def get_available_providers():
    """Gibt verfügbare KI-Provider zurück (basierend auf API-Keys)"""
    try:
        providers = provider_utils.get_available_providers()
        return jsonify({"providers": providers})
    except Exception as exc:
        logger.error(f"Fehler beim Abrufen von Providern: {exc}")
        return jsonify({"error": "Provider konnten nicht abgerufen werden"}), 500


@app.route("/settings/2fa/setup", methods=["GET", "POST"])
@login_required
def setup_2fa():
    """2FA Setup: QR-Code und Recovery-Codes"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        if user.totp_enabled:
            return redirect(url_for("settings"))

        if request.method == "POST":
            token = request.form.get("token", "").strip()

            totp_secret = session.get("totp_setup_secret")
            if not totp_secret:
                return redirect(url_for("setup_2fa"))

            if not auth.AuthManager.verify_totp(totp_secret, token):
                return render_template("setup_2fa.html", error="Ungültiger Code"), 401

            user.totp_secret = totp_secret
            user.totp_enabled = True
            db.commit()

            recovery_codes = auth.RecoveryCodeManager.create_recovery_codes(
                user.id, db, count=10
            )

            session.pop("totp_setup_secret", None)

            logger.info(f"✅ 2FA für User {user.username} aktiviert")

            return render_template(
                "setup_2fa_success.html", recovery_codes=recovery_codes
            )

        totp_secret = auth.AuthManager.generate_totp_secret()
        qr_code = auth.AuthManager.generate_qr_code(user.email, totp_secret)

        session["totp_setup_secret"] = totp_secret

        return render_template(
            "setup_2fa.html", qr_code=qr_code, totp_secret=totp_secret
        )

    finally:
        db.close()


@app.route("/settings/2fa/recovery-codes/regenerate", methods=["POST"])
@login_required
def regenerate_recovery_codes():
    """Generiert neue Recovery-Codes und invalidiert alte (Phase 8c Security Hardening)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        if not user.totp_enabled:
            flash("2FA ist nicht aktiviert", "danger")
            return redirect(url_for("settings"))

        # Invalidiere alle alten Recovery-Codes
        auth.RecoveryCodeManager.invalidate_all_codes(user.id, db)

        # Generiere neue 10 Recovery-Codes
        recovery_codes = auth.RecoveryCodeManager.create_recovery_codes(
            user.id, db, count=10
        )

        logger.info(f"✅ Recovery-Codes regeneriert für User {user.id}")

        return render_template(
            "recovery_codes_regenerated.html", recovery_codes=recovery_codes
        )

    finally:
        db.close()


@app.route("/settings/mail-account/select-type", methods=["GET"])
@login_required
def select_account_type():
    """Wählt Konto-Typ: Google OAuth oder Manuell"""
    return render_template("select_account_type.html")


@app.route("/settings/mail-account/google-setup", methods=["GET", "POST"])
@login_required
def google_oauth_setup():
    """Google OAuth Setup: Sammelt Client ID/Secret und startet OAuth Flow"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        if request.method == "POST":
            client_id = request.form.get("client_id", "").strip()
            client_secret = request.form.get("client_secret", "").strip()

            if not client_id or not client_secret:
                return (
                    render_template(
                        "google_oauth_setup.html",
                        step=1,
                        error="Client-ID und Client-Secret sind erforderlich",
                    ),
                    400,
                )

            session["google_oauth_client_id"] = client_id
            session["google_oauth_client_secret"] = client_secret
            session["google_oauth_state"] = auth.AuthManager.generate_totp_secret()[:16]

            redirect_uri = url_for(
                "google_oauth_callback", _external=True, _scheme="http"
            )

            auth_url = google_oauth.GoogleOAuthManager.get_auth_url(
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=session["google_oauth_state"],
            )

            return render_template(
                "google_oauth_setup.html", step=2, google_auth_url=auth_url
            )

        return render_template("google_oauth_setup.html", step=1)

    finally:
        db.close()


@app.route("/settings/mail-account/google/callback", methods=["GET"])
@login_required
def google_oauth_callback():
    """Google OAuth Callback: Tauscht Auth Code gegen Token"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        code = request.args.get("code")
        state = request.args.get("state")
        error = request.args.get("error")

        if error:
            logger.error(f"Google OAuth Fehler: {error}")
            return (
                render_template(
                    "google_oauth_setup.html",
                    step=1,
                    error=f"Google hat Zugriff verweigert: {error}",
                ),
                401,
            )

        if not code:
            return (
                render_template(
                    "google_oauth_setup.html",
                    step=1,
                    error="Kein Authorization Code erhalten",
                ),
                400,
            )

        stored_state = session.get("google_oauth_state")
        if state != stored_state:
            logger.warning(f"State mismatch: {state} vs {stored_state}")
            return (
                render_template(
                    "google_oauth_setup.html",
                    step=1,
                    error="Sicherheitsfehler: State mismatch",
                ),
                401,
            )

        client_id = session.get("google_oauth_client_id")
        client_secret = session.get("google_oauth_client_secret")

        if not client_id or not client_secret:
            return (
                render_template(
                    "google_oauth_setup.html",
                    step=1,
                    error="OAuth Credentials nicht im Session",
                ),
                401,
            )

        redirect_uri = url_for("google_oauth_callback", _external=True, _scheme="http")

        token_data = google_oauth.GoogleOAuthManager.exchange_code_for_token(
            auth_code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )

        if not token_data:
            return (
                render_template(
                    "google_oauth_setup.html",
                    step=1,
                    error="Token-Austausch fehlgeschlagen",
                ),
                401,
            )

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 3600)

        email = google_oauth.GoogleOAuthManager.get_user_email(access_token)
        if not email:
            return (
                render_template(
                    "google_oauth_setup.html",
                    step=1,
                    error="User Email konnte nicht abgerufen werden",
                ),
                401,
            )

        master_key = session.get("master_key")

        encrypted_token = access_token
        encrypted_refresh_token = refresh_token
        if master_key:
            encrypted_token = encryption.CredentialManager.encrypt_imap_password(
                access_token, master_key
            )
            if refresh_token:
                encrypted_refresh_token = (
                    encryption.CredentialManager.encrypt_imap_password(
                        refresh_token, master_key
                    )
                )

        oauth_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Zero-Knowledge: Verschlüssele E-Mail-Adresse und Server
        encrypted_server = encryption.CredentialManager.encrypt_server(
            "gmail.com", master_key
        )
        encrypted_username = encryption.CredentialManager.encrypt_email_address(
            email, master_key
        )
        server_hash = encryption.CredentialManager.hash_email_address("gmail.com")
        username_hash = encryption.CredentialManager.hash_email_address(email)

        mail_account = models.MailAccount(
            user_id=user.id,
            name=f"Gmail ({email[:3]}***)",  # Nur Teilanzeige für Zero-Knowledge
            encrypted_imap_server=encrypted_server,
            imap_server_hash=server_hash,
            imap_port=993,
            encrypted_imap_username=encrypted_username,
            imap_username_hash=username_hash,
            imap_encryption="SSL",
            oauth_provider="google",
            encrypted_oauth_token=encrypted_token,
            encrypted_oauth_refresh_token=encrypted_refresh_token,
            oauth_expires_at=oauth_expires_at,
            enabled=True,
        )

        db.add(mail_account)
        db.commit()
        
        # P2-008: Phase Y Config automatisch erstellen
        email_domain = email.split('@')[1] if '@' in email else None
        initialize_phase_y_config(db, user.id, mail_account.id, email_domain)

        session.pop("google_oauth_client_id", None)
        session.pop("google_oauth_client_secret", None)
        session.pop("google_oauth_state", None)

        logger.info(
            f"✅ Google OAuth Account hinzugefügt für User (ID: {user.id}): {email[:3]}***@***"
        )

        return redirect(url_for("settings"))

    except Exception as e:
        logger.error(f"OAuth Callback Fehler: {type(e).__name__}")
        return (
            render_template(
                "google_oauth_setup.html",
                step=1,
                error="OAuth-Authentifizierung fehlgeschlagen",
            ),
            500,
        )

    finally:
        db.close()


@app.route("/settings/mail-account/add", methods=["GET", "POST"])
@login_required
def add_mail_account():
    """Fügt einen neuen Mail-Account hinzu"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        if request.method == "POST":
            name = request.form.get("name")
            imap_server = request.form.get("imap_server")
            imap_port = request.form.get("imap_port", "993")
            imap_username = request.form.get("imap_username")
            imap_password = request.form.get("imap_password")
            imap_encryption = request.form.get("imap_encryption", "SSL")

            if not all([name, imap_server, imap_username, imap_password]):
                return (
                    render_template(
                        "add_mail_account.html", error="Alle Felder sind erforderlich"
                    ),
                    400,
                )

            try:
                imap_port = int(imap_port)
            except ValueError:
                imap_port = 993

            if not ensure_master_key_in_session():
                return (
                    render_template(
                        "add_mail_account.html",
                        error="Session abgelaufen. Bitte neu einloggen.",
                    ),
                    401,
                )

            master_key = session.get("master_key")

            # Zero-Knowledge: Verschlüssele alle sensiblen Daten
            encrypted_password = encryption.CredentialManager.encrypt_imap_password(
                imap_password, master_key
            )
            encrypted_imap_server = encryption.CredentialManager.encrypt_server(
                imap_server, master_key
            )
            encrypted_imap_username = (
                encryption.CredentialManager.encrypt_email_address(
                    imap_username, master_key
                )
            )

            # Hash für Suche (nicht umkehrbar)
            imap_server_hash = encryption.CredentialManager.hash_email_address(
                imap_server
            )
            imap_username_hash = encryption.CredentialManager.hash_email_address(
                imap_username
            )

            smtp_server = request.form.get("smtp_server", "").strip() or None
            smtp_username = request.form.get("smtp_username", "").strip() or None

            encrypted_smtp_server = None
            encrypted_smtp_username = None
            if smtp_server:
                encrypted_smtp_server = encryption.CredentialManager.encrypt_server(
                    smtp_server, master_key
                )
            if smtp_username:
                encrypted_smtp_username = (
                    encryption.CredentialManager.encrypt_email_address(
                        smtp_username, master_key
                    )
                )

            mail_account = models.MailAccount(
                user_id=user.id,
                name=name,
                encrypted_imap_server=encrypted_imap_server,
                imap_server_hash=imap_server_hash,
                imap_port=imap_port,
                encrypted_imap_username=encrypted_imap_username,
                imap_username_hash=imap_username_hash,
                encrypted_imap_password=encrypted_password,
                imap_encryption=imap_encryption,
                encrypted_smtp_server=encrypted_smtp_server,
                smtp_port=int(request.form.get("smtp_port", 587))
                if smtp_server
                else None,
                encrypted_smtp_username=encrypted_smtp_username,
                smtp_encryption=request.form.get("smtp_encryption", "STARTTLS"),
            )

            smtp_password = request.form.get("smtp_password", "").strip()
            if smtp_password:
                master_key = session.get("master_key")
                encrypted_smtp_password = (
                    encryption.CredentialManager.encrypt_imap_password(
                        smtp_password, master_key
                    )
                )
                mail_account.encrypted_smtp_password = encrypted_smtp_password

            db.add(mail_account)
            db.commit()
            
            # P2-008: Phase Y Config automatisch erstellen
            email_domain = imap_username.split('@')[1] if '@' in imap_username else None
            initialize_phase_y_config(db, user.id, mail_account.id, email_domain)

            logger.info(f"✅ Mail-Account '{name}' hinzugefügt für User {user.username}")

            return redirect(url_for("settings"))

        return render_template("add_mail_account.html")

    except Exception as e:
        logger.error(f"Fehler beim Hinzufügen von Mail-Account: {type(e).__name__}")
        return (
            render_template("add_mail_account.html", error="Fehler beim Speichern"),
            500,
        )

    finally:
        db.close()


@app.route("/settings/mail-account/<int:account_id>/edit", methods=["GET", "POST"])
@login_required
def edit_mail_account(account_id):
    """Bearbeitet einen Mail-Account"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )

        if not account:
            return redirect(url_for("settings"))

        if request.method == "POST":
            account.name = request.form.get("name", account.name)
            account.imap_port = int(request.form.get("imap_port", account.imap_port))
            account.imap_encryption = request.form.get(
                "imap_encryption", account.imap_encryption
            )

            if not ensure_master_key_in_session():
                return (
                    render_template(
                        "edit_mail_account.html",
                        account=account,
                        error="Session abgelaufen. Bitte neu einloggen.",
                    ),
                    401,
                )

            master_key = session.get("master_key")

            # Zero-Knowledge: Verschlüssele Server und Username wenn geändert
            new_imap_server = request.form.get("imap_server", "").strip()
            if new_imap_server:
                account.encrypted_imap_server = (
                    encryption.CredentialManager.encrypt_server(
                        new_imap_server, master_key
                    )
                )
                account.imap_server_hash = (
                    encryption.CredentialManager.hash_email_address(new_imap_server)
                )

            new_imap_username = request.form.get("imap_username", "").strip()
            if new_imap_username:
                account.encrypted_imap_username = (
                    encryption.CredentialManager.encrypt_email_address(
                        new_imap_username, master_key
                    )
                )
                account.imap_username_hash = (
                    encryption.CredentialManager.hash_email_address(new_imap_username)
                )

            new_password = request.form.get("imap_password", "").strip()
            if new_password:
                encrypted_password = encryption.CredentialManager.encrypt_imap_password(
                    new_password, master_key
                )
                account.encrypted_imap_password = encrypted_password

            # SMTP Felder
            new_smtp_server = request.form.get("smtp_server", "").strip() or None
            if new_smtp_server:
                account.encrypted_smtp_server = (
                    encryption.CredentialManager.encrypt_server(
                        new_smtp_server, master_key
                    )
                )
            else:
                account.encrypted_smtp_server = None

            account.smtp_port = (
                int(request.form.get("smtp_port", 587)) if new_smtp_server else None
            )

            new_smtp_username = request.form.get("smtp_username", "").strip() or None
            if new_smtp_username:
                account.encrypted_smtp_username = (
                    encryption.CredentialManager.encrypt_email_address(
                        new_smtp_username, master_key
                    )
                )
            else:
                account.encrypted_smtp_username = None

            account.smtp_encryption = request.form.get("smtp_encryption", "STARTTLS")

            smtp_password = request.form.get("smtp_password", "").strip()
            if smtp_password:
                if not ensure_master_key_in_session():
                    return (
                        render_template(
                            "edit_mail_account.html",
                            account=account,
                            error="Session abgelaufen. Bitte neu einloggen.",
                        ),
                        401,
                    )

                master_key = session.get("master_key")
                encrypted_smtp_password = (
                    encryption.CredentialManager.encrypt_imap_password(
                        smtp_password, master_key
                    )
                )
                account.encrypted_smtp_password = encrypted_smtp_password

            # Phase I.2: Account-spezifische Signatur
            signature_enabled = request.form.get("signature_enabled") == "on"
            account.signature_enabled = signature_enabled
            
            if signature_enabled:
                signature_text = request.form.get("signature_text", "").strip()
                if not signature_text:
                    # Validierung: signature_enabled aber Text leer
                    return (
                        render_template(
                            "edit_mail_account.html",
                            account=account,
                            error="Signatur aktiviert aber Text ist leer. Bitte Text eingeben oder Checkbox deaktivieren.",
                        ),
                        400,
                    )
                if len(signature_text) > 2000:
                    return (
                        render_template(
                            "edit_mail_account.html",
                            account=account,
                            error="Signatur zu lang (max. 2000 Zeichen).",
                        ),
                        400,
                    )
                # Verschlüssele Signatur mit Master-Key (wie andere Account-Daten)
                try:
                    encrypted_signature = encryption.CredentialManager.encrypt_email_address(
                        signature_text, master_key
                    )
                    account.encrypted_signature_text = encrypted_signature
                except Exception as e:
                    logger.error(f"Failed to encrypt account signature: {e}")
                    return (
                        render_template(
                            "edit_mail_account.html",
                            account=account,
                            error="Fehler beim Verschlüsseln der Signatur.",
                        ),
                        500,
                    )
            else:
                # Wenn deaktiviert, lösche verschlüsselte Signatur
                account.encrypted_signature_text = None

            db.commit()
            logger.info(f"✅ Mail-Account '{account.name}' aktualisiert")

            return redirect(url_for("settings"))

        # Zero-Knowledge: Entschlüssele für Edit-Formular
        master_key = session.get("master_key")
        if master_key:
            try:
                if account.encrypted_imap_server:
                    account.imap_server = encryption.CredentialManager.decrypt_server(
                        account.encrypted_imap_server, master_key
                    )
                if account.encrypted_imap_username:
                    account.imap_username = (
                        encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_imap_username, master_key
                        )
                    )
                if account.encrypted_smtp_server:
                    account.smtp_server = encryption.CredentialManager.decrypt_server(
                        account.encrypted_smtp_server, master_key
                    )
                if account.encrypted_smtp_username:
                    account.smtp_username = (
                        encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_smtp_username, master_key
                        )
                    )
                # Phase I.2: Entschlüssele Account-Signatur
                if account.signature_enabled and account.encrypted_signature_text:
                    account.decrypted_signature_text = (
                        encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_signature_text, master_key
                        )
                    )
                else:
                    account.decrypted_signature_text = None
            except Exception as e:
                logger.warning(f"Konnte Account {account.id} nicht entschlüsseln: {e}")
                account.imap_server = "***verschlüsselt***"
                account.imap_username = "***verschlüsselt***"

        return render_template("edit_mail_account.html", account=account)

    except Exception as e:
        logger.error(f"Fehler beim Bearbeiten von Mail-Account: {type(e).__name__}")
        return redirect(url_for("settings"))

    finally:
        db.close()


@app.route("/settings/mail-account/<int:account_id>/delete", methods=["POST"])
@login_required
def delete_mail_account(account_id):
    """Löscht einen Mail-Account"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)

        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )

        if account:
            db.delete(account)
            db.commit()
            logger.info(f"🗑️  Mail-Account '{account.name}' gelöscht")

        return redirect(url_for("settings"))

    except Exception as e:
        logger.error(f"Fehler beim Löschen von Mail-Account: {type(e).__name__}")
        return redirect(url_for("settings"))

    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Phase 11.5a: IMAP Connection Diagnostics
# ═══════════════════════════════════════════════════════════════════════


@app.route("/imap-diagnostics")
@login_required
def imap_diagnostics():
    """IMAP Connection Diagnostics Dashboard (Phase 11.5a)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        # Phase INV: Zugriffskontrolle - nur für autorisierte User
        if not user.imap_diagnostics_enabled:
            flash("Zugriff verweigert. IMAP-Diagnostics ist für deinen Account nicht aktiviert.", "error")
            return redirect(url_for("dashboard"))

        # Lade Mail-Accounts mit entschlüsselten Usernames
        mail_accounts = (
            db.query(models.MailAccount)
            .filter_by(
                user_id=user.id, enabled=True, auth_type="imap"  # Nur IMAP-Accounts
            )
            .all()
        )

        # Entschlüssele Usernames für Anzeige
        master_key = session.get("master_key")
        if master_key:
            for account in mail_accounts:
                try:
                    if account.encrypted_imap_username:
                        account.decrypted_imap_username = (
                            encryption.CredentialManager.decrypt_email_address(
                                account.encrypted_imap_username, master_key
                            )
                        )
                except Exception as e:
                    logger.warning(
                        f"Konnte Username für Account {account.id} nicht entschlüsseln: {e}"
                    )
                    account.decrypted_imap_username = "***verschlüsselt***"

        return render_template(
            "imap_diagnostics.html",
            user=user,
            accounts=mail_accounts
        )

    finally:
        db.close()


@app.route("/api/imap-diagnostics/<int:account_id>", methods=["POST"])
@login_required
@limiter.limit("10 per minute")  # 🐛 BUG-012 FIX: Rate Limit für IMAP-Tests
def api_imap_diagnostics(account_id):
    """API: Run IMAP diagnostics for a specific account"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"success": False, "error": "Unauthorized"}), 401

        # Lade Account
        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )

        if not account:
            return jsonify({"success": False, "error": "Account nicht gefunden"}), 404

        if account.auth_type != "imap":
            return (
                jsonify({"success": False, "error": "Nur IMAP-Accounts unterstützt"}),
                400,
            )

        # Entschlüssele Credentials
        master_key = session.get("master_key")
        if not master_key:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Session abgelaufen - bitte erneut anmelden",
                    }
                ),
                401,
            )

        try:
            imap_server = encryption.CredentialManager.decrypt_server(
                account.encrypted_imap_server, master_key
            )
            imap_username = encryption.CredentialManager.decrypt_email_address(
                account.encrypted_imap_username, master_key
            )
            imap_password = encryption.CredentialManager.decrypt_imap_password(
                account.encrypted_imap_password, master_key
            )
        except Exception as e:
            logger.error(f"Fehler beim Entschlüsseln der Credentials: {e}")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Fehler beim Entschlüsseln der Credentials",
                    }
                ),
                500,
            )

        # Run Diagnostics
        try:
            # Check for subscribed_only parameter in query string or request body
            subscribed_only = False
            try:
                if request.args.get("subscribed_only"):
                    subscribed_only = request.args.get("subscribed_only").lower() in (
                        "true",
                        "1",
                        "yes",
                    )
                elif request.is_json:
                    json_data = request.get_json(silent=True) or {}
                    subscribed_only = json_data.get("subscribed_only", False)
            except Exception as param_error:
                logger.debug(f"Parameter parsing error (using default): {param_error}")
                subscribed_only = False

            imap_diag_mod = importlib.import_module("src.imap_diagnostics")

            diagnostics = imap_diag_mod.IMAPDiagnostics(
                host=imap_server,
                port=account.imap_port or 993,
                username=imap_username,
                password=imap_password,
                timeout=120,
                ssl=(account.imap_encryption == "SSL"),
            )

            # Phase 15: Folder-Parameter für Test 12 aus Request-Body holen
            target_folder = None
            if request.is_json:
                json_data = request.get_json(silent=True) or {}
                target_folder = json_data.get("folder_name", None)
                logger.info(f"📁 Test 12 folder selection: {target_folder or 'ALL folders'}")
            
            result = diagnostics.run_diagnostics(
                subscribed_only=subscribed_only,
                account_id=account_id,
                session=db,
                folder_name=target_folder
            )

            return jsonify({"success": True, "diagnostics": result}), 200

        except TimeoutError as e:
            logger.error(f"IMAP Diagnostics Timeout: {e}")
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Verbindungs-Timeout: Server antwortet zu langsam. Überprüfen Sie die Netzwerkverbindung oder versuchen Sie es später erneut.",
                    }
                ),
                504,
            )
        except Exception as e:
            logger.error(f"IMAP Diagnostics Fehler: {e}")
            return (
                jsonify(
                    {"success": False, "error": f"Diagnostics fehlgeschlagen: {str(e)}"}
                ),
                500,
            )

    finally:
        db.close()


@app.route("/mail-account/<int:account_id>/fetch", methods=["POST"])
@login_required
def fetch_mails(account_id):
    """Holt Mails für einen Account ab (On-Demand) - IMAP oder OAuth"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )

        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404

        master_key = session.get("master_key")
        if not master_key:
            return jsonify({
                "error": "Session abgelaufen - bitte neu einloggen",
                "code": "SESSION_EXPIRED"
            }), 401

        is_initial = not account.initial_sync_done
        fetch_limit = 500 if is_initial else 50

        provider = (user.preferred_ai_provider or "ollama").lower()
        resolved_model = ai_client.resolve_model(provider, user.preferred_ai_model)
        use_cloud = ai_client.provider_requires_cloud(provider)
        sanitize_level = sanitizer.get_sanitization_level(use_cloud)

        try:
            job_id = job_queue.enqueue_fetch_job(
                user_id=user.id,
                account_id=account.id,
                master_key=master_key,
                provider=provider,
                model=resolved_model,
                max_mails=fetch_limit,
                sanitize_level=sanitize_level,
                meta={"trigger": "settings", "is_initial": is_initial},
            )
        except ValueError as exc:
            logger.error(f"Job-Fehler: {exc}")
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.error(f"Konnte Hintergrundjob nicht anlegen: {type(exc).__name__}")
            return jsonify({"error": "Hintergrundjob fehlgeschlagen"}), 500

        return jsonify(
            {
                "status": "queued",
                "job_id": job_id,
                "provider": provider,
                "model": resolved_model,
                "is_initial": is_initial,
                "max_mails": fetch_limit,
            }
        )

    except Exception as e:
        logger.error(f"Fehler beim Mail-Abruf: {type(e).__name__}")
        return jsonify({"error": "Mail-Abruf fehlgeschlagen"}), 500

    finally:
        db.close()


@app.route("/mail-account/<int:account_id>/purge", methods=["POST"])
@login_required
def purge_mail_account(account_id):
    """Löscht alle lokal gespeicherten Mails (Raw + Processed) für einen Account."""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        account = (
            db.query(models.MailAccount)
            .filter_by(id=account_id, user_id=user.id)
            .first()
        )

        if not account:
            return jsonify({"error": "Account nicht gefunden"}), 404

        raw_ids = [
            raw_id
            for (raw_id,) in db.query(models.RawEmail.id)
            .filter_by(user_id=user.id, mail_account_id=account.id)
            .all()
        ]

        processed_deleted = 0
        raw_deleted = 0

        if raw_ids:
            processed_deleted = (
                db.query(models.ProcessedEmail)
                .filter(models.ProcessedEmail.raw_email_id.in_(raw_ids))
                .delete(synchronize_session=False)
            )

            raw_deleted = (
                db.query(models.RawEmail)
                .filter(models.RawEmail.id.in_(raw_ids))
                .delete(synchronize_session=False)
            )

        db.commit()

        logger.info(
            "🧹 Account %s: %d Raw / %d Processed gelöscht",
            account.name,
            raw_deleted,
            processed_deleted,
        )

        return jsonify(
            {
                "status": "ok",
                "raw_deleted": raw_deleted,
                "processed_deleted": processed_deleted,
            }
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Fehler beim Purge: {type(e).__name__}")
        return jsonify({"error": "Purge fehlgeschlagen"}), 500

    finally:
        db.close()


@app.route("/jobs/<string:job_id>", methods=["GET"])
@login_required
@limiter.limit("1200 per hour")  # Erhöht für lange Background-Jobs (Embedding-Generation)
def job_status(job_id: str):
    """Liefert Status-Infos zu einem Hintergrundjob."""
    status = job_queue.get_status(job_id, current_user.id)
    if not status:
        return jsonify({"error": "Job nicht gefunden"}), 404
    return jsonify(status)


@app.route("/email/<int:raw_email_id>/delete", methods=["POST"])
@login_required
def delete_email(raw_email_id):
    """Löscht eine Email auf dem Server"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        raw_email = email.raw_email
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401

        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == raw_email.mail_account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )

        if not account or account.auth_type != "imap":
            return jsonify({"error": "IMAP-Account erforderlich"}), 400

        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password, master_key
        )

        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port,
        )
        fetcher.connect()

        try:
            if not fetcher.connection:
                logger.error(
                    f"IMAP-Verbindung nicht initialisiert für Email {email_id}"
                )
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500

            synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)
            uid_to_use = raw_email.imap_uid  # Phase 14f: uid Feld entfernt
            folder_to_use = raw_email.imap_folder or "INBOX"
            success, message = synchronizer.delete_email(uid_to_use, folder_to_use)

            if success:
                email.deleted_at = datetime.now(UTC)
                db.commit()
                logger.info(f"✓ Email {email_id} auf Server gelöscht")
                return jsonify({"success": True, "message": message})
            else:
                return jsonify({"error": message}), 500

        finally:
            fetcher.disconnect()

    except Exception as e:
        logger.error(
            f"Fehler beim Löschen von Email {email_id}: {type(e).__name__}: {e}"
        )
        return jsonify({"error": "Fehler beim Löschen"}), 500

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/move-trash", methods=["POST"])
@login_required
def move_email_to_trash(raw_email_id):
    """Verschiebt eine Email in den Papierkorb auf dem Server"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        raw_email = email.raw_email
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401

        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == raw_email.mail_account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )

        if not account or account.auth_type != "imap":
            return jsonify({"error": "IMAP-Account erforderlich"}), 400

        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password, master_key
        )

        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port,
        )
        fetcher.connect()

        try:
            if not fetcher.connection:
                logger.error(
                    f"IMAP-Verbindung nicht initialisiert für Email {email_id}"
                )
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500

            synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)
            uid_to_use = raw_email.imap_uid  # Phase 14f: uid Feld entfernt
            folder_to_use = raw_email.imap_folder or "INBOX"

            # Phase 15: move_to_trash gibt MoveResult zurück (mit UIDPLUS COPYUID)
            result = synchronizer.move_to_trash(uid_to_use, folder_to_use)

            if result.success:
                # Phase 15: DB DIREKT UPDATEN mit neuer UID vom Server (analog zu move_to_folder)
                try:
                    logger.info(
                        f"📝 Starte DB-Update für Email {email_id} (raw_email.id={raw_email.id}): "
                        f"UID {uid_to_use} → {result.target_uid}, "
                        f"Folder {folder_to_use} → {result.target_folder}, "
                        f"UIDVAL {raw_email.imap_uidvalidity} → {result.target_uidvalidity}"
                    )
                    
                    raw_email.imap_folder = result.target_folder
                    
                    # Wenn COPYUID verfügbar: neue UID + UIDVALIDITY speichern
                    if result.target_uid is not None:
                        raw_email.imap_uid = result.target_uid
                        logger.info(
                            f"✅ Email {email_id}: UID {uid_to_use} → {result.target_uid} "
                            f"({folder_to_use} → {result.target_folder})"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Email {email_id}: COPYUID nicht verfügbar (target_uid=None)"
                        )
                    
                    if result.target_uidvalidity is not None:
                        raw_email.imap_uidvalidity = result.target_uidvalidity
                        logger.info(f"✅ Email {email_id}: UIDVALIDITY → {result.target_uidvalidity}")
                    
                    # Soft-delete Marker setzen
                    email.deleted_at = datetime.now(UTC)
                    db.commit()
                    
                    logger.info(f"✅ Email {email_id} erfolgreich in Papierkorb verschoben und DB aktualisiert")
                    
                    return jsonify({
                        "success": True,
                        "message": result.message,
                        "target_folder": result.target_folder,
                        "target_uid": result.target_uid,
                        "target_uidvalidity": result.target_uidvalidity
                    })
                    
                except Exception as db_error:
                    logger.error(f"DB-Update fehlgeschlagen für Email {email_id}: {db_error}")
                    db.rollback()
                    return jsonify({"error": f"IMAP erfolgreich, DB-Update fehlgeschlagen: {str(db_error)}"}), 500
            else:
                return jsonify({"error": result.message}), 500

        finally:
            fetcher.disconnect()

    except Exception as e:
        logger.error(
            f"Fehler beim Verschieben von Email {email_id} in Papierkorb: {type(e).__name__}: {e}"
        )
        return jsonify({"error": "Fehler beim Verschieben in Papierkorb"}), 500

    finally:
        db.close()


# 🚀 PERFORMANCE: Cache für mail-count (verhindert wiederholte IMAP-Queries)
# Cache-Format: {account_id: {'timestamp': float, 'data': dict}}
mail_count_cache = {}
MAIL_COUNT_CACHE_TTL = 30  # Sekunden

@app.route("/account/<int:account_id>/mail-count", methods=["GET"])
@login_required
def get_account_mail_count(account_id):
    """Zählt schnell wie viele Mails auf dem Server sind (ohne sie zu fetchen)
    
    Phase 13C Part 4: Quick Count für intelligentes Fetching
    - Zeigt User wie viele Mails remote vorhanden sind
    - User kann dann entscheiden: Alle holen oder in Portionen?
    Phase 13C Part 6+: Auch SINCE-Date Count für exakte Schätzung
    
    Performance: Mit 30s Cache um doppelte Requests zu vermeiden
    """
    import time
    
    # 🚀 Cache-Check: Verwende gecachte Daten wenn < 30s alt
    cache_key = account_id
    current_time = time.time()
    
    if cache_key in mail_count_cache:
        cache_entry = mail_count_cache[cache_key]
        cache_age = current_time - cache_entry['timestamp']
        if cache_age < MAIL_COUNT_CACHE_TTL:
            logger.info(f"⚡ Cache-Hit für Account {account_id} (Alter: {cache_age:.1f}s)")
            return jsonify(cache_entry['data'])
        else:
            logger.debug(f"🗑️ Cache abgelaufen für Account {account_id} ({cache_age:.1f}s)")
    
    db = get_db_session()
    
    # Optional: since_date für SINCE count (Format: YYYY-MM-DD)
    since_date_str = request.args.get('since_date')
    since_date = None
    if since_date_str:
        try:
            from datetime import datetime
            since_date = datetime.strptime(since_date_str, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"Ungültiges since_date Format: {since_date_str}")
            since_date = None
    
    # Optional: unseen_only für kombinierte Filter
    unseen_only = request.args.get('unseen_only', '').lower() == 'true'
    
    # 🎯 NEU: include_folders als JSON-Array (nur für diese Ordner SINCE-Search durchführen!)
    include_folders_param = request.args.get('include_folders')
    include_folders_set = None
    if include_folders_param:
        try:
            import json
            include_folders_list = json.loads(include_folders_param)
            include_folders_set = set(include_folders_list) if include_folders_list else None
            logger.info(f"🎯 SINCE-Search nur für {len(include_folders_set)} Include-Ordner")
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Ungültiges include_folders Format: {e}")
            include_folders_set = None

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )

        if not account or account.auth_type != "imap":
            return jsonify({"error": "IMAP-Account erforderlich"}), 400

        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401

        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password, master_key
        )

        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port,
        )
        fetcher.connect()

        try:
            # IMAPClient.list_folders() gibt schon Tupel zurück
            folders = fetcher.connection.list_folders()
            
            folder_counts = {}
            total_remote = 0
            total_unseen = 0
            
            for flags, delimiter, folder_name in folders:
                # folder_name ist bytes, decode UTF-7
                folder_display = mail_fetcher_mod.decode_imap_folder_name(folder_name)
                
                # Prüfe ob Folder selectable ist
                if b'\\Noselect' in flags or '\\Noselect' in [f.decode() if isinstance(f, bytes) else f for f in flags]:
                    continue
                
                try:
                    # Status gibt direkt Dict zurück!
                    status_dict = fetcher.connection.folder_status(folder_name, ['MESSAGES', 'UNSEEN'])
                    
                    messages_count = status_dict.get(b'MESSAGES', 0)
                    unseen_count = status_dict.get(b'UNSEEN', 0)
                    
                    # 🎯 PERFORMANCE FIX: SINCE-Search nur für include_folders
                    # - Alle 132 Ordner: STATUS (schnell, ~5s)
                    # - Nur ausgewählte Ordner (z.B. 10): SELECT+SEARCH (~2-3s)
                    # - Total: ~7-8s statt 120s!
                    since_count = None
                    if since_date and include_folders_set is not None:
                        # Nur wenn dieser Ordner in include_folders ist
                        if folder_display in include_folders_set:
                            try:
                                # SELECT folder für SEARCH (readonly)
                                fetcher.connection.select_folder(folder_name, readonly=True)
                                # IMAP SEARCH SINCE format: DD-Mon-YYYY
                                date_str = since_date.strftime("%d-%b-%Y")
                                
                                # Build search criteria: SINCE [+ UNSEEN]
                                search_criteria = ['SINCE', date_str]
                                if unseen_only:
                                    search_criteria.append('UNSEEN')
                                
                                since_messages = fetcher.connection.search(search_criteria)
                                since_count = len(since_messages) if since_messages else 0
                                logger.debug(f"✅ SINCE-Search für {folder_display}: {since_count} Mails")
                            except Exception as search_err:
                                logger.debug(f"SINCE search failed für {folder_display}: {search_err}")
                                since_count = None
                    
                    folder_counts[folder_display] = {
                        "total": messages_count,
                        "unseen": unseen_count,
                        "since": since_count
                    }
                    total_remote += messages_count
                    total_unseen += unseen_count
                except Exception as e:
                    logger.warning(f"Status fehlgeschlagen für {folder_display}: {e}")
                    continue

            # Zähle lokale Mails in DB
            total_local = db.query(models.RawEmail).filter(
                models.RawEmail.mail_account_id == account_id,
                models.RawEmail.deleted_at.is_(None)
            ).count()

            result_data = {
                "account_id": account_id,
                "folders": folder_counts,
                "summary": {
                    "total_remote": total_remote,
                    "total_unseen": total_unseen,
                    "total_local": total_local,
                    "delta": total_remote - total_local
                }
            }
            
            # 💾 Cache für 30s speichern
            mail_count_cache[cache_key] = {
                'timestamp': current_time,
                'data': result_data
            }
            logger.info(f"💾 Cache gespeichert für Account {account_id} (132 Ordner)")
            
            return jsonify(result_data)

        finally:
            fetcher.disconnect()

    except Exception as e:
        logger.error(f"Fehler beim Mail-Count für Account {account_id}: {type(e).__name__}")
        return jsonify({"error": f"Fehler beim Zählen: {str(e)}"}), 500

    finally:
        db.close()


@app.route("/account/<int:account_id>/folders", methods=["GET"])
@login_required
def get_account_folders(account_id):
    """Listet verfügbare Ordner für einen IMAP-Account auf"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )

        if not account or account.auth_type != "imap":
            return jsonify({"error": "IMAP-Account erforderlich"}), 400

        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401

        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password, master_key
        )

        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port,
        )
        fetcher.connect()

        try:
            if not fetcher.connection:
                logger.error(f"IMAP-Verbindung nicht initialisiert für Account {account_id}")
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500

            # IMAPClient.list_folders() returns (flags, delimiter, folder_name) tuples
            mailboxes = fetcher.connection.list_folders()

            folders = []
            for flags, delimiter, folder_name in mailboxes:
                # Skip \Noselect folders
                if b'\\Noselect' in flags or '\\Noselect' in [f.decode() if isinstance(f, bytes) else f for f in flags]:
                    continue
                # folder_name is bytes, decode UTF-7 via mail_fetcher_mod
                folder_display = mail_fetcher_mod.decode_imap_folder_name(folder_name)
                folders.append({"name": folder_display})

            folders.sort(key=lambda x: x['name'])
            return jsonify({"success": True, "folders": folders})

        finally:
            fetcher.disconnect()

    except Exception as e:
        logger.error(f"Fehler beim Abrufen von Folders für Account {account_id}: {type(e).__name__}")
        return jsonify({"error": "Fehler beim Abrufen von Ordnern"}), 500

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/move-to-folder", methods=["POST"])
@login_required
def move_email_to_folder(raw_email_id):
    """Verschiebt eine Email in einen bestimmten Ordner"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        raw_email = email.raw_email
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401

        data = request.get_json() or {}
        target_folder = data.get("target_folder")
        if not target_folder:
            return jsonify({"error": "Ziel-Ordner erforderlich"}), 400

        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == raw_email.mail_account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )

        if not account or account.auth_type != "imap":
            return jsonify({"error": "IMAP-Account erforderlich"}), 400

        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password, master_key
        )

        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port,
        )
        fetcher.connect()

        try:
            if not fetcher.connection:
                logger.error(f"IMAP-Verbindung nicht initialisiert für Email {email_id}")
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500

            synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)
            uid_to_use = raw_email.imap_uid  # Phase 14f: uid Feld entfernt
            folder_to_use = raw_email.imap_folder or "INBOX"

            # Phase 14c: move_to_folder gibt MoveResult zurück
            result = synchronizer.move_to_folder(
                uid_to_use, target_folder, folder_to_use
            )

            if result.success:
                # Phase 14d: DB DIREKT UPDATEN mit neuer UID vom Server!
                # RFC 4315 UIDPLUS: Server gibt neue UID zurück (COPYUID)
                try:
                    logger.info(
                        f"📝 Starte DB-Update für Email {email_id} (raw_email.id={raw_email.id}): "
                        f"UID {uid_to_use} → {result.target_uid}, "
                        f"UIDVAL {raw_email.imap_uidvalidity} → {result.target_uidvalidity}"
                    )
                    
                    raw_email.imap_folder = result.target_folder
                    
                    # Wenn COPYUID verfügbar: neue UID + UIDVALIDITY speichern
                    if result.target_uid is not None:
                        raw_email.imap_uid = result.target_uid
                        logger.info(
                            f"✅ Email {email_id}: UID {uid_to_use} → {result.target_uid} "
                            f"({folder_to_use} → {result.target_folder})"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Email {email_id}: COPYUID nicht verfügbar (target_uid=None)"
                        )
                    
                    if result.target_uidvalidity is not None:
                        raw_email.imap_uidvalidity = result.target_uidvalidity
                        logger.info(
                            f"✅ Email {email_id}: UIDVALIDITY = {result.target_uidvalidity}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Email {email_id}: UIDVALIDITY nicht verfügbar (target_uidvalidity=None)"
                        )
                    
                    raw_email.imap_last_seen_at = datetime.now(UTC)
                    
                    logger.info(f"💾 Führe db.commit() aus für Email {email_id}...")
                    db.commit()
                    
                    logger.info(
                        f"✅ Email {email_id} zu {result.target_folder} verschoben "
                        f"(DB direkt aktualisiert: UID={raw_email.imap_uid}, UIDVAL={raw_email.imap_uidvalidity})"
                    )
                    return jsonify({"success": True, "message": result.message})
                    
                except Exception as commit_error:
                    logger.error(
                        f"❌ FEHLER beim DB-Commit für Email {email_id}: "
                        f"{type(commit_error).__name__}: {commit_error}"
                    )
                    db.rollback()
                    return jsonify({
                        "error": f"IMAP-Verschiebung erfolgreich, aber DB-Update fehlgeschlagen: {commit_error}"
                    }), 500
            else:
                return jsonify({"error": result.message}), 500

        finally:
            fetcher.disconnect()

    except Exception as e:
        logger.error(
            f"Fehler beim Verschieben von Email {email_id}: {type(e).__name__}: {e}"
        )
        return jsonify({"error": "Fehler beim Verschieben"}), 500

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/mark-read", methods=["POST"])
@login_required
def mark_email_read(raw_email_id):
    """Markiert eine Email als gelesen auf dem Server"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        raw_email = email.raw_email
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401

        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == raw_email.mail_account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )

        if not account or account.auth_type != "imap":
            return jsonify({"error": "IMAP-Account erforderlich"}), 400

        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password, master_key
        )

        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port,
        )
        fetcher.connect()

        try:
            if not fetcher.connection:
                logger.error(
                    f"IMAP-Verbindung nicht initialisiert für Email {email_id}"
                )
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500

            synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)
            uid_to_use = raw_email.imap_uid  # Phase 14f: uid Feld entfernt
            folder_to_use = raw_email.imap_folder or "INBOX"
            success, message = synchronizer.mark_as_read(uid_to_use, folder_to_use)

            if success:
                raw_email.imap_is_seen = True
                db.commit()
                return jsonify({"success": True, "message": message})
            else:
                return jsonify({"error": message}), 500

        finally:
            fetcher.disconnect()

    except Exception as e:
        logger.error(
            f"Fehler beim Mark-as-Read für Email {email_id}: {type(e).__name__}"
        )
        return jsonify({"error": "Fehler beim Markieren"}), 500

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/toggle-read", methods=["POST"])
@login_required
def toggle_email_read(raw_email_id):
    """Togglet Gelesen/Ungelesen Status einer Email auf dem Server"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        raw_email = email.raw_email
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401

        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == raw_email.mail_account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )

        if not account or account.auth_type != "imap":
            return jsonify({"error": "IMAP-Account erforderlich"}), 400

        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password, master_key
        )

        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port,
        )
        fetcher.connect()

        try:
            if not fetcher.connection:
                logger.error(
                    f"IMAP-Verbindung nicht initialisiert für Email {email_id}"
                )
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500

            synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)
            uid_to_use = raw_email.imap_uid  # Phase 14f: uid Feld entfernt
            folder_to_use = raw_email.imap_folder or "INBOX"

            logger.debug(
                f"Toggle-Read: uid={uid_to_use}, folder={folder_to_use}, is_seen={raw_email.imap_is_seen}"
            )

            if raw_email.imap_is_seen:
                success, message = synchronizer.mark_as_unread(
                    uid_to_use, folder_to_use
                )
                is_now_seen = False
            else:
                success, message = synchronizer.mark_as_read(uid_to_use, folder_to_use)
                is_now_seen = True

            if success:
                raw_email.imap_is_seen = is_now_seen
                db.commit()
                return jsonify(
                    {"success": True, "message": message, "is_seen": is_now_seen}
                )
            else:
                return jsonify({"error": message}), 500

        finally:
            fetcher.disconnect()

    except Exception as e:
        logger.error(
            f"Fehler beim Toggle-Read für Email {email_id}: {type(e).__name__}"
        )
        return jsonify({"error": "Fehler beim Umschalten des Lesestatus"}), 500

    finally:
        db.close()


@app.route("/email/<int:raw_email_id>/mark-flag", methods=["POST"])
@login_required
def toggle_email_flag(raw_email_id):
    """Togglet Wichtig-Flag einer Email auf dem Server"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Nicht authentifiziert"}), 401

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        raw_email = email.raw_email
        master_key = session.get("master_key")
        if not master_key:
            return jsonify({"error": "Master-Key erforderlich"}), 401

        account = (
            db.query(models.MailAccount)
            .filter(
                models.MailAccount.id == raw_email.mail_account_id,
                models.MailAccount.user_id == user.id,
            )
            .first()
        )

        if not account or account.auth_type != "imap":
            return jsonify({"error": "IMAP-Account erforderlich"}), 400

        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password, master_key
        )

        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port,
        )
        fetcher.connect()

        try:
            if not fetcher.connection:
                logger.error(
                    f"IMAP-Verbindung nicht initialisiert für Email {email_id}"
                )
                return jsonify({"error": "IMAP-Verbindung fehlgeschlagen"}), 500

            synchronizer = mail_sync.MailSynchronizer(fetcher.connection, logger)

            # Use imap_uid (Phase 12 attribute) instead of uid (legacy)
            uid_to_use = raw_email.imap_uid  # Phase 14f: uid Feld entfernt
            folder_to_use = raw_email.imap_folder or "INBOX"

            logger.debug(
                f"Flag-Toggle: uid={uid_to_use}, folder={folder_to_use}, flagged={raw_email.imap_is_flagged}"
            )

            if raw_email.imap_is_flagged:
                success, message = synchronizer.unset_flag(uid_to_use, folder_to_use)
                flag_state = False
            else:
                success, message = synchronizer.set_flag(uid_to_use, folder_to_use)
                flag_state = True

            if success:
                raw_email.imap_is_flagged = flag_state
                db.commit()
                return jsonify(
                    {"success": True, "message": message, "flagged": flag_state}
                )
            else:
                return jsonify({"error": message}), 500

        finally:
            fetcher.disconnect()

    except Exception as e:
        import traceback

        logger.error(
            f"Fehler beim Flag-Toggle für Email {email_id}: {type(e).__name__}"
        )
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": "Fehler beim Flag-Toggle"}), 500

    finally:
        db.close()


@app.errorhandler(404)
def not_found(e):
    """404-Handler"""
    return redirect(url_for("index"))


@app.errorhandler(500)
def server_error(e):
    """500-Handler"""
    logger.error(f"Server-Fehler: {type(e).__name__}")
    return "500 - Server-Fehler", 500


# ============================================================================
# Phase X: Trusted Senders + UrgencyBooster API Endpoints
# ============================================================================

@app.route("/api/trusted-senders", methods=["GET"])
@login_required
def api_list_trusted_senders():
    """List trusted senders for current user, optionally filtered by account_id"""
    db = get_db_session()
    try:
        models_mod = importlib.import_module(".02_models", "src")
        
        # Get optional account_id parameter
        account_id = request.args.get('account_id', type=int)
        
        # Build query
        query = db.query(models_mod.TrustedSender).filter_by(user_id=current_user.id)
        
        if account_id:
            # For specific account: include account-specific AND global (account_id=NULL)
            query = query.filter(
                (models_mod.TrustedSender.account_id == account_id) |
                (models_mod.TrustedSender.account_id.is_(None))
            )
        # else: No filter - show ALL trusted senders (global + account-specific)
        
        trusted_senders = query.all()
        
        senders = []
        for ts in trusted_senders:
            senders.append({
                "id": ts.id,
                "sender_pattern": ts.sender_pattern,
                "pattern_type": ts.pattern_type,
                "label": ts.label or "",
                "use_urgency_booster": ts.use_urgency_booster,
                "added_at": ts.added_at.isoformat() if ts.added_at else None,
                "last_seen_at": ts.last_seen_at.isoformat() if ts.last_seen_at else None,
                "email_count": ts.email_count or 0,
                "account_id": ts.account_id
            })
        
        return {"success": True, "senders": senders}, 200
    except Exception as e:
        logger.error(f"Error listing trusted senders: {e}")
        return {"success": False, "error": str(e)}, 500
    finally:
        db.close()


@app.route("/api/trusted-senders", methods=["POST"])
@login_required
def api_add_trusted_sender():
    """Add a new trusted sender"""
    db = get_db_session()
    try:
        data = request.get_json()
        if not data:
            return {"success": False, "error": "No JSON data"}, 400
        
        sender_pattern = (data.get("sender_pattern") or "").strip()
        pattern_type = (data.get("pattern_type") or "exact").strip()
        label = (data.get("label") or "").strip() or None
        use_urgency_booster = data.get("use_urgency_booster", True)
        account_id = data.get("account_id")
        
        if not sender_pattern:
            return {"success": False, "error": "sender_pattern erforderlich"}, 400
        
        # Normalisiere pattern_type
        if not pattern_type or pattern_type not in ["exact", "email_domain", "domain"]:
            pattern_type = "exact"
        
        # Use TrustedSenderManager to add with validation
        trusted_senders_mod = importlib.import_module(".services.trusted_senders", "src")
        try:
            ts = trusted_senders_mod.TrustedSenderManager.add_trusted_sender(
                db=db,
                user_id=current_user.id,
                sender_pattern=sender_pattern,
                account_id=account_id,
                pattern_type=pattern_type,
                label=label
            )
            if ts and ts.get('success'):
                response = {
                    "success": True,
                    "sender": {
                        "id": ts['id'],
                        "sender_pattern": ts['sender_pattern'],
                        "pattern_type": ts['pattern_type'],
                        "label": ts['label']
                    }
                }
                # Pass through already_exists flag if present
                if ts.get('already_exists'):
                    response['already_exists'] = True
                    response['message'] = ts.get('message', 'Sender bereits in Liste')
                return response, 201
            elif ts and not ts.get('success'):
                return {"success": False, "error": ts.get('error', 'Unknown error')}, 400
            else:
                return {"success": False, "error": "Failed to add trusted sender"}, 400
        except ValueError as e:
            return {"success": False, "error": str(e)}, 400
        except Exception as e:
            logger.error(f"Error adding trusted sender: {e}")
            return {"success": False, "error": str(e)}, 500
    except Exception as e:
        logger.error(f"Error in add trusted sender: {e}")
        return {"success": False, "error": str(e)}, 500
    finally:
        db.close()


@app.route("/api/trusted-senders/<int:sender_id>", methods=["PATCH"])
@login_required
def api_update_trusted_sender(sender_id):
    """Update a trusted sender (toggle use_urgency_booster flag)"""
    db = get_db_session()
    try:
        models_mod = importlib.import_module(".02_models", "src")
        account_id = request.args.get('account_id', type=int)
        
        # Query with account filter if provided
        query = db.query(models_mod.TrustedSender).filter_by(
            id=sender_id,
            user_id=current_user.id
        )
        
        if account_id:
            # Verify sender belongs to this account or is global
            query = query.filter(
                (models_mod.TrustedSender.account_id == account_id) |
                (models_mod.TrustedSender.account_id.is_(None))
            )
        else:
            # No account filter - allow access to all trusted senders for this user
            pass
        
        ts = query.first()
        
        if not ts:
            return {"success": False, "error": "Trusted sender not found"}, 404
        
        data = request.get_json()
        if not data:
            return {"success": False, "error": "No JSON data"}, 400
        
        # Update use_urgency_booster flag
        if "use_urgency_booster" in data:
            ts.use_urgency_booster = bool(data["use_urgency_booster"])
        
        if "label" in data:
            label = data.get("label")
            ts.label = label.strip() if label else None
        
        if "pattern_type" in data:
            valid_types = ["exact", "email_domain", "domain"]
            new_type = data.get("pattern_type", "").strip().lower()
            if new_type in valid_types:
                ts.pattern_type = new_type
            else:
                return {"success": False, "error": f"Invalid pattern_type: {new_type}"}, 400
        
        db.commit()
        return {
            "success": True,
            "sender": {
                "id": ts.id,
                "sender_pattern": ts.sender_pattern,
                "pattern_type": ts.pattern_type,
                "label": ts.label,
                "use_urgency_booster": ts.use_urgency_booster,
                "account_id": ts.account_id
            }
        }, 200
    except Exception as e:
        logger.error(f"Error updating trusted sender: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}, 500
    finally:
        db.close()


@app.route("/api/trusted-senders/<int:sender_id>", methods=["DELETE"])
@login_required
def api_delete_trusted_sender(sender_id):
    """Delete a trusted sender"""
    db = get_db_session()
    try:
        models_mod = importlib.import_module(".02_models", "src")
        account_id = request.args.get('account_id', type=int)
        
        # Query with account filter if provided
        query = db.query(models_mod.TrustedSender).filter_by(
            id=sender_id,
            user_id=current_user.id
        )
        
        if account_id:
            # Verify sender belongs to this account or is global
            query = query.filter(
                (models_mod.TrustedSender.account_id == account_id) |
                (models_mod.TrustedSender.account_id.is_(None))
            )
        else:
            # No account filter - allow access to all trusted senders for this user
            pass
        
        ts = query.first()
        
        if not ts:
            return {"success": False, "error": "Trusted sender not found"}, 404
        
        db.delete(ts)
        db.commit()
        return {"success": True}, 200
    except Exception as e:
        logger.error(f"Error deleting trusted sender: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}, 500
    finally:
        db.close()


@app.route("/api/settings/urgency-booster", methods=["GET"])
@login_required
def api_get_urgency_booster():
    """Get current urgency booster setting"""
    db = get_db_session()
    try:
        models_mod = importlib.import_module(".02_models", "src")
        user = db.query(models_mod.User).filter_by(id=current_user.id).first()
        if not user:
            return {"success": False, "error": "User not found"}, 404
        
        return {
            "success": True,
            "urgency_booster_enabled": user.urgency_booster_enabled
        }, 200
    except Exception as e:
        logger.error(f"Error getting urgency booster setting: {e}")
        return {"success": False, "error": str(e)}, 500
    finally:
        db.close()


@app.route("/api/settings/urgency-booster", methods=["POST"])
@login_required
def api_set_urgency_booster():
    """Toggle urgency booster setting"""
    db = get_db_session()
    try:
        data = request.get_json()
        if not data:
            return {"success": False, "error": "No JSON data"}, 400
        
        enabled = data.get("enabled", True)
        
        models_mod = importlib.import_module(".02_models", "src")
        user = db.query(models_mod.User).filter_by(id=current_user.id).first()
        if not user:
            return {"success": False, "error": "User not found"}, 404
        
        user.urgency_booster_enabled = bool(enabled)
        db.commit()
        
        logger.info(f"UrgencyBooster for user {current_user.id}: {enabled}")
        return {
            "success": True,
            "urgency_booster_enabled": user.urgency_booster_enabled
        }, 200
    except Exception as e:
        logger.error(f"Error setting urgency booster: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}, 500
    finally:
        db.close()


@app.route("/api/accounts/urgency-booster-settings", methods=["GET"])
@login_required
def api_get_accounts_urgency_booster_settings():
    """Get UrgencyBooster settings for all user accounts"""
    db = get_db_session()
    try:
        models_mod = importlib.import_module(".02_models", "src")
        
        accounts = db.query(models_mod.MailAccount).filter_by(user_id=current_user.id).order_by(models_mod.MailAccount.name).all()
        
        # Get master key for decryption
        master_key = session.get("master_key")
        
        accounts_data = []
        for account in accounts:
            # Decrypt IMAP username for display
            decrypted_email = None
            if master_key and account.encrypted_imap_username:
                try:
                    decrypted_email = encryption.EmailDataManager.decrypt_email_sender(
                        account.encrypted_imap_username, master_key
                    )
                except Exception as e:
                    logger.warning(f"Could not decrypt email for account {account.id}: {e}")
            
            accounts_data.append({
                'id': account.id,
                'name': account.name,
                'decrypted_imap_username': decrypted_email,
                'urgency_booster_enabled': getattr(account, 'urgency_booster_enabled', True),
                'enable_ai_analysis_on_fetch': getattr(account, 'enable_ai_analysis_on_fetch', True),
                # Phase Y2: Neue Felder
                'anonymize_with_spacy': getattr(account, 'anonymize_with_spacy', False),
                'ai_analysis_anon_enabled': getattr(account, 'ai_analysis_anon_enabled', False),
                'ai_analysis_original_enabled': getattr(account, 'ai_analysis_original_enabled', False),
                'effective_ai_mode': account.effective_ai_mode if hasattr(account, 'effective_ai_mode') else 'llm_original'
            })
        
        return {
            "success": True,
            "accounts": accounts_data
        }, 200
    except Exception as e:
        logger.error(f"Error getting accounts urgency booster settings: {e}")
        return {"success": False, "error": str(e)}, 500
    finally:
        db.close()


@app.route("/api/accounts/<int:account_id>/urgency-booster", methods=["POST"])
@login_required
def api_set_account_urgency_booster(account_id):
    """Set UrgencyBooster and Analysis Modes for a specific account (Phase Y2)"""
    db = get_db_session()
    try:
        data = request.get_json()
        if not data:
            return {"success": False, "error": "No JSON data"}, 400
        
        models_mod = importlib.import_module(".02_models", "src")
        account = db.query(models_mod.MailAccount).filter_by(
            id=account_id,
            user_id=current_user.id
        ).first()
        
        if not account:
            return {"success": False, "error": "Account nicht gefunden"}, 404
        
        # ===== PHASE Y2: ANALYSIS MODES =====
        # Legacy-Support (alte Toggles)
        if "urgency_booster_enabled" in data:
            account.urgency_booster_enabled = bool(data["urgency_booster_enabled"])
        if "enable_ai_analysis_on_fetch" in data:
            account.enable_ai_analysis_on_fetch = bool(data["enable_ai_analysis_on_fetch"])
        
        # Phase Y2: Neue Toggle-Struktur
        if "anonymize_with_spacy" in data:
            account.anonymize_with_spacy = bool(data["anonymize_with_spacy"])
        
        if "analysis_mode" in data:
            # Radio-Button Modus: Setze alle Toggles zurück, aktiviere nur gewählten
            mode = data["analysis_mode"]
            
            account.urgency_booster_enabled = False
            account.ai_analysis_anon_enabled = False
            account.ai_analysis_original_enabled = False
            
            if mode == "spacy_booster":
                account.urgency_booster_enabled = True
            elif mode == "llm_anon":
                if not account.anonymize_with_spacy:
                    logger.warning("llm_anon gewählt aber anonymize_with_spacy=False, Fallback auf none")
                    # Lasse alle False
                else:
                    account.ai_analysis_anon_enabled = True
            elif mode == "llm_original":
                account.ai_analysis_original_enabled = True
            # else: "none" → alle bleiben False
            
            # Legacy-Support: Synchronisiere enable_ai_analysis_on_fetch
            account.enable_ai_analysis_on_fetch = (
                account.ai_analysis_original_enabled or account.ai_analysis_anon_enabled
            )
        
        db.commit()
        
        logger.info(f"Account {account_id} settings: effective_mode={account.effective_ai_mode}")
        return {
            "success": True,
            "effective_mode": account.effective_ai_mode,
            "urgency_booster_enabled": account.urgency_booster_enabled,
            "enable_ai_analysis_on_fetch": account.enable_ai_analysis_on_fetch,
            "anonymize_with_spacy": account.anonymize_with_spacy,
            "ai_analysis_anon_enabled": account.ai_analysis_anon_enabled,
            "ai_analysis_original_enabled": account.ai_analysis_original_enabled
        }, 200
    except Exception as e:
        logger.error(f"Error setting account settings: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}, 500
    finally:
        db.close()


@app.route("/api/trusted-senders/suggestions", methods=["GET"])
@login_required
def api_get_trusted_senders_suggestions():
    """Get suggestions for new trusted senders based on email history"""
    db = get_db_session()
    try:
        models_mod = importlib.import_module(".02_models", "src")
        encryption_mod = importlib.import_module(".08_encryption", "src")
        trusted_senders_mod = importlib.import_module(".services.trusted_senders", "src")
        
        # Get master key from Flask session
        master_key = session.get("master_key")
        if not master_key:
            return {"success": False, "error": "Master key not available"}, 400
        
        # Get optional account_id parameter
        account_id = request.args.get('account_id', type=int)
        
        # Get suggestions
        suggestions = trusted_senders_mod.TrustedSenderManager.get_suggestions_from_emails(
            db=db,
            user_id=current_user.id,
            master_key=master_key,
            limit=10,
            account_id=account_id  # Pass account context for filtering existing senders
        )
        
        return {
            "success": True,
            "suggestions": suggestions,
            "account_id": account_id
        }, 200
    except Exception as e:
        logger.error(f"Error getting trusted sender suggestions: {e}")
        return {"success": False, "error": str(e)}, 500


# ============================================================================
# IMAP Sender Scanner - Pre-Fetch Whitelist Setup (Phase X.3)
# ============================================================================

# Concurrent Scan Prevention (in-memory lock)
_active_scans = set()  # Set von account_ids die gerade scannen

# Rate-Limiting pro User (60s Cooldown zwischen Scans)
_last_scan_time = {}  # Dict: user_id -> timestamp
SCAN_COOLDOWN_SECONDS = 60  # Minimum Zeit zwischen Scans


def check_scan_rate_limit(user_id: int) -> tuple:
    """
    Prüft ob User sein Rate-Limit für IMAP-Scans überschritten hat.
    
    Returns:
        (allowed: bool, seconds_remaining: int)
    """
    import time
    current_time = time.time()
    last_scan = _last_scan_time.get(user_id)
    
    if last_scan is None:
        # Erster Scan
        _last_scan_time[user_id] = current_time
        return (True, 0)
    
    elapsed = current_time - last_scan
    
    if elapsed < SCAN_COOLDOWN_SECONDS:
        seconds_remaining = int(SCAN_COOLDOWN_SECONDS - elapsed)
        return (False, seconds_remaining)
    
    # Cooldown abgelaufen
    _last_scan_time[user_id] = current_time
    return (True, 0)


@app.route("/whitelist-imap-setup")
@login_required
def whitelist_imap_setup_page():
    """
    Separate Seite für IMAP-Setup (Pre-Fetch Absender-Scan).
    Ermöglicht Bulk-Whitelist ohne Mails zu importieren.
    """
    master_key = session.get('master_key')
    if not master_key:
        flash('Bitte erst einloggen', 'warning')
        return redirect(url_for('login'))
    
    db = get_db_session()
    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))
        
        # Alle Mail-Accounts des Users laden
        mail_accounts = db.query(models.MailAccount).filter_by(user_id=user.id).all()
        
        # Zero-Knowledge: Entschlüssele Credentials für Anzeige
        if master_key and mail_accounts:
            for account in mail_accounts:
                if account.auth_type == "imap":
                    try:
                        if account.encrypted_imap_server:
                            account.decrypted_imap_server = encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_server, master_key
                            )
                        if account.encrypted_imap_username:
                            account.decrypted_imap_username = encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_username, master_key
                            )
                    except Exception as e:
                        logger.warning(f"Fehler beim Entschlüsseln der Account-Daten: {e}")
                        account.decrypted_imap_server = None
                        account.decrypted_imap_username = None
        
        return render_template(
            'whitelist_imap_setup.html',
            user=user,
            mail_accounts=mail_accounts
        )
    finally:
        db.close()


@app.route('/api/scan-account-senders/<int:account_id>', methods=['POST'])
@login_required
def api_scan_account_senders(account_id):
    """
    Scannt Mail-Account nach Absendern (nur IMAP-Header, kein Full-Fetch).
    
    Security:
        - Account-Ownership validiert (CRITICAL)
        - Concurrent-Scan Prevention
        - Rate-Limiting (60s Cooldown)
        - CSRF-Token required
    
    POST Body:
    {
        "folder": "INBOX",  // default: INBOX
        "limit": 1000       // default: 1000 (Max für Timeout-Prevention)
    }
    
    Returns:
        {
            "success": true,
            "senders": [{"email": str, "name": str, "count": int, "suggested_type": str}, ...],
            "total_senders": int,
            "total_emails": int,
            "scanned_emails": int,
            "limited": bool
        }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            'success': False,
            'error': 'Nicht authentifiziert'
        }), 401
    
    # CRITICAL: Account-Ownership validieren
    db = get_db_session()
    try:
        account = db.query(models.MailAccount).filter_by(
            id=account_id,
            user_id=current_user.id  # ✅ User darf nur eigene Accounts scannen
        ).first()
        
        if not account:
            logger.warning(f"Unauthorized scan attempt: account_id={account_id}, user_id={current_user.id}")
            return jsonify({
                'success': False,
                'error': 'Account nicht gefunden oder keine Berechtigung'
            }), 404
        
        # Rate-Limiting prüfen
        allowed, seconds_remaining = check_scan_rate_limit(current_user.id)
        if not allowed:
            return jsonify({
                'success': False,
                'error': f'Rate-Limit erreicht. Bitte warte noch {seconds_remaining} Sekunden.',
                'seconds_remaining': seconds_remaining
            }), 429  # HTTP 429 Too Many Requests
        
        # Concurrent-Scan Prevention
        if account_id in _active_scans:
            return jsonify({
                'success': False,
                'error': 'Scan läuft bereits für diesen Account. Bitte warten.'
            }), 409  # HTTP 409 Conflict
        
        # Request-Body parsen
        data = request.get_json() or {}
        folder = data.get('folder', 'INBOX')
        limit = data.get('limit', 1000)
        
        # Limit validieren
        if not isinstance(limit, int) or limit < 1 or limit > 5000:
            return jsonify({
                'success': False,
                'error': 'Limit muss zwischen 1 und 5000 liegen'
            }), 400
        
        # Credentials entschlüsseln
        try:
            imap_server = encryption.EmailDataManager.decrypt_email_sender(
                account.encrypted_imap_server, master_key
            )
            imap_username = encryption.EmailDataManager.decrypt_email_sender(
                account.encrypted_imap_username, master_key
            )
            imap_password = encryption.EmailDataManager.decrypt_email_sender(
                account.encrypted_imap_password, master_key
            )
        except Exception as e:
            logger.error(f"Decryption error for account {account_id}: {e}")
            return jsonify({
                'success': False,
                'error': 'Fehler beim Entschlüsseln der Credentials'
            }), 500
        
        # Scan-Lock setzen
        _active_scans.add(account_id)
        
        try:
            # IMAP-Scan durchführen
            from src.services.imap_sender_scanner import scan_account_senders
            
            result = scan_account_senders(
                imap_server=imap_server,
                imap_username=imap_username,
                imap_password=imap_password,
                folder=folder,
                limit=limit
            )
            
            return jsonify(result)
        
        finally:
            # Scan-Lock immer freigeben
            _active_scans.discard(account_id)
    
    finally:
        db.close()


@app.route('/api/trusted-senders/bulk-add', methods=['POST'])
@login_required
def api_bulk_add_trusted_senders():
    """
    Fügt mehrere Absender zur Whitelist hinzu (Bulk-Insert).
    
    Duplikat-Handling:
        - Existierende Sender werden übersprungen (Skip + Warning)
        - Transactional mit Rollback bei kritischen Fehlern
        - Detailed Error-Reporting
    
    POST Body:
    {
        "senders": [
            {"pattern": "boss@firma.de", "type": "exact", "label": "Chef"},
            ...
        ],
        "account_id": 1  // optional: null = global
    }
    
    Returns:
        {
            "success": true,
            "added": int,
            "skipped": int,
            "details": {
                "added": [str, ...],
                "skipped": [{"pattern": str, "reason": str}, ...]
            }
        }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            'success': False,
            'error': 'Nicht authentifiziert'
        }), 401
    
    db = get_db_session()
    try:
        data = request.get_json()
        if not data or 'senders' not in data:
            return jsonify({
                'success': False,
                'error': 'Keine Absender angegeben'
            }), 400
        
        senders = data.get('senders', [])
        account_id = data.get('account_id')
        
        logger.info(f"📥 Bulk-Add Request: {len(senders)} Absender für User {current_user.id}, Account {account_id}")
        
        # Account validieren (falls angegeben)
        if account_id is not None:
            account = db.query(models.MailAccount).filter_by(
                id=account_id,
                user_id=current_user.id  # ✅ Ownership-Check
            ).first()
            
            if not account:
                return jsonify({
                    'success': False,
                    'error': 'Account nicht gefunden oder keine Berechtigung'
                }), 404
        
        added = []
        skipped = []
        
        # Import Service
        from src.services.trusted_senders import TrustedSenderManager
        
        # TRANSACTIONAL Bulk-Add
        try:
            for sender_data in senders:
                try:
                    pattern = sender_data.get('pattern', '').strip()
                    pattern_type = sender_data.get('type', 'exact')
                    label = sender_data.get('label', '').strip() or None
                    
                    logger.debug(f"  Processing: {pattern} ({pattern_type})")
                    
                    if not pattern:
                        skipped.append({
                            'pattern': pattern,
                            'reason': 'Leeres Pattern'
                        })
                        continue
                    
                    # Hinzufügen (Duplikat-Check im Service)
                    result = TrustedSenderManager.add_trusted_sender(
                        db=db,
                        user_id=current_user.id,
                        sender_pattern=pattern,
                        pattern_type=pattern_type,
                        label=label,
                        account_id=account_id
                    )
                    
                    if result.get('success'):
                        if result.get('already_exists'):
                            # Duplikat - skippen
                            logger.info(f"  ⚠️  Duplikat: {pattern}")
                            skipped.append({
                                'pattern': pattern,
                                'reason': result.get('message', 'Absender existiert bereits')
                            })
                        else:
                            # Erfolgreich hinzugefügt
                            logger.info(f"  ✅ Hinzugefügt: {pattern}")
                            added.append(pattern)
                    else:
                        # Fehler (z.B. Validierung, Limit)
                        logger.warning(f"  ❌ Fehler für {pattern}: {result.get('error')}")
                        skipped.append({
                            'pattern': pattern,
                            'reason': result.get('error', 'Unbekannter Fehler')
                        })
                        
                except Exception as e:
                    logger.error(f"Bulk-Add Error for {sender_data}: {e}")
                    skipped.append({
                        'pattern': sender_data.get('pattern', 'unknown'),
                        'reason': f"Exception: {str(e)}"
                    })
            
            # Alle erfolgreich → Commit
            db.commit()
            
            logger.info(f"✅ Bulk-Add abgeschlossen: {len(added)} hinzugefügt, {len(skipped)} übersprungen")
            
        except Exception as critical_error:
            # Kritischer Fehler → ROLLBACK alles!
            logger.error(f"CRITICAL: Bulk-Add Transaction failed, rolling back: {critical_error}")
            db.rollback()
            
            return jsonify({
                'success': False,
                'error': f'Kritischer Fehler: {str(critical_error)}. Keine Änderungen wurden gespeichert.'
            }), 500
        
        return jsonify({
            'success': True,
            'added': len(added),
            'skipped': len(skipped),
            'details': {
                'added': added,
                'skipped': skipped
            }
        })
    
    finally:
        db.close()


def start_server(host="0.0.0.0", port=5000, debug=True, use_https=False):
    """Startet den Flask-Server

    Args:
        host: Server Host (default: 0.0.0.0)
        port: Server Port (default: 5000)
        debug: Debug-Modus (default: True)
        use_https: HTTPS aktivieren (default: False)
                   - True: Self-signed Certificate (adhoc) + HTTP Redirector
                   - ('cert.pem', 'key.pem'): Eigene Zertifikate
    """
    global talisman

    if use_https:
        # Enable Secure Cookie Flag for HTTPS mode
        app.config["SESSION_COOKIE_SECURE"] = True
        logger.info("🔒 SESSION_COOKIE_SECURE=True (HTTPS-Modus)")

        # Dual-Port Setup: HTTP Redirector + HTTPS Server
        https_port = port + 1  # z.B. 5001 für HTTPS

        # 1. HTTP Redirector auf Port 5000
        def run_http_redirector():
            """Einfacher HTTP→HTTPS Redirector"""
            from flask import Flask as RedirectorApp

            redirector = RedirectorApp("redirector")

            @redirector.route("/", defaults={"path": ""})
            @redirector.route("/<path:path>")
            def redirect_to_https(path):
                https_url = request.url.replace("http://", "https://").replace(
                    f":{port}", f":{https_port}"
                )
                return redirect(https_url, code=301)

            print(
                f"🔀 HTTP Redirector läuft auf http://{host}:{port} → https://localhost:{https_port}"
            )
            redirector_server = make_server(host, port, redirector, threaded=True)
            redirector_server.serve_forever()

        # Starte HTTP Redirector in separatem Thread
        redirector_thread = threading.Thread(target=run_http_redirector, daemon=True)
        redirector_thread.start()

        # 2. HTTPS Server auf Port 5001
        ssl_context = "adhoc" if use_https is True else use_https
        logger.info(f"🔒 HTTPS aktiviert (Port {https_port}, Self-signed Certificate)")

        # Flask-Talisman für zusätzliche Security Headers
        talisman_instance = None
        if TALISMAN_AVAILABLE and os.getenv("FORCE_HTTPS", "false").lower() == "true":
            # CSP Policy: Erlaubt Bootstrap CDN, inline-styles/-scripts für bestehende App
            csp = {
                "default-src": "'self'",
                "script-src": [
                    "'self'",
                    "'unsafe-inline'",  # TODO: Refactor inline-scripts zu external files
                    "https://cdn.jsdelivr.net",  # Bootstrap JS
                ],
                "style-src": [
                    "'self'",
                    "'unsafe-inline'",  # Bootstrap inline-styles
                    "https://cdn.jsdelivr.net",  # Bootstrap CSS
                ],
                "img-src": "'self' data:",  # Data-URLs für embedded images
                "font-src": ["'self'", "https://cdn.jsdelivr.net"],
                "connect-src": "'self'",  # AJAX nur zu eigenem Server
                "frame-src": "'none'",  # Keine externen Frames (nur sandbox-iframes)
                "object-src": "'none'",  # Kein Flash/Java
            }

            talisman_instance = Talisman(
                app,
                force_https=False,  # Redirector übernimmt das
                strict_transport_security=True,
                strict_transport_security_max_age=31536000,
                content_security_policy=csp,
                content_security_policy_nonce_in=[
                    "script-src"
                ],  # Nonce-basierte CSP für inline-scripts
                content_security_policy_report_only=False,
            )

            logger.info("🔒 Flask-Talisman aktiviert - Security Headers + CSP + Nonce")

        # Store talisman instance globally for decorator usage
        global talisman
        talisman = talisman_instance

        print(f"🌐 Dashboard läuft auf https://{host}:{https_port}")
        print(
            f"💡 Tipp: Browser öffnet http://localhost:{port} → Auto-Redirect zu HTTPS"
        )
        app.run(host=host, port=https_port, debug=debug, ssl_context=ssl_context)

    else:
        # Standard HTTP-Modus (ohne HTTPS)
        print(f"🌐 Dashboard läuft auf http://{host}:{port}")
        app.run(host=host, port=port, debug=debug)


# ===== Debug Logger Status API =====
@app.route("/api/debug-logger-status")
@login_required
def api_debug_logger_status():
    """API: Zeigt Status des Debug-Loggers (nur für Admins)"""
    status = DebugLogger.get_status()
    
    if status["enabled"]:
        return jsonify({
            "enabled": True,
            "warning": "⚠️ DEBUG-LOGGING IST AKTIV - Sensible Daten werden geloggt!",
            "log_dir": status["log_dir"],
            "log_files": status["log_files"],
            "hint": "Zum Deaktivieren: src/debug_logger.py → ENABLED = False"
        }), 200
    else:
        return jsonify({
            "enabled": False,
            "status": "✅ Debug-Logging ist deaktiviert",
            "hint": "Zum Aktivieren: src/debug_logger.py → ENABLED = True"
        }), 200


if __name__ == "__main__":
    start_server()
