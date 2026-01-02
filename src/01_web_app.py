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
    response.headers[
        "Strict-Transport-Security"
    ] = "max-age=31536000; includeSubDomains"
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

engine = create_engine(f"sqlite:///{DATABASE_PATH}")
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


def ensure_master_key_in_session():
    """Stellt sicher, dass Master-Key in Session vorhanden ist"""
    if not session.get("master_key"):
        logger.error(f"Master-Key nicht in Session für User {current_user.id}")
        return False
    return True


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

        matrix_data = {}
        total_mails = 0
        high_priority_count = 0

        processed_mails = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.done == False,
                models.ProcessedEmail.deleted_at == None,
            )
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

        done_mails = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.done == True,
                models.ProcessedEmail.deleted_at == None,
            )
            .count()
        )

        stats = {
            "total": total_mails + done_mails,
            "open": total_mails,
            "done": done_mails,
        }

        return render_template(
            "dashboard.html", matrix=matrix, ampel=amp_colors, stats=stats, top_tags=[]
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

        if sort_order == "asc":
            mails = query.order_by(sort_col.asc()).all()
        else:
            mails = query.order_by(sort_col.desc()).all()

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

        return render_template("threads_view.html", user=user, csp_nonce=g.csp_nonce)

    finally:
        db.close()


@app.route("/email/<int:email_id>")
@login_required
def email_detail(email_id):
    """Detailansicht einer einzelnen Mail"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.ProcessedEmail.id == email_id,
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
        decrypted_body = ""
        decrypted_summary_de = ""
        decrypted_text_de = ""
        decrypted_tags = ""

        if master_key:
            try:
                # RawEmail entschlüsseln
                decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                    raw.encrypted_subject or "", master_key
                )
                decrypted_sender = encryption.EmailDataManager.decrypt_email_sender(
                    raw.encrypted_sender or "", master_key
                )
                decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                    raw.encrypted_body or "", master_key
                )

                # ProcessedEmail entschlüsseln
                decrypted_summary_de = encryption.EmailDataManager.decrypt_summary(
                    processed.encrypted_summary_de or "", master_key
                )
                decrypted_text_de = encryption.EmailDataManager.decrypt_summary(
                    processed.encrypted_text_de or "", master_key
                )
                decrypted_tags = encryption.EmailDataManager.decrypt_summary(
                    processed.encrypted_tags or "", master_key
                )
            except Exception as e:
                logger.error(
                    f"Entschlüsselung fehlgeschlagen für RawEmail {raw.id}: {type(e).__name__}"
                )

        # Phase 10: Lade Email-Tags
        email_tags = []
        all_user_tags = []
        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            email_tags = tag_manager_mod.TagManager.get_email_tags(
                db, email_id, user.id
            )
            all_user_tags = tag_manager_mod.TagManager.get_user_tags(db, user.id)
        except ImportError:
            logger.warning("TagManager nicht verfügbar")

        return render_template(
            "email_detail.html",
            user=user,
            email=processed,
            raw=raw,
            decrypted_subject=decrypted_subject,
            decrypted_sender=decrypted_sender,
            decrypted_body=decrypted_body,
            decrypted_summary_de=decrypted_summary_de,
            decrypted_text_de=decrypted_text_de,
            decrypted_tags=decrypted_tags,
            priority_label=priority_label,
            email_tags=email_tags,
            all_user_tags=all_user_tags,
        )

    finally:
        db.close()


@app.route("/email/<int:email_id>/render-html")
@login_required
def render_email_html(email_id: int):
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
            logger.error(f"render_email_html: User not found (email_id={email_id})")
            return "Unauthorized", 403

        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.ProcessedEmail.id == email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not processed:
            logger.error(
                f"render_email_html: Email {email_id} not found for user {user.id}"
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
                f"render_email_html: Entschlüsselung fehlgeschlagen für Email {email_id}: {type(e).__name__}: {e}"
            )
            return "Decryption failed", 500

        # Marker für after_request Hook: Überschreibe Headers nicht (MUSS VOR make_response!)
        g.skip_security_headers = True

        # Response mit lockerer CSP nur für E-Mail-Content
        response = make_response(decrypted_body)
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


@app.route("/email/<int:email_id>/done", methods=["POST"])
@login_required
def mark_done(email_id):
    """Markiert eine Mail als erledigt"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.ProcessedEmail.id == email_id,
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
            logger.info(f"✅ Mail {email_id} als erledigt markiert")

        return redirect(request.referrer or url_for("list_view"))

    except Exception as e:
        # Security: Log details internally, show generic message to user
        logger.error(f"Fehler bei mark_done: {type(e).__name__}")
        flash("Fehler beim Markieren der E-Mail. Bitte versuche es erneut.", "error")
        return redirect(url_for("list_view"))

    finally:
        db.close()


@app.route("/email/<int:email_id>/undo", methods=["POST"])
@login_required
def mark_undone(email_id):
    """Macht 'erledigt'-Markierung rückgängig"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)

        email = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.ProcessedEmail.id == email_id,
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
            logger.info(f"↩️  Mail {email_id} zurückgesetzt")

        return redirect(request.referrer or url_for("list_view"))

    except Exception as e:
        logger.error(f"Fehler bei mark_undone: {type(e).__name__}")
        return redirect(url_for("list_view"))

    finally:
        db.close()


@app.route("/email/<int:email_id>/reprocess", methods=["POST"])
@login_required
def reprocess_email(email_id):
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
                models.ProcessedEmail.id == email_id,
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
            logger.info(f"✅ Mail {email_id} erneut verarbeitet: Score={email.score}")

            return jsonify(
                {
                    "status": "success",
                    "message": "Email erfolgreich neu verarbeitet",
                    "score": email.score,
                    "farbe": email.farbe,
                }
            )

        except Exception as proc_err:
            logger.error(f"❌ Fehler bei Reprocessing von Email {email_id}: {proc_err}")
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
        logger.error(f"Fehler bei reprocess_email: {type(e).__name__}")
        return jsonify({"error": "Verarbeitung fehlgeschlagen"}), 500

    finally:
        db.close()


@app.route("/email/<int:email_id>/optimize", methods=["POST"])
@login_required
def optimize_email(email_id):
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
                models.ProcessedEmail.id == email_id,
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
            email.optimize_model = resolved_model
            email.optimize_provider = provider_optimize
            email.optimization_status = models.OptimizationStatus.DONE.value
            email.optimization_completed_at = datetime.now(UTC)
            email.updated_at = datetime.now(UTC)

            db.commit()
            logger.info(f"✅ Mail {email_id} optimiert: Score={email.optimize_score}")

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
        logger.error(f"Fehler bei optimize_email: {type(e).__name__}")
        return jsonify({"error": "Optimierung fehlgeschlagen"}), 500

    finally:
        db.close()


@app.route("/email/<int:email_id>/correct", methods=["POST"])
def correct_email(email_id: int):
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
                models.ProcessedEmail.id == email_id,
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
        email.user_correction_note = data.get("note")
        email.correction_timestamp = datetime.now(UTC)
        email.updated_at = datetime.now(UTC)

        db.commit()

        logger.info(f"✅ Mail {email_id} korrigiert durch User {user.id}")

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
        logger.error(f"Fehler beim Speichern der Korrektur: {type(e).__name__}")
        return jsonify({"error": "Speichern fehlgeschlagen"}), 500
    finally:
        db.close()


@app.route("/api/email/<int:email_id>/flags", methods=["GET"])
@login_required
def get_email_flags(email_id):
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
                models.ProcessedEmail.id == email_id,
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

        selected_provider_base = (user.preferred_ai_provider or "ollama").lower()
        selected_model_base = user.preferred_ai_model or "all-minilm:22m"

        selected_provider_optimize = (
            user.preferred_ai_provider_optimize or "ollama"
        ).lower()
        selected_model_optimize = user.preferred_ai_model_optimize or "llama3.2:1b"

        # Phase 13C Part 4: User Fetch Preferences
        user_prefs = {
            'mails_per_folder': getattr(user, 'fetch_mails_per_folder', 100),
            'max_total_mails': getattr(user, 'fetch_max_total', 0),
            'use_delta_sync': getattr(user, 'fetch_use_delta_sync', True)
        }

        return render_template(
            "settings.html",
            user=user,
            mail_accounts=mail_accounts,
            totp_enabled=user.totp_enabled,
            ai_selected_provider_base=selected_provider_base,
            ai_selected_model_base=selected_model_base,
            ai_selected_provider_optimize=selected_provider_optimize,
            ai_selected_model_optimize=selected_model_optimize,
            user_prefs=user_prefs,
        )

    finally:
        db.close()


@app.route("/settings/fetch-config", methods=["POST"])
@login_required
def save_fetch_config():
    """Speichert Fetch-Präferenzen des Users
    
    Phase 13C Part 4: User kann steuern wie viele Mails abgerufen werden
    """
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        mails_per_folder = int(request.form.get('mails_per_folder', 100))
        max_total_mails = int(request.form.get('max_total_mails', 0))
        use_delta_sync = request.form.get('use_delta_sync') == 'on'

        # Validierung
        if mails_per_folder < 10 or mails_per_folder > 1000:
            flash("❌ Mails pro Ordner muss zwischen 10 und 1000 liegen", "error")
            return redirect(url_for("settings"))
        
        if max_total_mails < 0 or max_total_mails > 10000:
            flash("❌ Max. Gesamt muss zwischen 0 und 10000 liegen", "error")
            return redirect(url_for("settings"))

        # Speichere in User-Modell (erweitere 02_models.py wenn nötig)
        user.fetch_mails_per_folder = mails_per_folder
        user.fetch_max_total = max_total_mails
        user.fetch_use_delta_sync = use_delta_sync
        
        db.commit()

        flash(f"✅ Fetch-Konfiguration gespeichert: {mails_per_folder}/Ordner, Max={max_total_mails}, Delta={use_delta_sync}", "success")
        return redirect(url_for("settings"))

    except Exception as e:
        logger.error(f"Fehler beim Speichern der Fetch-Config: {e}")
        flash("❌ Fehler beim Speichern", "error")
        return redirect(url_for("settings"))

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
                    "email_count": email_count,
                }
            )

        return render_template(
            "tags.html", user=user, tags=tags_with_counts, csp_nonce=g.csp_nonce
        )

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
    """API: Tag erstellen"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        name = data.get("name", "").strip()
        color = data.get("color", "#3B82F6")

        if not name:
            return jsonify({"error": "Tag-Name erforderlich"}), 400

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            tag = tag_manager_mod.TagManager.create_tag(db, user.id, name, color)

            return jsonify({"id": tag.id, "name": tag.name, "color": tag.color}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    finally:
        db.close()


@app.route("/api/tags/<int:tag_id>", methods=["PUT"])
@login_required
def api_update_tag(tag_id):
    """API: Tag aktualisieren"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        name = data.get("name")
        color = data.get("color")

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            tag = tag_manager_mod.TagManager.update_tag(
                db, tag_id, user.id, name=name, color=color
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


@app.route("/api/emails/<int:email_id>/tags", methods=["GET"])
@login_required
def api_get_email_tags(email_id):
    """API: Tags einer E-Mail abrufen (für Learning-Modal)"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            tags = tag_manager_mod.TagManager.get_email_tags(db, email_id, user.id)

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


@app.route("/api/emails/<int:email_id>/tag-suggestions", methods=["GET"])
@login_required
def api_get_tag_suggestions(email_id):
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
                    models.ProcessedEmail.id == email_id,
                    models.RawEmail.user_id == user.id,
                    models.RawEmail.deleted_at == None
                )
                .first()
            )
            
            if not processed or not processed.raw_email:
                return jsonify({"suggestions": [], "email_id": email_id, "method": "none"}), 200
            
            raw_email = processed.raw_email
            
            # 2. Wenn Email-Embedding vorhanden: Nutze Phase F.2 Methode
            if raw_email.email_embedding:
                # Bereits zugewiesene Tags holen
                assigned_tag_ids = [
                    assignment.tag_id 
                    for assignment in db.query(models.EmailTagAssignment)
                    .filter_by(email_id=email_id).all()
                ]
                
                # Phase F.2: Email-Embedding-basierte Suggestions
                tag_suggestions = tag_manager_mod.TagManager.suggest_tags_by_email_embedding(
                    db=db,
                    user_id=user.id,
                    email_embedding_bytes=raw_email.email_embedding,
                    top_k=5,
                    min_similarity=0.70,  # 70% als UI-Threshold
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
                
                return jsonify({
                    "suggestions": suggestions, 
                    "email_id": email_id,
                    "method": "embedding",  # Phase F.2
                    "embedding_available": True
                }), 200
            
            else:
                # Fallback: Alte text-basierte Methode (Phase 11c)
                # Für Emails ohne Embedding (z.B. alte Daten vor Phase F.1)
                suggestions = tag_manager_mod.TagManager.get_tag_suggestions_for_email(
                    db, email_id, user.id, top_k=5
                )
                
                return jsonify({
                    "suggestions": suggestions, 
                    "email_id": email_id,
                    "method": "text-fallback",  # Legacy
                    "embedding_available": False
                }), 200
                
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Tag-Vorschläge: {e}")
            return jsonify({"suggestions": [], "email_id": email_id}), 200

    finally:
        db.close()


@app.route("/api/emails/<int:email_id>/tags", methods=["POST"])
@login_required
def api_assign_tag_to_email(email_id):
    """API: Tag zu E-Mail zuweisen"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        tag_id = data.get("tag_id")

        if not tag_id:
            return jsonify({"error": "tag_id erforderlich"}), 400

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            success = tag_manager_mod.TagManager.assign_tag(
                db, email_id, tag_id, user.id
            )

            if not success:
                return (
                    jsonify({"error": "Tag bereits zugewiesen oder nicht gefunden"}),
                    400,
                )

            # Learning: Update user_override_tags für ML-Training
            _update_user_override_tags(db, email_id, user.id, tag_manager_mod)

            return jsonify({"success": True})
        except ValueError as e:
            return jsonify({"error": str(e)}), 404

    finally:
        db.close()


@app.route("/api/emails/<int:email_id>/tags/<int:tag_id>", methods=["DELETE"])
@login_required
def api_remove_tag_from_email(email_id, tag_id):
    """API: Tag von E-Mail entfernen"""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            success = tag_manager_mod.TagManager.remove_tag(
                db, email_id, tag_id, user.id
            )

            if not success:
                return jsonify({"error": "Tag-Verknüpfung nicht gefunden"}), 404

            # Learning: Update user_override_tags für ML-Training
            _update_user_override_tags(db, email_id, user.id, tag_manager_mod)

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

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


# ===== Phase F.1: Semantic Search API Endpoints =====


@app.route("/api/search/semantic", methods=["GET"])
@login_required
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
                threshold=threshold
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


@app.route("/api/emails/<int:email_id>/similar", methods=["GET"])
@login_required
def api_find_similar_emails(email_id):
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
        except ValueError:
            return jsonify({"error": "Invalid limit parameter"}), 400
            
        # Ownership Check: User muss die Email besitzen
        ref_email = db.query(models.RawEmail).filter_by(
            id=email_id,
            user_id=user.id
        ).first()
        
        if not ref_email:
            return jsonify({"error": "Email not found or access denied"}), 404
            
        # Similar Emails finden
        try:
            search_service = semantic_search.SemanticSearchService(db)
            results = search_service.find_similar(
                email_id=email_id,
                limit=limit
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
                "reference_email_id": email_id,
                "total": len(formatted_results)
            }), 200
            
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 404
        except Exception as search_err:
            logger.error(f"Similar search failed: {search_err}")
            return jsonify({
                "similar_emails": [],
                "reference_email_id": email_id,
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

@app.route("/api/emails/<int:email_id>/generate-reply", methods=["POST"])
@login_required
def api_generate_reply(email_id):
    """
    API: Generiert Antwort-Entwurf auf eine Email (Phase G.1)
    
    Request Body:
    {
        "tone": "formal|friendly|brief|decline"  // Optional, default: "formal"
    }
    
    Returns:
    {
        "success": true,
        "reply_text": "Sehr geehrte Frau Müller,\n\n...",
        "tone_used": "formal",
        "tone_name": "Formell",
        "tone_icon": "📜",
        "timestamp": "2026-01-02T10:30:00"
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
        
        # Validiere Email-Zugriff
        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.ProcessedEmail.id == email_id,
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
            logger.error(f"Decryption failed for email {email_id}: {e}")
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
            
            # Get AI Client (gleicher wie für Processing)
            ai_client = get_active_ai_client()
            
            generator = reply_generator_mod.ReplyGenerator(ai_client=ai_client)
            result = generator.generate_reply(
                original_subject=decrypted_subject,
                original_body=decrypted_body,
                original_sender=decrypted_sender,
                tone=tone,
                thread_context=thread_context if thread_context else None
            )
            
            if result["success"]:
                logger.info(
                    f"✅ Reply-Entwurf generiert für Email {email_id} "
                    f"(Ton: {result['tone_used']}, {len(result['reply_text'])} chars)"
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
    """Speichert KI-Provider- und Modellpräferenzen für Base + Optimize Pass."""
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        provider_base = (request.form.get("ai_provider_base") or "ollama").lower()
        model_base = (request.form.get("ai_model_base") or "").strip()

        provider_optimize = (
            request.form.get("ai_provider_optimize") or "ollama"
        ).lower()
        model_optimize = (request.form.get("ai_model_optimize") or "").strip()

        ok, resolved_base, error = ai_client.validate_provider_choice(
            provider_base, model_base, kind="base"
        )
        if not ok:
            flash(f"Base-Pass: {error or 'Ungültige Auswahl'}", "danger")
            return redirect(url_for("settings"))

        ok, resolved_optimize, error = ai_client.validate_provider_choice(
            provider_optimize, model_optimize, kind="optimize"
        )
        if not ok:
            flash(f"Optimize-Pass: {error or 'Ungültige Auswahl'}", "danger")
            return redirect(url_for("settings"))

        user.preferred_ai_provider = provider_base
        user.preferred_ai_model = resolved_base
        user.preferred_ai_provider_optimize = provider_optimize
        user.preferred_ai_model_optimize = resolved_optimize
        db.commit()

        flash("KI-Präferenzen gespeichert (Base + Optimize).", "success")
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
            accounts=mail_accounts,
            csp_nonce=g.csp_nonce,
        )

    finally:
        db.close()


@app.route("/api/imap-diagnostics/<int:account_id>", methods=["POST"])
@login_required
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
def job_status(job_id: str):
    """Liefert Status-Infos zu einem Hintergrundjob."""
    status = job_queue.get_status(job_id, current_user.id)
    if not status:
        return jsonify({"error": "Job nicht gefunden"}), 404
    return jsonify(status)


@app.route("/email/<int:email_id>/delete", methods=["POST"])
@login_required
def delete_email(email_id):
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
                models.ProcessedEmail.id == email_id,
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


@app.route("/email/<int:email_id>/move-trash", methods=["POST"])
@login_required
def move_email_to_trash(email_id):
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
                models.ProcessedEmail.id == email_id,
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


@app.route("/account/<int:account_id>/mail-count", methods=["GET"])
@login_required
def get_account_mail_count(account_id):
    """Zählt schnell wie viele Mails auf dem Server sind (ohne sie zu fetchen)
    
    Phase 13C Part 4: Quick Count für intelligentes Fetching
    - Zeigt User wie viele Mails remote vorhanden sind
    - User kann dann entscheiden: Alle holen oder in Portionen?
    """
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
                    
                    folder_counts[folder_display] = {
                        "total": messages_count,
                        "unseen": unseen_count
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

            return jsonify({
                "account_id": account_id,
                "folders": folder_counts,
                "summary": {
                    "total_remote": total_remote,
                    "total_unseen": total_unseen,
                    "total_local": total_local,
                    "delta": total_remote - total_local
                }
            })

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
                folders.append(folder_display)

            folders.sort()
            return jsonify({"folders": folders})

        finally:
            fetcher.disconnect()

    except Exception as e:
        logger.error(f"Fehler beim Abrufen von Folders für Account {account_id}: {type(e).__name__}")
        return jsonify({"error": "Fehler beim Abrufen von Ordnern"}), 500

    finally:
        db.close()


@app.route("/email/<int:email_id>/move-to-folder", methods=["POST"])
@login_required
def move_email_to_folder(email_id):
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
                models.ProcessedEmail.id == email_id,
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


@app.route("/email/<int:email_id>/mark-read", methods=["POST"])
@login_required
def mark_email_read(email_id):
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
                models.ProcessedEmail.id == email_id,
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


@app.route("/email/<int:email_id>/toggle-read", methods=["POST"])
@login_required
def toggle_email_read(email_id):
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
                models.ProcessedEmail.id == email_id,
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


@app.route("/email/<int:email_id>/mark-flag", methods=["POST"])
@login_required
def toggle_email_flag(email_id):
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
                models.ProcessedEmail.id == email_id,
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


if __name__ == "__main__":
    start_server()
