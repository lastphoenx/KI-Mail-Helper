# 🏭 App Factory Pattern Refactoring - Konkretes Konzept

**Zweck:** Refaktoriere `src/01_web_app.py` (8.8k Zeilen, 79 Routes) in modulare Blueprints  
**Aufwand:** 8-12 Stunden  
**Nutzen:** Testability, Maintainability, Code Organization  
**Status:** PLAN (nicht implementiert)

---

## 📊 Aktuelle Situation

### Problem: Monolithische Struktur
```
src/01_web_app.py (3.5k Zeilen)
├── Config (SECRET_KEY, Session, CSRF, Security Headers)
├── Extensions (LoginManager, Limiter, CSRF, Talisman)
├── Helper-Funktionen (decrypt_raw_email, ensure_master_key, etc.)
├── 79 Routes vermischt:
│   ├── Auth-Routes (login, register, 2fa, logout)
│   ├── Email-Routes (list, detail, mark_done, etc.)
│   ├── Settings-Routes (settings, change-password, add-account)
│   ├── Tag-Routes (tags, api_create_tag, api_delete_tag)
│   ├── API-Routes (semantic_search, embeddings_stats)
│   ├── Admin-Routes (retrain, training_stats)
│   └── ...
└── Error-Handler (404, 500, etc.)
```

### Konsequenzen
- ❌ Nicht testbar (global app object)
- ❌ Unmöglich zu navigieren (79 Routes in einer Datei)
- ❌ Schwer Features zu isolieren
- ❌ Code-Duplication (z.B. decrypt-Logik wiederholt)
- ❌ Keine klaren Schnittstellen zwischen Features

---

## 🎯 Zielstruktur

### Nach Refactoring
```
src/
├── app_factory.py              # NEW - Factory-Funktion
├── config.py                   # NEW - Config-Klassen
├── extensions.py               # NEW - Extensions initialisieren
├── helpers/                    # NEW - Shared Utilities
│   ├── __init__.py
│   ├── crypto.py               # decrypt_raw_email, decrypt_email_subject, etc.
│   ├── decorators.py           # ensure_master_key, require_dek
│   └── response.py             # JSON-Response Formatter
├── blueprints/                 # NEW - Modularisierte Routes
│   ├── __init__.py
│   ├── auth.py                 # login, register, 2fa, logout, change_password
│   ├── emails.py               # list, detail, mark_done, undo, threads
│   ├── email_actions.py        # reprocess, optimize, correct, flags
│   ├── tags.py                 # tags_view + api_* tag routes
│   ├── search.py               # semantic_search, find_similar, embeddings
│   ├── accounts.py             # settings, add_account, delete_account
│   ├── training.py             # retrain, get_training_stats
│   └── api.py                  # General API endpoints
├── 00_main.py                  # Entry Point (nutzt create_app)
├── 01_web_app.py               # OLD - KEEP für Fallback (aber nicht nutzen)
├── 02_models.py                # Unchanged
├── services/                   # Unchanged (tag_manager, sender_patterns, etc.)
└── ...
```

---

## 🔧 Step-by-Step Implementation

### PHASE 1: Setup (0.5-1 Stunde)

#### Schritt 1.1: Erstelle `src/config.py`
**Ziel:** Zentrale Config-Verwaltung

```python
# src/config.py
"""Configuration classes for different environments"""

import os
from datetime import timedelta


class Config:
    """Base configuration (shared by all environments)"""
    
    # Flask
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError(
            "FLASK_SECRET_KEY environment variable must be set!\n"
            "Development: Add to .env file\n"
            "Production: Set in systemd service or /etc/environment"
        )
    
    # Session
    SESSION_TYPE = "filesystem"
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_KEY_PREFIX = "mail_helper_"
    SESSION_ID_LENGTH = 32
    
    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    
    # Reverse Proxy
    BEHIND_REVERSE_PROXY = os.getenv("BEHIND_REVERSE_PROXY", "false").lower() == "true"


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)


class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False  # Einfacheres Testing ohne CSRF
```

