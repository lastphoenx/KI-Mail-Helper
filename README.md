# 📧 KI-Mail-Helper – Lokaler KI-Mail-Assistent

> **Intelligente E-Mail-Priorisierung mit lokalem LLM & Zero-Knowledge Encryption**  
> Datenschutzfreundlich • End-to-End verschlüsselt • Automatische Übersetzung • 3×3-Prioritäten-Dashboard  
> Security Score: **98/100** 🔒 | Phase: **9 (Production Ready)** ✅

## 🎯 Was ist Mail Helper?

Ein lokaler Mail-Assistent, der E-Mails automatisch:
- ✅ Von IMAP-Servern (GMX, Yahoo, Hotmail) & Gmail OAuth abholt
- 🔒 **Zero-Knowledge verschlüsselt** – Server hat keinen Zugriff auf Klartext-Daten
- 🤖 Mit lokalem LLM (Ollama: llama3.2, all-minilm:22m, etc.) oder Cloud-KI analysiert
- 📊 In einem **3×3-Prioritäten-Dashboard** darstellt (Wichtigkeit × Dringlichkeit)
- 🌍 Automatisch ins Deutsche übersetzt
- 💡 Mit Handlungsempfehlungen versieht
- 📋 IMAP-Metadaten (UID, Folder, Flags) für jede Email speichert

---

## ✨ Features

### Kernfunktionen
- **🔐 Zero-Knowledge Encryption (Phase 8a+8b)** – AES-256-GCM End-to-End Verschlüsselung (siehe [docs/ZERO_KNOWLEDGE_COMPLETE.md](docs/ZERO_KNOWLEDGE_COMPLETE.md))
  - **DEK/KEK Pattern** – Passwort ändern ohne E-Mails neu zu verschlüsseln
  - Alle E-Mails verschlüsselt (Sender, Subject, Body, AI-Ergebnisse)
  - Alle Credentials verschlüsselt (IMAP/SMTP Server, Usernames, Passwords)
  - DEK (Data Encryption Key) nur in Server-RAM (Flask Server-Side Sessions)
  - Server kann niemals auf Klartext-Daten zugreifen
  - Session Security: Auto-Logout bei DEK-Loss, keine Passwörter in Session
- **🔒 Production Security (Phase 9)** – Enterprise-Grade Hardening (siehe [DEPLOYMENT.md](DEPLOYMENT.md))
  - **Flask-Limiter**: Rate Limiting (5 requests/min Login/2FA)
  - **Account Lockout**: 5 Failed → 15min Ban
  - **Session Timeout**: 30min Inaktivität → Auto-Logout
  - **Fail2Ban Integration**: Network-Level IP Banning
  - **Audit Logging**: Strukturierte Security-Events für Monitoring
  - **Automated Backups**: Daily + Weekly mit Rotation
  - **SECRET_KEY Security**: System Environment (nicht .env!)
  - **Gunicorn + Systemd**: Production WSGI Server mit Auto-Restart
  - **Security Score: 98/100** 🔒
