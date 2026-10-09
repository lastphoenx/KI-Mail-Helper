# 📧 KI-Mail-Helper

**Lokaler KI-Mail-Assistent, selbst betrieben**

Ein selbst-gehosteter Email-Organizer. Mail-Inhalte und Zugangsdaten liegen verschlüsselt in der Datenbank. Solange du angemeldet bist, entschlüsselt der Server sie, um Mails anzuzeigen, abzuholen und zu bewerten. Das ist Verschlüsselung im Ruhezustand, kein Zero-Knowledge im engen Sinn: der Betreiber des Servers kann den Klartext sehen, während eine Sitzung läuft. Das Projekt dient dem eigenen Betrieb und dem Ausprobieren lokaler Modelle.

---

## Kernfeatures

- **Verschlüsselung im Ruhezustand** – AES-256-GCM, DEK/KEK. Klartext nur, solange die Sitzung den Schlüssel hält
- **3×3 Prioritäts-Matrix** – Dringlichkeit × Wichtigkeit mit Farbcodierung + Account-Filter
- **KI-gestützte Priorisierung** – spaCy NLP (80%) + Keywords (20%) + Ensemble Learning
- **Multi-Provider AI** – Lokale Modelle (Ollama) oder Cloud (Claude, OpenAI, Mistral)
- **🌍 KI-Übersetzer** – Standalone Translation Tool
  - Spracherkennung: fastText (176 Sprachen, lokal)
  - Cloud-Übersetzung: OpenAI/Anthropic/Mistral
  - Lokale Übersetzung: Opus-MT (Helsinki-NLP, offline)
- **Email-Anonymisierung** – spaCy PII-Entfernung (DSGVO-konform) vor Cloud-AI-Übertragung
  - 3 Levels: Regex (EMAIL, PHONE, IBAN, URL), Light (+ PER), Full (+ ORG, GPE, LOC)
  - On-the-fly Anonymisierung: Automatisch beim Reply-Generieren wenn keine anonymisierte Version existiert
- **Optimized Reply Prompts** – Speziell für Small Local LLMs (<8B Parameter) optimiert
- **Provider/Model Selection** – Dynamische Auswahl in Reply Modal (Ollama, OpenAI, Anthropic, Mistral)
- **Dynamic Temperature Support** – Automatische Erkennung für o1/o3/gpt-5 Modelle
- **Confidence Tracking** – Transparenz über AI-Analyse-Qualität (0.65-0.9 für Hybrid Booster)
- **Hybrid Score-Learning** – Global + Personal Classifier pro Benutzer
  - Global Classifier: Trainiert auf alle User-Korrekturen
  - Personal Classifier: Individuelles Modell mit TTL-Caching
  - UI-Toggle in Settings: "Persönlich trainierte Modelle bevorzugen"
  - Fallback-Hierarchie: Personal → Global → AI-Only
- **Online-Learning System** – SGD-Classifier lernt aus User-Korrekturen (4 Classifier: D/W/Spam/Kategorie)
- **AI Action Engine** – Reply Draft Generator (4 Ton-Varianten) + Aktions-Regeln (15 Bedingungen, inkl. Mail-Alter, Learning pro Regel)
- **Customizable Reply Styles** – Anrede, Grussformel, Signatur & Instructions pro Stil + Account-spezifisch
- **Account-Specific Signatures** – Individuelle Signaturen pro Mail-Account (Geschäft/Privat/Uni)
- **Trusted Senders + UrgencyBooster** – Account-basierte Whitelist mit Urgency-Override (Global + Per-Account)
- **Dedizierte Whitelist-Seite** – `/whitelist` mit 2-Spalten-Layout, Batch-Operationen und Live-Filter
- **Account-Level AI-Fetch-Control** – Separate AI-Analyse und UrgencyBooster Toggles pro Account
- **Semantische Suche** – Embeddings für "finde ähnliche Emails"
- **Tag-System** – Manuell + KI-Vorschläge basierend auf gelernten Mustern
- **Email-Inline-Bilder (CID)** – Automatische Anzeige von Inline-Attachments ohne externe Requests
- **Klassische Anhänge** – PDF, Word, Excel, Bilder verschlüsselt speichern & herunterladen (≤25MB)
- **IMAP & Gmail OAuth** – Funktioniert mit GMX, Gmail, Outlook, etc.
- **SMTP Versand** – Antworten & neue Emails mit Sent-Ordner-Sync
- **Thread-View** – Konversations-basierte Ansicht mit Context
- **Fetch-Filter** – Account-spezifisch: Ordner, Datum, UNSEEN, Delta-Sync
- **Multi-Account Dashboard** – Filter Dashboard nach spezifischem Email-Account
- **Kalender-Erkennung** – Automatische Erkennung von iCalendar-Einladungen (REQUEST/REPLY/CANCEL)
  - Farbcodierte Kalender-Karte in Detailansicht (blau/grün/rot)
  - Filter-Dropdown und Badges in Listenansicht
