# 🏗️ KI-Mail-Helper – Architektur & Entwicklungsprinzipien

**Letztes Update:** 29. Dezember 2025  
**Zweck:** Grundlegende Architektur-Entscheidungen für neue Chat-Sessions und Context-Loss-Situationen

---

## 🎯 Kern-Prinzipien

### 1. **UI-First Development**
- ✅ **Alle Tests laufen im UI** (Web-Interface)
- ❌ **KEINE CLI-Tests für Produktions-Features**
- 🧪 **Unit-Tests (`/tests/`):** Nur für isolierte Funktionen (mit Mocks)
- 🌐 **Integration-Tests:** Im laufenden UI mit echten Daten

### 2. **Zero-Knowledge Verschlüsselung**
- 🔐 **Alle sensiblen Daten verschlüsselt in DB**
- 🔑 **Master-Password entschlüsselt Daten** (nie im Klartext gespeichert)
- 📧 **Verschlüsselte Felder:**
  - `MailAccount`: `encrypted_imap_server`, `encrypted_imap_username`, `encrypted_imap_password`
  - `RawEmail`: Body, Betreff, Absender (verschlüsselt)
- 🔍 **Hash-Felder für Suche:** `imap_server_hash`, `imap_username_hash` (ermöglichen Suche ohne Klartext)

### 3. **Authentifizierung**
```
Login-Flow: Username → Master-Password → 2FA → UI-Zugriff
```
- **Username:** Identifikation
- **Master-Password:** Entschlüsselt DEK (Data Encryption Key)
- **2FA:** Time-based OTP (TOTP)
- **Session:** Flask-Session mit verschlüsselten Cookies

---

## 📁 Ordnerstruktur

```
/home/thomas/projects/KI-Mail-Helper/
├── src/                      # Backend-Module (Python)
│   ├── 00_main.py           # Flask-App Entry Point
│   ├── 01_web_app.py        # Web-Routes (UI-Endpunkte)
│   ├── 02_models.py         # SQLAlchemy-Modelle (DB-Schema)
│   ├── 03_ai_client.py      # KI-Integration (Ollama, OpenAI, Anthropic)
│   ├── 06_encryption.py     # Verschlüsselungs-Manager
│   ├── 07_auth.py           # Master-Key-Manager, 2FA
│   ├── 12_processing.py     # Email-Verarbeitung
│   └── services/            # Service-Layer (Tag-Manager, Sender-Patterns, etc.)
│
├── templates/               # Jinja2-HTML-Templates (UI)
│   ├── email_detail.html   # Email-Detailansicht
│   ├── list_view.html      # Email-Liste
│   ├── tags.html           # Tag-Management
│   └── ...
│
├── tests/                   # Unit-Tests (pytest, mit Mocks)
│   ├── test_imap_diagnostics.py  # Mock-Tests für IMAP-Diagnostics
│   └── ...
│
├── scripts/                 # Wartungs-Skripte (CLI)
│   └── ...
│
├── migrations/              # Alembic DB-Migrationen
│   └── versions/
│
├── docs/                    # Dokumentation
│   ├── DEPLOYMENT.md
│   ├── SECURITY.md
│   └── ...
│
├── config/                  # Produktions-Konfiguration
│   ├── gunicorn.conf.py
│   └── ...
│
├── emails.db                # SQLite-Datenbank (verschlüsselte Daten)
├── .env                     # Secrets (NICHT in Git!)
└── requirements.txt         # Python-Abhängigkeiten
```

---

## 🧪 Test-Strategie

### **Unit-Tests (`/tests/`):**
- **Zweck:** Isolierte Funktionen testen (z.B. `IMAPDiagnostics.test_connection()`)
- **Mocks:** Vollständig gemockt (keine echten IMAP-Calls, keine DB-Zugriffe)
- **Ausführung:** `pytest tests/ -v`
- **Beispiel:** `test_imap_diagnostics.py` (10 Tests, 100% gemockt)

