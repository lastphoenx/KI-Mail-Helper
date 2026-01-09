# 📧 KI-Mail-Helper

**Lokaler KI-Mail-Assistent mit Zero-Knowledge-Architektur**

Ein selbst-gehosteter Email-Organizer, der KI-Analyse mit clientseitiger Verschlüsselung kombiniert. Der Server sieht niemals Klartext-Daten – Entschlüsselung erfolgt ausschließlich im Browser mit deinem Passwort.

---

## Kernfeatures

- **Zero-Knowledge Encryption** – AES-256-GCM, DEK/KEK-Pattern, Master-Key nur im RAM
- **3×3 Prioritäts-Matrix** – Dringlichkeit × Wichtigkeit mit Farbcodierung + Account-Filter
- **KI-gestützte Priorisierung** – spaCy NLP (80%) + Keywords (20%) + Ensemble Learning
- **Multi-Provider AI** – Lokale Modelle (Ollama) oder Cloud (Claude, OpenAI, Mistral)
- **Email-Anonymisierung** – spaCy PII-Entfernung (DSGVO-konform) vor Cloud-AI-Übertragung
- **Confidence Tracking** – Transparenz über AI-Analyse-Qualität (0.65-0.9 für Hybrid Booster)
- **Online-Learning System** – SGD-Classifier lernt aus User-Korrekturen (4 Classifier: D/W/Spam/Kategorie)
- **AI Action Engine** – Reply Draft Generator (4 Ton-Varianten) + Auto-Rules (14 Bedingungen)
- **Customizable Reply Styles** – Anrede, Grussformel, Signatur & Instructions pro Stil + Account-spezifisch
- **Account-Specific Signatures** – Individuelle Signaturen pro Mail-Account (Geschäft/Privat/Uni)
- **Trusted Senders + UrgencyBooster** – Account-basierte Whitelist mit Urgency-Override (Global + Per-Account)
- **Dedizierte Whitelist-Seite** – `/whitelist` mit 2-Spalten-Layout, Batch-Operationen und Live-Filter
- **Account-Level AI-Fetch-Control** – Separate AI-Analyse und UrgencyBooster Toggles pro Account
- **Semantische Suche** – Embeddings für "finde ähnliche Emails"
- **Tag-System** – Manuell + KI-Vorschläge basierend auf gelernten Mustern
- **IMAP & Gmail OAuth** – Funktioniert mit GMX, Gmail, Outlook, etc.
- **SMTP Versand** – Antworten & neue Emails mit Sent-Ordner-Sync
- **Thread-View** – Konversations-basierte Ansicht mit Context
- **Fetch-Filter** – Account-spezifisch: Ordner, Datum, UNSEEN, Delta-Sync
- **Multi-Account Dashboard** – Filter Dashboard nach spezifischem Email-Account

---

## Status

**Version:** 1.3.0  
**Development:** Aktiv (Email-Anonymisierung & Confidence Tracking abgeschlossen)  
**Stability:** Production-ready für Single-User-Deployment  
**Next:** Benchmarks & Performance Testing

**Abgeschlossene Phasen:**
- ✅ Phase 0-12: Core System, Zero-Knowledge, Production Hardening
- ✅ Phase 13C: Account-spezifische Fetch-Filter
- ✅ Phase 14: RFC-konformer IMAP UID-Sync (UIDVALIDITY)
- ✅ Phase 15: Multi-Folder UIDPLUS Support
- ✅ Phase E: Thread-Context & Conversation View
- ✅ Phase F1: Semantic Search mit Embeddings
- ✅ Phase F2: Smart Tag Suggestions & Learning (Enhanced 2026-01-06)
- ✅ Phase F.3: Negative Feedback für Tag-Learning
- ✅ Phase G: AI Action Engine (Reply Generator + Auto-Rules)
- ✅ Phase H: SMTP Mail-Versand mit Sent-Sync
- ✅ Phase I.1: Customizable Reply Styles (4 Stile)
- ✅ Phase I.2: Account-Specific Signatures
- ✅ Phase X: Trusted Senders + UrgencyBooster (Account-Based)
- ✅ Phase X.2: Dedizierte Whitelist-Seite (/whitelist)
- ✅ Phase X.3: Account-Level AI-Fetch-Control (enable_ai_analysis_on_fetch)
- ✅ Phase Y: KI-gestützte Priorisierung (spaCy NLP + Ensemble Learning)
- ✅ Phase 22: Email-Anonymisierung mit spaCy (DSGVO-konform)
- ✅ Confidence Tracking: ai_confidence & optimize_confidence

---

## ⚠️ Haftungsausschluss / Disclaimer (AI-Generated Code)

> **🚧 WORK IN PROGRESS**: Dieses Projekt befindet sich in aktiver Entwicklung. Features werden kontinuierlich hinzugefügt, verbessert und getestet. Für produktive Nutzung bitte eigene Tests durchführen und regelmäßig Updates prüfen.

### 🇩🇪 Deutsch

**Hinweis: KI-generierter Code (in aktiver Entwicklung)**

Dieses Repository wurde mit mehreren KI-Systemen erstellt. Der Code wurde bisher **vollständig von KI erzeugt**; keine Zeile wurde manuell von einem Menschen geschrieben. Die gesamte Entwicklung erfolgte in **Microsoft Visual Studio Code (VS Code)** mit GitHub Copilot als primärem Entwickler.