- **Ordner-Audit** – Bewertet Mails in beliebigen Ordnern: sicher löschbar, prüfen, möglicherweise wichtig, Scam/Betrug und Verdacht
  - Scam-Erkennung ohne fest eingebaute Konten: Marken-Imitation, Auth-Fehler, Domain-Alter (DNS/RDAP), optional KI-Identitätsprüfung nur bei Grauzone
  - Alles konfigurierbar pro Account in der UI: Marken, Meine Domains/Adressen, VIP, wichtige Ordner, Wortlisten, Aufbewahrungsfristen
  - Bekannte Kontakte verschlüsselt (wie Mails)

---

## Status

**Version:** 2.3.0 (Oktober 2026)  
**Betrieb:** Produktiv, Schwerpunkt Benutzung  
**Development:** Keine aktive Feature-Entwicklung  
**Architecture:** Flask Blueprints + PostgreSQL + Celery  
**Stability:** Im eigenen Betrieb 

**v2.0 Highlights:**
- ✅ Multi-User mit vollständiger User-Isolation
- ✅ PostgreSQL statt SQLite (skalierbar)
- ✅ Celery Task Queue (asynchrone Verarbeitung)
- ✅ Blueprint-basierte Modularisierung (10 Blueprints)
- ✅ Verschlüsselung im Ruhezustand (DEK/KEK)
- ✅ Mandatory 2FA für alle Accounts

**v2.2.1 Highlights (Januar 2026):**
- ✅ Robuste Mail-Verarbeitung: Fortsetzung unvollständiger Emails
- ✅ Live-Status-Tracking: Erfolg/Fehler/Warnungen mit Delta-Anzeige
- ✅ Verbessertes Opus-MT: inscriptis-Konfiguration + Token-Count-Präzision
- ✅ Prozess-Reihenfolge: Älteste unverarbeitete Emails zuerst
- ✅ SQL-Wartungsbefehle: Schnelle DB-Operationen für Status-Reset & Debugging

**v2.2.2 Highlights (Januar 2026):**
- ✅ Ordner-Audit: erste UI-Konfiguration (Domains, Keywords, VIP, Patterns)
- ✅ UI-Konfiguration: Vertrauenswürdige Domains, Keywords, Patterns, VIP-Absender
- ✅ Mehrsprachige Defaults: CH/DE/IT/FR Keywords und Patterns
- ✅ VIP-Absender: Wildcard (`*@firma.example`) und Regex-Unterstützung
- ✅ Einstufungs-Regeln: Pattern-basierte Disposition (SAFE/IMPORTANT/SCAM/REVIEW)
- ✅ Cluster-Dropdown: Einheitliches UI für alle 6 Konfigurationslisten

**v2.3.0 Highlights (Oktober 2026):**
- ✅ Scam- und Verdacht-Kachel im Ordner-Audit
- ✅ Marken-Tabelle mit Domain-Status
- ✅ Wichtige Ordner aus der Ordnerliste (Ordner plus Unterordner)
- ✅ Aufbewahrung von Routine-Mails (Erfolg und Versand, 1–3650 Tage)
- ✅ Wortlisten: sensibel, Alarm, Erfolg, Versand
- ✅ Aktions-Regeln: «Mail älter als N Tage», Test-Knopf zeigt die Treffer vorher

---

## ⚠️ Haftungsausschluss / Disclaimer (AI-Generated Code)

> **Betrieb:** Die Software läuft produktiv. Neue Features sind zurzeit nicht der Schwerpunkt. Vor einem Update trotzdem die eigenen Tests machen.

### 🇩🇪 Deutsch

**Hinweis: KI-generierter Code (im Betrieb)**

Dieses Repository wurde mit mehreren KI-Systemen erstellt. Der Code wurde bisher **vollständig von KI erzeugt**; keine Zeile wurde manuell von einem Menschen geschrieben. Die gesamte Entwicklung erfolgte in **Microsoft Visual Studio Code (VS Code)** mit GitHub Copilot als primärem Entwickler.

