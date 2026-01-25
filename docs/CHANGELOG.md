# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [2.2.2] - 2026-01-25

### 🗂️ Ordner-Audit System mit UI-Konfiguration

#### Neues Feature: Ordner-Audit (Trash-Audit)
- **Analyse von Papierkorb-Ordnern** auf potenziell wichtige Emails
- **Mehrsprachige Unterstützung** für CH/DE/IT/FR Keywords und Patterns
- **Intelligente Erkennung** von:
  - Vertrauenswürdigen Domains (Behörden, Banken, Versicherungen)
  - Wichtigen Betreff-Keywords (Rechnung, Kündigung, Mahnung, etc.)
  - Sicheren Lösch-Patterns (Newsletter, Marketing, Werbung)
  - VIP-Absendern mit Wildcard/Regex-Unterstützung
- **Scan-Ergebnis-Karten** mit Confidence-Score und Kategorisierung

#### UI-Konfiguration für Audit
- **Neuer "Konfiguration"-Tab** im Ordner-Audit-Dialog
- **Vier konfigurierbare Listen:**
  - 🏛️ Vertrauenswürdige Domains (z.B. admin.ch, sparkasse.de)
  - 📋 Wichtige Keywords (z.B. rechnung, kündigung, mahnung)
  - 🔇 Sichere Patterns – Betreff (z.B. Newsletter, Werbung)
  - 🔇 Sichere Patterns – Absender (z.B. @newsletter., noreply@)
  - ⭐ VIP-Absender (Wildcards: *@firma.ch, Regex: /pattern/)
- **"Defaults laden"** Button für mehrsprachige Standardwerte
- **Account-spezifisch oder Global** (Optional per Account)

#### Neue Datenbank-Tabellen
- `audit_trusted_domains` – Vertrauenswürdige Domains
- `audit_important_keywords` – Wichtige Betreff-Keywords
- `audit_safe_patterns` – Sichere Lösch-Patterns (subject/sender)
- `audit_vip_senders` – VIP-Absender mit Wildcard/Regex
- `audit_list_sources` – Tracking für geladene Default-Listen

#### API-Endpoints
- `GET/POST /api/audit-config/trusted-domains` – Domain-Liste verwalten
- `GET/POST /api/audit-config/important-keywords` – Keyword-Liste verwalten
- `GET/POST /api/audit-config/safe-patterns` – Pattern-Liste verwalten
- `GET/POST /api/audit-config/vip-senders` – VIP-Liste verwalten
- `POST /api/audit-config/load-defaults` – Mehrsprachige Defaults laden
- `GET /api/audit-config/stats` – Statistiken über konfigurierte Einträge

#### Technische Details
- **AuditConfigCache**: In-Memory-Caching für performante Konfiguration
- **Pattern-Erkennung**: Automatische Unterscheidung zwischen Wildcard und Regex
- **Batch-Operationen**: Komma-separierte Eingabe für schnelle Bulk-Updates
- **Alembic Migration**: `46a0f5ab4550_add_audit_config_tables`

#### Migration von Trusted-Senders
- Modal "Als Trusted Sender" → "Als VIP Absender" umbenannt
- Verwendet jetzt `/api/audit-config/vip-senders` statt altem System
- VIP-Absender gelten spezifisch für Ordner-Audit

---

## [2.2.1] - 2026-01-24

### 🔧 Mail-Processing-Verbesserungen & Übersetzungs-Fix

#### Mail-Verarbeitung robuster gemacht
- **Fortsetzung unvollständiger Verarbeitung**
  - System setzt Verarbeitung bei Status 10, 20, 40, 50 fort (nicht nur bei 0)
  - Ermöglicht Recovery nach Crashes oder abgebrochenen Prozessen
  - ProcessedEmails werden gelöscht wenn RawEmail neu verarbeitet wird
  
- **Verbesserte Status-Anzeige**
  - Frontend zeigt jetzt Fehler-Status (⚠️) und Erfolgs-Status (✅) mit Tooltips
  - Delta-Anzeige: Zeigt Differenz seit letztem Abruf (z.B. "+3 neue")
  - Warnung bei Quota-Limits oder Verbindungsfehlern
  - UI lädt automatisch nach jedem Fetch