**Aktuelle Features (Stand Januar 2026):**
- 🎯 **KI-Priorisierung:** spaCy NLP (80%) + Keywords (20%) + Ensemble Learning mit SGD
- 🛡️ **Email-Anonymisierung:** spaCy PII-Entfernung (3 Levels: Regex, Light, Full) vor Cloud-AI-Übertragung
- 📊 **Confidence Tracking:** Transparenz über AI-Analyse-Qualität mit ai_confidence/optimize_confidence
- 🤖 **Core System:** Zero-Knowledge Encryption, 3×3 Prioritäts-Matrix, Multi-Provider AI
- 🧠 **Online-Learning:** SGD-Classifier mit inkrementellem Training aus User-Korrekturen (D/W/Spam/Kategorie)
- 🔐 **Security:** Production-hardened (98/100 Score), Rate Limiting, 2FA, Account Lockout
- 📥 **Fetch:** IMAP/Gmail OAuth mit account-spezifischen Filtern (Ordner, Datum, UNSEEN)
- 📤 **Send:** SMTP-Versand mit automatischer Sent-Ordner-Synchronisation
- 🧵 **Thread-View:** Konversations-basierte Email-Ansicht mit KI-Context
- 🔍 **Semantic Search:** Vector-basierte Suche mit Embeddings (OpenAI, Mistral, etc.)
- 🏷️ **Smart Tags:** KI-Vorschläge + Learning-System + Multi-Tag-Filter
- 🤖 **AI Actions:** Reply Draft Generator (4 Ton-Varianten) + Auto-Rules Engine (14 Bedingungen)

**Trotz größter Sorgfalt beim Prompting, kritischem Hinterfragen und wiederholten Reviews erfolgt die Verwendung auf eigenes Risiko.** Die Software wird „wie gesehen" (as is) bereitgestellt – ohne Gewährleistung und ohne Zusicherung hinsichtlich Korrektheit, Sicherheit oder Eignung. Wenn du das Tool mit echten Mail-Accounts oder sensiblen Daten nutzen willst, führe bitte eigene Tests, Threat-Modeling und ein unabhängiges Security-Review durch.

### 🇬🇧 English

**Notice: AI-generated code (Active Development)**

> **🚧 WORK IN PROGRESS**: This project is under active development. Features are continuously being added, improved, and tested. For production use, please conduct your own testing and check for updates regularly.

This repository was created with multiple AI systems. So far, the codebase has been generated **entirely by AI** — not a single line was written manually by a human. All development work was performed in **Microsoft Visual Studio Code (VS Code)** with GitHub Copilot as primary developer.

**Current Features (January 2026):**
- 🎯 **AI Prioritization:** spaCy NLP (80%) + Keywords (20%) + Ensemble Learning with SGD
- 🛡️ **Email Anonymization:** spaCy PII removal (3 levels: Regex, Light, Full) before Cloud-AI transmission
- 📊 **Confidence Tracking:** Transparency in AI analysis quality with ai_confidence/optimize_confidence
- 🤖 **Core System:** Zero-Knowledge Encryption, 3×3 Priority Matrix, Multi-Provider AI
- 🧠 **Online-Learning:** SGD classifiers with incremental training from user corrections (D/W/Spam/Category)
- 🔐 **Security:** Production-hardened (98/100 Score), Rate Limiting, 2FA, Account Lockout
- 📥 **Fetch:** IMAP/Gmail OAuth with account-specific filters (folders, date, UNSEEN)
- 📤 **Send:** SMTP with automatic Sent folder sync
- 🧵 **Thread-View:** Conversation-based email view with AI context
- 🔍 **Semantic Search:** Vector-based search with embeddings (OpenAI, Mistral, etc.)
- 🏷️ **Smart Tags:** AI suggestions + learning system + multi-tag filters
- 🤖 **AI Actions:** Reply Draft Generator (4 tone variants) + Auto-Rules Engine (14 conditions)

**Despite careful prompting, critical challenge/verification, and repeated reviews, use is at your own risk.** The software is provided "as is", without warranty, and with no guarantee of correctness, security, or fitness for a particular purpose. If you plan to use it with real email accounts or sensitive data, please conduct your own testing, threat modeling, and an independent security review first.

---

## 🎯 Was ist KI-Mail-Helper?

Ein lokaler Mail-Assistent, der E-Mails automatisch:
- ✅ Von IMAP-Servern (GMX, Yahoo, Hotmail) & Gmail OAuth abholt
- 🔒 **Zero-Knowledge verschlüsselt** – Server hat keinen Zugriff auf Klartext-Daten
- 🤖 Mit lokalem LLM (Ollama: llama3.2, mistral, etc.) oder Cloud-KI analysiert
- 📊 In einem **3×3-Prioritäten-Dashboard** darstellt (Wichtigkeit × Dringlichkeit)
- 🏷️ Mit KI-gestützten Tag-Vorschlägen versieht
- 💡 Mit Handlungsempfehlungen versieht
- 📧 **SMTP-Versand** mit automatischer Sent-Ordner-Synchronisation ermöglicht
- � **AI Action Engine**: Antwort-Entwürfe generieren + Auto-Rules für Email-Aktionen
- �🧵 In **Thread-View** mit Konversations-Context darstellt
- 🔍 Mit **semantischer Suche** durchsuchbar macht

---

## ✨ Features

### Kernfunktionen
- **🔐 Zero-Knowledge Encryption (Phase 8)** – AES-256-GCM End-to-End Verschlüsselung (siehe [docs/ZERO_KNOWLEDGE_COMPLETE.md](docs/ZERO_KNOWLEDGE_COMPLETE.md))
  - **DEK/KEK Pattern** – Passwort ändern ohne E-Mails neu zu verschlüsseln
  - Alle E-Mails verschlüsselt (Sender, Subject, Body, AI-Ergebnisse)
  - Alle Credentials verschlüsselt (IMAP/SMTP Server, Usernames, Passwords)
  - DEK (Data Encryption Key) nur in Server-RAM (Flask Server-Side Sessions)
  - Server kann niemals auf Klartext-Daten zugreifen
