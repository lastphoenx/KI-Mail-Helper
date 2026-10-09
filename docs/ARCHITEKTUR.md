# 🏗️ KI-Mail-Helper – Architektur

**Version:** 2.3.0  
**Stand:** Oktober 2026

---

## Übersicht

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BROWSER (Client)                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  • Oberfläche: Dashboard, Ordner-Audit, Aktions-Regeln, Einstellungen  │ │
│  │  • Passwort geht über HTTPS an den Server                              │ │
│  │  • Keine Entschlüsselung im Browser                                    │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ HTTPS (TLS 1.3)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLASK APPLICATION                                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │   Auth     │ │  Accounts  │ │   Emails   │ │    API     │              │
│  │ Blueprint  │ │ Blueprint  │ │ Blueprint  │ │ Blueprint  │   ...        │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘              │
│                         │                                                   │
│                         ▼                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    SQLAlchemy ORM (PostgreSQL)                       │   │
│  │  • Connection Pool (20 base, 40 overflow)                           │   │
│  │  • Pre-Ping Health Checks                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
┌─────────────────────────┐  ┌──────────────┐  ┌──────────────────────────┐
│      PostgreSQL 17      │  │   Redis 8    │  │      Celery Workers      │
│  • mail_helper DB       │  │  • Sessions  │  │  • Mail-Sync, Regeln     │
│  • Modelle in           │  │  • Broker    │  │  • Bewertung, Audit      │
│    src/02_models.py     │  │  • Results   │  │  • Antworten             │
└─────────────────────────┘  └──────────────┘  └──────────────────────────┘
```

---

## Komponenten

### 1. Flask Application (Web Layer)

Registriert in `src/app_factory.py`:

| Blueprint | Wo | Verantwortung |
|-----------|-----|---------------|
| `auth_bp` | `blueprints/auth.py` | Login, Logout, Register, 2FA |
| `accounts_bp` | `blueprints/accounts.py` | `/settings`, Mail-Konten, KI-Auswahl |
| `emails_bp` | `blueprints/emails.py` | `/dashboard`, Liste, Detail |
| `email_actions_bp` | `blueprints/email_actions.py` | Antworten, Optimize-Aufruf |
| `api_bp` | `blueprints/api.py` | `/api` |
| `tags_bp` | `blueprints/tags.py` | Tags |
| `rules_bp` | `blueprints/rules.py` | `/rules`, Aktions-Regeln |
| `folder_audit_bp` | `blueprints/folder_audit.py` | `/folder-audit` |
| `audit_config_bp` | `blueprints/audit_config.py` | `/api/audit-config`, Einstufungs-Regeln |
| `translator_bp` | `blueprints/translator.py` | Übersetzung |
| `training_bp` | `blueprints/training.py` | Classifier-Training |
| `admin_bp` | `blueprints/admin.py` | Admin |
| `thread_api` | `src/thread_api.py` | `/api/threads` |

### 2. Datenbank (PostgreSQL)

Die Tabellen stehen in `src/02_models.py`. Auszug:

```
users                    # Benutzer, gewickelter DEK
├── mail_accounts        # IMAP/SMTP, Zugangsdaten verschlüsselt
│   ├── raw_emails       # Mails verschlüsselt
│   ├── processed_emails # Bewertung, Base und Optimize getrennt
│   └── mail_server_state
├── service_tokens       # kurzlebiger DEK für Celery, mit SECRET_KEY gewickelt
├── auto_rules           # Aktions-Regeln (/rules)
├── audit_*              # Einstufung, Wortlisten, Kontakte, Domain-Cache
├── email_tags
└── alembic_version
```

### 3. Task Queue (Celery + Redis)

**Asynchrone Verarbeitung** für lang laufende Jobs:

```text
src/celery_app.py
src/tasks/mail_sync_tasks.py
src/tasks/email_processing_tasks.py
src/tasks/reply_generation_tasks.py
src/tasks/rule_execution_tasks.py
src/tasks/folder_audit_tasks.py
src/tasks/maintenance_tasks.py
```

**Konfiguration:**
```
CELERY_BROKER_URL = redis://localhost:6379/1
CELERY_RESULT_BACKEND = redis://localhost:6379/2
```

### 4. AI Layer

**Multi-Provider Support:**

Modelle stehen in den Einstellungen, nicht fest im Code. Provider: Ollama, OpenAI, Anthropic, Mistral.

| Rolle | Wofür |
|-------|--------|
| **Embedding** | Semantische Suche und Tag-Vorschläge |
| **Base** | Erster Durchlauf der Posteingang-Bewertung |
| **Optimize** | Optionaler zweiter Durchlauf, nur hohe Scores |
| **Identität** | Ordner-Audit, nur die Grauzone. Nicht der Optimize-Durchlauf |

Denkende lokale Modelle (zum Beispiel Qwen) brauchen für JSON-Antworten das Denken aus.

**Lokaler Score, dann optional der zweite Durchlauf:**
```
Email → spaCy NLP (80%) → Detektoren → Ensemble → Score
              ↓                              ↑
         Keywords (20%) ──────────────────────
                                ↓
                    optional: Optimize-Modell
