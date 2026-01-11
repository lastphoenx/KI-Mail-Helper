# BLUEPRINT_STRUCTURE.md

**Erstellt:** 11. Januar 2026  
**Zweck:** Detaillierte Struktur jedes Blueprints

---

## 📂 DATEISTRUKTUR

```
src/
├── app_factory.py           # Flask App Factory
├── blueprints/
│   ├── __init__.py          # Blueprint-Registrierung
│   ├── auth.py              # 7 Routes
│   ├── emails.py            # 5 Routes
│   ├── email_actions.py     # 11 Routes
│   ├── accounts.py          # 22 Routes
│   ├── tags.py              # 2 Routes
│   ├── api.py               # 64 Routes (Prefix: /api)
│   ├── rules.py             # 10 Routes
│   ├── training.py          # 1 Route
│   └── admin.py             # 1 Route
└── helpers/
    ├── __init__.py
    ├── database.py
    ├── validation.py
    └── responses.py
```

---

## 🔧 app_factory.py

```python
# src/app_factory.py
"""Flask Application Factory for Blueprint-based architecture."""

from flask import Flask, render_template, request, g, session
from flask_login import LoginManager, current_user
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

# Globale Variablen (shared zwischen Factory und Blueprints)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///emails.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def create_app(config_name="production"):
    """Create and configure the Flask application."""
    
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    
    # Configuration
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["SESSION_FILE_DIR"] = "flask_session"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    
    # Initialize CSRF Protection
    csrf = CSRFProtect(app)
    
    # Initialize Session
    Session(app)
    
    # Initialize Login Manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # Blueprint-qualified!
    
    # User Loader (aus 01_web_app.py Zeile 387-397)
    @login_manager.user_loader
    def load_user(user_id):
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
    
    # =========================================================================
    # BEFORE/AFTER REQUEST HOOKS (aus 01_web_app.py Zeile 154-230, 265-314)
    # =========================================================================
    
    @app.before_request
    def generate_csp_nonce():
        """Generate CSP nonce for each request (Zeile 155-159)"""
        g.csp_nonce = secrets.token_urlsafe(16)
    
    @app.before_request
    def csrf_protect_ajax():
        """CSRF protection for AJAX requests (Zeile 166-184)"""
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
        """Set security headers on all responses (Zeile 186-230)"""
        nonce = getattr(g, 'csp_nonce', '')
        response.headers['Content-Security-Policy'] = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            f"style-src 'self' 'unsafe-inline'; "
            f"img-src 'self' data: https:; "
            f"font-src 'self' data:; "
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'"
        )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
    
    @app.before_request
    def check_dek_in_session():
        """Check for DEK in session (Zeile 265-314)"""
        # Skip für Login/Logout/Static-Routes + 2FA-Setup
        if request.endpoint in [
            "auth.login",
            "auth.register",
            "auth.logout",
            "static",
            "auth.verify_2fa",
            "auth.setup_2fa",
        ]:
            return None

        # DEK-Check (Zero-Knowledge)
        if current_user.is_authenticated and not session.get("master_key"):
            logger.warning(
                f"⚠️ User {current_user.id} authenticated aber DEK in Session fehlt - Reauth erforderlich"
            )
            session.clear()
            from flask_login import logout_user
            logout_user()
            from flask import flash, redirect, url_for
            flash("Sitzung abgelaufen - bitte erneut anmelden", "warning")
            return redirect(url_for("auth.login"))

        # Mandatory 2FA Check (Phase 8c Security Hardening)
        if current_user.is_authenticated:
            # User-Model laden für totp_enabled Check
            db = SessionLocal()
            try:
                models = importlib.import_module(".02_models", "src")
                user = db.query(models.User).filter_by(id=current_user.id).first()
                if user and not user.totp_enabled:
                    logger.warning(
                        f"⚠️ User {current_user.id} hat 2FA nicht aktiviert - Redirect zu Setup"
                    )
                    from flask import flash, redirect, url_for
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
        return render_template("404.html"), 404
    
    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Server error: {e}")
        return render_template("500.html"), 500
    
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
        return dict(csp_nonce=getattr(g, 'csp_nonce', ''))
    
    return app
```

---

## 📦 blueprints/__init__.py