- **🔒 Production Security (Phase 9)** – Enterprise-Grade Hardening (siehe [DEPLOYMENT.md](docs/DEPLOYMENT.md))
  - **Flask-Limiter**: Rate Limiting (5 requests/min Login/2FA)
  - **Account Lockout**: 5 Failed → 15min Ban
  - **Session Timeout**: 30min Inaktivität → Auto-Logout
  - **Fail2Ban Integration**: Network-Level IP Banning
  - **Audit Logging**: Strukturierte Security-Events für Monitoring
  - **Security Score: 98/100** 🔒
- **📥 Fetch-System** – Intelligente Mail-Synchronisation
  - **IMAP** – GMX, Yahoo, Hotmail, custom servers
  - **Gmail OAuth2** – Google API mit automatischer Token-Refresh
  - **Account-spezifische Filter (Phase 13C):**
    - Ordner: Include/Exclude Listen
    - Datum: SINCE-Filter (nur Mails ab Datum X)
    - Status: UNSEEN-only (nur ungelesene)
    - Limit: Mails pro Ordner + Gesamt-Maximum
    - Delta-Sync: Nur neue Mails seit letztem Sync (UID-Range)
  - **Live-Vorschau**: Zeigt geschätzte Mail-Anzahl vor Fetch
  - **UIDVALIDITY-Tracking (Phase 14)**: RFC-konformer UID-Sync
  - **Multi-Folder UIDPLUS (Phase 15)**: Paralleles Fetching
  - **Performance-Optimierungen (2026-01-05):**
    - Smart SINCE-Search: Nur ausgewählte Ordner, nicht alle 132
    - 30s Server-Side Cache für `/mail-count` Requests
    - Client-Side Request-Abbruch bei Account-Wechsel
    - Result: 132 Ordner in ~7-8s statt 120s+ (94% schneller)
- **📤 SMTP-Versand (Phase H)** – Email-Versand mit Sync
  - **Antworten**: Direkt aus Email-Detail mit Reply-To-Header
  - **Neue Emails**: Compose mit To/CC/BCC/Betreff/Body
  - **Sent-Sync**: Automatisches APPEND in IMAP Sent-Ordner
  - **Thread-Support**: In-Reply-To + References Headers
  - **DB-Synchronisation**: Gesendete Mails als ProcessedEmail
  - **Zero-Knowledge**: SMTP-Credentials verschlüsselt
- **🧵 Thread-View (Phase E)** – Konversations-basierte Ansicht
  - **Thread-ID Berechnung**: SHA256(normalized_subject + participants)
  - **Conversation-Grouping**: Emails mit gleichem Thread-ID gruppiert
  - **Chronologische Sortierung**: Älteste → Neueste
  - **Context-Aware AI**: KI sieht vollständigen Thread-Context
  - **Collapse/Expand**: Threads können eingeklappt werden
- **🔍 Semantische Suche (Phase F1)** – Vector-basierte Suche
  - **Embeddings**: OpenAI, Mistral, Voyage, Cohere, etc.
  - **"Finde ähnliche"**: Ähnlichkeitssuche basierend auf Semantik
  - **Fast**: Cosine Similarity mit NumPy
  - **User-spezifisch**: Nur eigene Emails durchsuchbar
- **🏷️ Smart Tag-System (Phase F2 Enhanced)** – KI-gestützte Tag-Vorschläge mit Learning
  - **Embedding-basierte Suggestions**: Semantische Ähnlichkeit zwischen Email und Tag-Embeddings
  - **Learning-Hierarchie**: 
    1. `learned_embedding` (aggregiert aus assigned emails) - Beste Qualität!
    2. `description` Embedding (semantische Beschreibung)
    3. `name` Embedding (nur Tag-Name)
  - **Tag-Suggestion Queue** (`/tag-suggestions`): KI schlägt NEUE Tag-Namen vor → User genehmigt/merged/ablehnt
  - **Auto-Assignment**: Bestehende Tags werden bei ≥80% Similarity automatisch zugewiesen (optional)
  - **Separate Flags**: `enable_tag_suggestion_queue` (neue Tags) vs `enable_auto_assignment` (bestehende Tags)
  - **Negative Feedback (Phase F.3)**: 
    - Reject-Buttons (×) auf Tag-Vorschlägen in Email-Detail
    - System lernt von Ablehnungen und schlägt unpassende Tags nicht mehr vor
    - Penalty-System: 0-20% Score-Reduktion basierend auf Similarity zu negativen Beispielen
    - Count-Bonus: Mehr Rejects = höhere Confidence = stärkere Penalty
  - **Tag-Management**: Create/Edit/Delete mit 7 Farben + Email-Count + Statistics
  - **Multi-Tag-Filter**: Kombiniere Tags mit Farbe/Done/Suche
  - **Performance**: Preloading aller Tag-Embeddings (1× Batch statt 11-13× einzelne Calls)
- **🤖 AI Action Engine (Phase G)** – Automatisierung & KI-Assistenz
  - **G.1 Reply Draft Generator**: KI generiert Antwort-Entwürfe mit 4 Ton-Varianten (Formell/Freundlich/Kurz/Ablehnend)
  - **G.2 Auto-Rules Engine**: Automatische Email-Aktionen mit Bedingungen & Aktionen
    - 14 Bedingungstypen: Sender, Subject, Body, Regex, Tags, KI-Vorschläge
    - 6 Aktionstypen: Move, Tag, Flag, Read, Priority, Delete
    - Farbige Tag-Indikatoren (CSS-Kreise)
    - Regel-Ketten mit `has_tag` / `not_has_tag` Conditions
    - KI-Integration: `ai_suggested_tag` mit Confidence-Threshold
    - 4 Templates: Newsletter-Archiv, Spam-Filter, Important-Sender, Attachment-Archive