```

### 5. Ordner-Audit

Blueprint `folder_audit_bp` (`/folder-audit`). Die Bewertung liegt in Diensten, nicht in der Oberfläche:

| Dienst | Aufgabe |
|--------|---------|
| `audit_quality_rules` | Kategorien, Wortlisten, Aufbewahrungsfristen, wichtige Ordner |
| `audit_domain_intel` | DNS/RDAP nur im Zweifel, Cache, Domain-Badge |
| `audit_own_domains` | Eigene Domains und einzelne eigene Adressen |
| `audit_safe_delete_veto` | Warum eine Mail nicht «sicher löschbar» wird |
| `folder_audit_service` | Scan und Einordnung einer Mail |

Index und Spalten: `docs/audit/`.

---

## Datenfluss

### Email-Abruf

```
1. User klickt "Jetzt abrufen"
2. Flask API → Celery Task (fetch_emails_for_account)
3. Celery Worker:
   a. IMAP-Verbindung mit entschlüsselten Credentials
   b. Neue Emails abrufen (UID-basiert)
   c. Für jede Email:
      - Verschlüsselung (Subject, Body, Sender, etc.)
      - Inline-Attachments extrahieren (CID-Bilder)
      - AI-Analyse (wenn aktiviert)
      - Embedding-Generierung
      - In PostgreSQL speichern
