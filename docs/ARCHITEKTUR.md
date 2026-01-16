# 🏗️ KI-Mail-Helper – Architektur

**Version:** 2.0.0 (Multi-User Edition)  
**Stand:** Januar 2026

---

## Übersicht

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BROWSER (Client)                                │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  • Passwort → KEK (Key Encryption Key) ableiten                        │ │
│  │  • KEK entschlüsselt → DEK (Data Encryption Key)                       │ │
│  │  • DEK entschlüsselt → Emails, Credentials (Klartext)                  │ │
│  │  • JavaScript Crypto API (AES-256-GCM)                                 │ │
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
│  • mail_helper DB       │  │  • Sessions  │  │  • Email Fetch Tasks     │
│  • 23 Tabellen          │  │  • Broker    │  │  • AI Processing Tasks   │
│  • User-Isolation       │  │  • Results   │  │  • Reply Generation      │
└─────────────────────────┘  └──────────────┘  └──────────────────────────┘
```

---

## Komponenten

### 1. Flask Application (Web Layer)

**10 Blueprints** für modulare Struktur:

| Blueprint | Präfix | Verantwortung |
|-----------|--------|---------------|
| `auth_bp` | `/auth` | Login, Logout, Register, 2FA |
| `accounts_bp` | `/accounts` | Mail-Account CRUD, IMAP/SMTP Config |
| `emails_bp` | `/emails` | Email-Liste, Detail, IMAP-Aktionen |
| `api_bp` | `/api` | REST API Endpoints |
| `dashboard_bp` | `/dashboard` | Prioritäts-Matrix, Statistiken |
| `tags_bp` | `/tags` | Tag-Verwaltung, Suggestions |
| `rules_bp` | `/rules` | Auto-Rules Engine |
| `settings_bp` | `/settings` | User-Einstellungen, AI-Config |
| `threads_bp` | `/threads` | Conversation View |
| `main_bp` | `/` | Index, Static Routes |

### 2. Datenbank (PostgreSQL)

**23 Tabellen** mit User-Isolation:

```
users                    # Benutzer mit verschlüsseltem DEK
├── mail_accounts       # IMAP/SMTP Accounts (verschlüsselt)
│   ├── raw_emails      # Rohe Emails (verschlüsselt)
│   ├── processed_emails # KI-Analyse-Ergebnisse
│   ├── mail_server_states # UIDVALIDITY, Last-Sync
│   └── trusted_senders # Whitelist pro Account
├── email_tags          # User-Tags mit Embeddings
├── email_tag_assignments # Tag-Email-Zuordnungen
├── auto_rules          # Automatische Regeln
├── reply_style_settings # Antwort-Stil-Konfiguration
├── tag_suggestion_queue # Pending Tag-Vorschläge
├── spacy_*             # KI-Priorisierung Config
└── alembic_version     # Migration Tracking
```

### 3. Task Queue (Celery + Redis)

**Asynchrone Verarbeitung** für lang laufende Jobs:

```python
# Tasks in src/celery_tasks/
email_fetch_tasks.py      # fetch_emails_for_account()
email_processing_tasks.py # process_single_email(), reprocess_email_base()
reply_generation_tasks.py # generate_reply_draft()
maintenance_tasks.py      # cleanup_old_sessions()
```

**Konfiguration:**
```
CELERY_BROKER_URL = redis://localhost:6379/1
CELERY_RESULT_BACKEND = redis://localhost:6379/2
```

### 4. AI Layer

**Multi-Provider Support:**

| Provider | Embedding | Base | Optimize |
|----------|-----------|------|----------|
| **Ollama** | all-minilm:22m | llama3.2:1b | llama3.2:3b |
| **OpenAI** | text-embedding-3-small | gpt-4o-mini | gpt-4o |
| **Anthropic** | - | claude-3-haiku | claude-3-5-sonnet |
| **Mistral** | mistral-embed | mistral-small | mistral-large |

**Hybrid Pipeline (Phase Y):**
```
Email → spaCy NLP (80%) → Detektoren → Ensemble Combiner → Score
              ↓                              ↑
         Keywords (20%) ──────────────────────
```

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

### Zero-Knowledge Verschlüsselung

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER LOGIN                                   │
│                                                                  │
│  Passwort ──PBKDF2──▶ KEK (Key Encryption Key)                  │
│                          │                                       │
│                          ▼                                       │
│             encrypted_dek (aus DB) ──AES-GCM──▶ DEK             │
│                                                    │             │
│                                                    ▼             │
│             encrypted_* Felder ──AES-GCM──▶ Klartext            │
│                                                                  │
│  KEK + DEK nur in Server-RAM (Session)                          │
│  DB enthält NUR verschlüsselte Daten                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Verzeichnisstruktur

```
KI-Mail-Helper/
├── src/
│   ├── __init__.py           # App Factory
│   ├── blueprints/           # 10 Flask Blueprints
│   │   ├── auth.py
│   │   ├── accounts.py
│   │   ├── emails.py
│   │   ├── api.py
│   │   └── ...
│   ├── celery_tasks/         # Asynchrone Tasks
│   │   ├── celery_app.py
│   │   ├── email_fetch_tasks.py
│   │   └── ...
│   ├── services/             # Business Logic
│   │   ├── encryption_service.py
│   │   ├── ai_client.py
│   │   ├── mail_fetcher.py
│   │   └── ...
│   └── models.py             # SQLAlchemy Models
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
mail-helper.service          # Gunicorn (Flask App)
mail-helper-worker.service   # Celery Worker
mail-helper-beat.service     # Celery Beat (Scheduler)
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
journalctl -u mail-helper-worker -f

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

*Dieses Dokument beschreibt die Architektur von KI-Mail-Helper v2.0 (Multi-User Edition).*