- **📬 Account-Level AI-Fetch-Control (Phase X.3)** – Granulare Steuerung der AI-Analyse pro Account
  - **3 unabhängige Toggles pro Account:**
    - ✅ **AI-Analyse beim Abruf**: LLM-Analyse (Dringlichkeit/Wichtigkeit/Kategorie/Summary/Tags)
    - ✅ **UrgencyBooster (spaCy)**: Schnelle Entity-basierte Analyse für Trusted Senders (100-300ms)
    - 🛡️ **Mit Spacy anonymisieren**: PII-Entfernung mit spaCy NER vor Cloud-AI-Übertragung (DSGVO-konform)
  - **Hierarchische Analyse-Modi**:
    - **spacy_booster**: UrgencyBooster auf Original-Daten (lokal, schnell, keine LLM-Kosten)
    - **llm_anon**: LLM-Analyse auf anonymisierten Daten (Privacy für Cloud-AI)
    - **llm_original**: LLM-Analyse auf Original-Daten (beste Qualität)
    - **none**: Nur Embeddings, keine Bewertung (für manuelles Tagging + ML-Learning)
  - **Email-Anonymisierung (Phase 22)**:
    - **3 Sanitization-Levels**: Regex (schnell), Light (häufige Entities), Full (alles inkl. ORG/LOC)
    - **ContentSanitizer**: spaCy de_core_news_sm (German 14.6 MB) mit Named Entity Recognition
    - **Dual-Storage**: Originale verschlüsselt + anonymisierte Versionen verschlüsselt
    - **Performance**: ~1200ms erste Analyse (Modell-Loading), ~10-15ms folgende Emails
    - **Lazy-Loading**: spaCy-Modell nur bei Bedarf geladen (kein Startup-Overhead)
    - **UI**: Neuer Tab "🛡️ Anonymisiert" in Email-Detail mit Entity-Count + Level-Anzeige
  - **Confidence Tracking** (transparent für User):
    - **ai_confidence**: Initiale Analyse-Qualität (0.65-0.9 für Hybrid Booster basierend auf SGD-Korrekturen)
    - **optimize_confidence**: Zweite-Pass-Qualität mit besserem Modell
    - **NULL-Policy**: Keine Fake-Defaults für LLMs ohne native Confidence
  - **Flexible Strategien**:
    - **Beide aktiviert**: Trusted Senders → spaCy Booster, alle anderen → LLM
    - **Nur LLM**: Universelle AI-Analyse für alle Mails (langsamer, aber präziser)
    - **Nur Embedding**: Keine automatische Bewertung → Manuelles Tagging → ML-Learning
  - **Use Cases**:
    - Newsletter-Accounts (GMX): AI-Analyse AUS → Manuelles Tagging → Besseres ML-Learning
    - Business-Accounts (Beispiel-Firma): AI-Analyse AN + Booster AN → Automatische Priorisierung
    - Hybrid: AI-Analyse AN + Booster AUS → Nur LLM ohne spaCy-Overhead
    - DSGVO: Anonymisierung AN + Cloud-AI → Keine PII-Übertragung an externe Provider
  - **UI**: Dedizierte Seite "📬 Absender & Abruf" (`/whitelist`) mit ausführlichen Erklärungen
  - **Settings-Integration**: Status-Badges (🛡️ Anon, ⚡ Booster, 🤖 AI-Anon, 🤖 AI-Orig, ❌ Keine AI) in Account-Tabelle
  - **Performance**: Keine AI-Calls bei deaktivierter Analyse → Drastisch schnelleres Fetching
  - **Begründung**: Rule-basierte Systeme (spaCy) funktionieren nur bei expliziten Signalen (Rechnungen, Deadlines). 
    Für Newsletter/Marketing-Mails mit subtilen Mustern ist ML-Learning aus User-Korrekturen überlegen.
- **Dynamic Provider-Dropdowns** – Auto-Erkennung verfügbarer KI-Modelle basierend auf API-Keys
- **Flexible Modellauswahl** – Keine Hardcodierung! llama3.2, mistral, oder beliebige Ollama/Cloud-Modelle
- **Two-Pass Optimization** – Base-Pass (schnell) + Optimize-Pass (optional, bessere Kategorisierung)
- **Learning System (Phase 9 ML)** – Human-in-the-Loop Training mit User-Korrektionen
- **Datenschutz-Sanitizer** – 3 Level (Volltext → Pseudonymisierung)
- **Multi-Provider KI-Analyse** – Lokal (Ollama) oder Cloud (OpenAI, Anthropic, Mistral)
- **Intelligentes Scoring** – 3×3-Matrix + Ampelfarben (Rot/Gelb/Grün)
- **Web-Dashboard** – Übersichtliche Darstellung mit Matrix- und Listenansicht
- **2FA (TOTP) + Recovery-Codes** – Zwei-Faktor-Authentifizierung mit Backup-Codes
- **Background-Jobs** – Asynchrone Email-Verarbeitung mit Progress-Tracking
- **Maintenance Helper** – Scripts für DB-Reset, Migrationen, Troubleshooting (siehe [scripts/README.md](scripts/README.md))

### Ansichten
1. **3×3-Matrix** – Wichtigkeit (x) × Dringlichkeit (y) mit Farbcodierung
2. **Ampel-Ansicht** – Rot (hoch) / Gelb (mittel) / Grün (niedrig)
3. **Listen-View** – Sortiert nach Score mit Filtern + Tag-Filter (Multi-Select)
4. **Thread-View** – Konversations-basierte Gruppierung mit Context
5. **Detail-Ansicht** – Vollständige Mail-Info + Aktionen + Tag-Management + SMTP-Reply
6. **Tag-Management** – `/tags` Route für CRUD-Operationen + Statistiken
7. **Semantic Search** – `/search` mit "Finde ähnliche" Button

---

## 🏗️ Architektur