**Aktuelle Features (Stand Oktober 2026):**
- 🎯 **KI-Priorisierung:** spaCy plus Keywords, dazu ein optionaler zweiter Durchlauf (Optimize) für die Posteingang-Bewertung
- 📁 **Ordner-Audit:** Regeln für Scam, Verdacht, wichtige Ordner, Aufbewahrung und Wortlisten. Eine optionale Identitäts-KI nur in der Grauzone, nicht der Optimize-Durchlauf
- 🛡️ **Email-Anonymisierung:** spaCy-PII-Entfernung vor einer Cloud-Bewertung der Posteingang-Analyse
- 📊 **Confidence Tracking:** getrennte Werte für den ersten und den optionalen zweiten Durchlauf
- 🤖 **Kern:** Verschlüsselung im Ruhezustand, 3×3-Matrix, lokale oder Cloud-Modelle
- 🧠 **Lernen:** Globaler und persönlicher Classifier, plus Korrekturen aus der Benutzung
- 🔐 **Sicherheit:** Rate Limiting, Pflicht-2FA, Sperre nach Fehlversuchen
- 📥 **Fetch:** IMAP/Gmail OAuth mit account-spezifischen Filtern (Ordner, Datum, UNSEEN)
- 📤 **Send:** SMTP-Versand mit automatischer Sent-Ordner-Synchronisation
- 🧵 **Thread-View:** Konversations-basierte Email-Ansicht mit KI-Context
- 🔍 **Semantic Search:** Vector-basierte Suche mit Embeddings (OpenAI, Mistral, etc.)
- 🏷️ **Smart Tags:** KI-Vorschläge + Learning-System + Multi-Tag-Filter
- 🤖 **AI Actions:** Reply Draft Generator (4 Ton-Varianten) + Aktions-Regeln (15 Bedingungen, inkl. Mail-Alter)

**Trotz größter Sorgfalt beim Prompting, kritischem Hinterfragen und wiederholten Reviews erfolgt die Verwendung auf eigenes Risiko.** Die Software wird „wie gesehen" (as is) bereitgestellt – ohne Gewährleistung und ohne Zusicherung hinsichtlich Korrektheit, Sicherheit oder Eignung. Wenn du das Tool mit echten Mail-Accounts oder sensiblen Daten nutzen willst, führe bitte eigene Tests, Threat-Modeling und ein unabhängiges Security-Review durch.

### 🇬🇧 English

**Notice: AI-generated code (in production use)**

> **In use:** The software runs in production. New features are not the current focus. Still test before you update.

This repository was created with multiple AI systems. So far, the codebase has been generated **entirely by AI** — not a single line was written manually by a human. All development work was performed in **Microsoft Visual Studio Code (VS Code)** with GitHub Copilot as primary developer.

**Current Features (October 2026):**
- 🎯 **AI prioritization:** spaCy plus keywords, plus an optional second pass for the inbox score
- 📁 **Folder audit:** scam, suspicion, important folders, retention and word lists. An optional identity model only in the gray zone, separate from the inbox optimize pass
- 🛡️ **Anonymization:** spaCy PII removal before a cloud inbox analysis
- 📊 **Confidence:** separate values for the first pass and the optional second pass
- 🤖 **Core:** encryption at rest, 3×3 matrix, local or cloud models
- 🧠 **Learning:** global and personal classifiers, plus corrections from use
- 🔐 **Security:** rate limiting, mandatory 2FA, lockout after failed logins
- 📥 **Fetch:** IMAP/Gmail OAuth with account-specific filters (folders, date, UNSEEN)
- 📤 **Send:** SMTP with automatic Sent folder sync
- 🧵 **Thread-View:** Conversation-based email view with AI context
- 🔍 **Semantic Search:** Vector-based search with embeddings (OpenAI, Mistral, etc.)
- 🏷️ **Smart Tags:** AI suggestions + learning system + multi-tag filters
- 🤖 **AI Actions:** Reply Draft Generator (4 tone variants) + action rules (15 conditions, including mail age)

**Despite careful prompting, critical challenge/verification, and repeated reviews, use is at your own risk.** The software is provided "as is", without warranty, and with no guarantee of correctness, security, or fitness for a particular purpose. If you plan to use it with real email accounts or sensitive data, please conduct your own testing, threat modeling, and an independent security review first.

---

## 🎯 Was ist KI-Mail-Helper?