```python
# src/blueprints/__init__.py
"""Blueprint registration module."""

from .auth import auth_bp
from .emails import emails_bp
from .email_actions import email_actions_bp
from .accounts import accounts_bp
from .tags import tags_bp
from .api import api_bp
from .rules import rules_bp
from .training import training_bp
from .admin import admin_bp

__all__ = [
    "auth_bp",
    "emails_bp", 
    "email_actions_bp",
    "accounts_bp",
    "tags_bp",
    "api_bp",
    "rules_bp",
    "training_bp",
    "admin_bp",
]
```

---

## 🔐 auth.py (7 Routes)

```python
# src/blueprints/auth.py
"""Authentication Blueprint - Login, Register, 2FA, Logout."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
import importlib

from src.helpers import get_db_session, get_current_user_model

auth_bp = Blueprint("auth", __name__)

# Lazy imports
models = None
encryption = None
auth_utils = None

def _get_models():
    global models
    if models is None:
        models = importlib.import_module(".02_models", "src")
    return models

def _get_encryption():
    global encryption
    if encryption is None:
        encryption = importlib.import_module(".08_encryption", "src")
    return encryption


# Route 1: / (Zeile 647-653)
@auth_bp.route("/")
def index():
    # EXAKT aus 01_web_app.py kopieren!
    if current_user.is_authenticated:
        return redirect(url_for("emails.dashboard"))  # Blueprint-qualified!
    return redirect(url_for("auth.login"))


# Route 2: /login (Zeile 655-763)
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # EXAKT aus 01_web_app.py Zeile 657-763 kopieren!
    pass


# Route 3: /register (Zeile 765-883)
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    # EXAKT aus 01_web_app.py Zeile 766-883 kopieren!
    pass


# Route 4: /2fa/verify (Zeile 885-955)
@auth_bp.route("/2fa/verify", methods=["GET", "POST"])
def verify_2fa():
    # EXAKT aus 01_web_app.py Zeile 887-955 kopieren!
    pass


# Route 5: /logout (Zeile 957-976)
@auth_bp.route("/logout")
@login_required
def logout():
    # EXAKT aus 01_web_app.py Zeile 959-976 kopieren!
    pass


# Route 90: /settings/2fa/setup (Zeile 6497-6548)
@auth_bp.route("/settings/2fa/setup", methods=["GET", "POST"])
@login_required
def setup_2fa():
    # EXAKT aus 01_web_app.py Zeile 6499-6548 kopieren!
    pass


# Route 91: /settings/2fa/recovery-codes/regenerate (Zeile 6550-6581)
@auth_bp.route("/settings/2fa/recovery-codes/regenerate", methods=["POST"])
@login_required
def regenerate_recovery_codes():
    # EXAKT aus 01_web_app.py Zeile 6552-6581 kopieren!
    pass
```

---

## 📧 emails.py (5 Routes)

```python
# src/blueprints/emails.py
"""Email Display Blueprint - Dashboard, List, Detail Views."""

from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
import importlib

from src.helpers import get_db_session, get_current_user_model

emails_bp = Blueprint("emails", __name__)


# Route 6: /dashboard (Zeile 978-1121)
@emails_bp.route("/dashboard")
@login_required
def dashboard():
    # EXAKT aus 01_web_app.py Zeile 980-1121 kopieren!
    pass


# Route 7: /list (Zeile 1123-1463)
@emails_bp.route("/list")
@login_required
def list_view():
    # EXAKT aus 01_web_app.py Zeile 1125-1463 kopieren!
    pass


# Route 8: /threads (Zeile 1465-1511)
@emails_bp.route("/threads")
@login_required
def threads_view():
    # EXAKT aus 01_web_app.py Zeile 1467-1511 kopieren!
    pass


# Route 9: /email/<id> (Zeile 1513-1691)
@emails_bp.route("/email/<int:raw_email_id>")
@login_required
def email_detail(raw_email_id):
    # EXAKT aus 01_web_app.py Zeile 1515-1691 kopieren!
    pass


# Route 10: /email/<id>/render-html (Zeile 1693-1794)
@emails_bp.route("/email/<int:raw_email_id>/render-html")
@login_required
def render_email_html(raw_email_id):
    # EXAKT aus 01_web_app.py Zeile 1695-1794 kopieren!
    pass
```

---

## ⚡ email_actions.py (11 Routes)