- **Verarbeitungs-Reihenfolge korrigiert**
  - Emails werden jetzt nach `received_at` aufsteigend verarbeitet (älteste zuerst)
  - Vorher: Nach ID (zufällig bei gleichzeitigem Fetch mehrerer Accounts)
  - Verhindert, dass neueste Emails alte blockieren

#### Opus-MT Übersetzungs-Fix (Halluzination behoben)
- **Root Cause:** HTML→Plain-Text-Konvertierung mit inscriptis produzierte massive Trailing Spaces
- **Fixes:**
  - `inscriptis.get_text()` nutzt jetzt `ParserConfig(display_links=False)` (kein Link-Text mehr)
  - `line.rstrip()` entfernt Trailing Spaces vor Opus-MT-Übergabe
  - Token-Count statt Char-Count für Chunking-Entscheidung (präziser)
  - MAX_TRANSLATION_CHARS von 1500 → 5000 erhöht (vermeidet vorzeitiges Abschneiden)
  - Whitespace-Skipping in Chunking-Logik: `if not chunk.strip(): continue`
- **Ergebnis:** Keine "Es ist nicht bekannt, ob"-Halluzinationen mehr, saubere Übersetzungen

#### Neue SQL-Wartungsbefehle
- Dokumentiert in `docs/CLI_REFERENZ.md` → Abschnitt "4.5 Schnelle DB-Wartung (SQL)"
- Status zurücksetzen: `UPDATE raw_emails SET processing_status=0 WHERE id=X;`
- Übersetzung löschen: `SET encrypted_translation_de=NULL, translation_engine=NULL`
- Fehler bereinigen: `SET processing_error=NULL, processing_warnings=NULL`
- Batch-Operationen: `WHERE processing_status > 0 AND processing_status < 100`

#### Geänderte Dateien
- `src/12_processing.py` – inscriptis ParserConfig, Verarbeitungs-Reihenfolge (ORDER BY received_at ASC)
- `src/services/translator_service.py` – Token-Count-Check, line.rstrip(), Whitespace-Skipping
- `src/blueprints/api.py` – Frontend-Response mit Fehler/Erfolg/Delta-Counts
- `templates/settings.html` – Fehler-Status-Icon, Delta-Anzeige, bessere Tooltips
- `docs/CLI_REFERENZ.md` – Neue SQL-Befehle für DB-Wartung

---

## [2.2.0] - 2026-01-22

### 🧹 Code-Bereinigung & Architektur-Migration

#### Entfernte Legacy-Dateien
- `src/01_web_app.py` → Vollständig migriert zu Blueprint-Architektur
- `src/14_background_jobs.py` → Vollständig migriert zu Celery-Tasks (`src/tasks/`)
- `src/02_models_ph18_trustsender.py` → Obsoletes Model-Fragment entfernt
- `src/09_migrate_oauth.py` → Migration abgeschlossen, Script nicht mehr benötigt
- `src/13_migrate_ai_preferences.py` → Migration abgeschlossen
- `src/16_migrate_user_corrections.py` → Migration abgeschlossen
- `src/17_migrate_model_tracking.py` → Migration abgeschlossen
- `src/18_migrate_ml_columns.py` → Migration abgeschlossen
- `migrations/versions_sqlite_legacy/` → SQLite-Legacy-Support entfernt
- `src/blueprints/email_actions_legacy.py` → Nicht mehr genutzt

#### Neue Helper-Module
- `src/helpers/database.py` → Zentrale DB-Session-Verwaltung
- `src/helpers/responses.py` → Standardisierte API-Responses
- `src/helpers/validation.py` → Input-Validierung für alle Blueprints
- `src/helpers/__init__.py` → Helper-Package

#### Breaking Changes
- ⚠️ **Environment Variables entfernt:**
  - `USE_LEGACY_JOBS` → Nicht mehr unterstützt
  - `USE_BLUEPRINTS` → Nicht mehr unterstützt (immer aktiv)