#### Schritt 1.2: Erstelle `src/extensions.py`
**Ziel:** Extensions initialisieren (können später injiziert werden)

```python
# src/extensions.py
"""Flask extensions - initialized without app (lazy initialization)"""

from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_session import Session
from flask_talisman import Talisman

# Lazy-initialize (wird später mit app initialisiert)
login_manager = LoginManager()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
)
csrf = CSRFProtect()
session_manager = Session()
talisman = Talisman()


def init_extensions(app):
    """Initialize all extensions with app context"""
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)
    session_manager.init_app(app)
    
    try:
        talisman.init_app(app)
    except ImportError:
        pass
    
    # Configure login_manager
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Bitte einloggen"
```

#### Schritt 1.3: Erstelle `src/helpers/__init__.py`

```python
# src/helpers/__init__.py
"""Helper functions and decorators"""

from .crypto import decrypt_raw_email, decrypt_email_subject, decrypt_email_sender
from .decorators import ensure_master_key_in_session, require_dek
from .response import success_response, error_response

__all__ = [
    "decrypt_raw_email",
    "decrypt_email_subject",
    "decrypt_email_sender",
    "ensure_master_key_in_session",
    "require_dek",
    "success_response",
    "error_response",
]
```

---

### PHASE 2: Core App Factory (1-1.5 Stunden)

#### Schritt 2.1: Erstelle `src/app_factory.py`
**Ziel:** Zentrale Factory-Funktion

```python
# src/app_factory.py
"""App factory for creating Flask application instances"""

import os
import logging
from flask import Flask, g, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

import importlib
from config import DevelopmentConfig, ProductionConfig, TestingConfig
from extensions import init_extensions
from helpers.decorators import setup_security_headers

logger = logging.getLogger(__name__)


def create_app(config_name: str = "development") -> Flask:
    """
    Factory function to create Flask app with configuration
    
    Args:
        config_name: "development", "production", or "testing"
    
    Returns:
        Configured Flask application instance
    """
    
    # 1. Create Flask app
    app = Flask(__name__, template_folder="../templates")
    
    # 2. Load configuration
    if config_name == "production":
        app.config.from_object(ProductionConfig)
    elif config_name == "testing":
        app.config.from_object(TestingConfig)
    else:
        app.config.from_object(DevelopmentConfig)
    
    # 3. Validate environment (z.B. FLASK_SECRET_KEY)
    env_validator = importlib.import_module(".00_env_validator", "src")
    env_validator.validate_environment()
    
    # 4. Initialize extensions (db, auth, limiter, etc.)
    init_extensions(app)
    
    # 5. Setup Reverse Proxy Support
    if app.config.get("BEHIND_REVERSE_PROXY"):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_prefix=1,
        )
        logger.info("🔄 ProxyFix aktiviert - App läuft hinter Reverse Proxy")
    
    # 6. Register hooks
    register_hooks(app)
    
    # 7. Register blueprints
    register_blueprints(app)
    
    # 8. Register error handlers
    register_error_handlers(app)
    
    logger.info(f"✅ Flask App created with config: {config_name}")
    return app


def register_hooks(app: Flask):
    """Register before_request and after_request hooks"""
    
    import secrets
    
    @app.before_request
    def generate_csp_nonce():
        """Generate CSP nonce for inline scripts"""
        g.csp_nonce = secrets.token_urlsafe(16)
    
    @app.before_request
    def csrf_protect_ajax():
        """Validate CSRF tokens for AJAX requests"""
        from flask import request, jsonify
        from flask_wtf.csrf import validate_csrf
        from werkzeug.exceptions import BadRequest
        
        if request.method in ["POST", "PUT", "DELETE"] and request.is_json:
            token = request.headers.get("X-CSRFToken")
            if not token:
                logger.warning(
                    "⚠️ CSRF token missing in AJAX request from %s", 
                    request.remote_addr
                )
                return jsonify({"error": "CSRF token missing"}), 403
            try:
                validate_csrf(token)
            except BadRequest:
                logger.warning(
                    "⚠️ CSRF token invalid in AJAX request from %s", 
                    request.remote_addr
                )
                return jsonify({"error": "CSRF token invalid"}), 403
    
    @app.after_request
    def set_security_headers(response):
        """Set CSP and security headers for all responses"""
        from flask import g
        
        # Skip for email rendering endpoint
        if g.get("skip_security_headers", False):
            return response
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # ... weitere Headers
        
        return response
    
    @app.context_processor
    def inject_globals():
        """Inject csrf_token and csp_nonce in all templates"""
        from flask_wtf.csrf import generate_csrf
        return dict(
            csrf_token=generate_csrf,
            csp_nonce=lambda: g.get("csp_nonce", ""),
        )


def register_blueprints(app: Flask):
    """Register all blueprints (modularized routes)"""
    
    # Import blueprints
    from blueprints.auth import auth_bp
    from blueprints.emails import emails_bp
    from blueprints.email_actions import email_actions_bp
    from blueprints.tags import tags_bp
    from blueprints.search import search_bp
    from blueprints.accounts import accounts_bp
    from blueprints.training import training_bp
    from blueprints.api import api_bp
    
    # Register with URL prefixes
    app.register_blueprint(auth_bp)
    app.register_blueprint(emails_bp)
    app.register_blueprint(email_actions_bp)
    app.register_blueprint(tags_bp, url_prefix="/api")
    app.register_blueprint(search_bp, url_prefix="/api")
    app.register_blueprint(accounts_bp)
    app.register_blueprint(training_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    
    logger.info("✅ All blueprints registered")


def register_error_handlers(app: Flask):
    """Register global error handlers"""
    
    @app.errorhandler(404)
    def not_found(error):
        return render_template("404.html"), 404
    
    @app.errorhandler(500)
    def server_error(error):
        logger.error(f"❌ Server error: {error}", exc_info=True)
        return render_template("500.html"), 500
    
    logger.info("✅ Error handlers registered")
```