### **Integration-Tests (UI-basiert):**
- **Zweck:** End-to-End-Tests mit echten Daten
- **Ablauf:**
  1. Login im UI (Username + Master-Password + 2FA)
  2. Navigation zu Test-Feature (z.B. IMAP-Diagnostics-Dashboard)
  3. Test-Button klicken → Backend-Modul wird aufgerufen
  4. Ergebnis im UI validieren
- **Daten:** Echte Credentials aus DB (verschlüsselt, im UI entschlüsselt)
- **Beispiel:** Phase 11.5 IMAP-Test-Dashboard

### **NIEMALS:**
- ❌ CLI-Tests mit echten Credentials in `.env`
- ❌ Klartext-Passwörter in Skripten/Config-Files
- ❌ Integration-Tests in pytest (nur Mock-Tests erlaubt)

---

## 🔄 Datenfluss: UI → Backend → DB

### **Beispiel: Email-Liste anzeigen**

```
1. User öffnet /emails im Browser
   ↓
2. templates/list_view.html wird gerendert
   ↓
3. Jinja2-Template ruft Flask-Route auf (/api/emails)
   ↓
4. src/01_web_app.py: @app.route('/api/emails')
   ↓
5. src/12_processing.py: load_emails_from_db()
   ↓
6. src/06_encryption.py: EncryptionManager.decrypt()
   ↓
7. src/02_models.py: RawEmail.query.all()
   ↓
8. emails.db: SELECT * FROM raw_emails
   ↓
9. Entschlüsselte Daten zurück an UI
   ↓
10. templates/list_view.html zeigt Emails an
```

### **Schlüssel-Komponenten:**

- **UI-Templates (`/templates/`):**
  - Jinja2-Templates mit CSP-compliant Inline-JavaScript
  - AJAX-Calls zu Backend-APIs
  - Display entschlüsselter Daten

- **Backend-Routes (`src/01_web_app.py`):**
  - Flask-Routes (`@app.route()`)
  - Session-Handling (Login-Status prüfen)
  - API-Endpunkte für AJAX-Calls

- **Service-Layer (`src/services/`):**
  - Business-Logik (Tag-Manager, Sender-Patterns)
  - Zugriff auf Modelle + Verschlüsselung

- **Datenbank (`emails.db`):**
  - SQLite mit SQLAlchemy ORM
  - Verschlüsselte Felder (`encrypted_*`)
  - Hash-Felder für Suche (`*_hash`)

---

## 🔐 Verschlüsselungs-Architektur

### **Key-Hierarchie:**

```
User-Password (nur im Login bekannt)
    ↓ (PBKDF2)
KEK (Key Encryption Key)
    ↓ (AES-256-GCM)
DEK (Data Encryption Key)
    ↓ (AES-256-GCM)
Encrypted Data in DB
```

### **Entschlüsselung im UI:**

1. **Login:** User gibt Master-Password ein
2. **KEK ableiten:** PBKDF2(Master-Password, salt)
3. **DEK entschlüsseln:** AES-Decrypt(encrypted_dek, KEK)
4. **Session:** DEK in Flask-Session speichern (verschlüsselt)
5. **Daten entschlüsseln:** AES-Decrypt(encrypted_data, DEK)

### **Module:**

- `src/06_encryption.py`: `EncryptionManager` (AES-256-GCM)
- `src/07_auth.py`: `MasterKeyManager` (KEK/DEK-Verwaltung)

---

## 🚀 Entwicklungs-Workflow

### **Feature-Entwicklung:**

1. **Backend-Modul erstellen:** `src/XX_feature.py`
2. **Unit-Tests schreiben:** `tests/test_feature.py` (mit Mocks)
3. **Flask-Route hinzufügen:** `src/01_web_app.py`
4. **UI-Template erstellen:** `templates/feature.html`
5. **Server starten:** `python src/00_main.py`
6. **UI-Test:** Login → Feature-Seite → Funktionalität testen
7. **Commit:** `git commit -m "Phase X: Feature-Name"`

### **Test-First Development (empfohlen):**

1. **Tests schreiben ZUERST:** `tests/test_feature.py`
2. **Implementierung:** `src/XX_feature.py`
3. **Unit-Tests laufen:** `pytest tests/test_feature.py -v`
4. **UI-Integration:** Template + Route
5. **UI-Test:** Manuell im Browser

