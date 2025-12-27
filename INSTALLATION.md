# 📦 KI-Mail-Helper - Installation Guide

Komplette Installationsanleitung für frische Umgebungen (Linux/WSL2).

---

## 🔧 Voraussetzungen

- **Python 3.11+** (empfohlen: 3.13)
- **SQLite3** (meist vorinstalliert)
- **Git**
- **Ollama** (für lokale KI, optional wenn Cloud-KI verwendet wird)

---

## 📥 Schritt-für-Schritt Installation

### 1. System-Dependencies

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git sqlite3

# Optional: Ollama für lokale KI
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl start ollama
sudo systemctl enable ollama
```

### 2. Repository klonen

```bash
git clone <YOUR_REPO_URL> ki-mail-helper
cd ki-mail-helper
```

### 3. Virtual Environment erstellen

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac

# Prüfe Python-Version
python --version  # Sollte >= 3.11 sein
```

### 4. Python Dependencies installieren

```bash
# Standard-Installation
pip install --upgrade pip
pip install -r requirements.txt

# WICHTIG: Flask-Session für Zero-Knowledge Server-Side Sessions
pip install Flask-Session

# Optional: Machine Learning Features (Newsletter-Klassifizierung)
pip install -r requirements-ml.txt
```

### 5. Environment-Variablen konfigurieren

```bash
# Kopiere Template
cp .env.example .env

# Editiere Datei
nano .env  # oder vim, code, etc.
```

**Wichtigste Einstellungen:**

```dotenv
# === PFLICHT: Security Keys für Zero-Knowledge ===
# Generiere mit: python -c "import secrets; print(secrets.token_hex(32))"
FLASK_SECRET_KEY=your-generated-secret-key-here

# Nicht mehr verwendet (veraltet)
# SERVER_MASTER_SECRET=...  # War für Cron-Jobs, Zero-Knowledge verhindert automatische Jobs

# === KI-Backend ===
AI_BACKEND=ollama                    # ollama, openai, anthropic, mistral
OLLAMA_MODEL=llama3.2                # Wenn ollama
OLLAMA_BASE_URL=http://localhost:11434
USE_CLOUD_AI=false

# === Optional: Cloud-KI ===
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=...
# MISTRAL_API_KEY=...

# === Datenbank ===
DATABASE_PATH=emails.db

# === Web-Server ===
WEB_HOST=0.0.0.0
WEB_PORT=5000
WEB_DEBUG=true
```

**Security Keys generieren:**

```bash
# FLASK_SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
```

### 6. Ollama Modell laden (wenn lokal)

```bash
# Für Base-Pass (schnelle Analyse)
ollama pull llama3.2

# Optional: Kleineres Modell für Optimize-Pass
ollama pull all-minilm:22m

# Prüfe verfügbare Modelle
ollama list
```

### 7. Datenbank initialisieren

**Zero-Knowledge Setup:**
```bash
# Flask-Session Directory erstellen (für Zero-Knowledge)
mkdir -p .flask_sessions
chmod 700 .flask_sessions
```

**Option A: Automatisch beim ersten Start** (empfohlen)

```bash
# Web-App startet und erstellt DB automatisch
python -m src.00_main --serve
```

**Option B: Manuell via CLI**

```bash
python -m src.00_main --init-db
```

**Option C: Via Python-Script**

```bash
python -c "import importlib; models = importlib.import_module('.02_models', 'src'); models.init_db()"
```

### 8. Database-Migrationen anwenden

```bash
# Alembic Migrationen auf neuesten Stand bringen
alembic upgrade head
```

**Output sollte sein:**

```
INFO  [alembic.runtime.migration] Running upgrade -> d1be18ce087b, initial schema
INFO  [alembic.runtime.migration] Running upgrade d1be18ce087b -> b899fc331a19, add two-pass optimization
INFO  [alembic.runtime.migration] Running upgrade b899fc331a19 -> 3a1ac5983a2d, add model tracking
INFO  [alembic.runtime.migration] Running upgrade 3a1ac5983a2d -> 86ca02f07586, add auth_type and pop3 support
INFO  [alembic.runtime.migration] Running upgrade 86ca02f07586 -> f1a2b3c4d5e6, add imap_flags tracking
```