#### Schritt 2.2: Aktualisiere `src/00_main.py`
**Ziel:** Nutze die neue Factory

```python
# src/00_main.py (UPDATE)
"""Mail Helper - Entry Point"""

import os
import sys
import logging
from argparse import ArgumentParser

# Import the factory
sys.path.insert(0, os.path.dirname(__file__))
from app_factory import create_app

logger = logging.getLogger(__name__)


def main():
    parser = ArgumentParser(description="KI-Mail-Helper Server")
    parser.add_argument(
        "--serve", 
        action="store_true", 
        help="Start web server"
    )
    parser.add_argument(
        "--https", 
        action="store_true", 
        help="Use HTTPS (self-signed cert)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=5000, 
        help="Port to run on"
    )
    parser.add_argument(
        "--env", 
        default="development", 
        choices=["development", "production", "testing"],
        help="Environment"
    )
    args = parser.parse_args()
    
    # Create app with factory
    app = create_app(config_name=args.env)
    
    if args.serve:
        if args.https:
            # HTTPS mit self-signed cert
            import ssl
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            # ... cert loading
            app.run(
                host="0.0.0.0",
                port=args.port,
                ssl_context=ssl_context,
                debug=False,
            )
        else:
            app.run(
                host="0.0.0.0",
                port=args.port,
                debug=False,
            )
    else:
        logger.info("App created. Use --serve to start server.")


if __name__ == "__main__":
    main()
```

---

### PHASE 3: Extract Blueprints (4-6 Stunden)

#### Schritt 3.1: Erstelle `src/blueprints/auth.py`
**Routes from 01_web_app.py:**
- `/` (index)
- `/login` (411-520)
- `/register` (521-640)
- `/2fa/verify` (641-712)
- `/logout` (713-732)
- `/settings/change-password` (in settings route)

