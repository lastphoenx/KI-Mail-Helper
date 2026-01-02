# 🏗️ KI-Mail-Helper – Architektur & Entwicklungsprinzipien

**Letztes Update:** 02. Januar 2026  
**Zweck:** Grundlegende Architektur-Entscheidungen für neue Chat-Sessions und Context-Loss-Situationen

---

## 🎯 Kern-Prinzipien

### 1. **UI-First Development & CLI-Testing**
- ✅ **CLI-Tests:** Unit-Tests mit Mocks (`pytest tests/`)
- ✅ **CLI-Tests:** Skripte ohne Credentials (Datenbank-Checks, Migrations)
- ❌ **KEINE CLI-Tests mit echten Credentials** (Mail-Account-Passwörter)
- 🔐 **Master-Password nur im UI:** Login → Entschlüsselung → Flask-Session
- 🌐 **Integration-Tests:** Im laufenden UI mit echten Daten (Master-Password geschützt)

### 2. **Zero-Knowledge Verschlüsselung**
- 🔐 **Alle sensiblen Daten verschlüsselt in DB**
- 🔑 **Master-Password entschlüsselt Daten** (nie im Klartext gespeichert)
- 📧 **Verschlüsselte Felder:**
  - `MailAccount`: `encrypted_imap_server`, `encrypted_imap_username`, `encrypted_imap_password`
  - `RawEmail`: Body, Betreff, Absender (verschlüsselt)
- 🔍 **Hash-Felder für Suche:** `imap_server_hash`, `imap_username_hash` (ermöglichen Suche ohne Klartext)
- 🧠 **Semantic Search Exception (Phase F.1):**
  - **Email Embeddings:** Unverschlüsselt in DB (als BLOB)
  - **Grund:** Embeddings sind nicht reversibel → keine Klartext-Rekonstruktion möglich
  - **Generierung:** Beim IMAP-Fetch (Klartext verfügbar) VOR Encryption
  - **Zero-Knowledge Compliance:** Embeddings sind mathematische Vektoren, kein Klartext
  - **Speicherplatz:** 1.5KB/Email (384-dim float32 vector)

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
│   ├── semantic_search.py   # Semantic Email Search (Phase F.1)
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

### **Unit-Tests (`/tests/`) - CLI OK:**
- **Zweck:** Isolierte Funktionen testen (z.B. `IMAPDiagnostics.test_connection()`)
- **Mocks:** Vollständig gemockt (keine echten IMAP-Calls, keine DB-Zugriffe)
- **Ausführung:** `pytest tests/ -v` ✅ (CLI erlaubt)
- **Beispiel:** `test_imap_diagnostics.py` (10 Tests, 100% gemockt)
- **Keine Credentials benötigt:** Nur Mock-Objekte

### **Wartungs-Skripte (`/scripts/`) - CLI OK:**
- **Zweck:** Datenbank-Checks, Migrationen, Cleanup
- **Beispiele:**
  - `check_accounts.py`: Liste Mail-Accounts (ohne Passwörter)
  - `cleanup_old_emails.py`: Alte Emails löschen
- **Keine Credentials benötigt:** Nur Lese-Zugriffe oder Metadaten
- **Ausführung:** `python scripts/check_accounts.py` ✅ (CLI erlaubt)

### **Integration-Tests (UI-basiert) - NUR UI:**
- **Zweck:** End-to-End-Tests mit echten Credentials
- **Warum nur UI?**
  - ✅ Master-Password wird im UI eingegeben (Login)
  - ✅ Flask-Session speichert DEK (entschlüsselter Data Encryption Key)
  - ✅ Während Session: Credentials entschlüsselbar
  - ❌ CLI hat kein Master-Password → Credentials nicht entschlüsselbar
- **Ablauf:**
  1. Login im UI (Username + Master-Password + 2FA)
  2. Navigation zu Test-Feature (z.B. IMAP-Diagnostics-Dashboard)
  3. Test-Button klicken → Backend lädt verschlüsselte Credentials aus DB
  4. Backend entschlüsselt mit DEK aus Flask-Session
  5. Echter IMAP-Call mit entschlüsselten Credentials
  6. Ergebnis im UI anzeigen
- **Beispiel:** Phase 11.5 IMAP-Test-Dashboard

### **NIEMALS:**
- ❌ CLI-Tests/Skripte mit echten Mail-Credentials
- ❌ Master-Password in CLI/Skripten/`.env`-Files
- ❌ Klartext-Passwörter irgendwo speichern
- ❌ `TEST_IMAP_PASSWORD=klartext` in `.env` (Zero-Knowledge-Verletzung!)

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

1. **Login:** User gibt Master-Password ein (nur im UI!)
2. **KEK ableiten:** PBKDF2(Master-Password, salt)
3. **DEK entschlüsseln:** AES-Decrypt(encrypted_dek, KEK)
4. **Flask-Session:** DEK im Session-Cookie speichern (server-side, verschlüsselt)
5. **Session-Lebensdauer:** DEK verfügbar während aktiver Session
6. **Daten entschlüsseln:** AES-Decrypt(encrypted_data, DEK) - im Request-Context
7. **Logout/Timeout:** Session beenden → DEK gelöscht

**Warum nur im UI?**
- 🔐 **Master-Password nie in CLI:** Kein Input-Mechanismus für sichere Passwort-Eingabe
- 🔒 **Flask-Session schützt DEK:** Server-side Sessions (`.flask_sessions/` Directory)
- ⏱️ **Session-Timeout:** Automatisches Logout nach Inaktivität
- 🚪 **CLI hat keinen Session-Context:** Keine Möglichkeit, DEK zu erhalten

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

### ❌ **CLI-Tests mit echten Mail-Credentials:**
```python
# FALSCH - Zero-Knowledge-Verletzung!
TEST_IMAP_HOST=imap.gmx.net
TEST_IMAP_USER=user@example.com
TEST_IMAP_PASSWORD=klartext_passwort  # ← NIEMALS! Credentials sind verschlüsselt in DB!
```

**Warum falsch?**
- ❌ Credentials sind verschlüsselt in DB (nur mit Master-Password entschlüsselbar)
- ❌ Master-Password wird nur im UI eingegeben (nie in CLI/`.env`)
- ❌ CLI hat keinen Flask-Session-Context → kein Zugriff auf DEK

### ✅ **Richtig: Unterschiedliche Test-Typen:**
```python
# ✅ CLI: Unit-Test mit Mock (ERLAUBT)
@pytest.mark.unit
def test_connection_with_mock():
    mock_client = Mock()
    mock_client.login.return_value = None
    # ... Test mit Mock (keine echten Credentials)

# ✅ CLI: Wartungs-Skript ohne Credentials (ERLAUBT)
def list_accounts():
    accounts = MailAccount.query.all()
    for acc in accounts:
        print(f"{acc.name} (ID: {acc.id})")
        # Keine Passwort-Entschlüsselung!

# ✅ UI: Integration-Test mit echten Credentials (NUR HIER!)
# 1. Login im Browser (Master-Password eingeben)
# 2. /imap-test-dashboard öffnen
# 3. "Test Connection" Button klicken
# 4. Backend lädt Credentials aus DB (verschlüsselt)
# 5. Backend entschlüsselt mit DEK aus Flask-Session
# 6. Echter IMAP-Call
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