### 9. Web-App starten

```bash
python -m src.00_main --serve

# Oder direkt:
python src/01_web_app.py
```

**Öffne im Browser:**

```
http://localhost:5000
```

### 10. Ersten User registrieren

1. Gehe zu: http://localhost:5000/register
2. Erstelle Account (Username, Email, Passwort)
3. Login mit Credentials
4. Master-Key wird automatisch erstellt & verschlüsselt

---

## ✅ Installation verifizieren

### Check 1: Datenbank existiert

```bash
ls -lh emails.db
# Sollte existieren (~100KB wenn leer)
```

### Check 2: Tabellen erstellt

```bash
sqlite3 emails.db "SELECT name FROM sqlite_master WHERE type='table';"
```

**Erwartete Tabellen:**

```
users
mail_accounts
raw_emails
processed_emails
service_tokens
recovery_codes
alembic_version
```

### Check 3: Alembic Version

```bash
sqlite3 emails.db "SELECT version_num FROM alembic_version;"
```

**Sollte aktuellste Migration zeigen** (z.B. `86ca02f07586`)

### Check 4: Web-App läuft

```bash
curl http://localhost:5000
# Sollte HTML zurückgeben (keine Fehler)
```

### Check 5: Ollama läuft (wenn lokal)

```bash
curl http://localhost:11434/api/tags
# Sollte JSON mit geladenen Modellen zurückgeben
```

---

## 🔐 Encryption Key Setup (DEK/KEK Pattern - Phase 8b)

### Erste User-Registrierung

Beim ersten User-Account wird automatisch:

1. **User Salt** generiert (32 Bytes, base64-encoded = 44 chars)
2. **KEK (Key Encryption Key)** abgeleitet (PBKDF2-HMAC-SHA256, 600.000 Iterations)
3. **DEK (Data Encryption Key)** generiert (zufällige 32 Bytes)
4. **Encrypted DEK** (AES-256-GCM(DEK, KEK)) in DB gespeichert
5. **DEK in Session** (Server-RAM, nicht in DB!) für aktuelle Session

**DEK/KEK Architektur:**
- **DEK** verschlüsselt alle E-Mails (einmal generiert, bleibt konstant)
- **KEK** aus Passwort abgeleitet (ändert sich bei Passwort-Wechsel)
- **Vorteil:** Passwort ändern = nur DEK re-encrypten (nicht alle E-Mails!)

**Wichtig:** Das User-Passwort wird **NIEMALS** im Klartext gespeichert!

### Encryption Key Überprüfung

```bash
sqlite3 emails.db "SELECT id, username, LENGTH(salt), LENGTH(encrypted_dek) FROM users;"
```

**Output sollte sein:**

```
1|thomas|44|<number>
```

### Migration von alten Usern (encrypted_master_key → encrypted_dek)

Falls du einen User aus Phase 8a hast:

```bash
python scripts/migrate_to_dek_kek.py
# Gibt Passwort ein → encrypted_master_key wird als DEK verwendet
```

---

## 📧 Mail-Account hinzufügen

### Via Web-UI (empfohlen)

1. Login: http://localhost:5000
2. Gehe zu **Einstellungen** (⚙️)
3. **"Neuen Account hinzufügen"**
4. Wähle Methode:
   - **IMAP/SMTP** (GMX, Gmail mit App-Passwort, etc.)
   - **Google OAuth** (Gmail ohne Passwort)
   - **POP3** (experimental)

### IMAP Beispiel (GMX)

```
Name: GMX Postfach
IMAP-Server: imap.gmx.net
Port: 993
Verschlüsselung: SSL
Username: deine@email.de
Passwort: <dein-passwort>
```