- ⚠️ **Celery + Redis jetzt erforderlich:**
  - Alle asynchronen Jobs laufen ausschließlich über Celery
  - Redis muss als Message Broker verfügbar sein
  - Siehe: `docs/INSTALLATION.md` für Setup-Anleitung

#### Geänderte Dateien
- `src/blueprints/api.py` → Batch-Reprocess auf Celery-Task migriert
- `src/blueprints/rules.py` → Syntax-Fix (Einrückung)
- `src/thread_api.py` → Import auf `helpers.database` umgestellt
- `scripts/verify_anonymized_flag.py` → Import auf `helpers.database` umgestellt
- `README.md` → Referenzen auf `01_web_app.py` entfernt
- `src/blueprints/*.py` → Header-Kommentare aktualisiert
- `src/helpers/*.py` → Header-Kommentare aktualisiert
- `templates/base.html` → Kommentare aktualisiert
- `src/app_factory.py` → Kommentare aktualisiert

---

## [2.2.0] - 2026-01-21

### 🌍 KI-Übersetzer (Translator Feature)

#### Neue Features
- **Standalone Translator Tool** – Erreichbar unter `/translator`
  - Automatische Spracherkennung via fastText (176 Sprachen)
  - Cloud-Übersetzung via OpenAI/Anthropic/Mistral
  - Lokale Übersetzung via Opus-MT (Helsinki-NLP)
- **fastText Integration**
  - Facebook's lid.176.bin Modell (126 MB)
  - Erkennt 176 Sprachen mit Confidence-Score
  - Lazy-Loading für schnellen App-Start
- **Opus-MT Integration (lokal)**
  - Helsinki-NLP/opus-mt-{src}-{tgt} Modelle
  - ~300MB pro Sprachpaar, gecached in ~/.cache/huggingface
  - Keine API-Kosten, läuft komplett offline
- **UI Features**
  - Engine-Toggle: Cloud-KI vs. Opus-MT (lokal)
  - Provider/Model-Auswahl für Cloud (kuratierte Liste)
  - Echtzeit-Spracherkennung beim Tippen
  - Zielsprachen-Buttons (DE, EN, FR, IT, ES, PT, NL, PL)
  - Copy-to-Clipboard für Übersetzung

#### Neue Dateien
- `src/services/translator_service.py` – TranslatorService mit fastText + Opus-MT
- `src/blueprints/translator.py` – API Endpoints für Übersetzung
- `templates/translator.html` – Translator UI
- `models/lid.176.bin` – fastText Language Detection Modell

#### Neue Dependencies
- `fasttext-wheel==0.9.2` – Language Detection (manuell gepatcht für GCC 13+)
- `transformers==4.57.6` – Hugging Face Transformers für Opus-MT
- `sentencepiece==0.2.1` – Tokenizer für MarianMT
- `torch` (CPU) – PyTorch Backend für Transformers

#### Geänderte Dateien
- `src/app_factory.py` – translator_bp registriert
- `templates/base.html` – "🌍 Übersetzer" im Navigationsmenü

---

## [2.1.0] - 2026-01-19 (Unreleased)

### 🏛️ Architektur-Defaults geändert

#### Blueprint-Architektur als Standard
- **Blueprint-Refactoring** abgeschlossen – Modulare Architektur ist jetzt der einzige Standard
- **Celery/Redis Queue** – Asynchrone Job-Queue ist jetzt der einzige Standard

#### Geänderte Dateien
- `src/00_main.py` – Default von `"0"` auf `"1"` geändert
- `src/app_factory.py` – Default von `"true"` auf `"false"` geändert

---

### 🧠 Personal Classifier UI-Toggle

#### Neue Features
- **UI-Toggle in Settings** – "Persönlich trainierte Modelle bevorzugen"
  - Platzierung: Machine Learning Card, nach Training-Stats, vor dem Training-Button
  - Speichert `prefer_personal_classifier` Präferenz in DB
  - Toast-Feedback bei Änderung