Ein lokaler Mail-Assistent, der E-Mails:
- von IMAP-Konten und über Gmail OAuth abholt
- im Ruhezustand verschlüsselt speichert und während der Sitzung entschlüsselt
- mit einem lokalen Modell (Ollama, Modell in den Einstellungen) oder einer Cloud-KI bewertet
- in der **3×3-Matrix** zeigt (Wichtigkeit × Dringlichkeit, nur der Posteingang)
- im **Ordner-Audit** nach Regeln einstuft (Scam, Verdacht, prüfen, sicher löschbar)
- mit Aktions-Regeln verschiebt oder markiert, getrennt von den Einstufungs-Regeln
- als Threads und über die semantische Suche erreichbar macht

---

## ✨ Features

### Kernfunktionen
- **🔐 Verschlüsselung im Ruhezustand** – AES-256-GCM, DEK/KEK ([docs/SECURITY.md](docs/SECURITY.md))
  - Mails, KI-Texte und IMAP/SMTP-Zugangsdaten liegen verschlüsselt in PostgreSQL
  - Passwort ändern verschlüsselt nur den DEK neu, nicht jede Mail
  - Während der Anmeldung liegt der DEK in der Server-Sitzung. Hintergrundjobs bekommen einen kurzlebigen Dienst-Token
  - Ein Datenbank-Dump ohne Sitzung und ohne diesen Token zeigt keinen Mail-Klartext. Wer den Server oder die Sitzungsdateien liest, kann den Klartext sehen
- **🔒 Härtung** – siehe [docs/SECURITY.md](docs/SECURITY.md). Host, systemd und `.env` stehen im privaten Betriebsdokument des Betreibers
  - **Flask-Limiter**: Rate Limiting (5 requests/min Login, 2FA und die Freigabe-POSTs)
  - **Account Lockout**: 5 Fehlversuche → 15 Minuten, gemeinsamer Zähler für Passwort, 2FA und Freigabe
  - **Session Timeout**: Standard 60 Minuten (`SESSION_LIFETIME_MINUTES`)
  - **Fail2Ban**: IP-Bann für `LOGIN_FAILED`, `2FA_FAILED` und `LOCKOUT`. Die Freigabe-Zeile `STEPUP_FAILED` hat keine IP und zählt dort nicht.
  - **Audit Logging**: Strukturierte Security-Events für Monitoring
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
  - **Zugangsdaten**: SMTP-Credentials verschlüsselt gespeichert
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
  - **G.2 Aktions-Regeln**: Automatische Email-Aktionen mit Bedingungen & Aktionen
    - 15 Bedingungstypen (inkl. Mail-Alter): Sender, Subject, Body, Regex, Tags, KI-Vorschläge, Alter
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
- **Modellauswahl in den Einstellungen** – lokale Ollama-Modelle oder Cloud. Denkende Modelle (zum Beispiel Qwen) brauchen für JSON-Antworten das Denken aus
- **Zwei Durchläufe nur für die Posteingang-Bewertung** – erster Durchlauf, optional ein zweiter für hohe Scores. Das Ordner-Audit nutzt das nicht
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
7. **Semantic Search** – `/search` mit «Finde ähnliche»
8. **Ordner-Audit** – `/folder-audit`, Kacheln und Einstufungs-Regeln
9. **Aktions-Regeln** – `/rules`, verschieben und markieren

---

## 🏗️ Architektur

> **Stand 2.3.0** – Flask, PostgreSQL, Celery. Ordner-Audit und Aktions-Regeln sind getrennte Wege.