```python
# src/blueprints/auth.py
"""Authentication routes: login, register, 2FA, logout"""

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    session,
    flash,
    current_app,
)
from flask_login import login_user, logout_user, login_required, current_user
import logging
import importlib

from helpers.decorators import ensure_master_key_in_session

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

# Lazy load modules (wie in 01_web_app.py)
models = None
auth_module = None
encryption = None

def _load_modules():
    global models, auth_module, encryption
    if models is None:
        models = importlib.import_module(".02_models", "src")
        auth_module = importlib.import_module(".07_auth", "src")
        encryption = importlib.import_module(".08_encryption", "src")


@auth_bp.route("/")
def index():
    """Landing page"""
    _load_modules()
    if current_user.is_authenticated:
        return redirect(url_for("emails.dashboard"))
    return render_template("index.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """User login with 2FA verification"""
    _load_modules()
    
    if request.method == "GET":
        if current_user.is_authenticated:
            return redirect(url_for("emails.dashboard"))
        return render_template("login.html")
    
    # POST: Process login
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    
    if not username or not password:
        flash("Username und Passwort erforderlich", "danger")
        return render_template("login.html"), 400
    
    # Database lookup
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(
        f"sqlite:///{current_app.config.get('DATABASE_PATH', 'emails.db')}",
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # Rate limiting & Account Lockout checks
        user = db.query(models.User).filter_by(username=username).first()
        
        if user and user.is_locked_out():
            flash("Account gesperrt. Versuche es später", "danger")
            logger.info(f"SECURITY[ACCOUNT_LOCKED] User {user.id} locked out")
            return render_template("login.html"), 429
        
        # Verify password
        if not user or not user.check_password(password):
            if user:
                user.record_failed_login(db)
            flash("Ungültige Credentials", "danger")
            return render_template("login.html"), 401
        
        # Reset failed login attempts
        if user:
            user.reset_failed_logins(db)
        
        # Redirect to 2FA verification
        session["pending_user_id"] = user.id
        return redirect(url_for("auth.verify_2fa"))
    
    finally:
        db.close()


@auth_bp.route("/2fa/verify", methods=["GET", "POST"])
def verify_2fa():
    """2FA verification (TOTP)"""
    _load_modules()
    
    pending_user_id = session.get("pending_user_id")
    if not pending_user_id:
        return redirect(url_for("auth.login"))
    
    # ... 2FA logic
    # (Copy from 01_web_app.py lines 641-712)


@auth_bp.route("/logout")
@login_required
def logout():
    """User logout"""
    user_id = current_user.id
    logout_user()
    logger.info(f"User {user_id} logged out")
    flash("Logout erfolgreich", "success")
    return redirect(url_for("auth.login"))
```

**Hinweis:** Ich zeige nur das Skeleton – die vollständige Implementierung würde den Content aus `01_web_app.py:411-732` kopieren.

---

#### Schritt 3.2: Erstelle `src/blueprints/emails.py`
**Routes from 01_web_app.py:**
- `/dashboard` (734-878)
- `/list` (879-1200)
- `/threads` (1201-1217)
- `/email/<id>` (1218-1315)

```python
# src/blueprints/emails.py
"""Email viewing and listing routes"""

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
import logging

from helpers.decorators import ensure_master_key_in_session

logger = logging.getLogger(__name__)

emails_bp = Blueprint("emails", __name__)


@emails_bp.route("/dashboard")
@login_required
def dashboard():
    """3×3 Priority Matrix Dashboard"""
    if not ensure_master_key_in_session():
        return redirect(url_for("auth.login"))
    
    # Copy implementation from 01_web_app.py:734-878
    ...


@emails_bp.route("/list")
@login_required
def list_view():
    """List view with filters"""
    if not ensure_master_key_in_session():
        return redirect(url_for("auth.login"))
    
    # Copy implementation from 01_web_app.py:879-1200
    ...


@emails_bp.route("/threads")
@login_required
def threads_view():
    """Thread/Conversation view"""
    if not ensure_master_key_in_session():
        return redirect(url_for("auth.login"))
    
    # Copy implementation from 01_web_app.py:1201-1217
    ...


@emails_bp.route("/email/<int:email_id>")
@login_required
def email_detail(email_id):
    """Email detail view"""
    if not ensure_master_key_in_session():
        return redirect(url_for("auth.login"))
    
    # Copy implementation from 01_web_app.py:1218-1315
    ...
```