- **API-Endpoint** – `GET/POST /api/classifier-preferences`
  - Konsistent mit bestehenden Settings-APIs
  - CSRF-Protected

#### Geänderte Dateien
- `src/blueprints/api.py` – Neuer Endpoint `api_classifier_preferences()`
- `templates/settings.html` – Toggle, JavaScript, showToast-Funktion

---

## [2.1.0] - 2026-01-18 (Unreleased)

### 📅 Kalender-Erkennung (Phase 25)

#### Neue Features
- **Automatische Kalender-Erkennung** – Erkennt iCalendar-Einladungen (iMIP/RFC 6047) beim Email-Abruf
  - Unterstützte Methoden: REQUEST (Einladung), REPLY (Zu-/Absage), CANCEL (Absage)
  - Erkennung von Datum, Uhrzeit, Ort, Organisator und Teilnehmern
- **Prominente Kalender-Karte** – Farbcodierte Anzeige in der Email-Detailansicht
  - 📅 Blau für Termineinladungen (REQUEST)
  - ✅ Grün für Terminantworten (REPLY/ACCEPTED)
  - ❌ Rot für Terminabsagen (CANCEL/DECLINED)
- **Kalender-Filter in Listenansicht** – Dropdown "📅 Termine" zum Filtern
  - Alle anzeigen, Nur Termine, Keine Termine
- **Kalender-Badges** – Farbige Badges vor dem Betreff in der Liste
  - Unterschiedliche Farben je nach Methode (REQUEST/REPLY/CANCEL)
- **Robuster iCalendar-Parser** – `icalendar`-Bibliothek mit Regex-Fallback

#### Neue Felder (Datenbank)
- `is_calendar_invite` (Boolean, indexed) – Schneller Filter
- `calendar_method` (String) – REQUEST/REPLY/CANCEL für Badges ohne Entschlüsselung
- `encrypted_calendar_data` (Text) – Verschlüsselte Kalenderdetails (JSON)

#### Geänderte Dateien
- `src/02_models.py` – Neue Spalten in RawEmail
- `src/06_mail_fetcher.py` – `_extract_calendar_data()`, `_parse_icalendar()`, `_parse_icalendar_regex()`
- `src/tasks/mail_sync_tasks.py` – Kalender-Felder in `_persist_raw_emails()`
- `src/blueprints/emails.py` – Kalender-Filter und Entschlüsselung
- `templates/email_detail.html` – Kalender-Karte mit Farbcodierung
- `templates/list_view.html` – Filter-Dropdown und Badges

#### Migrationen
- `b2c3d4e5f6g7_add_calendar_invite_fields.py` – `is_calendar_invite`, `encrypted_calendar_data`
- `c3d4e5f6g7h8_add_calendar_method_field.py` – `calendar_method`

---

### ⚡ Auto-Rules UI-Verbesserungen

#### Neue Features
- **Learning pro Regel** – Learning kann jetzt auf Regel-Ebene aktiviert/deaktiviert werden
  - Neuer Toggle-Button in der Regeltabelle (🎓 Aktiv / Inaktiv)
  - Klickbar wie der Status-Toggle
  - API-Unterstützung: GET/POST/PUT mit `enable_learning` Feld
- **Verbesserte Regeltabelle** – Übersichtlichere Darstellung
  - **Status-Toggle** – Klickbarer Button mit Hover-Effekt (grün "Aktiv" / grau "Inaktiv")
  - **Learning-Spalte** – Separate Spalte mit violettem Toggle-Button
  - **Aktions-Buttons** – Icons mit Beschriftung: 🧪 T (Testen), ✏️ B (Bearbeiten), 🗑️ L (Löschen)
  - **Einheitliche Badge-Größen** – Alle Badges (Status, Priorität, Learning) gleich groß
  - **Vertikale Ausrichtung** – Alle Tabellenzellen oben ausgerichtet