---

## 📝 Wichtige Module

| Modul | Zweck |
|-------|-------|
| `src/00_main.py` | Flask-App Entry Point, Server-Start |
| `src/01_web_app.py` | Web-Routes, UI-Endpunkte |
| `src/02_models.py` | SQLAlchemy-Modelle (User, MailAccount, RawEmail, etc.) |
| `src/03_ai_client.py` | KI-Integration (Embeddings, Klassifikation) |
| `src/06_encryption.py` | Verschlüsselung (AES-256-GCM) |
| `src/07_auth.py` | Authentifizierung (Master-Key, 2FA) |
| `src/12_processing.py` | Email-Verarbeitung (Fetch, Parse, Store) |
| `src/services/tag_manager.py` | Tag-Management (Phase 10/11) |
| `src/services/sender_patterns.py` | Sender-Pattern-Learning (Phase 11d) |

---

## ⚠️ Häufige Fehler (VERMEIDEN!)

### ❌ **CLI-Tests mit echten Credentials:**
```python
# FALSCH:
TEST_IMAP_HOST=imap.gmx.net
TEST_IMAP_PASSWORD=klartext_passwort  # ← NIEMALS!
```

### ✅ **Richtig: UI-basierte Tests:**
```python
# Unit-Test mit Mock:
@pytest.mark.unit
def test_connection_with_mock():
    mock_client = Mock()
    # ... Test mit Mock

# Integration-Test im UI:
# 1. Login im Browser
# 2. /imap-test-dashboard öffnen
# 3. "Test Connection" Button klicken
# 4. Backend lädt Credentials aus DB (verschlüsselt)
```

---

### ❌ **Credentials in Code hardcoden:**
```python
# FALSCH:
imap_password = "mein_passwort_123"  # ← NIEMALS!
```

### ✅ **Richtig: Aus DB laden & entschlüsseln:**
```python
# In src/01_web_app.py Route:
account = MailAccount.query.get(account_id)
dek = session['dek']  # Aus Flask-Session
imap_password = EncryptionManager.decrypt(account.encrypted_imap_password, dek)
```

---

### ❌ **Modelle direkt importieren:**
```python
# FALSCH (Import-Fehler):
from src.models import MailAccount  # ← ModuleNotFoundError
```

### ✅ **Richtig: Über Modulnummer:**
```python
# In Flask-App Context:
from src.02_models import MailAccount  # ← Korrekt

# In Skripten (außerhalb Flask):
import importlib.util
spec = importlib.util.spec_from_file_location("models", "src/02_models.py")
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)
MailAccount = models.MailAccount
```

---

## 🔧 Nützliche Befehle

```bash
# Server starten (UI-Tests):
python src/00_main.py

# Unit-Tests ausführen:
pytest tests/ -v

# DB-Migration erstellen:
alembic revision -m "Phase X: Feature"

# DB-Migration anwenden:
alembic upgrade head

# Git-Status prüfen:
git status
git log --oneline -5

# Requirements installieren:
pip install -r requirements.txt
```

---

## 📚 Weitere Dokumentation

- **Deployment:** `docs/DEPLOYMENT.md`
- **Security:** `docs/SECURITY.md`
- **Installation:** `docs/INSTALLATION.md`
- **Testing:** `docs/TESTING_GUIDE.md`
- **OAuth/IMAP:** `docs/OAUTH_AND_IMAP_SETUP.md`

---

## 🎯 Zusammenfassung

1. **Tests im UI, nicht CLI**
2. **Zero-Knowledge: Alles verschlüsselt in DB**
3. **Ordnerstruktur:** `/src/` (Backend), `/templates/` (UI), `/tests/` (Unit-Tests)
4. **Datenfluss:** UI → Flask-Route → Service → DB → Entschlüsseln → UI
5. **Test-First Development:** Tests schreiben, implementieren, UI-Test
6. **Keine Klartext-Credentials:** Nur verschlüsselt in DB

---

**Bei Context-Loss oder neuem Chat:** Dieses Dokument lesen! ✅
