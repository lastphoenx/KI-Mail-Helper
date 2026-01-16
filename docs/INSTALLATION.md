# 📦 KI-Mail-Helper – Installationsanleitung

**Version:** 2.0.0 (Multi-User Edition)  
**Stand:** Januar 2026

---

## Inhaltsverzeichnis

1. [Voraussetzungen](#1-voraussetzungen)
2. [PostgreSQL einrichten](#2-postgresql-einrichten)
3. [Redis einrichten](#3-redis-einrichten)
4. [Ollama installieren](#4-ollama-installieren)
5. [Anwendung installieren](#5-anwendung-installieren)
6. [Konfiguration](#6-konfiguration)
7. [Datenbank initialisieren](#7-datenbank-initialisieren)
8. [App starten (Development)](#8-app-starten-development)
9. [Production Deployment](#9-production-deployment)
10. [Erste Schritte](#10-erste-schritte)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Voraussetzungen

### System-Anforderungen

| Komponente | Minimum | Empfohlen |
|------------|---------|-----------|
| **OS** | Debian 11 / Ubuntu 22.04 | Debian 12 / Ubuntu 24.04 |
| **Python** | 3.11 | 3.12+ |
| **RAM** | 4 GB | 8-16 GB (für Ollama) |
| **Disk** | 10 GB | 50 GB (für Ollama-Modelle) |
| **PostgreSQL** | 14 | 17 |
| **Redis** | 6 | 8 |

### System-Pakete installieren

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y \
    python3 python3-pip python3-venv \
    postgresql postgresql-contrib \
    redis-server \
    git curl build-essential \
    libpq-dev  # Für psycopg2
```

---

## 2. PostgreSQL einrichten

### Installation prüfen

```bash
sudo systemctl status postgresql
```

### Datenbank und User erstellen

> ⚠️ **Wichtig:** Merke dir das Passwort! Du brauchst es später für die `.env` Datei.

```bash
# Wähle ein sicheres Passwort (z.B. mit: openssl rand -base64 24)
DB_PASSWORD="dein_sicheres_passwort_hier"

sudo -u postgres psql << EOF
CREATE USER mail_helper WITH PASSWORD '$DB_PASSWORD';
CREATE DATABASE mail_helper OWNER mail_helper;
GRANT ALL PRIVILEGES ON DATABASE mail_helper TO mail_helper;
\q
EOF

echo "Dein DB-Passwort für .env: $DB_PASSWORD"
```

### Verbindung testen

```bash
# Mit dem eben vergebenen Passwort:
psql -U mail_helper -h localhost -d mail_helper -c "SELECT version();"
```

---

## 3. Redis einrichten

### Installation prüfen

```bash
sudo systemctl status redis-server
```

### Verbindung testen

```bash
redis-cli ping
# Antwort: PONG
```

---

## 4. Ollama installieren

> ⚠️ **Optional:** Nur wenn du lokale KI nutzen willst. Für Cloud-KI (OpenAI, etc.) überspringe diesen Schritt.

### Ollama installieren

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama
sudo systemctl start ollama
```

### Modelle herunterladen

```bash
# PFLICHT: Embedding-Modell
ollama pull all-minilm:22m      # 46 MB

# EMPFOHLEN: Analyse-Modelle
ollama pull llama3.2:1b         # 1.3 GB (schnell)
ollama pull llama3.2:3b         # 2.0 GB (besser)

# Prüfen
ollama list
```

---

## 5. Anwendung installieren

### Repository klonen

```bash
cd /opt  # oder /home/$USER/projects
git clone https://github.com/dein-username/KI-Mail-Helper.git
cd KI-Mail-Helper
```

### Virtual Environment erstellen

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### Dependencies installieren

```bash
pip install -r requirements.txt
```

---

## 6. Konfiguration

### .env Datei erstellen

```bash
cp .env.example .env
nano .env
```

### Minimale Konfiguration

```dotenv
# ═══════════════════════════════════════════════════════════════
# PFLICHT: Datenbank & Cache
# ═══════════════════════════════════════════════════════════════
# ⚠️ WICHTIG: Ersetze 'dein_passwort' mit dem Passwort aus Schritt 2!
DATABASE_URL=postgresql://mail_helper:dein_passwort@localhost:5432/mail_helper
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ═══════════════════════════════════════════════════════════════
# PFLICHT: Sicherheit
# ═══════════════════════════════════════════════════════════════
SECRET_KEY=  # Generiere mit: python3 -c "import secrets; print(secrets.token_hex(32))"
FLASK_ENV=production

# ═══════════════════════════════════════════════════════════════
# PFLICHT: Feature Flags
# ═══════════════════════════════════════════════════════════════
USE_POSTGRESQL=true
USE_LEGACY_JOBS=false
USE_BLUEPRINTS=1

# ═══════════════════════════════════════════════════════════════
# KI-Backend (wähle eins oder mehrere)
# ═══════════════════════════════════════════════════════════════
AI_BACKEND=ollama
OLLAMA_BASE_URL=http://localhost:11434

# Optional: Cloud-KI API Keys
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# MISTRAL_API_KEY=...

# ═══════════════════════════════════════════════════════════════
# Web-Server
# ═══════════════════════════════════════════════════════════════
WEB_HOST=127.0.0.1
WEB_PORT=5000
FORCE_HTTPS=true
SESSION_COOKIE_SECURE=true
BEHIND_REVERSE_PROXY=true
```

### Secret Key generieren

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Kopiere Ausgabe in .env als SECRET_KEY
```

---

## 7. Datenbank initialisieren

> ℹ️ **Hinweis:** Die Datenbank wird automatisch durch Alembic-Migrationen erstellt. Du musst nur PostgreSQL User und Datenbank vorher angelegt haben (Abschnitt 2).

### Flask-Session Verzeichnis

```bash
mkdir -p .flask_sessions
chmod 700 .flask_sessions
```

### Logs-Verzeichnis

```bash
mkdir -p logs
chmod 755 logs
```

### Migrationen ausführen

```bash
source venv/bin/activate
alembic upgrade head
```

Dies erstellt automatisch alle ~23 Tabellen (users, emails, email_tags, auto_rules, etc.) mit korrekten Indizes und Foreign Keys.

### Tabellen prüfen

```bash
psql -U mail_helper -h localhost -d mail_helper -c "\dt"
# Sollte ~23 Tabellen zeigen (users, emails, email_tags, ...)
```

---

## 7a. SQLite → PostgreSQL Migration (Optional)

> ⚠️ **Nur relevant** wenn du von einer älteren SQLite-Installation (v1.x) migrierst. Bei Neuinstallation überspringe diesen Abschnitt.

### Voraussetzungen

- Bestehende SQLite-Datenbank (`emails.db` oder `ki_mail_helper.db`)
- PostgreSQL bereits eingerichtet (Abschnitt 2)
- Migrationen ausgeführt (`alembic upgrade head`)

### Dry-Run (empfohlen)

```bash
source venv/bin/activate

# Nur prüfen, was migriert würde (keine Daten geschrieben)
python scripts/migrate_sqlite_to_postgresql.py \
  --source sqlite:///emails.db \
  --target "postgresql://mail_helper:DEIN_PASSWORT@localhost:5432/mail_helper" \
  --dry-run
```

### Echte Migration

```bash
# ⚠️ Backup vorher erstellen!
python scripts/migrate_sqlite_to_postgresql.py \
  --source sqlite:///emails.db \
  --target "postgresql://mail_helper:DEIN_PASSWORT@localhost:5432/mail_helper"
```

### Nach der Migration

```bash
# Verifizieren
psql -U mail_helper -h localhost -d mail_helper -c "SELECT COUNT(*) FROM users;"
psql -U mail_helper -h localhost -d mail_helper -c "SELECT COUNT(*) FROM raw_emails;"

# Alte SQLite-Datei archivieren (nicht löschen!)
mv emails.db emails.db.backup-$(date +%Y%m%d)
```

---

## 8. App starten (Development)

### Terminal 1: Flask App

```bash
source venv/bin/activate
python -m flask --app src run --host 127.0.0.1 --port 5000
```

### Terminal 2: Celery Worker

```bash
source venv/bin/activate
celery -A src.celery_app worker --loglevel=info
```

### Terminal 3: Celery Beat (Optional)

```bash
source venv/bin/activate
celery -A src.celery_app beat --loglevel=info
```

Öffne: **http://localhost:5000**

---

## 9. Production Deployment

### Systemd Services erstellen

**Flask App (`/etc/systemd/system/mail-helper.service`):**

```ini
[Unit]
Description=KI-Mail-Helper Web Application
After=network.target postgresql.service redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/KI-Mail-Helper
Environment="PATH=/opt/KI-Mail-Helper/venv/bin"
ExecStart=/opt/KI-Mail-Helper/venv/bin/gunicorn \
    -c config/gunicorn.conf.py \
    "src:create_app()"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Celery Worker (`/etc/systemd/system/mail-helper-worker.service`):**

```ini
[Unit]
Description=KI-Mail-Helper Celery Worker
After=network.target postgresql.service redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/KI-Mail-Helper
Environment="PATH=/opt/KI-Mail-Helper/venv/bin"
ExecStart=/opt/KI-Mail-Helper/venv/bin/celery \
    -A src.celery_app worker \
    --loglevel=info \
    --concurrency=4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Services aktivieren

```bash
sudo systemctl daemon-reload
sudo systemctl enable mail-helper mail-helper-worker
sudo systemctl start mail-helper mail-helper-worker
```

### Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name mail-helper.example.com;

    ssl_certificate /etc/letsencrypt/live/mail-helper.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mail-helper.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /opt/KI-Mail-Helper/static;
        expires 30d;
    }
}

server {
    listen 80;
    server_name mail-helper.example.com;
    return 301 https://$server_name$request_uri;
}
```

---

## 10. Erste Schritte

### 1. Account registrieren

1. Öffne **https://mail-helper.example.com/register**
2. Erstelle Account (erster User kann sich frei registrieren)
3. Richte 2FA ein (Pflicht!)
4. **Speichere Recovery-Codes!**

### 2. Mail-Account hinzufügen

1. Gehe zu **⚙️ Einstellungen**
2. Klicke **"Neuen Account hinzufügen"**
3. Gib IMAP/SMTP-Daten ein
4. Teste Verbindung

### 3. Emails abrufen

1. Klicke **"Jetzt abrufen"**
2. Warte auf Fortschrittsbalken
3. Emails erscheinen im Dashboard!

---

## 11. Troubleshooting

### "Connection refused" (PostgreSQL)

```bash
# PostgreSQL läuft?
sudo systemctl status postgresql

# Passwort korrekt?
psql -U mail_helper -h localhost -d mail_helper
```

### "Connection refused" (Redis)

```bash
# Redis läuft?
sudo systemctl status redis-server

# Test
redis-cli ping
```

### "No module named 'src'"

```bash
# Im richtigen Verzeichnis?
pwd  # Sollte /opt/KI-Mail-Helper zeigen

# venv aktiv?
source venv/bin/activate
which python  # Sollte venv/bin/python zeigen
```

### Celery Tasks starten nicht

```bash
# Worker läuft?
sudo systemctl status mail-helper-worker

# Logs prüfen
journalctl -u mail-helper-worker -f
```

### Migrationen fehlgeschlagen

```bash
# Aktuelle Version prüfen
alembic current

# Heads anzeigen
alembic heads

# Upgrade
alembic upgrade head
```

---

## Quick Reference

```bash
# Services
sudo systemctl status mail-helper
sudo systemctl status mail-helper-worker
sudo systemctl status postgresql
sudo systemctl status redis-server

# Logs
journalctl -u mail-helper -f
journalctl -u mail-helper-worker -f

# Datenbank
psql -U mail_helper -h localhost -d mail_helper

# Celery
celery -A src.celery_app inspect ping
celery -A src.celery_app inspect active
```

---

*Diese Anleitung gilt für KI-Mail-Helper v2.0 (Multi-User Edition) auf Debian/Ubuntu.*
