# 📦 KI-Mail-Helper – Installationsanleitung

**Komplette Schritt-für-Schritt Anleitung für Linux/WSL2**

---

## Inhaltsverzeichnis

1. [Voraussetzungen](#1-voraussetzungen)
2. [Repository klonen](#2-repository-klonen)
3. [Python-Umgebung einrichten](#3-python-umgebung-einrichten)
4. [Ollama installieren (lokale KI)](#4-ollama-installieren-lokale-ki)
5. [Konfiguration (.env)](#5-konfiguration-env)
6. [Datenbank initialisieren](#6-datenbank-initialisieren)
7. [App starten](#7-app-starten)
8. [Erste Schritte nach dem Start](#8-erste-schritte-nach-dem-start)
9. [User-Verwaltung](#9-user-verwaltung)
10. [Installation verifizieren](#10-installation-verifizieren)
11. [Production Deployment](#11-production-deployment)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Voraussetzungen

### System-Anforderungen

| Komponente | Minimum | Empfohlen |
|------------|---------|-----------|
| **OS** | Debian 11 / Ubuntu 22.04 | Debian 12 / Ubuntu 24.04 |
| **Python** | 3.11 | 3.13 |
| **RAM** | 4 GB | 8 GB (für lokale KI) |
| **Disk** | 2 GB | 10 GB (für Ollama-Modelle) |

### System-Pakete installieren

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git sqlite3 curl
```

---

## 2. Repository klonen

```bash
# In gewünschtes Verzeichnis wechseln
cd /home/$USER/projects  # oder /opt für Production

# Repository klonen
git clone https://github.com/lastphoenx/KI-Mail-Helper.git
cd KI-Mail-Helper
```

---

## 3. Python-Umgebung einrichten

### Virtual Environment erstellen

```bash
# venv erstellen
python3 -m venv venv

# venv aktivieren
source venv/bin/activate

# Prüfen (sollte >= 3.11 sein)
python --version
```

### Dependencies installieren

```bash
# Pip aktualisieren
pip install --upgrade pip

# Alle Abhängigkeiten installieren
pip install -r requirements.txt
```

> 💡 **Tipp:** Bei Problemen mit einzelnen Paketen: `pip install -r requirements.txt --ignore-installed`

---

## 4. Ollama installieren (lokale KI)

> ⚠️ **Optional:** Wenn du nur Cloud-KI (OpenAI, Anthropic, Mistral) nutzen willst, überspringe diesen Schritt.

### Ollama installieren

```bash
# Ollama installieren
curl -fsSL https://ollama.com/install.sh | sh

# Service starten
sudo systemctl start ollama
sudo systemctl enable ollama

# Status prüfen
systemctl status ollama
```

### Modelle herunterladen

```bash
# PFLICHT: Embedding-Modell (für semantische Suche)
ollama pull all-minilm:22m      # 46 MB, schnell

# EMPFOHLEN: Analyse-Modell
ollama pull llama3.2:1b         # 1.3 GB, schnelle Analyse
ollama pull llama3.2:3b         # 2.0 GB, tiefere Analyse (optional)

# Prüfen
ollama list
```

**Modell-Übersicht:**

| Modell | Größe | Zweck | VRAM |
|--------|-------|-------|------|
| `all-minilm:22m` | 46 MB | Embeddings (semantische Suche) | < 1 GB |
| `llama3.2:1b` | 1.3 GB | Base-Analyse (schnell) | 2-3 GB |
| `llama3.2:3b` | 2.0 GB | Optimize-Analyse (tief) | 4-5 GB |
| `mxbai-embed-large` | 670 MB | Alternative Embeddings | 1-2 GB |

> 💡 **CPU-only:** Alle Modelle laufen auch ohne GPU, nur langsamer.

---

## 5. Konfiguration (.env)

### .env Datei erstellen

```bash
# Template kopieren
cp .env.example .env

# Bearbeiten
nano .env
```

### Minimale Konfiguration

```dotenv
# ═══════════════════════════════════════════════════════════════
# PFLICHT
# ═══════════════════════════════════════════════════════════════
FLASK_SECRET_KEY=                    # Generiere mit: python3 -c "import secrets; print(secrets.token_hex(32))"

# ═══════════════════════════════════════════════════════════════
# KI-BACKEND (wähle eins)
# ═══════════════════════════════════════════════════════════════
AI_BACKEND=ollama                    # ollama | openai | anthropic | mistral
OLLAMA_BASE_URL=http://localhost:11434

# Cloud-KI API Keys (nur wenn AI_BACKEND entsprechend gesetzt)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# MISTRAL_API_KEY=...

# ═══════════════════════════════════════════════════════════════
# WEB-SERVER
# ═══════════════════════════════════════════════════════════════
WEB_HOST=127.0.0.1                   # 0.0.0.0 für LAN-Zugriff
WEB_PORT=5000
FLASK_DEBUG=false                    # true nur für Development

# ═══════════════════════════════════════════════════════════════
# HTTPS & SECURITY
# ═══════════════════════════════════════════════════════════════
FORCE_HTTPS=false                    # true für HTTPS-Redirect
SESSION_COOKIE_SECURE=false          # true wenn HTTPS
BEHIND_REVERSE_PROXY=false           # true hinter Nginx/Caddy

# ═══════════════════════════════════════════════════════════════
# DATENBANK
# ═══════════════════════════════════════════════════════════════
DATABASE_PATH=emails.db
```

### Secret Key generieren

```bash
# Generiere sicheren Key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Kopiere Ausgabe in .env als FLASK_SECRET_KEY
```

> ⚠️ **Wichtig:** Die `.env` enthält **KEINE** Mail-Passwörter! Diese werden über das Web-UI eingegeben und **verschlüsselt** in der DB gespeichert (Zero-Knowledge-Architektur).

---

## 6. Datenbank initialisieren

### Flask-Session Verzeichnis

```bash
# Für Server-Side Sessions (Zero-Knowledge)
mkdir -p .flask_sessions
chmod 700 .flask_sessions
```

### Datenbank + Migrationen

```bash
# Datenbank initialisieren
python3 -m src.00_main --init-db

# Migrationen anwenden
alembic upgrade head
```

### Verifizieren

```bash
# Tabellen prüfen
sqlite3 emails.db "SELECT name FROM sqlite_master WHERE type='table';"
```

**Erwartete Tabellen:**

```
users
mail_accounts
raw_emails
processed_emails
email_tags
email_tag_assignments
auto_rules
invited_emails
service_tokens
recovery_codes
alembic_version
```

---

## 7. App starten

### Development (HTTP)

```bash
# venv aktivieren
source venv/bin/activate

# Server starten
python3 -m src.00_main --serve
```

Öffne: **http://localhost:5000**

### Development mit HTTPS

```bash
python3 -m src.00_main --serve --https
```

Öffne: **https://localhost:5001** (Browser-Warnung akzeptieren)

---

## 8. Erste Schritte nach dem Start

### 8.1 Account registrieren

1. Öffne **http://localhost:5000/register**
2. Erstelle Account:
   - **Benutzername:** 3-80 Zeichen
   - **E-Mail:** Deine Email
   - **Passwort:** Mindestens 24 Zeichen

> ⚠️ **Wichtig:** Das Passwort ist dein **Master-Passwort**. Bei Verlust sind deine Daten **unwiederbringlich verloren**!

> **ℹ️ Hinweis:** Der **erste User kann sich frei registrieren**. Alle weiteren User benötigen einen Whitelist-Eintrag (siehe Abschnitt "User-Verwaltung").

### 8.2 Zwei-Faktor-Authentifizierung

Nach der Registrierung: 2FA-Setup (**Pflicht!**):

1. Öffne Authenticator-App (Google Authenticator, Authy)
2. Scanne QR-Code
3. Gib 6-stelligen Code ein
4. **Speichere Recovery-Codes sicher ab!**

### 8.3 Mail-Account hinzufügen

1. **⚙️ Einstellungen** → **"Neuen Account hinzufügen"**
2. Fülle Formular aus

**Beispiel GMX:**

| Feld | Wert |
|------|------|
| Name | GMX Postfach |
| IMAP-Server | imap.gmx.net |
| IMAP-Port | 993 |
| Verschlüsselung | SSL |
| Benutzername | deine@email.de |
| Passwort | Email-Passwort |
| SMTP-Server | smtp.gmx.net |
| SMTP-Port | 587 |

3. **"Verbindung testen"** → **"Speichern"**

### 8.4 KI-Modelle konfigurieren

**⚙️ Einstellungen** → **KI-Einstellungen**

| Einstellung | Empfehlung | Zweck |
|-------------|------------|-------|
| **Embedding Model** | all-minilm:22m | Semantische Suche |
| **Base Model** | llama3.2:1b | Schnelle Analyse |
| **Optimize Model** | llama3.2:3b | Tiefe Analyse |

### 8.5 Emails abrufen

1. **⚙️ Einstellungen** → **"Jetzt abrufen"**
2. Warte auf Fortschrittsbalken
3. **📊 Dashboard** → Emails erscheinen in Matrix!

---

## 9. User-Verwaltung

### Invite-Whitelist

Nach der ersten Registration ist die Registrierung **geschlossen**. Weitere User nur per CLI:

```bash
# Email zur Whitelist hinzufügen
python3 scripts/manage_users.py add-whitelist max@example.com

# Whitelist anzeigen
python3 scripts/manage_users.py list-whitelist

# Email entfernen
python3 scripts/manage_users.py remove-whitelist max@example.com
```

User kann sich nun mit der **exakten Email** registrieren.

### IMAP-Diagnostics Zugriff

Die `/imap-diagnostics` Route ist standardmäßig **deaktiviert**:

```bash
# Zugriff aktivieren
python3 scripts/manage_users.py enable-diagnostics admin@example.com

# Liste anzeigen
python3 scripts/manage_users.py list-diagnostics

# Zugriff widerrufen
python3 scripts/manage_users.py disable-diagnostics admin@example.com
```

---

## 10. Installation verifizieren

```bash
# 1. Datenbank existiert?
ls -lh emails.db

# 2. Tabellen korrekt?
sqlite3 emails.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"
# → Sollte >= 11 sein

# 3. Alembic aktuell?
sqlite3 emails.db "SELECT version_num FROM alembic_version;"

# 4. Ollama läuft?
curl http://localhost:11434/api/tags

# 5. Web-App erreichbar?
curl -s http://localhost:5000 | head -5
```

---

## 11. Production Deployment

### Gunicorn

```bash
gunicorn -c config/gunicorn.conf.py "src.01_web_app:create_app()"
```

### Systemd Service

```bash
# Service kopieren
sudo cp config/mail-helper.service /etc/systemd/system/

# Pfade anpassen
sudo nano /etc/systemd/system/mail-helper.service

# Aktivieren
sudo systemctl daemon-reload
sudo systemctl enable mail-helper
sudo systemctl start mail-helper
```

### Reverse Proxy

```bash
# .env anpassen
BEHIND_REVERSE_PROXY=true
SESSION_COOKIE_SECURE=true
FORCE_HTTPS=true
```

Siehe **[DEPLOYMENT.md](./DEPLOYMENT.md)** für Nginx/Caddy-Konfiguration.

---

## 12. Troubleshooting

### "No module named 'src'"

```bash
# Richtiges Verzeichnis?
pwd

# venv aktiv?
which python  # Sollte venv/bin/python zeigen
source venv/bin/activate
```

### "FLASK_SECRET_KEY not set"

```bash
# .env existiert?
cat .env | grep FLASK_SECRET_KEY

# Key generieren
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### "Ollama connection refused"

```bash
# Ollama läuft?
systemctl status ollama

# Starten
sudo systemctl start ollama
```

### "no such column" (DB-Fehler)

```bash
# Migrationen ausführen
alembic upgrade head

# Notfall: DB neu (löscht Daten!)
rm emails.db emails.db-wal emails.db-shm
python3 -m src.00_main --init-db
alembic upgrade head
```

### "SQLITE_BUSY"

```bash
# WAL-Checkpoint
sqlite3 emails.db "PRAGMA wal_checkpoint(TRUNCATE);"

# WAL prüfen
python3 scripts/verify_wal_mode.py
```

### "Login funktioniert nicht"

```bash
# Session-Dateien löschen
rm -rf .flask_sessions/*
```

### "2FA-Code nicht akzeptiert"

1. **Zeit prüfen:** Handy-Uhr korrekt?
2. **Recovery-Code:** Einen der 10 Backup-Codes nutzen
3. **Neuer Account:** Falls alles fehlschlägt

---

*Stand: Januar 2026 | KI-Mail-Helper v1.0.0*