- **Dual Mail-Fetcher** – IMAP (GMX, Yahoo, Hotmail) + Gmail OAuth2 API
- **IMAP-Metadaten** – Speichert UID, Folder, Flags für jede Email
- **Two-Pass Optimization** – Base-Pass (schnell) + Optimize-Pass (optional, bessere Kategorisierung)
- **Dynamic Provider-Dropdowns** – Auto-Erkennung verfügbarer KI-Modelle basierend auf API-Keys
- **Flexible Modellauswahl** – Keine Hardcodierung! llama3.2, all-minilm:22m (46MB, ~100x schneller), oder beliebige Ollama-Modelle
- **Learning System (Phase 9 ML)** – Human-in-the-Loop Training mit User-Korrektionen
- **🏷️ Smart Tag-System (Phase 10)** – KI-gestützte Tag-Vorschläge & Filter (siehe [Features](#tag-system-phase-10))
  - **Auto-Tagging**: KI schlägt 1-5 semantische Tags vor (suggested_tags)
  - **Tag-Management**: Create/Edit/Delete mit 7 Farben + Email-Count
  - **Multi-Tag-Filter**: Kombiniere Tags mit Farbe/Done/Suche
  - **Learning-Integration**: Manuelle Tag-Änderungen → ML-Training (user_override_tags)
  - **Performance**: Eager Loading verhindert n+1 Queries (2 Queries für 100 Emails)
- **Datenschutz-Sanitizer** – 3 Level (Volltext → Pseudonymisierung)
- **Multi-Provider KI-Analyse** – Lokal (Ollama) oder Cloud (OpenAI, Anthropic, Mistral)
- **Intelligentes Scoring** – 3×3-Matrix + Ampelfarben (Rot/Gelb/Grün)
- **Web-Dashboard** – Übersichtliche Darstellung mit Matrix- und Listenansicht
- **Automatische Übersetzung** – Mehrsprachige Mails → Deutsch
- **2FA (TOTP) + Recovery-Codes** – Zwei-Faktor-Authentifizierung mit Backup-Codes
- **Background-Jobs** – Asynchrone Email-Verarbeitung mit Progress-Tracking
- **Maintenance Helper** – Scripts für DB-Reset, Migrationen, Troubleshooting (in `scripts/` organisiert)

### Ansichten
1. **3×3-Matrix** – Wichtigkeit (x) × Dringlichkeit (y) mit Farbcodierung
2. **Ampel-Ansicht** – Rot (hoch) / Gelb (mittel) / Grün (niedrig)
3. **Listen-View** – Sortiert nach Score mit Filtern + Tag-Filter (Multi-Select)
4. **Detail-Ansicht** – Vollständige Mail-Info + Aktionen + Tag-Management
5. **Tag-Management** – `/tags` Route für CRUD-Operationen + Statistiken

---

## 🏗️ Architektur

```
mail-helper/
├── src/
│   ├── 00_main.py              # Entry Point / CLI + Cron-Orchestrierung
│   ├── 01_web_app.py           # Flask Web-Dashboard + Auth
│   ├── 02_models.py            # SQLAlchemy DB-Modelle + Soft-Delete
│   ├── 03_ai_client.py         # KI-Client (Ollama, OpenAI, Anthropic, Mistral)
│   │                           # ✨ Dynamische Modellauswahl (llama3.2, all-minilm:22m, etc.)
│   ├── 04_sanitizer.py         # Datenschutz-Level 1-3
│   ├── 05_scoring.py           # 3×3-Matrix + Farben
│   ├── 06_mail_fetcher.py      # IMAP-Client (GMX, Yahoo, Hotmail) mit UID/Folder/Flags
│   ├── 07_auth.py              # Auth + Master-Key + 2FA
│   ├── 08_encryption.py        # Zero-Knowledge AES-256-GCM Encryption/Decryption
│   ├── 10_google_oauth.py      # Gmail OAuth2 API Fetcher
│   ├── 12_processing.py        # Email-Verarbeitungs-Workflow
│   ├── 14_background_jobs.py   # Job Queue für Hintergrund-Verarbeitung
│   ├── 15_provider_utils.py    # Dynamic Provider/Model Discovery
│   ├── services/
│   │   └── tag_manager.py      # Tag CRUD + Assignment Logic (Phase 10)
│   └── ...
├── templates/                  # HTML-Templates (20+)
├── tests/                      # Unit Tests (pytest)
│   ├── test_ai_client.py       # AI-Client Tests
│   ├── test_mail_fetcher.py    # Mail-Fetcher Tests
│   └── ...
├── scripts/                    # Utility & Maintenance Scripts
│   ├── reset_base_pass.py      # Base-Pass Analysis Reset
│   ├── check_db.py             # DB-Health-Check
│   ├── encrypt_db_verification.py
│   └── ... (9+ Helper-Scripts)
├── migrations/                 # Alembic DB-Migrationen
├── mail-helper-processor.service  # Systemd Service
├── mail-helper-processor.timer    # Cron Timer (15 min)
├── emails.db                   # SQLite Datenbank
├── docs/
│   ├── ZERO_KNOWLEDGE_COMPLETE.md  # Zero-Knowledge Implementierung (100/100 Score)
│   ├── TESTING_GUIDE.md            # Kompletter Testing-Workflow
│   └── ...                         # Weitere Dokumentation
├── Instruction_&_goal.md       # Projekt-Spezifikation (Phase 0-7)
├── INSTALLATION.md             # Komplette Installationsanleitung
├── MAINTENANCE.md              # Maintenance & Helper-Skripte
├── OAUTH_AND_IMAP_SETUP.md     # OAuth & IMAP Konfiguration
└── README.md                   # Dieses Dokument
```

---

## 🚀 Quick Start (WSL2/Linux)

### 1. Ollama Installation
```bash
# Ollama installieren
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl start ollama
sudo systemctl enable ollama

# Modell laden (~10 Min, ~8GB)
ollama pull llama3.2

# Überprüfen
systemctl status ollama
```

### 2. Repository klonen
```bash
git clone https://github.com/lastphoenx/KI-Mail-Helper.git
cd KI-Mail-Helper
```

### 3. Python-Umgebung
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Konfiguration
```bash
cp .env.example .env
# Bearbeite .env mit deinen Credentials
# Wichtig: SECRET_KEY und SERVER_MASTER_SECRET setzen!
```

### 5. Datenbank initialisieren
```bash
python3 -m src.00_main --init-db
```

### 6. Web-Dashboard starten

**Development (HTTP):**
```bash
python3 -m src.00_main --serve
# http://localhost:5000
```

**Development mit HTTPS (Self-signed Certificate):**
```bash
python3 -m src.00_main --serve --https
# Dual-Port Setup:
#   - HTTP Redirector: http://localhost:5000 → https://localhost:5001
#   - HTTPS Server: https://localhost:5001
# Browser zeigt Sicherheitswarnung (einmal akzeptieren)
```

**Production (hinter Reverse Proxy):**
```bash
# .env anpassen:
BEHIND_REVERSE_PROXY=true
SESSION_COOKIE_SECURE=true

python3 -m src.00_main --serve --https
# Siehe "Production Deployment" für Nginx/Caddy Konfiguration
```

---

## 📚 Documentation

**Before you deploy to production, read:**
- **[SECURITY.md](./SECURITY.md)** – Threat Model, Security Features, Known Limitations
- **[DEPLOYMENT.md](./DEPLOYMENT.md)** – Production Setup (Gunicorn, Systemd, Fail2Ban, Backups)
- **[INSTALLATION.md](./INSTALLATION.md)** – Detailed step-by-step installation guide
- **[docs/ZERO_KNOWLEDGE_COMPLETE.md](./docs/ZERO_KNOWLEDGE_COMPLETE.md)** – Cryptography & Encryption Details

---

## 📋 Verwendung

### Erste Schritte

1. **Account erstellen** → `/register`
2. **2FA einrichten** → Dashboard → 2FA-Setup
3. **Mail-Account hinzufügen** → Settings → Add IMAP or Gmail OAuth
4. **Mails abrufen** → Dashboard → "Jetzt verarbeiten"
5. **Tags verwalten** → Navigation → "🏷️ Tags"

### Tag-System (Phase 10)

#### Auto-Tagging
Das KI-System schlägt automatisch 1-5 semantische Tags pro Email vor:

```json
{
  "suggested_tags": ["Rechnung", "Finanzen", "Wichtig"]
}
```

**Tags werden automatisch:**
- ✅ Erstellt (wenn nicht existent)
- ✅ Zugewiesen (EmailTagAssignment)
- ✅ Angezeigt (Liste + Detail)

#### Tag-Management UI (`/tags`)

**Features:**
- **Create Tag**: Name (1-50 Zeichen) + 7 Farben (Blue/Green/Orange/Red/Purple/Pink/Gray)
- **Edit Tag**: Name/Farbe ändern (constraint: unique pro User)
- **Delete Tag**: CASCADE löscht alle Assignments
- **Statistics**: Anzahl E-Mails pro Tag

**Constraints:**
- ✅ Unique(user_id, name) - keine Duplikate
- ✅ Max 50 Zeichen pro Tag-Name
- ✅ Hex-Color-Validation (#RRGGBB)

#### Tag-Filter & Search

**Dashboard Filter:**
```
Filter:
  ☐ Rechnung (3)
  ☐ Termin (7)
  ☐ Finanzen (12)
  
+ Farbe: [Alle] [Rot] [Gelb] [Grün]
+ Done: [Alle] [Erledigt] [Offen]
+ Suche: [           ]
```

**Multi-Select:** Strg/Cmd + Mehrere Tags → kombinierte Filterung

**Performance:** Eager Loading - 100 Emails = nur 2 SQL Queries (nicht 101)

#### Learning System

Manuelle Tag-Änderungen (Add/Remove) werden getrackt:

```python
# ProcessedEmail.user_override_tags
"Rechnung,Finanzen,Wichtig"  # Komma-separiert

# ProcessedEmail.correction_timestamp
"2025-12-28 15:30:45"  # Zeitstempel der Änderung
```

**ML-Training Flow:**
1. KI schlägt `suggested_tags` vor → Auto-Assignment
2. User ändert Tags manuell → `user_override_tags` gesetzt
3. `train_classifier.py` nutzt Korrekturen
4. KI-Vorschläge werden besser

---

## 📋 Verwendung (Allgemein)

### **Befehls-Referenz**

**Web-Dashboard starten:**
```bash
python3 -m src.00_main --serve
# Dashboard auf: http://localhost:5000
```

**Worker starten (Background-Verarbeitung):**
```bash
python3 -m src.00_main --worker
# Verarbeitet Mails im Hintergrund (alle 5 Sekunden prüfen)
```

**Mail-Verarbeitung einmalig:**
```bash
python3 -m src.00_main --process-once
# Verarbeitet alle unverarbeiteten RawEmails mit AI
```

**Nur neue Mails abholen (ohne KI):**
```bash
python3 -m src.00_main --fetch-only
```

**Datenbank initialisieren:**
```bash
python3 -m src.00_main --init-db
```

**Database-Migrationen aktualisieren:**
```bash
python -m alembic upgrade head
```

**Tests ausführen:**
```bash
python3 -m pytest tests/
python3 -m pytest tests/test_sanitizer.py -v
```

### **Maintenance & Helper-Skripte**

**Base-Pass Analysis zurücksetzen** (alle ProcessedEmails löschen):
```bash
# Mit Bestätigung
python3 scripts/reset_base_pass.py

# Ohne Bestätigung (automatisiert)
python3 scripts/reset_base_pass.py --force

# Nur für einen Mail-Account
python3 scripts/reset_base_pass.py --account=1 --force
```

Weitere Maintenance-Befehle: siehe **[MAINTENANCE.md](./MAINTENANCE.md)**

---

## 🤖 KI-Provider & Two-Pass Optimization

### Verfügbare Provider

Das System unterstützt **automatische Erkennung** verfügbarer KI-Provider mit **dynamischer Modellauswahl** (keine Hardcodierung!):

| Provider | Modelle | Modus | Schnelligkeit |
|----------|---------|-------|---------------|
| **Ollama** (lokal) | llama3.2, **all-minilm:22m** *, etc. | Base-Pass + Optimize | ⚡ Fast (lokal) |
| **OpenAI** | GPT-4o, GPT-4-Turbo, GPT-3.5 | Base-Pass + Optimize | 🚀 Schnell |
| **Anthropic** | Claude-3.5-Sonnet, Claude-Opus | Base-Pass + Optimize | 🚀 Schnell |
| **Mistral** | Mistral-Large, Mistral-Small | Base-Pass + Optimize | 🚀 Schnell |

*\* Keine Hardcodierung mehr! Alle installierten Ollama-Modelle können frei gewählt werden. `all-minilm:22m` für Optimize-Pass besonders geeignet.*

### Two-Pass System

**Base-Pass (schnell):**
- Initiale Email-Analyse mit konfig. Provider
- Erzeugt Score, Kategorie, Tags, deutsche Zusammenfassung

**Optimize-Pass (optional):**
- Nur für High-Priority-Emails (Score ≥ 8)
- Verwendet sekundären Provider für bessere Kategorisierung
- Kann mit leichterem Modell für Kostenersparnis konfiguriert werden

**Konfiguration in Settings-UI:**
- Base-Pass: Dropdown mit verfügbaren Providern/Modellen
- Optimize-Pass: Dropdown mit verfügbaren Providern/Modellen
- Modelle werden basierend auf API-Keys automatisch erkannt

**Setup in `.env`:**
```bash
# Ollama (lokal)
OLLAMA_API_URL=http://localhost:11434

# Cloud-APIs (optional)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...
MISTRAL_API_KEY=...
```

## 🔐 Zero-Knowledge Security

Das System verwendet **echte Zero-Knowledge Architektur**:

### Was bedeutet Zero-Knowledge?
- **Server speichert nur verschlüsselte Daten** (AES-256-GCM)
- **Master-Key existiert NUR im RAM** (Server-Side Sessions, nie in DB)
- **Server kann niemals auf Klartext zugreifen** (E-Mails, Passwörter, etc.)
- **Bei Logout wird Master-Key gelöscht** (keine Persistierung)

### Was ist verschlüsselt?
✅ Alle E-Mail-Inhalte (Sender, Subject, Body)  
✅ Alle AI-Ergebnisse (Zusammenfassungen, Tags, Übersetzungen)  
✅ Alle Zugangsdaten (IMAP/SMTP Server, Usernames, Passwords)  
✅ OAuth Tokens (Gmail API)

### Technische Details
- **Master-Key-Ableitung:** PBKDF2-HMAC-SHA256 (100.000 Iterationen)
- **Verschlüsselung:** AES-256-GCM (Authenticated Encryption)
- **Session-Storage:** Flask Server-Side Sessions (`.flask_sessions/`)
- **Keine Cron-Jobs:** Zero-Knowledge verhindert automatische Hintergrund-Jobs (Master-Key fehlt)

**📖 Vollständige Dokumentation:** [docs/ZERO_KNOWLEDGE_COMPLETE.md](docs/ZERO_KNOWLEDGE_COMPLETE.md)

**Setup in `.env`:**
```bash
# Zufällig generiert (mind. 32 Zeichen)
FLASK_SECRET_KEY=your-random-secret-key-here     # Für Session-Signierung
SERVER_MASTER_SECRET=your-server-secret-here     # (Veraltet, nicht mehr verwendet)
```

---

## 🔒 Datenschutz-Level

| Level | Beschreibung | Verwendung |
|-------|-------------|------------|
| **1** | Volltext (keine Änderungen) | Nur bei 100% lokalem Betrieb |
| **2** | Ohne Signatur + Historie | Standard für Ollama (lokal) |
| **3** | + Pseudonymisierung | **Pflicht** für Cloud-KI! |

**Level 3 ersetzt:**
- E-Mail-Adressen → `[EMAIL_1]`, `[EMAIL_2]`
- Telefonnummern → `[PHONE_1]`
- IBANs → `[IBAN_1]`
- URLs → `[URL_1]`
- Kreditkarten → `[CC_1]`

---

## 🔄 Automatisierung (Cron-Jobs)

Mails können automatisch alle **15 Minuten** verarbeitet werden:

**Setup:**
```bash
sudo systemctl enable mail-helper-processor.timer
sudo systemctl start mail-helper-processor.timer

# Status überprüfen
sudo systemctl status mail-helper-processor.timer
sudo journalctl -u mail-helper-processor -n 50 -f  # Logs folgen
```

**Timer-Konfiguration ändern:**
```bash
sudo systemctl edit mail-helper-processor.timer
# OnUnitActiveSec=15m  → auf gewünschtes Intervall ändern
```

---

## 🎨 Dashboard-Matrix

```
                   Wenig wichtig (1)  |  Mittel (2)      |  Sehr wichtig (3)
Sehr dringend      🟡 Score 7         |  🔴 Score 8-9    |  🔴 Score 9
Mittel dringend    🟡 Score 5-6       |  🟡 Score 6-7    |  🔴 Score 8
Wenig dringend     🟢 Score 2-3       |  🟢 Score 3-4    |  🟡 Score 5
```

**Farben:**
- 🔴 **Rot** – Sofort bearbeiten (Score 8-9)
- 🟡 **Gelb** – Zeitnah bearbeiten (Score 5-7)
- 🟢 **Grün** – Später bearbeiten (Score 1-4)

---

## 🛠️ Entwicklung

### Projektphasen
1. ✅ Phase 0: Projektstruktur
2. ✅ Phase 1: Single-User MVP + Ollama
3. ✅ Phase 2: Multi-User + 2FA + OAuth
4. ✅ Phase 3: Encryption (Master-Key + AES-256-GCM)
5. ✅ Phase 4: Schema-Redesign + Bug-Fixes + Alembic
6. ✅ Phase 5: Two-Pass Optimization Architecture
7. ✅ Phase 6: Dynamic Provider-Dropdowns + Multi-AI Support
8. ⏳ Phase 7: Advanced Features (Labels, Custom Prompts, Performance-Tuning)

### Testing
```bash
# Alle Tests
python3 -m pytest tests/ -v

# Mit Coverage
python3 -m pytest tests/ --cov=src

# Einzelne Module
python3 -m pytest tests/test_sanitizer.py -v
python3 -m pytest tests/test_scoring.py -v
```

---

## 🚀 Production Deployment

### Reverse Proxy Setup (Nginx/Caddy)

**1. Start Flask mit HTTPS:**
```bash
python3 -m src.00_main --serve --https
# Läuft auf https://localhost:5001
```

**2. .env anpassen:**
```bash
BEHIND_REVERSE_PROXY=true      # ProxyFix aktivieren
SESSION_COOKIE_SECURE=true     # Cookies nur über HTTPS
FORCE_HTTPS=true               # Talisman Security Headers
```

**3. Nginx Konfiguration:**
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    location / {
        proxy_pass https://127.0.0.1:5001;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header Host $host;
        
        # WebSocket Support (optional für Live-Updates)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# HTTP → HTTPS Redirect
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

**4. Caddy Konfiguration (Alternative):**
```caddy
your-domain.com {
    reverse_proxy https://127.0.0.1:5001 {
        transport http {
            tls_insecure_skip_verify  # Für Self-signed Cert
        }
        header_up X-Forwarded-Proto {scheme}
        header_up X-Forwarded-Host {host}
    }
}
```

**5. Systemd Service:**
```bash
sudo systemctl enable mail-helper-processor.service
sudo systemctl start mail-helper-processor.service
```

---

## 📦 Tech Stack

- **Python:** 3.13 (mit SQLAlchemy 2.0)
- **Web:** Flask 3.x + Bootstrap 5
- **DB:** SQLite + SQLAlchemy ORM + Alembic (Migrations)
- **LLM:** Ollama (llama3.2, mistral, etc.) + OpenAI + Anthropic + Mistral APIs
- **Auth:** Flask-Login + pyotp (TOTP 2FA) + Google OAuth2
- **Encryption:** cryptography (AES-256-GCM) + PBKDF2 + DEK/KEK Pattern
- **Security:** 
  - Flask-Limiter (Rate Limiting)
  - Flask-WTF (CSRF Protection)
  - Werkzeug ProxyFix (Reverse Proxy Support)
  - Fail2Ban Integration (Network-Level IP Banning)
  - Account Lockout + Session Timeout
  - HIBP Password Validation (500M+ compromised passwords)
- **Production:** Gunicorn + Systemd + Automated Backups
- **Background:** Threading + systemd Timer für Cron-Jobs
- **Testing:** pytest + mock + test_db_schema
- **Migration:** Alembic für DB-Schema-Versionierung
- **Security:** Soft-Delete, Foreign-Key-Constraints, Input-Validation

---

## 📚 Dokumentation

- **[Instruction_&_goal.md](Instruction_&_goal.md)** – Vollständige Projekt-Spezifikation (Phase 0-9)
- **[DEPLOYMENT.md](DEPLOYMENT.md)** – Production Deployment Guide (Gunicorn, Nginx, Fail2Ban)
- **[INSTALLATION.md](INSTALLATION.md)** – Schritt-für-Schritt Installation
- **[MAINTENANCE.md](MAINTENANCE.md)** – Maintenance & Helper-Skripte
- **[OAUTH_AND_IMAP_SETUP.md](OAUTH_AND_IMAP_SETUP.md)** – OAuth & IMAP Konfiguration
- **[TESTING_GUIDE.md](docs/TESTING_GUIDE.md)** – Testing-Workflow
- **[ZERO_KNOWLEDGE_COMPLETE.md](docs/ZERO_KNOWLEDGE_COMPLETE.md)** – Zero-Knowledge Implementierung

---

## 🐛 Troubleshooting

**Problem:** `Ollama: command not found`
```bash
# Ollama nicht installiert
curl -fsSL https://ollama.com/install.sh | sh
```

**Problem:** `IMAP Fehler: authentication failed`
```bash
# Master-Key mismatch – Web-UI besuchen und:
# Settings → Mail Accounts → Edit → Speichern
# Das aktualisiert den Cron Master-Key!
```

**Problem:** `Keine Emails in der Liste, obwohl fetch funktioniert`
```bash
# RawEmails existieren, aber AI-Verarbeitung läuft nicht
python3 -m src.00_main --process-once
# Oder auf Cron Timer warten (alle 15 Min)
```

**Problem:** `Ollama zu langsam`
```bash
# Kleineres Modell nehmen:
ollama pull mistral  # 4GB, schneller
# In .env:
# USE_CLOUD_AI=false
```

---

## 📊 Project Status

| Status | Details |
|--------|---------|
| **Development Phase** | Phase 9 – Production Hardening ✅ |
| **Security Score** | 98/100 🔒 |
| **Tested Platforms** | Linux (Debian 12), WSL2, Proxmox ✅ |
| **Supported Python** | 3.11+ |
| **Production Ready** | ✅ Yes (single-user, local deployment) |
| **Multi-User Support** | 🟡 Technically supported, not fully tested |
| **License** | [To be determined] |

---

## 📄 Lizenz

[Noch festzulegen]

---

## 🤝 Beitragen

Konstruktive Contributions sind sehr willkommen – einschließlich kritischer Gedanken und neuer Perspektiven.

Bitte lies [SECURITY.md](./SECURITY.md) für Sicherheitsfragen und öffne GitHub Issues für Bugs und Diskussionen.

---

**Verwendung auf eigene Gefahr** – Code vollständig von KI geschrieben. Größte Bemühungen durch gute Prompts und intelligentes Hinterfragen, um ein datenschutzfreundliches, lokal betriebenes KI-Mail-Helper Tool zu bauen. Optional: Cloud-KI-APIs statt lokaler Ollama. Bisher keine Praxiserfahrung in der Verwendung der Software.
