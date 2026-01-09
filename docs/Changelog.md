# Changelog - KI-Mail-Helper

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

---

## [1.4.0] - 2026-01-09

### 🎯 Reply Optimization für Small Local LLMs

**Hinzugefügt:**
- Provider/Model Selection in Reply Modal (Ollama, OpenAI, Anthropic, Mistral)
- Optimized Reply Prompts für kleine lokale LLMs (unter 8B Parameter)
- Dynamic Temperature Support Detection (o1/o3/gpt-5 Modelle ohne Custom Temperature)
- Anonymization Toggle mit Auto-Enable für Cloud-Provider

**Geändert:**
- On-the-fly Anonymisierung: Wenn `encrypted_*_sanitized` fehlt, wird beim Reply-Generieren automatisch anonymisiert und in DB gespeichert
- ContentSanitizer: Testfälle aus Hauptmodul entfernt → `/tests/test_content_sanitizer.py`
- Model Discovery: `supports_temperature` Flag für alle Modelle

**Technische Details:**
- [src/services/content_sanitizer.py](../src/services/content_sanitizer.py): Bereinigt von ~370 auf ~265 Zeilen
- [src/optimized_reply_prompts.py](../src/optimized_reply_prompts.py): 4 Tone Styles optimiert für Small LLMs
- [src/03_ai_client.py](../src/03_ai_client.py): Dynamische Temperature-Prüfung
- [templates/email_detail.html](../templates/email_detail.html): Provider/Model Dropdowns + Anonymization Toggle

---

## [1.3.0] - 2026-01-06

### 🤖 KI-Priorisierung & Email-Anonymisierung

**Hinzugefügt:**
- Phase Y: Ensemble Learning mit spaCy NLP (80%) + Keywords (20%)
- Phase 22: Content Sanitizer mit 3 Anonymisierungs-Stufen (Regex, Light, Full)
- Confidence Tracking: `ai_confidence` & `optimize_confidence` für Transparenz
- Online-Learning: SGD-Classifier mit inkrementellem Training aus User-Korrekturen

**Geändert:**
- Prioritäts-Matrix: Jetzt mit KI-Vorhersage + User-Override
- DB-Schema: `ai_confidence`, `ai_predicted_urgency`, `ai_predicted_importance`
- Security: PII-Entfernung vor Cloud-AI-Übertragung (DSGVO-konform)

---

## [1.2.0] - 2025-12-20

### 🎨 Customizable Reply Styles & Account Signatures

**Hinzugefügt:**
- Phase I.1: 4 Reply Styles (Formal, Freundlich, Direkt, Neutral)
- Phase I.2: Account-Specific Signatures mit Business/Personal Profiles
- Phase X: Trusted Senders + UrgencyBooster (Account-Based Whitelist)
- Phase X.2: Dedizierte `/whitelist` Seite mit Batch-Operationen

**Geändert:**
- Reply Modal: Style Dropdown + Signature Preview
- Whitelist: 2-Spalten-Layout mit Live-Filter & Bulk-Delete

---

## [1.1.0] - 2025-12-10

### 🧵 Thread-View & Semantic Search

**Hinzugefügt:**
- Phase E: Konversations-basierte Email-Ansicht mit Thread-Context
- Phase F1: Vector-basierte Semantic Search mit Embeddings
- Phase F2: Smart Tag Suggestions & Learning-System
- Phase F.3: Negative Feedback für Tag-Learning

**Geändert:**
- Email-Detail: Zeigt jetzt gesamten Thread mit Kontext
- Tag-System: KI-Vorschläge basierend auf gelernten Mustern
- Search: Findet semantisch ähnliche Emails statt nur Keyword-Match

---

## [1.0.0] - 2025-11-25

### 🚀 Production Release

**Hinzugefügt:**
- Phase 0-12: Core System (Zero-Knowledge, 3×3 Matrix, Multi-Provider AI)
- Phase 13C: Account-spezifische Fetch-Filter
- Phase 14: RFC-konformer IMAP UID-Sync (UIDVALIDITY)
- Phase 15: Multi-Folder UIDPLUS Support
- Phase G: AI Action Engine (Reply Generator + Auto-Rules)
- Phase H: SMTP Mail-Versand mit Sent-Sync

**Security:**
- Production Hardening: 98/100 Score
- Rate Limiting, 2FA, Account Lockout
- Zero-Knowledge Encryption: AES-256-GCM, DEK/KEK-Pattern

**Technische Details:**
- IMAP & Gmail OAuth Support
- 14 Auto-Rule Bedingungen
- 4 Ton-Varianten für Reply Generator
- Multi-Account Dashboard mit Filter

---

## Legende

- **Hinzugefügt** = Neue Features
- **Geändert** = Änderungen an bestehenden Features
- **Entfernt** = Gelöschte Features
- **Behoben** = Bug-Fixes
- **Sicherheit** = Security-relevante Änderungen