---

#### Schritt 3.3: Erstelle weitere Blueprints (ähnlich)

**`src/blueprints/email_actions.py`** – Mark done, undo, reprocess, optimize, correct
```python
# Routes: /email/<id>/done, /email/<id>/undo, /email/<id>/reprocess, etc.
# Copy from 01_web_app.py:1419-1806
```

**`src/blueprints/tags.py`** – Tag management
```python
# Routes: /tags, /api/tags, /api/tags/<id>, /api/emails/<id>/tags, etc.
# Copy from 01_web_app.py:2249-2700
```

**`src/blueprints/search.py`** – Semantic search
```python
# Routes: /api/search/semantic, /api/emails/<id>/similar, /api/embeddings/stats
# Copy from 01_web_app.py:2700-2920
```

**`src/blueprints/accounts.py`** – Mail account management
```python
# Routes: /settings, /api/accounts, /add-account, /delete-account, etc.
# Copy from 01_web_app.py settings-related routes
```

**`src/blueprints/training.py`** – ML training
```python
# Routes: /retrain, /api/training-stats
# Copy from 01_web_app.py:1863-1968
```

**`src/blueprints/api.py`** – General API
```python
# Routes: /api/models/<provider>, /api/emails/<id>/flags, etc.
# Copy from 01_web_app.py API routes
```

---

### PHASE 4: Extract Helpers (1-2 Stunden)

#### Schritt 4.1: Erstelle `src/helpers/crypto.py`
**Ziel:** Dezentralisiere Encryption-Logik

```python
# src/helpers/crypto.py
"""Cryptography helpers - decrypt email data, credentials, etc."""

import importlib
from typing import Optional

encryption = None


def _load_encryption():
    global encryption
    if encryption is None:
        encryption = importlib.import_module(".08_encryption", "src")


def decrypt_raw_email(raw_email, master_key: str) -> dict:
    """Decrypt raw email fields (sender, subject, body)"""
    _load_encryption()
    
    try:
        return {
            "sender": encryption.EmailDataManager.decrypt_email_sender(
                raw_email.encrypted_sender, master_key
            ),
            "subject": encryption.EmailDataManager.decrypt_email_subject(
                raw_email.encrypted_subject, master_key
            ),
            "body": encryption.EmailDataManager.decrypt_email_body(
                raw_email.encrypted_body, master_key
            ),
        }
    except Exception as e:
        logger.error(f"Failed to decrypt raw email {raw_email.id}: {e}")
        return {"sender": "[Error]", "subject": "[Error]", "body": "[Error]"}


def decrypt_email_subject(encrypted_subject: str, master_key: str) -> str:
    """Decrypt email subject"""
    _load_encryption()
    return encryption.EmailDataManager.decrypt_email_subject(encrypted_subject, master_key)


def decrypt_email_sender(encrypted_sender: str, master_key: str) -> str:
    """Decrypt email sender address"""
    _load_encryption()
    return encryption.EmailDataManager.decrypt_email_sender(encrypted_sender, master_key)
```

#### Schritt 4.2: Erstelle `src/helpers/decorators.py`
**Ziel:** Custom Decorators für häufige Patterns

```python
# src/helpers/decorators.py
"""Custom decorators for routes"""

from functools import wraps
from flask import session, flash, redirect, url_for
import logging

logger = logging.getLogger(__name__)


def ensure_master_key_in_session():
    """
    Check if master_key is in Flask session.
    Returns True if valid, False otherwise.
    """
    if "master_key" not in session:
        flash("Session abgelaufen. Bitte neu einloggen.", "error")
        return False
    return True


def require_dek(f):
    """Decorator: require valid DEK in session"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not ensure_master_key_in_session():
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function
```

---

### PHASE 5: Migration & Testing (2-3 Stunden)

#### Schritt 5.1: Migrations-Checklist