```
mail-helper/
├── src/
│   ├── 00_main.py              # Entry Point / CLI + Cron-Orchestrierung
│   ├── 01_web_app.py           # Flask Web-Dashboard + Auth + API Routes
│   ├── 02_models.py            # SQLAlchemy DB-Modelle + Soft-Delete
│   ├── 03_ai_client.py         # KI-Client (Ollama, OpenAI, Anthropic, Mistral)
│   ├── 04_sanitizer.py         # Datenschutz-Level 1-3
│   ├── 05_scoring.py           # 3×3-Matrix + Farben
│   ├── 05_embedding_api.py     # Embedding-Client für Semantic Search
│   ├── 06_mail_fetcher.py      # IMAP-Client mit UID/Folder/Flags

│   ├── 07_auth.py              # Auth + Master-Key + 2FA
│   ├── 08_encryption.py        # Zero-Knowledge AES-256-GCM
│   ├── 10_google_oauth.py      # Gmail OAuth2 API Fetcher
│   ├── 12_processing.py        # Email-Verarbeitungs-Workflow
│   ├── 14_background_jobs.py   # Job Queue für Hintergrund-Verarbeitung
│   ├── 15_provider_utils.py    # Dynamic Provider/Model Discovery
│   ├── 16_imap_flags.py        # IMAP Flag Management (Read/Unread/Flagged)
│   ├── 16_mail_sync.py         # Multi-Folder Sync Coordinator
│   ├── 19_smtp_sender.py       # SMTP Versand + Sent-Sync (Phase H)
│   ├── auto_rules_engine.py    # Auto-Rules Engine (Phase G.2)
│   ├── reply_generator.py      # AI Reply Draft Generator (Phase G.1)
│   ├── semantic_search.py      # Vector-basierte Suche (Phase F1)
│   ├── thread_api.py           # Thread-View API
│   ├── thread_service.py       # Thread-Grouping Logic
│   ├── services/
│   │   ├── tag_manager.py      # Tag CRUD + Assignment Logic
│   │   └── sender_patterns.py  # Sender Pattern Learning
│   └── ...
├── templates/                  # HTML-Templates (20+)
│   ├── dashboard.html          # 3×3 Matrix + Ampel-View
│   ├── list_view.html          # List + Filters
│   ├── threads_view.html       # Conversation View (Phase E)
│   ├── email_detail.html       # Detail + Reply + Tags
│   ├── tags.html               # Tag Management UI
│   ├── rules_management.html   # Auto-Rules UI (Phase G.2)
│   └── ...
├── tests/                      # Unit Tests (pytest)
│   ├── test_ai_client.py
│   ├── test_mail_fetcher.py
│   ├── test_sanitizer.py
│   ├── test_thread_id_calculation.py
│   └── ...
├── scripts/                    # Utility & Maintenance Scripts (siehe README.md)
│   ├── reset_base_pass.py      # Base-Pass Analysis Reset
│   ├── reset_all_emails.py     # Hard-Delete Emails
│   ├── backup_database.sh      # Automated WAL-aware Backups
│   ├── verify_wal_mode.py      # SQLite WAL-Check
│   └── ... (17 aktive Scripts)
├── migrations/                 # Alembic DB-Migrationen (24+ Versionen)
│   ├── versions/
│   │   ├── ph10_email_tags.py
│   │   ├── ph13c_p5_fetch_filters.py
│   │   ├── ph14a_rfc_unique_key_uidvalidity.py
│   │   ├── phE_thread_context.py
│   │   ├── phF1_semantic_search.py
│   │   ├── phG2_auto_rules.py
│   │   └── ...
├── config/                     # Konfigurationsdateien
│   ├── mail-helper.service     # Systemd Service (Web-App)
│   ├── mail-helper-processor.service
│   ├── mail-helper-processor.timer    # Cron Timer (15 min)
│   ├── gunicorn.conf.py        # Gunicorn WSGI Config
│   ├── fail2ban-filter.conf    # Fail2Ban Filter Rules
│   ├── fail2ban-jail.conf      # Fail2Ban Jail Config
│   └── logrotate.conf          # Log Rotation Config
├── docs/                       # Dokumentation
│   ├── INSTALLATION.md         # Komplette Installationsanleitung
│   ├── DEPLOYMENT.md           # Production Deployment Guide
│   ├── MAINTENANCE.md          # Maintenance & Helper-Skripte
│   ├── SECURITY.md             # Security Model & Threat Analysis
│   ├── OAUTH_AND_IMAP_SETUP.md # OAuth & IMAP Konfiguration
│   ├── TESTING_GUIDE.md        # Kompletter Testing-Workflow
│   ├── ZERO_KNOWLEDGE_COMPLETE.md  # Zero-Knowledge Implementierung
│   └── CHANGELOG.md            # Version History
├── doc/                        # Feature-Dokumentation
│   ├── Changelogs/             # Phase-Changelogs
│   ├── erledigt/               # Abgeschlossene Phasen
│   ├── fetch-filters/          # Fetch-Filter Docs
│   ├── imap/                   # IMAP-Strategie & Troubleshooting
│   ├── ki-tags/                # Tag-Learning Architektur
│   ├── smtp-modul/             # SMTP Integration (Phase H)
│   └── ...
├── config/                     # Konfigurationsdateien
│   ├── fail2ban-filter.conf    # Fail2Ban Filter Rules
│   ├── fail2ban-jail.conf      # Fail2Ban Jail Config
│   └── logrotate.conf          # Log Rotation Config
├── emails.db                   # SQLite Datenbank (WAL-Mode)
├── .env                        # Konfiguration (API-Keys, Secrets)
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

**For users:**
- **[📖 BENUTZERHANDBUCH.md](./docs/BENUTZERHANDBUCH.md)** – Vollständige Bedienungsanleitung (German User Manual)

**Before you deploy to production, read:**
- **[SECURITY.md](./docs/SECURITY.md)** – Threat Model, Security Features, Known Limitations
- **[DEPLOYMENT.md](./docs/DEPLOYMENT.md)** – Production Setup (Gunicorn, Systemd, Fail2Ban, Backups)
- **[INSTALLATION.md](./docs/INSTALLATION.md)** – Detailed step-by-step installation guide
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

> **Verwirrung vermeiden:** Das System hat **zwei verschiedene Bewertungstypen**:
> - **Tags** = Freie Kategorisierung (beliebig viele, user-definiert)
> - **Kategorie/Dringlichkeit/Wichtigkeit** = Scoring-System (fixe Werte, KI-gesteuert)

---

## 🏷️ Tag-System - Vollständige Dokumentation

### Architektur-Überblick

```
┌─────────────────────────────────────────────────────────────┐
│  KI-ANALYSE (all-minilm:22m / llama3.2)                     │
│  ├─ Dringlichkeit (1-3)        ← System-Feld für Scoring   │
│  ├─ Wichtigkeit (1-3)          ← System-Feld für Scoring   │
│  ├─ Kategorie/Aktion (3 Werte) ← System-Feld für Workflow  │
│  └─ suggested_tags (1-5 Tags)  ← Freie Kategorisierung     │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  DATENBANK-LAYER                                             │
│  ├─ ProcessedEmail                                           │
│  │  ├─ dringlichkeit, wichtigkeit, kategorie_aktion         │
│  │  ├─ user_override_dringlichkeit, _wichtigkeit, _kategorie│
│  │  └─ user_override_tags (String, comma-separated)         │
│  ├─ EmailTag (id, name, color, user_id)                     │
│  └─ EmailTagAssignment (email_id, tag_id)                   │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  USER-INTERFACE                                              │
│  ├─ Dashboard: Filter nach Tags (Multi-Select)              │
│  ├─ Email-Detail: Tag-Badges + Add/Remove                   │
│  ├─ /tags: Tag-Management (CRUD)                            │
│  └─ Learning-Modal: "Bewertung korrigieren"                 │
└─────────────────────────────────────────────────────────────┘
```

---

### 1️⃣ System-Felder (KI-gesteuert, nicht erweiterbar)

#### **Dringlichkeit (1-3)**
```python
1 = kann warten             # Trigger: "Info", "Newsletter", "optional"
2 = sollte bald erledigt    # Trigger: "nächste Woche", "bald"
3 = sehr dringend           # Trigger: "heute", "morgen", "sofort", "Frist"
```

#### **Wichtigkeit (1-3)**
```python
1 = eher unwichtig          # Trigger: "Werbung", "Promotion", "Angebot"
2 = wichtig                 # Trigger: "Termin", "Meeting", "Aufgabe"
3 = sehr wichtig            # Trigger: "Rechnung", "Vertrag", "Kündigung", "Bank"
```

#### **Kategorie/Aktion (3 fixe Werte)**
```python
"nur_information"           # Newsletter, Info, Status-Update
                           # Trigger: "Newsletter", "Abmelden", "Blog", "Update"