4. Task-Status → Redis → Frontend-Polling
5. UI aktualisiert sich
```

### Inline-Attachments (CID-Bilder)

```
┌─────────────────────────────────────────────────────────────────┐
│                     EMAIL FETCH (Mail Fetcher)                   │
│                                                                  │
│  MIME Email ──parse──▶ Inline Parts (Content-ID Header)         │
│                            │                                     │
│                            ▼                                     │
│  Für jedes CID-Attachment (image/*, max 500KB):                 │
│    • Content-ID extrahieren (z.B. "image001@example.com")       │
│    • Base64-Encoding des Binärbilds                             │
│    • MIME-Type beibehalten                                      │
│                            │                                     │
│                            ▼                                     │
│  JSON Dict: {"cid": {"mime_type": "...", "data": "base64..."}}  │
│                            │                                     │
│                            ▼                                     │
│  AES-256-GCM Verschlüsselung → encrypted_inline_attachments     │
│                                                                  │
│  Größenlimits: Max 2 MB total, 500 KB pro Attachment            │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     EMAIL RENDER (Blueprint)                     │
│                                                                  │
│  encrypted_inline_attachments ──DEK──▶ JSON Dict                │
│                                           │                      │
│                                           ▼                      │
│  HTML Body durchsuchen nach: src="cid:image001@example.com"     │
│                                           │                      │
│                                           ▼                      │
│  Regex-Replace: cid:... → data:image/png;base64,...             │
│  (Case-insensitive, Whitespace-tolerant, URL-decoded)           │
│                                           │                      │
│                                           ▼                      │
│  Gerendertes HTML mit eingebetteten Bildern (CSP: data:)        │
└─────────────────────────────────────────────────────────────────┘
```

### Verschlüsselung im Ruhezustand

Das ist nicht Zero-Knowledge. Der Server entschlüsselt, solange die Sitzung oder ein Dienst-Token den DEK hält. Grenzen: `docs/SECURITY.md`.

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER LOGIN                                   │
│                                                                  │
│  Passwort ──PBKDF2 (600.000)──▶ KEK                             │
│                          │                                       │
│                          ▼                                       │
│             encrypted_dek (aus DB) ──AES-GCM──▶ DEK             │
│                                                    │             │
│                                                    ▼             │
│             encrypted_* Felder ──AES-GCM──▶ Klartext            │
│                                                                  │
│  DEK in der Server-Sitzung (RAM und .flask_sessions)            │
│  Celery: kurzlebiger Token, DEK mit SECRET_KEY gewickelt        │
│  PostgreSQL selbst enthält den Mail-Klartext nicht              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Verzeichnisstruktur

```
KI-Mail-Helper/
├── src/
│   ├── app_factory.py        # Flask Application Factory
│   ├── celery_app.py         # Celery
│   ├── 02_models.py          # SQLAlchemy-Modelle
│   ├── 03_ai_client.py       # KI-Provider
│   ├── 08_encryption.py      # AES-256-GCM, DEK/KEK
│   ├── blueprints/           # siehe Tabelle oben
│   ├── tasks/                # Celery-Tasks
│   └── services/             # Audit, Sanitizer, Tags
├── templates/                # Jinja2 Templates
├── migrations/               # Alembic Migrations
│   └── versions/
├── config/                   # Systemd, Gunicorn, etc.
├── scripts/                  # CLI Tools
├── tests/                    # Test Suite
├── docs/                     # Dokumentation
├── requirements.txt
├── alembic.ini
└── .env.example
```

---

## Deployment-Architektur

### Systemd Services

```
mail-helper.service                 # Gunicorn
mail-helper-celery-worker.service   # Celery Worker
mail-helper-celery-beat.service     # Celery Beat
postgresql.service           # Datenbank
redis-server.service         # Cache & Message Broker
```

### Empfohlene Infrastruktur

```
┌─────────────────────────────────────────────────────────────┐
│                     REVERSE PROXY (Nginx/Caddy)             │
│                     • TLS Termination                       │
│                     • Rate Limiting                         │
│                     • Static Files                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     APPLICATION SERVER                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Gunicorn  │  │   Celery    │  │   Celery    │         │
│  │   (4 Workers)│  │   Worker    │  │   Beat      │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐  ┌──────────────┐  ┌──────────────┐
│   PostgreSQL    │  │    Redis     │  │    Ollama    │
│   (Database)    │  │   (Broker)   │  │  (Local AI)  │
└─────────────────┘  └──────────────┘  └──────────────┘
```

---

## Skalierung

### Horizontal (Multi-Worker)

```bash
# Mehr Gunicorn Workers
gunicorn -w 8 -k gevent "src.app_factory:create_app()"

# Mehr Celery Workers
celery -A src.celery_app worker --concurrency=8
```

### Vertikal (Ressourcen)

| Komponente | Min | Empfohlen |
|------------|-----|-----------|
| **RAM** | 4 GB | 8-16 GB |
| **CPU** | 2 Cores | 4+ Cores |
| **Disk** | 10 GB | 50+ GB (für Ollama-Modelle) |
| **PostgreSQL** | 20 Connections | 100+ Connections |

---

## Monitoring

### Logs

```bash
# Flask App
journalctl -u mail-helper -f

# Celery Worker
journalctl -u mail-helper-celery-worker -f

# PostgreSQL
tail -f /var/log/postgresql/postgresql-17-main.log
```

### Health Checks

```bash
# App
curl http://localhost:5000/health

# Celery
celery -A src.celery_app inspect ping

# PostgreSQL
pg_isready -h localhost -p 5432

# Redis
redis-cli ping
```

---

*Stand 2.3.0, Oktober 2026. Die Unit-Dateien liegen in `config/`.*