```python
# src/blueprints/email_actions.py
"""Email Action Blueprint - Mark done, delete, move, flag operations."""

from flask import Blueprint, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
import importlib

from src.helpers import get_db_session, get_current_user_model, api_success, api_error

email_actions_bp = Blueprint("email_actions", __name__)


# Route 11: /email/<id>/done (Zeile 1796-1834)
@email_actions_bp.route("/email/<int:raw_email_id>/done", methods=["POST"])
@login_required
def mark_done(raw_email_id):
    pass


# Route 12: /email/<id>/undo (Zeile 1836-1872)
@email_actions_bp.route("/email/<int:raw_email_id>/undo", methods=["POST"])
@login_required
def mark_undone(raw_email_id):
    pass


# ... weitere 9 Routes analog ...
```

---

## 🌐 api.py (64 Routes) - Prefix: /api

```python
# src/blueprints/api.py
"""API Blueprint - All /api/* endpoints."""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import importlib

from src.helpers import (
    get_db_session, get_current_user_model,
    validate_string, validate_integer,
    api_success, api_error
)

api_bp = Blueprint("api", __name__)
# WICHTIG: url_prefix="/api" wird in app_factory.py gesetzt!
# Daher: Route "/tags" wird zu URL "/api/tags"


# Route 16: /email/<id>/flags (Zeile 2192-2247)
@api_bp.route("/email/<int:raw_email_id>/flags", methods=["GET"])
@login_required
def get_email_flags(raw_email_id):
    pass


# Route 18: /training-stats (Zeile 2298-2353)
@api_bp.route("/training-stats", methods=["GET"])
@login_required
def get_training_stats():
    pass


# Route 29: /tags GET (Zeile 2818-2846)
@api_bp.route("/tags", methods=["GET"])
@login_required
def api_get_tags():
    pass


# Route 30: /tags POST (Zeile 2848-2889)
@api_bp.route("/tags", methods=["POST"])
@login_required
def api_create_tag():
    pass


# ... weitere 60 Routes analog ...
```

---

## 📏 rules.py (10 Routes) - KEIN Prefix!

```python
# src/blueprints/rules.py
"""Rules Blueprint - Auto-Rules Management."""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
import importlib

from src.helpers import get_db_session, api_success, api_error

rules_bp = Blueprint("rules", __name__)
# KEIN url_prefix! Routes behalten ihren vollen Pfad.


# Route 68: /rules (Zeile 4881-4906)
@rules_bp.route("/rules")
@login_required
def rules_management():
    pass


# Route 69: /api/rules GET (Zeile 4908-4943)
@rules_bp.route("/api/rules", methods=["GET"])
@login_required
def api_get_rules():
    pass


# Route 70: /api/rules POST (Zeile 4945-5008)
@rules_bp.route("/api/rules", methods=["POST"])
@login_required
def api_create_rule():
    pass


# ... weitere 7 Routes analog ...
```

---

## ✅ BLUEPRINT-REGISTRIERUNG

```python
# In app_factory.py:

app.register_blueprint(auth_bp)                          # Kein Prefix
app.register_blueprint(emails_bp)                        # Kein Prefix
app.register_blueprint(email_actions_bp)                 # Kein Prefix
app.register_blueprint(accounts_bp)                      # Kein Prefix
app.register_blueprint(tags_bp)                          # Kein Prefix
app.register_blueprint(api_bp, url_prefix="/api")        # MIT Prefix!
app.register_blueprint(rules_bp)                         # Kein Prefix
app.register_blueprint(training_bp)                      # Kein Prefix
app.register_blueprint(admin_bp)                         # Kein Prefix
```

---

## 🔗 URL_FOR KONVENTION

```python
# Alt (in 01_web_app.py):
url_for("login")
url_for("dashboard")
url_for("api_get_tags")

# Neu (in Blueprints):
url_for("auth.login")
url_for("emails.dashboard")
url_for("api.api_get_tags")
```

---

## 📋 CHECKLISTE PRO BLUEPRINT

- [ ] Blueprint-Datei erstellen
- [ ] Blueprint-Objekt definieren
- [ ] Lazy Imports für Module
- [ ] Alle Routes kopieren (1:1!)
- [ ] `@app.route` → `@{blueprint}_bp.route`
- [ ] `url_for("x")` → `url_for("{blueprint}.x")`
- [ ] In `blueprints/__init__.py` importieren
- [ ] In `app_factory.py` registrieren
- [ ] Testen!
