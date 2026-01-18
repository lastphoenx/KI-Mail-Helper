# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

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