```
KI-Mail-Helper/
├── src/
│   ├── __init__.py             # Package Init
│   ├── app_factory.py          # Flask Application Factory
│   ├── celery_app.py           # Celery Worker Configuration
│   ├── 00_env_validator.py     # Environment Validation
│   ├── 02_models.py            # SQLAlchemy-Modelle
│   ├── 03_ai_client.py         # Multi-Provider AI Client
│   ├── 05_embedding_api.py     # Embedding API (Semantic Search)
│   ├── 06_mail_fetcher.py      # IMAP Client (UID/Folder/Flags)
│   ├── 07_auth.py              # Auth + Master-Key + 2FA
│   ├── 08_encryption.py        # AES-256-GCM, DEK/KEK (Ruhezustand)
│   ├── 12_processing.py        # Email Processing Pipeline
│   ├── 19_smtp_sender.py       # SMTP + Sent-Sync
│   ├── auto_rules_engine.py    # Aktions-Regeln (/rules)
│   ├── reply_generator.py      # AI Reply Generator
│   ├── semantic_search.py      # Vector Search
│   ├── blueprints/             # Flask Blueprints
│   │   ├── __init__.py
│   │   ├── auth.py             # Login, Register, 2FA
│   │   ├── accounts.py         # Mail-Account CRUD
│   │   ├── emails.py           # Email Views
│   │   ├── api.py              # REST API
│   │   ├── dashboard.py        # Main Dashboard
│   │   ├── tags.py             # Tag Management
│   │   ├── rules.py            # Aktions-Regeln
│   │   ├── folder_audit.py     # Ordner-Audit
│   │   ├── audit_config.py     # Einstufungs-Regeln und Audit-Konfiguration
│   │   ├── settings.py         # User Settings
│   │   └── threads.py          # Thread View
│   ├── tasks/                  # Celery Tasks
│   │   ├── mail_sync_tasks.py  # Email Sync (async)
│   │   ├── rule_execution_tasks.py
│   │   └── ...
│   ├── services/               # Business Logic
│   │   ├── tag_manager.py
│   │   ├── sender_patterns.py
│   │   ├── mail_sync.py
│   │   └── ...
│   └── helpers/                # Utilities
├── templates/                  # Jinja2 Templates (25+)
├── migrations/                 # Alembic (PostgreSQL)
│   └── versions/
│       └── 55a17d1115b6_postgresql_initial_schema_baseline.py
├── config/                     # Production Configs
│   ├── mail-helper.service     # Systemd (Gunicorn)
│   ├── mail-helper-celery-worker.service
│   ├── mail-helper-celery-beat.service
│   ├── gunicorn.conf.py
│   ├── fail2ban-*.conf
│   └── logrotate.conf
├── docs/                       # Dokumentation
│   ├── INSTALLATION.md         # Setup Guide
│   ├── ARCHITEKTUR.md          # System Architecture
│   ├── SECURITY.md             # Security Model
│   ├── BENUTZERHANDBUCH.md     # User Manual
│   └── CHANGELOG.md            # Version History
├── scripts/                    # Utility Scripts
├── tests/                      # pytest Tests
├── .env.example                # Environment Template
├── alembic.ini                 # Alembic Config
├── requirements.txt            # Dependencies
└── README.md                   # This file
```

### Tech Stack

| Komponente | Technologie |
|------------|-------------|
| **Backend** | Flask 3.1 + Blueprints |
| **Database** | PostgreSQL 17 |
| **Cache/Queue** | Redis 8 |
| **Task Queue** | Celery 5.6 |
| **WSGI** | Gunicorn |
| **AI** | Ollama / OpenAI / Anthropic / Mistral |
| **Encryption** | AES-256-GCM (DEK/KEK) |

---

## 🚀 Quick Start (WSL2/Linux)

### 1. Ollama Installation
```bash
# Ollama installieren
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl start ollama
sudo systemctl enable ollama

# Modell, das du danach in den Einstellungen wählst
ollama pull <modellname>

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
- **[INSTALLATION.md](./docs/INSTALLATION.md)** – Detailed step-by-step installation guide
- **[docs/audit/](./docs/audit/)** – Ordner-Audit (Scam, Konfiguration, Regel-Kaskade)
- Deployment, systemd und `.env`: privates Betriebsdokument des Betreibers (nicht in diesem Repo)

---

## 📋 Verwendung

### Erste Schritte

1. **Account erstellen** → `/register`
2. **2FA einrichten** → Dashboard → 2FA-Setup
3. **Mail-Account hinzufügen** → Settings → Add IMAP or Gmail OAuth
4. **Mails abrufen** → Dashboard → «Jetzt verarbeiten»
5. **Ordner prüfen** → `/folder-audit`
6. **Tags verwalten** → Navigation → Tags

### Tag-System (Phase 10)

> **Verwirrung vermeiden:** Das System hat **zwei verschiedene Bewertungstypen**:
> - **Tags** = Freie Kategorisierung (beliebig viele, user-definiert)
> - **Kategorie/Dringlichkeit/Wichtigkeit** = Scoring-System (fixe Werte, KI-gesteuert)

---

## 🏷️ Tag-System - Vollständige Dokumentation

### Architektur-Überblick

```
┌─────────────────────────────────────────────────────────────┐
│  KI-ANALYSE (Modell aus den Einstellungen)                  │
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
# _update_user_override_tags() (src/blueprints/email_actions.py)
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

Die Skizzen A–C beschreiben die Tag-Oberfläche. Dazu kommen Ordner-Audit und Aktions-Regeln.

#### **D) Ordner-Audit (`/folder-audit`)**
Konto und Ordner wählen, Scan, Kacheln (Scam, Verdacht, sicher löschbar, prüfen, möglicherweise wichtig). Konfiguration: Einstufungs-Regeln, wichtige Ordner, Wortlisten, Aufbewahrung. Die Tage einer Einstufungs-Regel gelten nur bei «Sicher löschbar»; 0 heisst sofort, mit Rückfrage.