#### Geänderte Dateien
- `src/blueprints/api.py` – `enable_learning` zu GET/POST/PUT API hinzugefügt
- `templates/rules_management.html` – Neue Tabellenspalte, CSS und JavaScript

---

### 🧠 Hybrid Score-Learning (Personal Classifier)

#### Neue Features
- **Personal Classifier System** – Individuelles ML-Modell pro Benutzer
  - 4 Classifier-Typen: Dringlichkeit, Wichtigkeit, Spam, Kategorie
  - SGDClassifier mit StandardScaler für konsistente Feature-Skalierung
  - Automatisches Training aus User-Korrekturen (min. 5 Samples)
- **Global/Personal Fallback** – Robuste Hierarchie
  - Personal Classifier verfügbar → nutze Personal
  - Sonst → Fallback auf Global Classifier
  - Benutzer-Präferenz über `prefer_personal_classifier` Toggle
- **Async Training Pipeline** – Celery-basiertes Training
  - Redis-Lock verhindert parallele Training-Jobs
  - Throttling: Max 1 Training alle 5 Minuten pro Classifier
  - Atomic Writes: temp-Datei → os.rename() für Konsistenz
- **TTL-Caching** – 5-Minuten Cache für Classifier/Scaler
  - Thread-safe mit Lock-Protection
  - Negative-Caching mit `_NOT_FOUND` Sentinel
  - `invalidate_classifier_cache()` für Cache-Flush
- **Accuracy-Tracking** – LOO oder 5-Fold CV
  - `ClassifierMetadata` Tabelle mit accuracy_score, training_samples, etc.
  - Circuit-Breaker ready: Accuracy < 50% → Fallback auf Global
- **Auto-Training Trigger** – Training startet automatisch nach User-Korrekturen
- **User-Deletion Cleanup** – Event-Listener löscht Personal Classifier bei User-Löschung

#### Neue Dateien
- `src/services/personal_classifier_service.py` – Caching, Loading, Prediction
- `src/tasks/training_tasks.py` – Celery Training Task
- `migrations/versions/07f565a456dd_add_classifier_metadata_table.py` – DB-Migration

#### Datenbank-Änderungen
- **Neue Tabelle**: `classifier_metadata` (user_id, classifier_type, accuracy_score, etc.)
- **User-Feld**: `prefer_personal_classifier` (Boolean, default=False)
- **ProcessedEmail-Feld**: `used_model_source` ('global', 'personal', 'ai_only')

---

## [2.0.1] - 2026-01-17

### 🛠️ Bugfixes & Stabilität

#### Celery Worker OOM-Fixes
- **Memory-Limits optimiert** – `MemoryMax=6G`, `concurrency=4`, `max-tasks-per-child=50`
- **Ollama Keep-Alive** – `keep_alive="30m"` verhindert wiederholtes Modell-Laden
- **spaCy Global-Caching** – Modell wird nur einmal pro Worker geladen

#### Email-Rendering verbessert
- **HTML-Body-Präferenz** – E-Mails werden jetzt wie in Outlook mit HTML-Körper angezeigt
- **4 Render-Tabs** – Gerendert, Raw HTML, Raw Content (Plain Text), Anonymisiert
- **Intelligenter Fallback** – Nur bei defektem HTML (nowrap-Body) wird Plaintext verwendet

#### Klassische E-Mail-Anhänge
- **EmailAttachment-Model** – Neue DB-Tabelle für PDF, Word, Excel, Bilder
- **Zero-Knowledge Verschlüsselung** – Anhänge mit AES-256-GCM verschlüsselt
- **Download-Endpoint** – `/email/<id>/download-attachment/<att_id>`
- **UI-Integration** – 📎-Icon in Listenansicht, Anhänge-Sektion in Detailansicht
- **Größenlimits** – Max 25 MB pro Datei, 100 MB pro E-Mail

#### Race-Condition Fix
- **Duplicate Key Error** – Robuste Behandlung in 12_processing.py mit Session-Rollback