### Google OAuth Setup

Siehe: [OAUTH_AND_IMAP_SETUP.md](OAUTH_AND_IMAP_SETUP.md)

---

## 🤖 Background Processing (Cron)

### Systemd Timer Setup (produktiv)

```bash
# Kopiere Service-Dateien
sudo cp mail-helper-processor.service /etc/systemd/system/
sudo cp mail-helper-processor.timer /etc/systemd/system/

# Editiere Pfade in Service-Datei
sudo nano /etc/systemd/system/mail-helper-processor.service
# WorkingDirectory=/home/USER/ki-mail-helper
# ExecStart=/home/USER/ki-mail-helper/venv/bin/python ...

# Aktiviere Timer
sudo systemctl daemon-reload
sudo systemctl enable mail-helper-processor.timer
sudo systemctl start mail-helper-processor.timer

# Status prüfen
sudo systemctl status mail-helper-processor.timer
sudo journalctl -u mail-helper-processor.service -f
```

### Manueller Background Worker

```bash
# Worker läuft kontinuierlich
python -m src.00_main --worker

# Oder einmalig
python -m src.00_main --process-once
```

---

## 🧪 Tests

```bash
# Alle Tests
pytest tests/

# Spezifische Tests
pytest tests/test_ai_client.py -v
pytest tests/test_sanitizer.py -v
pytest tests/test_mail_fetcher.py -v

# Mit Coverage
pytest --cov=src tests/
```

---

## 🐛 Troubleshooting

### Problem: "No module named 'src'"

```bash
# Stelle sicher, dass du im Projekt-Root bist
cd /path/to/ki-mail-helper

# Python-Pfad prüfen
python -c "import sys; print(sys.path)"
```

### Problem: "emails.db locked"

```bash
# WAL-Modus Dateien löschen (nur wenn App NICHT läuft!)
rm emails.db-wal emails.db-shm

# Oder DB-Check
python scripts/check_db.py
```

### Problem: Ollama nicht erreichbar

```bash
# Status prüfen
systemctl status ollama

# Neu starten
sudo systemctl restart ollama

# Logs
journalctl -u ollama -f
```

### Problem: Master-Key Fehler

```bash
# Prüfe Encryption Setup
python -c "
import importlib
enc = importlib.import_module('.08_encryption', 'src')
print('✅ Encryption Module OK')
"
```

### Problem: Migration Fehler

```bash
# Zeige aktuelle Revision
alembic current

# Zeige Historie
alembic history

# Downgrade falls nötig
alembic downgrade -1

# Upgrade
alembic upgrade head
```

---

## 📚 Weiterführende Dokumentation

- [README.md](README.md) - Projekt-Übersicht & Quick Start
- [OAUTH_AND_IMAP_SETUP.md](OAUTH_AND_IMAP_SETUP.md) - OAuth & IMAP Konfiguration
- [MAINTENANCE.md](MAINTENANCE.md) - Wartung & Helper-Scripts
- [TESTING_GUIDE.md](TESTING_GUIDE.md) - Test-Anleitung
- [CRON_SETUP.md](CRON_SETUP.md) - Systemd Timer Setup
- [docs/MULTI_AUTH_ARCHITECTURE.md](docs/MULTI_AUTH_ARCHITECTURE.md) - Multi-Auth Architektur

---

## 🚀 Nächste Schritte

1. ✅ Installation abgeschlossen
2. ✅ User registriert
3. ✅ Mail-Account hinzugefügt
4. → **Erste Mails abrufen:** Klick "Abrufen" in Einstellungen
5. → **Dashboard nutzen:** 3×3-Matrix, Ampel-View, Details
6. → **Cron einrichten:** Automatischer Abruf alle 15 Min

---

**Viel Erfolg mit KI-Mail-Helper! 🎉**

Bei Fragen: Siehe [MAINTENANCE.md](MAINTENANCE.md) oder öffne ein Issue.