#### **E) Aktions-Regeln (`/rules`)**
Bedingungen und Aktionen (verschieben, markieren, löschen). Der Test-Knopf zeigt Treffer, bevor die Regel scharf ist. Das ist nicht die Einstufung im Ordner-Audit.

### 5️⃣ UI-Komponenten (Tags)

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
# src/blueprints/emails.py - Eager Loading
# Alle Tags für alle Emails in EINER Query
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

Die Zeilennummern in älteren Notizen veralten. Massgeblich sind die Dateien.

| Komponente | Datei | Beschreibung |
|------------|-------|--------------|
| **KI-Prompt** | `src/03_ai_client.py` | System-Prompt und Prüfung der KI-Antwort |
| **Verarbeitung** | `src/12_processing.py` | Posteingang-Pipeline, inkl. optionalem zweiten Durchlauf |
| **Tag-Manager** | `src/services/tag_manager.py` | Tags anlegen und zuweisen |
| **Modelle** | `src/02_models.py` | Tabellen, inkl. Audit-Konfiguration |
| **Aktions-Regeln** | `src/blueprints/rules.py` | `/rules` |
| **Ordner-Audit** | `src/blueprints/folder_audit.py` | Scan und Kacheln |
| **Audit-Regeln** | `src/services/audit_quality_rules.py` | Wortlisten, wichtige Ordner, Aufbewahrung |
| **Scam** | `src/services/audit_scam_detection.py` | Feste Ebene und optionale Identitäts-KI |

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
# src/blueprints/email_actions.py

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

**Hintergrund im Betrieb:** Celery-Worker und Celery-Beat, nicht ein Schleifen-Prozess alle paar Sekunden. Der lokale Eintrag `--worker` bleibt für Versuche ohne die Dienst-Units.

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

Weitere Hilfsskripte: **[scripts/README.md](scripts/README.md)**

---

## 🤖 KI-Provider und zwei Durchläufe

### Verfügbare Provider

Modelle werden in den Einstellungen gewählt, nicht im Code festgeschrieben. Lokal ist das Ollama. Cloud sind OpenAI, Anthropic und Mistral, wenn ein Schlüssel gesetzt ist.

| Provider | Wo | Rolle |
|----------|-----|--------|
| **Ollama** | auf demselben Rechner | Posteingang (erster und optionaler zweiter Durchlauf) und, wenn eingeschaltet, die Identitäts-KI im Ordner-Audit |
| **OpenAI, Anthropic, Mistral** | Cloud | dieselben Rollen, wenn du sie statt Ollama wählst |

Denkende lokale Modelle antworten sonst mit leerem JSON. In den Einstellungen bleibt das Denken für diese JSON-Aufrufe aus.

### Zwei Durchläufe (nur Posteingang)

**Erster Durchlauf:** Score, Kategorie, Tags, Zusammenfassung.

**Zweiter Durchlauf (optional):** nur für hohe Scores, mit einem zweiten Modell. Das ist die Posteingang-Priorisierung, nicht das Ordner-Audit.

### Ordner-Audit

Die Kacheln kommen aus Regeln (Marken, Auth, Domain-Alter, Wortlisten, wichtige Ordner). Eine Identitäts-KI läuft nur in der Grauzone und ist pro Scan begrenzt. Sie ist ein eigener Aufruf, kein zweiter Durchlauf der Posteingang-Bewertung. Abgeschaltet bleiben die festen Regeln.

**Konfiguration in Settings-UI:**
- Dropdown für Base-Durchlauf (Provider/Modelle)
- Dropdown für Optimize-Durchlauf (Provider/Modelle)
- Modelle werden basierend auf API-Keys automatisch erkannt

**Setup in `.env`:**
```bash
# Ollama (lokal)
OLLAMA_API_URL=http://localhost:11434
# Qwen3: Denken standardmässig aus (OLLAMA_CHAT_THINK=false) — sonst leeres JSON
# OLLAMA_CHAT_NUM_PREDICT=1024
# OLLAMA_CHAT_NUM_PREDICT_THINK=4096
# Andere Modelle: Denk-Fähigkeit via Ollama /api/show, Cache 7 Tage (DB + RAM).
# Bei /api/show-Fehler wird nichts gecacht; UI zeigt „Fähigkeit unbekannt“.

# Cloud-APIs (optional; Werte nur in .env, nie committen)
OPENAI_API_KEY=placeholder
ANTHROPIC_API_KEY=placeholder
MISTRAL_API_KEY=placeholder
```

