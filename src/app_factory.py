# src/app_factory.py
"""Flask Application Factory for Blueprint-based architecture.

This module provides the create_app() factory function that creates
and configures a Flask application with all blueprints registered.

Usage:
    from src.app_factory import create_app
    app = create_app()
    
Or via 00_main.py with USE_BLUEPRINTS=1 environment variable.
"""

from flask import Flask, render_template, request, g, session, flash, redirect, url_for
from flask_login import LoginManager, current_user, logout_user
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, validate_csrf
from werkzeug.exceptions import BadRequest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import secrets
import importlib
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# GLOBALE VARIABLEN (shared zwischen Factory und Blueprints)
# ============================================================================
DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "emails.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30.0}
)
SessionLocal = sessionmaker(bind=engine)


def create_app(config_name="production"):
    """Create and configure the Flask application.
    
    Args:
        config_name: Configuration name (currently unused, reserved for future)
        
    Returns:
        Configured Flask application with all blueprints registered
    """
    
    app = Flask(
        __name__, 
        template_folder="../templates", 
        static_folder="../static"
    )
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_FILE_DIR"] = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "flask_session"
    )
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 24 hours
    
    # =========================================================================
    # INITIALIZE EXTENSIONS
    # =========================================================================
    
    # CSRF Protection
    csrf = CSRFProtect(app)
    
    # Session
    Session(app)
    
    # Login Manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # Blueprint-qualified!
    login_manager.login_message = "Bitte melden Sie sich an."
    login_manager.login_message_category = "info"
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login (aus 01_web_app.py Zeile 387-397)"""
        models = importlib.import_module(".02_models", "src")
        db = SessionLocal()
        try:
            user = db.query(models.User).filter_by(id=int(user_id)).first()
            return user
        finally:
            db.close()
    
    # Rate Limiter (aus 01_web_app.py Zeile 252-264)
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )
    
    # Store limiter on app for blueprint access
    app.limiter = limiter
    
    # =========================================================================
    # BEFORE/AFTER REQUEST HOOKS
    # =========================================================================
    
    @app.before_request
    def generate_csp_nonce():
        """Generate CSP nonce for each request (aus 01_web_app.py Zeile 155-159)"""
        g.csp_nonce = secrets.token_urlsafe(16)
    
    @app.before_request
    def csrf_protect_ajax():
        """CSRF protection for AJAX requests (aus 01_web_app.py Zeile 166-184)"""
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                csrf_token = request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
                if csrf_token:
                    try:
                        validate_csrf(csrf_token)
                    except Exception:
                        pass  # Already handled by CSRFProtect
    
    @app.after_request
    def set_security_headers(response):
        """Set security headers on all responses (aus 01_web_app.py Zeile 186-230)"""
        # Skip für Endpoints die eigene Headers setzen (z.B. Email HTML Render)
        if g.get("skip_security_headers", False):
            return response
        
        # Security Headers für ALLE Responses - Defense-in-Depth
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        # CSP nur bei erfolgreichen Responses (< 400)
        if response.status_code < 400:
            nonce = getattr(g, 'csp_nonce', '')
            # CSP identisch zu 01_web_app.py Zeile 212-222
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
            response.headers['Content-Security-Policy'] = csp
        
        return response
    
    @app.before_request
    def check_dek_in_session():
        """Check for DEK in session (aus 01_web_app.py Zeile 265-314)
        
        Zero-Knowledge Encryption: User muss nach Session-Expire
        erneut Passwort eingeben um Master-Key zu regenerieren.
        
        Mandatory 2FA: User ohne aktivierte 2FA werden zu Setup weitergeleitet.
        """
        # Skip für bestimmte Endpoints
        if request.endpoint in [
            "auth.login",
            "auth.register", 
            "auth.logout",
            "static",
            "auth.verify_2fa",
            "auth.setup_2fa",
            # Legacy-Aliase auch skippen
            "login",
            "register",
            "logout",
            "verify_2fa",
            "setup_2fa",
        ]:
            return None

        # DEK-Check (Zero-Knowledge Encryption)
        if current_user.is_authenticated and not session.get("master_key"):
            logger.warning(
                f"⚠️ User {current_user.id} authenticated aber DEK in Session fehlt - Reauth erforderlich"
            )
            session.clear()
            logout_user()
            flash("Sitzung abgelaufen - bitte erneut anmelden", "warning")
            return redirect(url_for("auth.login"))

        # Mandatory 2FA Check (Phase 8c Security Hardening)
        if current_user.is_authenticated:
            models = importlib.import_module(".02_models", "src")
            db = SessionLocal()
            try:
                user = db.query(models.User).filter_by(id=current_user.id).first()
                if user and not user.totp_enabled:
                    logger.warning(
                        f"⚠️ User {current_user.id} hat 2FA nicht aktiviert - Redirect zu Setup"
                    )
                    flash("2FA ist Pflicht - bitte jetzt einrichten", "warning")
                    return redirect(url_for("auth.setup_2fa"))
            finally:
                db.close()

        return None
    
    # =========================================================================
    # ERROR HANDLERS (aus 01_web_app.py Zeile 8491-8504)
    # =========================================================================
    
    @app.errorhandler(404)
    def not_found(e):
        # Einfaches HTML ohne Template (404.html existiert nicht)
        html = '''<!DOCTYPE html>
        <html><head><title>404 - Nicht gefunden</title>
        <style>body{font-family:sans-serif;text-align:center;padding:50px;}
        h1{color:#dc3545;}a{color:#007bff;}</style></head>
        <body><h1>404 - Seite nicht gefunden</h1>
        <p>Die angeforderte Seite existiert nicht.</p>
        <a href="/">Zurück zur Startseite</a></body></html>'''
        return html, 404
    
    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Server error: {e}")
        html = '''<!DOCTYPE html>
        <html><head><title>500 - Server-Fehler</title>
        <style>body{font-family:sans-serif;text-align:center;padding:50px;}
        h1{color:#dc3545;}a{color:#007bff;}</style></head>
        <body><h1>500 - Interner Server-Fehler</h1>
        <p>Ein unerwarteter Fehler ist aufgetreten.</p>
        <a href="/">Zurück zur Startseite</a></body></html>'''
        return html, 500
    
    # =========================================================================
    # REGISTER BLUEPRINTS
    # =========================================================================
    
    from .blueprints import (
        auth_bp, emails_bp, email_actions_bp, accounts_bp,
        tags_bp, api_bp, rules_bp, training_bp, admin_bp
    )
    from .thread_api import thread_api
    
    app.register_blueprint(auth_bp)                      # Kein Prefix
    app.register_blueprint(emails_bp)                    # Kein Prefix
    app.register_blueprint(email_actions_bp)             # Kein Prefix
    app.register_blueprint(accounts_bp)                  # Kein Prefix
    app.register_blueprint(tags_bp)                      # Kein Prefix
    app.register_blueprint(api_bp, url_prefix="/api")    # MIT Prefix!
    app.register_blueprint(rules_bp)                     # Kein Prefix
    app.register_blueprint(training_bp)                  # Kein Prefix
    app.register_blueprint(admin_bp)                     # Kein Prefix
    app.register_blueprint(thread_api)                   # Thread API
    
    # =========================================================================
    # TEMPLATE CONTEXT PROCESSORS
    # =========================================================================
    
    @app.context_processor
    def inject_csp_nonce():
        """Make CSP nonce available in all templates"""
        return dict(csp_nonce=getattr(g, 'csp_nonce', ''))
    
    @app.context_processor
    def inject_current_user_model():
        """Make current user model available in templates"""
        if current_user.is_authenticated:
            models = importlib.import_module(".02_models", "src")
            db = SessionLocal()
            try:
                user = db.query(models.User).filter_by(id=current_user.id).first()
                return dict(current_user_model=user)
            finally:
                db.close()
        return dict(current_user_model=None)
    
    # =========================================================================
    # BACKWARDS-COMPATIBLE ENDPOINT ALIASE
    # Ermöglicht: url_for('login') statt url_for('auth.login')
    # Templates müssen NICHT geändert werden vor dem Schalter!
    # =========================================================================
    
    _register_endpoint_aliases(app)
    
    logger.info("✅ Flask App mit Blueprint-Architektur initialisiert")
    
    return app


def _register_endpoint_aliases(app):
    """Register backwards-compatible endpoint aliases.
    
    This allows old templates using url_for('login') to work
    with the new Blueprint architecture using url_for('auth.login').
    
    Total: 11 unique endpoints need aliases (78 url_for() calls use them).
    """
    
    # ┌─────────────────────────────────────────────────────────────────────┐
    # │ ALIAS-TABELLE: Alt → Neu                                            │
    # │ Anzahl = wie oft url_for('...') im Code/Templates vorkommt          │
    # └─────────────────────────────────────────────────────────────────────┘
    
    aliases = {
        # AUTH Blueprint (35 Aufrufe)
        'login': 'auth.login',                    # 29× in Python + Templates
        'setup_2fa': 'auth.setup_2fa',            # 3×
        'verify_2fa': 'auth.verify_2fa',          # 1×
        'index': 'auth.index',                    # 2×
        
        # EMAILS Blueprint (11 Aufrufe)
        'dashboard': 'emails.dashboard',          # 6×
        'list_view': 'emails.list_view',          # 5×
        
        # ACCOUNTS Blueprint (32 Aufrufe)
        'settings': 'accounts.settings',          # 26×
        'whitelist': 'accounts.whitelist',        # 3×
        'ki_prio': 'accounts.ki_prio',            # 1×
        'mail_fetch_config': 'accounts.mail_fetch_config',  # 1×
        'google_oauth_callback': 'accounts.google_oauth_callback',  # 1×
    }
    
    # Registriere alle Aliase
    registered = 0
    for old_name, new_name in aliases.items():
        if new_name in app.view_functions:
            app.view_functions[old_name] = app.view_functions[new_name]
            registered += 1
        else:
            logger.warning(f"⚠️ Alias '{old_name}' → '{new_name}': Endpoint nicht gefunden!")
    
    logger.info(f"✅ {registered}/{len(aliases)} Endpoint-Aliase registriert (Backwards-Compatibility)")


# =============================================================================
# SERVER START FUNCTION (identisch zu 01_web_app.py Zeile 9308-9408)
# =============================================================================

def start_server(host="0.0.0.0", port=5000, debug=False, use_https=False):
    """Startet den Flask-Server mit optionalem HTTPS-Support.
    
    Args:
        host: Server Host (default: 0.0.0.0)
        port: Server Port (default: 5000)
        debug: Debug-Modus (default: False)
        use_https: HTTPS aktivieren (default: False)
                   - True: Self-signed Certificate (adhoc) + HTTP Redirector
                   - ('cert.pem', 'key.pem'): Eigene Zertifikate
    """
    import threading
    
    # Flask-Talisman für HTTPS Security Headers
    try:
        from flask_talisman import Talisman
        TALISMAN_AVAILABLE = True
    except ImportError:
        TALISMAN_AVAILABLE = False
    
    _app = create_app()
    
    if use_https:
        # Enable Secure Cookie Flag for HTTPS mode
        _app.config["SESSION_COOKIE_SECURE"] = True
        logger.info("🔒 SESSION_COOKIE_SECURE=True (HTTPS-Modus)")
        
        # Dual-Port Setup: HTTP Redirector + HTTPS Server
        https_port = port + 1  # z.B. 5004 für HTTPS wenn port=5003
        
        # 1. HTTP Redirector auf port
        def run_http_redirector():
            """Einfacher HTTP→HTTPS Redirector"""
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
            
            print(f"🔀 HTTP Redirector läuft auf http://{host}:{port} → https://localhost:{https_port}")
            # Nutze werkzeug's make_server statt wsgiref (unterstützt threaded)
            redirector_server = werkzeug_make_server(host, port, redirector, threaded=True)
            redirector_server.serve_forever()
        
        # Starte HTTP Redirector in separatem Thread
        redirector_thread = threading.Thread(target=run_http_redirector, daemon=True)
        redirector_thread.start()
        
        # 2. HTTPS Server auf port + 1
        ssl_context = "adhoc" if use_https is True else use_https
        logger.info(f"🔒 HTTPS aktiviert (Port {https_port}, Self-signed Certificate)")
        
        # Flask-Talisman für zusätzliche Security Headers
        if TALISMAN_AVAILABLE and os.getenv("FORCE_HTTPS", "false").lower() == "true":
            csp = {
                "default-src": "'self'",
                "script-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
                "style-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
                "img-src": "'self' data:",
                "font-src": ["'self'", "https://cdn.jsdelivr.net"],
                "connect-src": "'self'",
                "frame-src": "'none'",
                "object-src": "'none'",
            }
            Talisman(
                _app,
                force_https=False,
                strict_transport_security=True,
                strict_transport_security_max_age=31536000,
                content_security_policy=csp,
            )
            logger.info("🔒 Flask-Talisman aktiviert - Security Headers + CSP")
        
        print(f"🌐 Blueprint-Dashboard läuft auf https://{host}:{https_port}")
        print(f"💡 Tipp: Browser öffnet http://localhost:{port} → Auto-Redirect zu HTTPS")
        _app.run(host=host, port=https_port, debug=debug, ssl_context=ssl_context)
    
    else:
        # Standard HTTP-Modus (ohne HTTPS)
        print(f"🌐 Blueprint-Dashboard läuft auf http://{host}:{port}")
        _app.run(host=host, port=port, debug=debug)