#### UX-Verbesserungen
- **Filter-Persistenz** – "Zurück zur Liste" Button behält Filter (Account, Ordner, etc.)
- **Reset-Button** – "🔄 Reset" in Listenansicht setzt alle Filter zurück
- **Account-Sortierung** – Mail-Accounts werden jetzt konsistent nach ID sortiert

### Geändert
- **inscriptis-Library** – Für HTML→Plain Text Konvertierung (statt html2text)

---

## [2.0.0] - 2026-01-16

### 🚀 Major Release: Multi-User Edition

**Komplette Architektur-Migration für Enterprise-Einsatz**

### Hinzugefügt

#### Multi-User & Datenbank
- **PostgreSQL-Backend** – Migration von SQLite zu PostgreSQL 17
- **Multi-User-Support** – Vollständige Benutzer-Isolation
- **Connection Pooling** – SQLAlchemy Pool (20 base, 40 overflow)
- **User-Whitelist** – Admin-kontrollierte Registrierung

#### Asynchrone Verarbeitung
- **Celery Task Queue** – Redis als Broker (statt synchroner Jobs)
- **Background Workers** – `mail-helper-worker.service`
- **Echtzeit-Progress** – WebSocket-ähnliche Task-Status-Updates
- **Scheduled Tasks** – Celery Beat für periodische Jobs

#### Blueprint-Architektur
- **10 Flask Blueprints** – Modulare Code-Struktur
- **145 API-Routes** – RESTful API-Design
- **Separation of Concerns** – Klare Trennung nach Funktionalität

#### Email-Rendering
- **Inline-Attachments (CID-Bilder)** – Automatische Konvertierung von `cid:` URLs zu `data:` URLs
  - Content-ID Bilder-Extraktion beim Mail-Fetch
  - AES-256-GCM Verschlüsselung (`encrypted_inline_attachments`)
  - Robustes Regex-Pattern (case-insensitive, Newline-tolerant)
  - CSP-Header angepasst: `img-src https: data:`
  - Größenlimit: 2 MB total, 500 KB pro Attachment

### Geändert
- **Datenbank-Layer** – SQLAlchemy 2.0 mit PostgreSQL-Dialekt
- **Session-Management** – Server-Side Sessions mit Redis
- **Background Jobs** – Von Thread-basiert zu Celery-Tasks
- **Config-Management** – Environment-basierte Konfiguration

### Entfernt
- **SQLite-Support** – Nur noch PostgreSQL
- **Legacy Job Queue** – Ersetzt durch Celery
- **Monolithische Struktur** – Aufgeteilt in Blueprints

---

## [1.3.2] - 2026-01-10

### Hinzugefügt
- **Rollen-basierte Email-Anonymisierung** mit granularen Platzhaltern
  - `[ABSENDER_VORNAME]`, `[ABSENDER_NACHNAME]`, `[ABSENDER_VOLLNAME]`
  - `[EMPFÄNGER_VORNAME]`, `[EMPFÄNGER_NACHNAME]`, `[EMPFÄNGER_VOLLNAME]`
- **EntityMap Persistierung** – Mapping wird verschlüsselt in DB gespeichert
- **Intelligente Namenserkennung** – Titel-Erkennung (Dr., Prof., etc.)

### Behoben
- De-Anonymisierung funktioniert jetzt bei allen Ton-Varianten

---

## [1.3.1] - 2026-01-10

### Hinzugefügt
- **Reply-Generator De-Anonymisierung** – Automatische Rück-Übersetzung
- **4 Ton-Varianten** – Formell, Freundlich, Kurz, Höflich ablehnen
- **EntityMap Integration** – Platzhalter → Echte Namen

---

## [1.3.0] - 2026-01-09

### Hinzugefügt
- **Email-Anonymisierung mit spaCy** (DSGVO-konform)
  - 3 Levels: Regex, Light (PER), Full (PER, ORG, LOC)
  - Lazy-Loading des spaCy-Modells
  - Batch-Processing für Performance
- **Confidence Tracking** – `ai_confidence` & `optimize_confidence` Felder
- **Dual-Storage** – Original + Anonymisiert (beide verschlüsselt)
- **Account-Level Analyse-Modi** – spacy_booster, llm_anon, llm_original, none