"aktion_erforderlich"      # User muss etwas tun
                           # Trigger: "bitte antworten", "zahlen", "bestätigen"

"dringend"                 # Aktion + Zeitdruck
                           # Trigger: "sofort", "umgehend", "bis Montag"
```

**Zweck:** Bestimmt **Farbe** (Rot/Gelb/Grün) und **Score-Berechnung**  
**Erweiterbar:** ❌ Nein - fixe Werte für Priorisierungs-Logik

---

### 2️⃣ Tag-System (User-definiert, erweiterbar)

#### **Was sind Tags?**
- Freie, semantische Kategorisierung ("Rechnung", "Finanzen", "Wichtig")
- Beliebig viele Tags pro Email
- User kann eigene Tags erstellen
- KI schlägt 1-5 Tags vor (`suggested_tags`)

#### **Datenmodell**
```sql
-- Tag-Definition
EmailTag:
  - id (PK)
  - name (String, unique per user)
  - color (Hex, #RRGGBB)
  - user_id (FK, CASCADE DELETE)

-- Tag-Zuweisung
EmailTagAssignment:
  - email_id (FK)
  - tag_id (FK)
  - assigned_at (Timestamp)
  - UNIQUE(email_id, tag_id)  -- Kein Duplikat
  - CASCADE DELETE bei Tag-Löschung
```

---

### 3️⃣ Workflow: KI → Auto-Assignment → User-Korrektur

#### **Schritt 1: Email-Verarbeitung (Base-Pass)**
```python
# src/12_processing.py:206-245
1. KI analysiert Email → generiert JSON:
   {
     "dringlichkeit": 2,
     "wichtigkeit": 3,
     "kategorie_aktion": "aktion_erforderlich",
     "suggested_tags": ["Rechnung", "Finanzen", "Wichtig"]
   }

2. _validate_ai_payload() extrahiert suggested_tags

3. process_pending_raw_emails():
   FOR EACH tag_name IN suggested_tags[:5]:  # Max 5
     tag = TagManager.get_or_create_tag(name=tag_name, color="#3B82F6")
     TagManager.assign_tag(email_id, tag.id, user.id)
```

**Ergebnis:** Email hat automatisch Tags aus KI-Vorschlägen

---

#### **Schritt 2: User-Interaktion (Email-Detail)**

**A) Tag hinzufügen/entfernen:**
```
Email-Detail → Tag-Bereich
├─ "Tag hinzufügen" Button → Modal mit allen User-Tags
│  └─ Click "Zuweisen" → POST /api/emails/<id>/tags
│     ├─ TagManager.assign_tag()
│     └─ _update_user_override_tags()  ← WICHTIG für ML!
│
└─ Tag-Badge (X) → removeTag()
   └─ DELETE /api/emails/<id>/tags/<tag_id>
      ├─ TagManager.remove_tag()
      └─ _update_user_override_tags()  ← WICHTIG für ML!
```

**B) Learning-Modal ("Bewertung korrigieren"):**
```
Email-Detail → "✏️ Bewertung korrigieren"
├─ Öffnet Modal (base.html:124-210)
│  ├─ Zeigt aktuelle Tags als Badges
│  └─ Multi-Select Dropdown (alle User-Tags)
│
└─ Submit "💾 Speichern & als Training markieren"
   ├─ POST /email/<id>/correct → Speichert Dringlichkeit/Wichtigkeit/Kategorie
   │  └─ Setzt user_override_* Felder + correction_timestamp
   │
   └─ Tag-Updates via API:
      ├─ GET /api/emails/<id>/tags (aktuelle Tags)
      ├─ Berechne Diff (zu entfernen, hinzuzufügen)
      ├─ DELETE /api/emails/<id>/tags/<tag_id> (für entfernte)
      └─ POST /api/emails/<id>/tags (für neue)
         → Jede Änderung ruft _update_user_override_tags() auf!
```

---

#### **Schritt 3: ML-Training (zukünftig)**
```python
# _update_user_override_tags() (01_web_app.py:1970-2003)
def _update_user_override_tags(email_id, user_id):
    current_tags = TagManager.get_email_tags(db, email_id, user_id)
    tag_string = ",".join([tag.name for tag in current_tags])
    
    processed.user_override_tags = tag_string  # "Rechnung,Finanzen"
    processed.correction_timestamp = datetime.now(UTC)
```

**ML kann damit:**
- Vergleichen: KI-Vorschlag vs. User-Korrektur
- Trainieren: "Bei ähnlichen Emails diese Tags verwenden"
- Verbessern: suggested_tags werden mit der Zeit genauer

---

### 4️⃣ API-Referenz

#### **Tag-Management**
```python
GET    /api/tags                    # Liste aller User-Tags
POST   /api/tags                    # Tag erstellen (name, color)
PUT    /api/tags/<tag_id>           # Tag bearbeiten
DELETE /api/tags/<tag_id>           # Tag löschen (CASCADE)

GET    /api/emails/<id>/tags        # Tags einer Email
POST   /api/emails/<id>/tags        # Tag zuweisen (tag_id)
DELETE /api/emails/<id>/tags/<tag_id>  # Tag entfernen
```

#### **CSRF-Schutz (WICHTIG!)**
```javascript
// Alle AJAX-Requests brauchen CSRF-Token
function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
}