**WICHTIG: Preserve Old Code**
```bash
# SCHRITT 1: Backup
cp src/01_web_app.py src/01_web_app.py.backup_20260105

# SCHRITT 2: Neue Struktur erstellen (siehe PHASE 1-4)
# - app_factory.py
# - config.py
# - extensions.py
# - helpers/*.py
# - blueprints/*.py

# SCHRITT 3: 00_main.py aktualisieren
# - nutzt create_app()
# - Tests mit verschiedenen Configs

# SCHRITT 4: 01_web_app.py NICHT löschen
# - Behalte als Fallback
# - Markiere als DEPRECATED
```

#### Schritt 5.2: Test-Strategie

**Neue Test-Struktur:**
```python
# tests/test_app_factory.py
import pytest
from src.app_factory import create_app


@pytest.fixture
def app():
    """Create app with testing config"""
    app = create_app("testing")
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    """Test client"""
    return app.test_client()


def test_app_factory_creates_app():
    """Test that app factory works"""
    app = create_app("development")
    assert app is not None
    assert app.config["DEBUG"] == True


def test_development_config():
    app = create_app("development")
    assert app.config["DEBUG"] == True


def test_production_config():
    app = create_app("production")
    assert app.config["DEBUG"] == False


def test_testing_config():
    app = create_app("testing")
    assert app.config["TESTING"] == True
    assert app.config["WTF_CSRF_ENABLED"] == False


# Blueprint Tests
def test_login_route_exists(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302  # Redirect to login


def test_auth_blueprint_registered(app):
    """Verify auth blueprint is registered"""
    assert "auth.login" in app.url_map._rules_by_endpoint
```

#### Schritt 5.3: Rollback-Plan

**Wenn Probleme auftauchen:**
```bash
# OPTION 1: Schneller Rollback (alten Code nutzen)
rm -rf src/blueprints src/app_factory.py src/config.py src/extensions.py
cp src/01_web_app.py.backup_20260105 src/01_web_app.py

# OPTION 2: Parallel Deployment (neue Factory + alte App)
# In 00_main.py:
# if USE_FACTORY:
#     app = create_app()
# else:
#     from src.01_web_app import app  # OLD

# OPTION 3: Feature Flags (schrittweise Migration)
# Route nur neue Blueprint wenn Feature-Flag aktiv
```

---

## 📋 Implementation Checkliste

### BEFORE STARTING
- [ ] Backup erstellen: `cp src/01_web_app.py src/01_web_app.py.backup_DATE`
- [ ] Git-Branch erstellen: `git checkout -b refactor/app-factory`
- [ ] Current Tests müssen grün sein: `pytest tests/ -v`

### PHASE 1: Setup
- [ ] `src/config.py` erstellen
- [ ] `src/extensions.py` erstellen
- [ ] `src/helpers/__init__.py` erstellen
- [ ] Tests: `test_config.py`, `test_extensions.py`

### PHASE 2: App Factory
- [ ] `src/app_factory.py` erstellen
- [ ] `src/00_main.py` aktualisieren (nutzt create_app)
- [ ] Server startet mit `python src/00_main.py --serve`
- [ ] Tests: `test_app_factory.py`

### PHASE 3: Blueprints
- [ ] `src/blueprints/auth.py` erstellen (75 Zeilen → 300 Zeilen)
- [ ] `src/blueprints/emails.py` erstellen
- [ ] `src/blueprints/email_actions.py` erstellen
- [ ] `src/blueprints/tags.py` erstellen
- [ ] `src/blueprints/search.py` erstellen
- [ ] `src/blueprints/accounts.py` erstellen
- [ ] `src/blueprints/training.py` erstellen
- [ ] `src/blueprints/api.py` erstellen
- [ ] Tests für jedes Blueprint: `test_blueprints_*.py`

### PHASE 4: Helpers
- [ ] `src/helpers/crypto.py` erstellen
- [ ] `src/helpers/decorators.py` erstellen
- [ ] `src/helpers/response.py` erstellen (optional)
- [ ] Tests: `test_helpers_*.py`

