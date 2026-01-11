# PRE_REFACTORING_AUDIT.md

**Erstellt:** 11. Januar 2026  
**Zweck:** Bestandsaufnahme vor dem Blueprint-Refactoring

---

## 📊 ZUSAMMENFASSUNG

| Metrik | Wert |
|--------|------|
| Routes in `01_web_app.py` | **123** |
| Routes in anderen Dateien | **0** |
| Dateigröße | ~9.500 Zeilen |
| `@login_required` Decorators | 116 |
| `@limiter` Decorators | 8 |
| `session[]` Zugriffe | 14 |
| `current_user` Nutzungen | 130 |
| `flask.g` Nutzungen | 1 |

---

## 🔧 GLOBALE VARIABLEN

Diese müssen in `app_factory.py` initialisiert werden:

| Variable | Zeile | Beschreibung |
|----------|-------|--------------|
| `app` | 71 | `Flask(__name__, template_folder="../templates")` |
| `limiter` | 252 | Rate Limiter |
| `SessionLocal` | 329 | SQLAlchemy Session Factory |
| `login_manager` | 331-333 | Flask-Login Manager |

### Code-Snippets:

```python
# Zeile 71
app = Flask(__name__, template_folder="../templates")

# Zeile 252-264
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# Zeile 329
SessionLocal = sessionmaker(bind=engine)

# Zeile 331-333
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
```

---

## 🔄 SHARED HELPER FUNCTIONS

Diese müssen nach `src/helpers/` extrahiert werden:

| Funktion | Zeilen | Nutzung |
|----------|--------|---------|
| `get_db_session()` | 399-403 | Contextmanager für DB Sessions |
| `get_current_user_model()` | 404-414 | Holt User-Objekt aus DB |
| `validate_string()` | 415-452 | Input-Validierung (38 Zeilen) |
| `validate_integer()` | 453-485 | Input-Validierung |
| `validate_email()` | 486-520 | Email-Validierung |
| `api_success()` | 521-542 | API Response Helper |
| `api_error()` | 543-565 | API Error Helper |
| `ensure_master_key_in_session()` | 566-571 | Encryption Helper (6 Zeilen) |
| `initialize_phase_y_config()` | 578-646 | Phase-Y Init (69 Zeilen) |
| `generate_csp_nonce()` | 155-159 | CSP Nonce Generator |

### get_db_session() - Zeile 399-402

```python
@contextmanager
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### get_current_user_model() - Zeile 404-414

```python
def get_current_user_model(db):
    """Holt das aktuelle User-Objekt aus der Datenbank."""
    if not current_user.is_authenticated:
        return None
    user = db.query(models.User).filter_by(id=current_user.id).first()
    return user
```

---

## 📦 IMPORTS

### Flask & Extensions
```python
from flask import (
    Flask, render_template, request, redirect, 
    url_for, flash, jsonify, session, Response,
    abort, send_file, make_response
)
from flask_login import (
    LoginManager, login_user, logout_user, 
    login_required, current_user
)
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
```

### SQLAlchemy
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
```

### Projekt-Module (via importlib)
```python
import importlib
models = importlib.import_module(".02_models", "src")
ai_client = importlib.import_module(".03_ai_client", "src")
mail_fetcher = importlib.import_module(".06_mail_fetcher", "src")
encryption = importlib.import_module(".08_encryption", "src")
# ... etc.
```

---

## ⚠️ ERROR HANDLERS

| Handler | Zeile | Funktion |
|---------|-------|----------|
| 404 | 8491 | `not_found(e)` |
| 500 | 8497 | `server_error(e)` |

Diese müssen in `app_factory.py` registriert werden.

---

## 🔐 BEFORE/AFTER REQUEST

| Hook | Zeile | Funktion |
|------|-------|----------|
| `@app.before_request` | 154 | `generate_csp_nonce()` |
| `@app.before_request` | 166 | `csrf_protect_ajax()` |
| `@app.after_request` | 186 | `set_security_headers()` |
| `@app.before_request` | 265 | `check_dek_in_session()` |

Diese müssen in `app_factory.py` registriert werden.

---

## ✅ AUDIT ERGEBNIS

- [x] Alle 123 Routes in einer Datei (01_web_app.py)
- [x] Keine Routes in anderen Dateien
- [x] Keine zirkulären Imports erkannt
- [x] Services haben keine Routes (verifiziert)
- [x] Background Jobs haben keine Routes (verifiziert)
- [x] Helper Functions sind identifiziert
- [x] Globale Variablen sind dokumentiert

**BEREIT FÜR REFACTORING** ✅