---

## [1.2.0] - 2026-01-08

### Hinzugefügt
- **Phase Y: KI-gestützte Priorisierung**
  - spaCy Hybrid Pipeline (80% NLP + 20% Keywords)
  - 7 NLP-Detektoren (Imperative, Deadline, VIP, etc.)
  - 12 Keyword-Sets mit 80 Begriffen
  - Ensemble Learning mit SGD-Regression
- **Phase X.3: Account-Level AI-Fetch-Control**
  - Separate Toggles für AI-Analyse und UrgencyBooster

---

## [1.1.0] - 2026-01-07

### Hinzugefügt
- **Phase X: Trusted Senders** – Account-basierte Whitelist
- **Phase X.2: Dedizierte Whitelist-Seite** (`/whitelist`)
- **UrgencyBooster** – Automatische Urgency für VIP-Absender

---

## [1.0.0] - 2026-01-06

### Hinzugefügt
- **Tag Suggestion Queue** – KI-Vorschläge für neue Tags
- **Negative Feedback** – System lernt aus Ablehnungen
- **Auto-Assignment Flag** – Automatische Tag-Zuweisung

---

## [0.9.0] - 2026-01-05

### Hinzugefügt
- **Online-Learning System** – 4 SGD-Classifier (D/W/Spam/Kategorie)
- **Bewertung korrigieren** – User-Override mit Training
- **Dashboard Multi-Account Filter**

---

## [0.8.0] - 2026-01-03

### Hinzugefügt
- **Phase F.2: 3-Settings System** – Embedding/Base/Optimize Model
- **Batch-Reprocess** – Async Embedding-Neuberechnung
- **Phase F.1: Semantic Search** – Embeddings für Ähnlichkeitssuche

---

## [0.7.0] - 2026-01-01

### Hinzugefügt
- **IMAPClient Migration** – Von imaplib zu IMAPClient 3.0.1
- **Phase 14: UIDVALIDITY Sync** – RFC-konforme UID-Synchronisation
- **ServiceToken Elimination** – Zero-Knowledge DEK-Handling

---

## [0.6.0] - 2025-12-31

### Hinzugefügt
- **Phase 12: Thread-basierte Conversations**
  - ThreadService mit Reply-Chain-Mapping
  - Thread-View Template
  - N+1 Query Optimization

---

## [0.5.0] - 2025-12-28

### Hinzugefügt
- **Production Security Hardening**
  - Rate Limiting (Flask-Limiter)
  - Account Lockout (5 Versuche → 15min Ban)
  - ReDoS Protection
  - Timing-Attack Protection

---

## [0.4.0] - 2025-12-27

### Hinzugefügt
- **Phase 8b: DEK/KEK Pattern** – Passwort ändern ohne Re-Encryption
- **AI Model Defaults** – Optimierte Standardwerte

---

## [0.3.0] - 2025-12-25

### Hinzugefügt
- **Phase G: AI Action Engine**
  - Reply Draft Generator (4 Ton-Varianten)
  - Auto-Rules Engine (14 Bedingungen)
- **Phase H: SMTP Mail-Versand** mit Sent-Sync
- **Phase I: Customizable Reply Styles**

---

## [0.2.0] - 2025-12-23

### Hinzugefügt
- **Phase 3: Zero-Knowledge Encryption**
  - Master Key System (PBKDF2 + AES-256-GCM)
  - IMAP Password Encryption
  - Email Body/Summary Encryption

---

## [0.1.0] - 2025-12-21

### Hinzugefügt
- **Initial Release**
  - Ollama Integration für Email-Analyse
  - Web Dashboard mit Flask
  - IMAP Mail Fetcher
  - Basic Processing Pipeline
  - Multi Mail-Accounts per User
  - 2FA (TOTP) mit QR-Code Setup

---

*Dieses Changelog dokumentiert die wesentlichen Meilensteine. Für detaillierte Commit-Historie siehe Git-Log.*