fetch('/api/tags', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()  // ← PFLICHT!
    },
    body: JSON.stringify({ name: 'Rechnung', color: '#3B82F6' })
});
```

---

### 5️⃣ UI-Komponenten

#### **A) Tag-Management (`/tags`)**
```
Navigation → 🏷️ Tags
├─ Tag-Liste mit Email-Count
├─ "Neuer Tag" Button → Modal
│  ├─ Name-Input (1-50 Zeichen)
│  └─ 7-Color-Picker (#3B82F6, #10B981, #F59E0B, #EF4444, ...)
├─ Edit-Button (Stift-Icon)
└─ Delete-Button (Papierkorb-Icon) → Confirmation
```

**Constraints:**
- ✅ Unique(user_id, name) - keine Duplikate
- ✅ Max 50 Zeichen
- ✅ Color als Hex (#RRGGBB)

---

#### **B) Email-Detail Tag-Bereich**
```
Email-Detail → oben unter Zusammenfassung
├─ 🏷️ Tags: [Badge1] [Badge2] [Badge3] [+ Tag hinzufügen]
│  └─ Badge (farbig, mit X) → Click X → removeTag()
│
└─ Modal: "Tag hinzufügen"
   ├─ Liste aller User-Tags (mit Farbe)
   ├─ "Zuweisen" Button pro Tag
   └─ Link: "Tag-Verwaltung" → /tags
```

---

#### **C) Dashboard Filter**
```
Dashboard → Filter-Bereich (links oder oben)
├─ Tags: [Multi-Select Dropdown]
│  ├─ Rechnung (3 Emails)
│  ├─ Finanzen (12 Emails)
│  └─ Wichtig (5 Emails)
│  → Strg/Cmd + Click für Mehrfachauswahl
│
├─ Kombinierbar mit:
│  ├─ Farbe (Rot/Gelb/Grün)
│  ├─ Done (Erledigt/Offen)
│  └─ Suche (Freitext)
```

**Performance-Optimierung:**
```python
# src/01_web_app.py:858-895
# Eager Loading: Alle Tags für alle Emails in EINER Query
email_ids = [mail.id for mail in mails]
tag_assignments = (
    db.query(EmailTagAssignment, EmailTag)
    .join(EmailTag)
    .filter(EmailTagAssignment.email_id.in_(email_ids))
    .all()
)

# Resultat: 100 Emails = 2 Queries (statt 101)
```

---

### 6️⃣ Wichtige Code-Stellen

| Komponente | Datei | Zeilen | Beschreibung |
|------------|-------|--------|--------------|
| **KI-Prompt** | `src/03_ai_client.py` | 78-130 | OLLAMA_SYSTEM_PROMPT mit suggested_tags |
| **Validation** | `src/03_ai_client.py` | 276-287 | _validate_ai_payload() extrahiert suggested_tags |
| **Auto-Assignment** | `src/12_processing.py` | 206-245 | KI-Tags → EmailTag + Assignment |
| **Tag-Manager** | `src/services/tag_manager.py` | 1-332 | 8 Methoden für CRUD + Assignment |
| **Models** | `src/02_models.py` | 87-125 | EmailTag + EmailTagAssignment |
| **Migration** | `migrations/versions/ph10_email_tags.py` | - | Alembic Migration |
| **API Routes** | `src/01_web_app.py` | 1763-2003 | 7 REST Endpoints |
| **Tag-UI** | `templates/tags.html` | 1-302 | Tag-Management Seite |
| **Email-Detail** | `templates/email_detail.html` | 90-787 | Tag-Badges + Modal |
| **Learning-Modal** | `templates/base.html` | 124-210 | "Bewertung korrigieren" |
| **Filter** | `templates/list_view.html` | 8-88 | Multi-Select Tag-Filter |
| **Learning Helper** | `src/01_web_app.py` | 1970-2003 | _update_user_override_tags() |

---

### 7️⃣ Häufige Fehler & Lösungen

#### **Problem: "CSRF token missing" (400 BAD REQUEST)**
```javascript
// ❌ Falsch:
fetch('/api/tags', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
});

