# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

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
