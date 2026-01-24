# src/app_factory.py
"""Flask Application Factory for Blueprint-based architecture."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env.local first (priority), then .env (fallback)
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env.local", override=True)
load_dotenv(project_root / ".env", override=False)

from flask import Flask, render_template, request, g, session, flash, redirect, url_for, jsonify
from flask_login import LoginManager, current_user, logout_user
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, validate_csrf, generate_csrf
from werkzeug.exceptions import BadRequest
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, UTC
import os
import secrets
import importlib
import logging
import json

logger = logging.getLogger(__name__)

env_validator = importlib.import_module(".00_env_validator", "src")
env_validator.validate_environment()

from src.debug_logger import DebugLogger

# Global limiter instance - initialized in create_app()
limiter = None

DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emails.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

# Feature-Flags für Multi-User Migration
USE_POSTGRESQL = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")

if USE_POSTGRESQL:
    logger.info("🐘 PostgreSQL Mode aktiviert")
    connect_args = {"connect_timeout": 10}
else:
    logger.info("📦 SQLite Mode (Legacy)")
    connect_args = {"check_same_thread": False, "timeout": 30.0}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args
)

if not USE_POSTGRESQL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        """SQLite Pragmas für Multi-Worker Concurrency"""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine)

job_queue = None
logger.info("🚀 Celery Mode - Legacy Job Queue deaktiviert")

encryption = importlib.import_module(".08_encryption", "src")

def decrypt_raw_email(raw_email, master_key):
    """Zero-Knowledge Helper: Entschlüsselt RawEmail-Felder"""
    try:
        return {
            "sender": encryption.EmailDataManager.decrypt_email_sender(
                raw_email.encrypted_sender or "", master_key
            ) if raw_email.encrypted_sender else "",
            "subject": encryption.EmailDataManager.decrypt_email_subject(
                raw_email.encrypted_subject or "", master_key
            ) if raw_email.encrypted_subject else "",
            "body": encryption.EmailDataManager.decrypt_email_body(
                raw_email.encrypted_body or "", master_key
            ) if raw_email.encrypted_body else "",
        }
    except (ValueError, KeyError, Exception) as e:
        logger.error(f"Entschlüsselung fehlgeschlagen für RawEmail {raw_email.id}: {type(e).__name__}")
        return {
            "sender": "***Entschlüsselung fehlgeschlagen***",
            "subject": "***Entschlüsselung fehlgeschlagen***",
            "body": "***Entschlüsselung fehlgeschlagen***",
        }

def create_app(config_name="production"):
    """Create and configure the Flask application."""
    
    app = Flask(
        __name__, 
        template_folder="../templates", 
        static_folder="../static"
    )
    
    if os.getenv("BEHIND_REVERSE_PROXY", "false").lower() == "true":
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1, x_proto=1, x_host=1, x_prefix=1,
        )
        logger.info("🔄 ProxyFix aktiviert - App läuft hinter Reverse Proxy")
    
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    app.config["SESSION_TYPE"] = "filesystem"
    
    session_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".flask_sessions")
    os.makedirs(session_dir, mode=0o700, exist_ok=True)
    app.config["SESSION_FILE_DIR"] = session_dir
    
    app.config["SESSION_PERMANENT"] = True
    session_lifetime_minutes = int(os.getenv("SESSION_LIFETIME_MINUTES", "60"))
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=session_lifetime_minutes)
    app.config["SESSION_USE_SIGNER"] = False
    app.config["SESSION_KEY_PREFIX"] = "mail_helper_"
    app.config["SESSION_ID_LENGTH"] = 32
    
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    
    csrf = CSRFProtect(app)
    Session(app)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Bitte melden Sie sich an."
    login_manager.login_message_category = "info"
    
    from flask_login import UserMixin
    
    class UserWrapper(UserMixin):
        """Wrapper für SQLAlchemy User-Model"""
        def __init__(self, user_model):
            self.user_model = user_model
            self.id = user_model.id
        
        def get_id(self):
            return str(self.user_model.id)
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID"""
        models = importlib.import_module(".02_models", "src")
        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(id=int(user_id)).first()
            if user:
                return UserWrapper(user)
        finally:
            db.close()
        return None
    
    rate_limit_storage = os.getenv("RATE_LIMIT_STORAGE", "memory://")
    if rate_limit_storage == "auto":
        try:
            import redis
            r = redis.Redis(host="localhost", port=6379, db=1, socket_connect_timeout=1)
            r.ping()
            rate_limit_storage = "redis://localhost:6379/1"
            logger.info("🟢 Redis detected - using for rate limiting")
        except (ImportError, ConnectionError):
            rate_limit_storage = "memory://"
            logger.warning("🟡 Redis not available - using memory storage")
    
    global limiter
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[],  # 🔥 KEINE Default-Limits - nur explizite Limits per Route
        storage_uri=rate_limit_storage,
    )
    app.limiter = limiter
    logger.info("🛡️  Rate Limiting aktiviert")
    
    @app.before_request
    def generate_csp_nonce():
        """Generate CSP nonce"""
        g.csp_nonce = secrets.token_urlsafe(16)
    
    @app.before_request
    def csrf_protect_ajax():
        """CSRF protection for AJAX"""
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                csrf_token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
                if csrf_token:
                    try:
                        validate_csrf(csrf_token)
                    except Exception:
                        pass
    
    @app.after_request
    def set_security_headers(response):
        """Set security headers"""
        if g.get("skip_security_headers", False):
            return response
        
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        if response.status_code < 400:
            nonce = getattr(g, 'csp_nonce', '')
            csp = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )
            response.headers['Content-Security-Policy'] = csp
        
        return response
    
    @app.before_request
    def check_dek_in_session():
        """Check for DEK in session"""
        if request.endpoint in [
            "auth.login", "auth.register", "auth.logout", "static",
            "auth.verify_2fa", "auth.setup_2fa",
            "login", "register", "logout", "verify_2fa", "setup_2fa",
        ]:
            return None

        if current_user.is_authenticated and not session.get("master_key"):
            logger.warning(f"User {current_user.id} needs reauth")
            session.clear()
            logout_user()
            flash("Sitzung abgelaufen", "warning")
            return redirect(url_for("auth.login"))

        if current_user.is_authenticated:
            models = importlib.import_module(".02_models", "src")
            db = SessionLocal()
            try:
                user = db.query(models.User).filter_by(id=current_user.id).first()
                if user and not user.totp_enabled:
                    logger.warning(f"User {current_user.id} needs 2FA setup")
                    flash("2FA erforderlich", "warning")
                    return redirect(url_for("auth.setup_2fa"))
            finally:
                db.close()

        return None
    
    @app.route('/favicon.ico')
    def favicon():
        return '', 204
    
    @app.errorhandler(404)
    def not_found(e):
        return '<h1>404</h1>', 404
    
    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Server error: {e}")
        return '<h1>500 Internal Server Error</h1>', 500
    
    from .blueprints import (
        auth_bp, emails_bp, email_actions_bp, accounts_bp,
        tags_bp, api_bp, rules_bp, training_bp, admin_bp
    )
    from .thread_api import thread_api
    from .blueprints.translator import translator_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(emails_bp)
    app.register_blueprint(email_actions_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(rules_bp)
    app.register_blueprint(training_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(thread_api)
    app.register_blueprint(translator_bp)
    
    # Context Processors für Templates
    @app.context_processor
    def inject_template_globals():
        """Make csrf_token and csp_nonce available in all templates"""
        return dict(
            csrf_token=generate_csrf, 
            csp_nonce=lambda: g.get("csp_nonce", "")
        )
    
    @app.context_processor
    def inject_current_user_model():
        if current_user.is_authenticated:
            models = importlib.import_module(".02_models", "src")
            db = SessionLocal()
            try:
                user = db.query(models.User).filter_by(id=current_user.id).first()
                return dict(current_user_model=user)
            finally:
                db.close()
        return dict(current_user_model=None)
    
    _register_endpoint_aliases(app)
    logger.info("✅ Flask App mit Blueprint-Architektur initialisiert")
    
    return app

def _register_endpoint_aliases(app):
    """Register backwards-compatible endpoint aliases.
    
    This allows old templates using url_for('login') to work
    with the new Blueprint architecture using url_for('auth.login').
    
    We register URL rules that point to the same view functions,
    allowing url_for() to resolve both old and new endpoint names.
    """
    
    # Mapping: alt_endpoint → blueprint_endpoint
    # Wir fügen URL-Regeln hinzu, die auf die Blueprint-View-Funktionen zeigen
    aliases = {
        # AUTH Blueprint
        'login': 'auth.login',
        'logout': 'auth.logout',
        'register': 'auth.register',
        'setup_2fa': 'auth.setup_2fa',
        'verify_2fa': 'auth.verify_2fa',
        'index': 'auth.index',
        
        # EMAILS Blueprint
        'dashboard': 'emails.dashboard',
        'list_view': 'emails.list_view',
        
        # ACCOUNTS Blueprint
        'settings': 'accounts.settings',
        'whitelist': 'accounts.whitelist',
        'ki_prio': 'accounts.ki_prio',
        'mail_fetch_config': 'accounts.mail_fetch_config',
        'google_oauth_callback': 'accounts.google_oauth_callback',
    }
    
    registered = 0
    for old_name, new_name in aliases.items():
        if new_name in app.view_functions:
            # Finde die URL-Regel für den Blueprint-Endpoint
            for rule in app.url_map.iter_rules():
                if rule.endpoint == new_name:
                    # Registriere dieselbe URL unter dem alten Endpoint-Namen
                    app.add_url_rule(
                        rule.rule,
                        endpoint=old_name,
                        view_func=app.view_functions[new_name],
                        methods=rule.methods - {'OPTIONS', 'HEAD'}
                    )
                    registered += 1
                    break
        else:
            logger.warning(f"Alias '{old_name}' → '{new_name}': Endpoint nicht gefunden")
    
    logger.info(f"✅ {registered}/{len(aliases)} Endpoint-Aliase registriert")

def start_server(host="0.0.0.0", port=5000, debug=False, use_https=False):
    """Start Flask server."""
    import threading
    
    try:
        from flask_talisman import Talisman
        TALISMAN_AVAILABLE = True
    except ImportError:
        TALISMAN_AVAILABLE = False
    
    _app = create_app()
    
    if use_https:
        _app.config["SESSION_COOKIE_SECURE"] = True
        logger.info("HTTPS-Modus")
        https_port = port + 1
        
        def run_http_redirector():
            from flask import Flask as RedirectorApp
            from werkzeug.serving import make_server as werkzeug_make_server
            
            redirector = RedirectorApp("redirector")
            
            @redirector.route("/", defaults={"path": ""})
            @redirector.route("/<path:path>")
            def redirect_to_https(path):
                from flask import request as req, redirect as redir
                https_url = req.url.replace("http://", "https://").replace(
                    f":{port}", f":{https_port}"
                )
                return redir(https_url, code=301)
            
            redirector_server = werkzeug_make_server(host, port, redirector, threaded=True)
            redirector_server.serve_forever()
        
        redirector_thread = threading.Thread(target=run_http_redirector, daemon=True)
        redirector_thread.start()
        
        ssl_context = "adhoc" if use_https is True else use_https
        _app.run(host=host, port=https_port, debug=debug, ssl_context=ssl_context)
    else:
        _app.run(host=host, port=port, debug=debug)