**Denken (think) in `/settings`:** pro Rolle Base/Optimize und Identitäts-KI — Schalter nur bei Modus «umschaltbar»; Regler wirkt auf `/api/chat`-Feld `think` inkl. Modelle mit Ollama-Capability `thinking` (nicht nur Qwen3).

## 🔐 Verschlüsselung

Das ist **Verschlüsselung im Ruhezustand**, nicht Zero-Knowledge. Bei Zero-Knowledge könnte der Betreiber den Klartext auch während der Nutzung nicht lesen. Hier kann er es, solange eine Sitzung oder ein Dienst-Token den DEK hält.

### Was gilt
- In PostgreSQL liegen Mails, KI-Texte und Zugangsdaten als AES-256-GCM
- Der DEK wird mit einem Schlüssel aus dem Passwort gewickelt (PBKDF2-HMAC-SHA256, 600.000 Runden)
- Nach der Anmeldung liegt der DEK in der Server-Sitzung (Dateien unter `.flask_sessions/`)
- Celery holt Mails mit einem kurzlebigen Token. Der DEK darin ist mit dem Anwendungs-Geheimnis gewickelt und wird beim Abmelden gelöscht
- Abmelden löscht die Sitzung. Ein Datenbank-Dump ohne Sitzung und ohne gültigen Token zeigt keinen Mail-Klartext

### Was es nicht ist
Wer den App-Server, die Sitzungsdateien oder das Anwendungs-Geheimnis zusammen mit einem aktiven Token liest, kommt an den Klartext. Die Grenzen stehen in [docs/SECURITY.md](docs/SECURITY.md).

**📖 Überblick:** [docs/SECURITY.md](docs/SECURITY.md). Das lange Krypto-Dokument liegt nicht in diesem Repo.

**Setup in `.env`:**
```bash
# Zufällig generiert (mind. 32 Zeichen)
FLASK_SECRET_KEY=placeholder     # Für Session-Signierung (z. B. secrets.token_hex(32))
# SERVER_MASTER_SECRET — veraltet, nicht mehr verwenden
```

---

## 🔒 Datenschutz-Level

Für die Posteingang-Bewertung hängt die Stufe am Provider (`src/tasks/email_processing_tasks.py`):

| Provider | Was das Modell sieht |
|----------|----------------------|
| **Lokal (Ollama)** | den Mailtext, ohne die Cloud-Anonymisierung |
| **Cloud** | spaCy ersetzt Namen, Orte und Organisationen. Regex ersetzt Adresse, Telefon, IBAN und URL |

`src/04_sanitizer.py` kennt daneben eine ältere Leiter (Volltext, ohne Signatur und Zitate, Regex-Pseudonyme). Die Cloud-Stufe des Workers ist die spaCy-Stufe, nicht nur diese Regex-Leiter.

Die Identitäts-KI im Ordner-Audit schickt Anzeigename, Adresse und Betreff an das gewählte Modell. Das ist ein eigener Aufruf. Lokal bleibt der Text auf dem Server, in der Cloud verlässt er ihn.

Die Regex-Ersetzung schreibt Platzhalter: `[EMAIL_1]`, `[PHONE_1]`, `[IBAN_1]`, `[URL_1]`, `[CC_1]`.

---

## 🔄 Hintergrund

Abruf, Bewertung und Aktions-Regeln laufen über Celery. Der Zeitplan kommt von Celery Beat, nicht von einem eigenen Timer-Dienst.

```bash
sudo systemctl enable mail-helper mail-helper-celery-worker mail-helper-celery-beat
sudo systemctl start mail-helper mail-helper-celery-worker mail-helper-celery-beat
```

Der Worker braucht einen gültigen Dienst-Token des angemeldeten Kontos. Ohne den Token kann er die Mails nicht entschlüsseln.

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

Die Matrix gilt für die Priorisierung im Posteingang, nicht für das Ordner-Audit.

---

## 🛠️ Entwicklung

### 🗺️ Roadmap

**Geplante Features:**