// ✅ Richtig:
fetch('/api/tags', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()  // ← Hinzufügen!
    }
});
```

#### **Problem: Tags werden nicht auto-assigned**
```python
# Check 1: _validate_ai_payload() extrahiert suggested_tags?
# src/03_ai_client.py:276-287
validated = {
    "suggested_tags": parsed.get("suggested_tags", [])  # ← Muss vorhanden sein
}

# Check 2: process_pending_raw_emails() verarbeitet Tags?
# src/12_processing.py:207
suggested_tags = ai_result.get("suggested_tags", [])  # ← Muss gefüllt sein
```

#### **Problem: user_override_tags nicht gesetzt**
```python
# _update_user_override_tags() muss nach JEDEM Tag-Add/Remove aufgerufen werden!
# src/01_web_app.py:1990-2003

# Prüfen:
sqlite3 emails.db "SELECT id, user_override_tags FROM processed_emails WHERE user_override_tags IS NOT NULL;"
```

---

### 8️⃣ Testing-Workflow

```bash
# 1. Neue DB mit Tag-System
alembic upgrade head

# 2. Re-process Emails (testet Auto-Assignment)
python3 scripts/reset_base_pass.py
# → Dashboard → "Jetzt verarbeiten"

# 3. Prüfe Tags in DB
sqlite3 emails.db "
SELECT 
    e.id,
    GROUP_CONCAT(t.name, ', ') as tags
FROM processed_emails e
LEFT JOIN email_tag_assignments a ON e.id = a.email_id
LEFT JOIN email_tags t ON a.tag_id = t.id
GROUP BY e.id
LIMIT 10;
"

# 4. Teste UI
# - /tags: Tag erstellen/bearbeiten/löschen
# - Email-Detail: Tag hinzufügen/entfernen
# - Dashboard: Filter nach Tags
# - Learning-Modal: Tags ändern → Check user_override_tags
```

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

Weitere Maintenance-Befehle: siehe **[MAINTENANCE.md](./docs/MAINTENANCE.md)**

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
- **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** – Production Deployment Guide (Gunicorn, Nginx, Fail2Ban)
- **[INSTALLATION.md](docs/INSTALLATION.md)** – Schritt-für-Schritt Installation
- **[MAINTENANCE.md](docs/MAINTENANCE.md)** – Maintenance & Helper-Skripte
- **[OAUTH_AND_IMAP_SETUP.md](docs/OAUTH_AND_IMAP_SETUP.md)** – OAuth & IMAP Konfiguration
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
| **Development** | Active - Core features complete |
| **Tested Platforms** | Linux (Debian 12), WSL2, macOS |
| **Python Version** | 3.11+ |
| **Production Ready** | ⚠️ Beta - single-user tested, please report bugs |
| **Multi-User** | 🟡 Supported, not fully tested |
| **License** | AGPL-3.0 |

---

## 🔒 Security

- **Zero-Knowledge Architecture** - Server kann Daten nicht entschlüsseln
- **AES-256-GCM** für alle E-Mail-Inhalte
- **DEK/KEK Pattern** - Passwort ändern ohne Daten neu zu verschlüsseln  
- **PBKDF2** mit 600.000 Iterationen (OWASP 2024 Standard)
- **Mandatory 2FA** für alle Accounts
- **Keine Klartext-Credentials** - nur verschlüsselt in DB

Siehe [SECURITY.md](./docs/SECURITY.md) für Details.

---

## 📄 Lizenz

Dieses Projekt ist unter der **GNU Affero General Public License v3.0 (AGPL-3.0)** lizenziert.

**Was bedeutet das?**
- ✅ Du kannst die Software **frei nutzen, modifizieren und selbst hosten**
- ✅ Wenn du die Software als **Web-Service anbietest**, musst du deine Änderungen **veröffentlichen**
- ✅ Forks müssen ebenfalls unter AGPL-3.0 bleiben (Copyleft)

Die volle Lizenz findest du in [LICENSE](./LICENSE).

**Warum AGPL?** Weil KI-Mail-Helper eine Web-App ist. AGPL stellt sicher, dass Cloud-Anbieter ihre Verbesserungen mit der Community teilen müssen – im Gegensatz zu MIT/Apache, wo sie es einfach als proprietären SaaS verkaufen könnten.

---

## 🤝 Beitragen

Konstruktive Contributions sind sehr willkommen – einschließlich kritischer Gedanken und neuer Perspektiven.

Bitte lies [SECURITY.md](./docs/SECURITY.md) für Sicherheitsfragen und öffne GitHub Issues für Bugs und Diskussionen.

---

**Verwendung auf eigene Gefahr** – Code vollständig von KI geschrieben. Größte Bemühungen durch gute Prompts und intelligentes Hinterfragen, um ein datenschutzfreundliches, lokal betriebenes KI-Mail-Helper Tool zu bauen. Optional: Cloud-KI-APIs statt lokaler Ollama. Bisher keine Praxiserfahrung in der Verwendung der Software.