### PHASE 5: Testing & Validation
- [ ] Alle Unit-Tests grün: `pytest tests/ -v`
- [ ] Server startet: `python src/00_main.py --serve --https`
- [ ] UI-Test: Login, Email-List, Detail, etc. (manuell)
- [ ] Load-Test (optional): `ab -n 100 http://localhost:5000/`

### FINALIZATION
- [ ] 01_web_app.py mit Deprecation-Warning kommentieren
- [ ] README.md aktualisieren: "New: App Factory Pattern"
- [ ] CHANGELOG.md: "Phase 16: Refactoring"
- [ ] PR/Commit: "Refactor: Extract blueprints with App Factory"
- [ ] Tag: `v1.1.0-refactoring`

---

## 🎯 Expected Outcomes

### Vorher
```
src/01_web_app.py
├── 3,500 lines
├── 79 routes
├── 0 tests
├── unmaintainable
└── hard to navigate
```

### Nachher
```
src/
├── app_factory.py (150 lines)          ← New
├── config.py (100 lines)               ← New
├── extensions.py (50 lines)            ← New
├── helpers/crypto.py (80 lines)        ← New
├── helpers/decorators.py (60 lines)    ← New
├── blueprints/auth.py (300 lines)      ← From 01_web_app.py:411-732
├── blueprints/emails.py (250 lines)    ← From 01_web_app.py:734-1315
├── blueprints/email_actions.py (200 lines)
├── blueprints/tags.py (180 lines)
├── blueprints/search.py (150 lines)
├── blueprints/accounts.py (200 lines)
├── blueprints/training.py (100 lines)
├── blueprints/api.py (200 lines)
├── 01_web_app.py (DEPRECATED - fallback only)
├── tests/test_app_factory.py (new)     ← Testability!
├── tests/test_blueprints_auth.py (new)
└── tests/test_blueprints_emails.py (new)

BENEFITS:
✅ Each file ~100-300 lines (readable)
✅ Routes organized by feature
✅ Easy to add/modify features
✅ Testable (each blueprint separately)
✅ Clear dependencies
```

---

## 📊 Effort & Timeline

| Phase | Task | Effort | Timeline |
|-------|------|--------|----------|
| 1 | Setup (config, extensions, helpers) | 1h | Tag 1 Morning |
| 2 | App Factory | 1.5h | Tag 1 Afternoon |
| 3 | Blueprints (8 files × 30min) | 4h | Tag 2 |
| 4 | Helpers extraction | 1.5h | Tag 2 Late |
| 5 | Testing & Validation | 1.5h | Tag 3 |
| **TOTAL** | **All Phases** | **9.5h** | **~1.5 days** |

---

## 🚨 Risk & Mitigation

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| Routes don't work after split | Low | Keep 01_web_app.py as fallback |
| Session/Auth issues | Low | Test every login flow |
| Import errors | Medium | Use explicit imports, test imports early |
| Performance regression | Very Low | Use same templates, same DB |
| CI/CD breaks | Low | Run full test suite before merge |

---

## 🎓 Additional Resources

**Flask App Factory Pattern:**
- https://flask.palletsprojects.com/patterns/appfactories/

**Blueprints Best Practices:**
- https://flask.palletsprojects.com/blueprints/

**Testing with Factory:**
- https://flask.palletsprojects.com/testing/

---

## 📝 Summary

Diese Refaktorierung:
1. **Macht Code testbar** – Jedes Blueprint hat seine Tests
2. **Verbessert Lesbarkeit** – 79 Routes in 8 Features aufgeteilt
3. **Reduziert Komplexität** – Zyklomatische Komplexität pro Datei sinkt
4. **Ermöglicht Parallelisierung** – Verschiedene Features können unabhängig entwickelt werden
5. **Ist reversibel** – 01_web_app.py bleibt als Fallback

**Recommendation:** Implementiere schrittweise (Phase 1 → Phase 2 → ... → Phase 5) mit Tests nach jeder Phase.