| Priorität | Feature | Beschreibung |
|-----------|---------|--------------|
| ✅ Done | **iCalendar-Einladungen** | Einladungen in Mails werden erkannt |
| ✅ Done | **Attachment-Handling** | Anhänge anzeigen, herunterladen (PDF, Word, Excel, Bilder ≤25MB) |
| ✅ Done | **Ordner-Audit** | Beliebige Ordner: Scam/Verdacht, wichtige Ordner, Aufbewahrung, vier Wortlisten, Domain-Alter |
| 🟡 Mittel | **Newsletter-Abmelde-Hilfe** | Nur bei vertrauenswürdigen Absendern, nur auf Klick, nie bei Scam, Verdacht oder Auth-Fehler |
| 🟡 Mittel | **Export von Terminen und Kontakten** | Datei `.ics` und `.vcf`, ohne Sync |
| 🟢 Low | **Mobile PWA** | Progressive Web App für Mobilgeräte |

**Ideen, nicht geplant:**
- Termine und Todos aus Freitext (Stapel, erst nach Bestätigung)

**Langfristig:**
- 🌍 Mehrsprachige AI-Analyse

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
FORCE_HTTPS=true               # wird von der App nicht gelesen; Header setzt app_factory
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

**5. Systemd:**
```bash
sudo systemctl enable mail-helper mail-helper-celery-worker mail-helper-celery-beat
sudo systemctl start mail-helper mail-helper-celery-worker mail-helper-celery-beat
```

---

## 📦 Tech Stack

- **Python:** 3.13 (mit SQLAlchemy 2.0)
- **Web:** Flask 3.x + Bootstrap 5
- **DB:** PostgreSQL + SQLAlchemy 2.0 + Alembic (Migrations)
- **LLM:** Ollama (Modell in den Einstellungen) oder OpenAI, Anthropic, Mistral
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
- **Background:** Celery + Redis (nicht nur Threads)
- **Testing:** pytest + mock + test_db_schema
- **Migration:** Alembic für DB-Schema-Versionierung
- **Security:** Soft-Delete, Foreign-Key-Constraints, Input-Validation

---

## 📚 Dokumentation

- **[BENUTZERHANDBUCH.md](docs/BENUTZERHANDBUCH.md)** – Bedienung, inkl. Ordner-Audit
- **[SECURITY.md](docs/SECURITY.md)** – Verschlüsselung und Grenzen
- **[ARCHITEKTUR.md](docs/ARCHITEKTUR.md)** – Aufbau
- **[INSTALLATION.md](docs/INSTALLATION.md)** – Installation
- **[CHANGELOG.md](docs/CHANGELOG.md)** – Änderungen
- **[docs/audit/](docs/audit/)** – Regeln des Ordner-Audits
- Deployment, systemd und `.env`: privates Betriebsdokument des Betreibers (nicht in diesem Repo)

---

## 🐛 Troubleshooting

**Problem:** `Ollama: command not found`
```bash
# Ollama nicht installiert
curl -fsSL https://ollama.com/install.sh | sh
```

**Problem:** `IMAP Fehler: authentication failed`
Konto in der Oberfläche erneut speichern, nachdem du angemeldet bist. Der DEK der Sitzung muss die Zugangsdaten neu schreiben können.

**Problem:** `Keine Emails in der Liste, obwohl der Abruf funktioniert`
Die Rohmails liegen da, die Bewertung läuft über den Celery-Worker. Prüfen, ob der Worker läuft. Ein einzelner Lauf geht mit `python3 -m src.00_main --process-once`.

**Problem:** `Ollama zu langsam oder leeres JSON`
In den Einstellungen ein kleineres lokales Modell wählen. Bei denkenden Modellen das Denken für die JSON-Rolle ausschalten.

---

## 📊 Project Status

| Status | Details |
|--------|---------|
| **Version** | 2.3.0 (Oktober 2026) |
| **Stand** | Produktiv. Schwerpunkt ist die Benutzung, nicht neue Features |
| **Architecture** | Flask Blueprints + PostgreSQL + Celery |
| **Python** | 3.13 |
| **License** | AGPL-3.0 |

---

## 🔒 Security

- **Verschlüsselung im Ruhezustand** – der Server liest Klartext, solange die Sitzung den DEK hält
- **AES-256-GCM** für Mail-Inhalte und Zugangsdaten
- **DEK/KEK** – Passwort ändern ohne jede Mail neu zu verschlüsseln
- **PBKDF2** mit 600.000 Runden
- **Pflicht-2FA**
- Grenzen (Sitzungsdateien, Dienst-Token): [SECURITY.md](./docs/SECURITY.md)

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

**Verwendung auf eigene Gefahr.** Der Code ist weitgehend von KI geschrieben und läuft im eigenen Betrieb. Lokal mit Ollama oder, wenn du es einschaltest, mit einer Cloud-KI. Die Verschlüsselung schützt die Datenbank im Ruhezustand, nicht gegen einen Zugriff auf den laufenden Server.
