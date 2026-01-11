# SHARED_COMPONENTS.md

**Erstellt:** 11. Januar 2026  
**Zweck:** Dokumentation der gemeinsam genutzten Komponenten, die nach `src/helpers/` extrahiert werden

---

## 📂 ZIELSTRUKTUR

```
src/helpers/
├── __init__.py          # Package-Init mit allen Exports
├── database.py          # DB Session & User-Helper
├── validation.py        # Input-Validierung
├── responses.py         # API Response-Helper
├── decorators.py        # Custom Decorators
├── security.py          # CSP, CSRF, Security Headers
└── crypto.py            # Encryption-Wrapper
```

---

## 📦 database.py

### Quellen in 01_web_app.py:

| Funktion | Zeilen | Beschreibung |
|----------|--------|--------------|
| `get_db_session()` | 399-401 | DB Session Factory |
| `get_current_user_model()` | 404-409 | Holt User aus DB |

### Code:

```python
# src/helpers/database.py
"""Database session helpers for all blueprints."""

from contextlib import contextmanager
from flask_login import current_user
import importlib

# Lazy imports to avoid circular dependencies
_SessionLocal = None
_models = None

def _get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import create_engine
        import os
        DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///emails.db")
        engine = create_engine(DATABASE_URL)
        _SessionLocal = sessionmaker(bind=engine)
    return _SessionLocal

def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


@contextmanager
def get_db_session():
    """Get database session from shared pool."""
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_model(db):
    """Holt das aktuelle User-Model aus DB."""
    if not current_user.is_authenticated:
        return None
    models = _get_models()
    return db.query(models.User).filter_by(id=current_user.id).first()
```

---

## 📦 validation.py

### Quellen in 01_web_app.py:

| Funktion | Zeilen | Beschreibung |
|----------|--------|--------------|
| `validate_string()` | 415-452 | String-Validierung |
| `validate_integer()` | 454-485 | Integer-Validierung |
| `validate_email()` | 487-520 | Email-Validierung |

### Code:

```python
# src/helpers/validation.py
"""Input validation helpers for API endpoints."""


def validate_string(value, field_name, min_len=1, max_len=1000, allow_empty=False):
    """Validiert String-Input für API-Endpoints.
    
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
    """Validiert Integer-Input für API-Endpoints.
    
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
    """Validiert E-Mail-Adresse.
    
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
```

---

## 📦 responses.py

### Quellen in 01_web_app.py:

| Funktion | Zeilen | Beschreibung |
|----------|--------|--------------|
| `api_success()` | 522-542 | Erfolgs-Response |
| `api_error()` | 544-565 | Fehler-Response |

### Code:

```python
# src/helpers/responses.py
"""Standardized API response helpers."""

from flask import jsonify


def api_success(data=None, message=None, status_code=200):
    """Standardisierte Erfolgs-Response.
    
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
    """Standardisierte Fehler-Response.
    
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
```

---

## 📦 security.py

### Quellen in 01_web_app.py:

| Funktion | Zeilen | Beschreibung |
|----------|--------|--------------|
| `generate_csp_nonce()` | 155-159 | CSP Nonce Generator |
| `csrf_protect_ajax()` | 166-184 | CSRF Schutz für AJAX |
| `set_security_headers()` | 186-230 | Security Headers |
| `ensure_master_key_in_session()` | 566-571 | Master-Key Check (6 Zeilen) |

### Hinweis:

Diese Funktionen werden NICHT nach helpers/ verschoben, sondern bleiben als `@app.before_request` / `@app.after_request` in `app_factory.py`, da sie auf `app` registriert werden müssen.

---

## 📦 crypto.py (optional)

### Beschreibung:

Wrapper für Encryption-Funktionen, falls benötigt. Aktuell wird `08_encryption.py` direkt via importlib geladen.

```python
# src/helpers/crypto.py
"""Encryption wrapper for easy access."""

import importlib

_encryption = None

def get_encryption():
    global _encryption
    if _encryption is None:
        _encryption = importlib.import_module(".08_encryption", "src")
    return _encryption
```

---

## 📦 __init__.py

```python
# src/helpers/__init__.py
"""Shared helper functions for all blueprints."""

from .database import get_db_session, get_current_user_model
from .validation import validate_string, validate_integer, validate_email
from .responses import api_success, api_error

__all__ = [
    "get_db_session",
    "get_current_user_model",
    "validate_string",
    "validate_integer",
    "validate_email",
    "api_success",
    "api_error",
]
```

---

## 🔗 NUTZUNG IN BLUEPRINTS

```python
# In jedem Blueprint:
from src.helpers import (
    get_db_session, 
    get_current_user_model,
    validate_string,
    api_success,
    api_error
)

@api_bp.route("/tags", methods=["POST"])
@login_required
def api_create_tag():
    with get_db_session() as db:
        user = get_current_user_model(db)
        try:
            name = validate_string(request.json.get("name"), "Name", max_len=100)
        except ValueError as e:
            return api_error(str(e))
        # ... Rest der Logik
        return api_success({"id": new_tag.id}, "Tag erstellt")
```

---

## ✅ CHECKLISTE

- [ ] `src/helpers/` Ordner erstellen
- [ ] `__init__.py` erstellen
- [ ] `database.py` erstellen und testen
- [ ] `validation.py` erstellen und testen
- [ ] `responses.py` erstellen und testen
- [ ] Import in `01_web_app.py` testen (Backwards-Compatibility)
- [ ] Erst dann in Blueprints verwenden
