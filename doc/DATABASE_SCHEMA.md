# Database Schema & Data Model

## Übersicht

Das KI-Mail-Helper System verwendet SQLAlchemy mit einer SQLite-Datenbank (`emails.db`). Die Datenbank ist in zwei Hauptbereiche aufgeteilt:

1. **Raw Emails** (`raw_emails`) - Rohdaten der E-Mails (verschlüsselt)
2. **Processed Emails** (`processed_emails`) - KI-Analyse-Ergebnisse (verschlüsselt)

## Wichtige Konzepte

### ID-Mapping: raw_email_id vs processed_email.id

⚠️ **WICHTIG**: URLs verwenden `raw_email.id`, NICHT `processed_email.id`!

```
URL: /email/4 → sucht nach raw_email.id=4
             → findet processed_email mit raw_email_id=4
```

**Warum?**
- `raw_emails` ist die **Master-Tabelle** (E-Mails können existieren ohne Analyse)
- `processed_emails` ist **optional** (nur wenn KI-Analyse durchgeführt wurde)
- IDs können unterschiedlich sein wegen Sortierung, Löschungen, etc.

### Beziehung

```
raw_emails (1) ←→ (1) processed_emails
   ↓                      ↓
  id (PK)            raw_email_id (FK)
```

**Beispiel:**
```sql
raw_emails:
  id=4, subject="Test", user_id=1

processed_emails:
  id=3, raw_email_id=4, dringlichkeit=5
```

→ URL `/email/4` zeigt diese E-Mail!

## Kern-Tabellen

### `raw_emails`
**Master-Tabelle** für alle E-Mails.

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `id` | INTEGER PK | **Primary Key - wird in URLs verwendet** |
| `user_id` | INTEGER FK | Benutzer (→ users.id) |
| `mail_account_id` | INTEGER FK | Mail-Account (→ mail_accounts.id) |
| `encrypted_sender` | TEXT | Absender (AES-256 verschlüsselt) |
| `encrypted_subject` | TEXT | Betreff (AES-256 verschlüsselt) |
| `encrypted_body` | TEXT | E-Mail-Body (AES-256 verschlüsselt) |
| `encrypted_subject_sanitized` | TEXT | **Anonymisierter Betreff (Phase 22)** |
| `encrypted_body_sanitized` | TEXT | **Anonymisierter Body (Phase 22)** |
| `sanitization_level` | VARCHAR | Anonymisierungsstufe: LIGHT/MEDIUM/STRICT/OFF |
| `sanitization_time_ms` | INTEGER | Performance-Metrik |
| `sanitization_entities_count` | INTEGER | Anzahl entfernter PII-Entitäten |
| `received_at` | DATETIME | Empfangszeitpunkt |
| `imap_folder` | VARCHAR(200) | IMAP-Ordner (z.B. "INBOX") |
| `imap_is_seen` | BOOLEAN | Gelesen-Status |
| `imap_is_flagged` | BOOLEAN | Geflaggt-Status |
| `has_attachments` | BOOLEAN | Hat Anhänge? |
| `message_size` | INTEGER | Größe in Bytes |
| `thread_id` | VARCHAR(36) | Thread-Gruppierung (UUID) |
| `deleted_at` | DATETIME | Soft-Delete Timestamp |

**Zugriff:**
```python
raw = db.query(RawEmail).filter_by(id=raw_email_id).first()
```

### `processed_emails`
**KI-Analyse-Ergebnisse** für E-Mails.

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `id` | INTEGER PK | ⚠️ NICHT für URLs verwenden! |
| `raw_email_id` | INTEGER FK | **Link zu raw_emails.id** |
| `dringlichkeit` | INTEGER | Dringlichkeit 0-10 |
| `wichtigkeit` | INTEGER | Wichtigkeit 0-10 |
| `kategorie_aktion` | VARCHAR(50) | Kategorie |
| `spam_flag` | BOOLEAN | Spam erkannt? |
| `encrypted_summary_de` | TEXT | Deutsche Zusammenfassung (verschlüsselt) |
| `encrypted_text_de` | TEXT | Deutsche Übersetzung (verschlüsselt) |
| `encrypted_tags` | TEXT | Auto-Tags (verschlüsselt, JSON) |
| `score` | INTEGER | Composite Score (0-100) |
| `matrix_x` | INTEGER | Wichtigkeit-Achse |
| `matrix_y` | INTEGER | Dringlichkeit-Achse |
| `farbe` | VARCHAR(10) | UI-Farbe (rot/gelb/grün) |
| `done` | BOOLEAN | Erledigt-Status |
| `done_at` | DATETIME | Erledigt-Zeitpunkt |
| `processed_at` | DATETIME | Erste Analyse |
| `base_provider` | VARCHAR(50) | KI-Provider (OpenAI/Anthropic/...) |
| `base_model` | VARCHAR(100) | KI-Modell |
| `analysis_method` | TEXT | Phase Y: REGEX/SPACY/HYBRID/ENSEMBLE |
| `ai_confidence` | REAL | KI-Konfidenz 0.0-1.0 |
| `deleted_at` | DATETIME | Soft-Delete Timestamp |

**Zugriff via raw_email_id:**
```python
processed = db.query(ProcessedEmail).filter_by(raw_email_id=raw_email_id).first()
```

## Anonymisierung (Phase 22)

### Speicherort
✅ In `raw_emails` Tabelle (NICHT processed_emails!)

### Felder
```sql
raw_emails:
  - encrypted_subject_sanitized  -- Anonymisierter Betreff
  - encrypted_body_sanitized     -- Anonymisierter Body
  - sanitization_level           -- LIGHT/MEDIUM/STRICT/OFF
  - sanitization_time_ms         -- Performance
  - sanitization_entities_count  -- Anzahl gefundener PII
```

### Flow
```
1. E-Mail laden: raw_email.encrypted_body
2. Entschlüsseln: master_key → plaintext
3. Anonymisieren: content_sanitizer.sanitize(plaintext, level)
4. Verschlüsseln: plaintext_sanitized → encrypted_body_sanitized
5. Speichern: UPDATE raw_emails SET encrypted_body_sanitized=...
```

### Konfiguration
Account-Level in `mail_accounts`:
```sql
mail_accounts:
  - anonymize_with_spacy (BOOLEAN)     -- spaCy aktiviert?
  - ai_analysis_anon_enabled (BOOLEAN) -- Anonymisierung für KI-Analyse?
```

## URL-Schema

### ✅ Korrekt (ab 2026-01-09)
```python
@app.route("/email/<int:raw_email_id>")
def email_detail(raw_email_id):
    processed = db.query(ProcessedEmail).filter_by(
        raw_email_id=raw_email_id
    ).first()
```

### ❌ Alt (vor 2026-01-09) - DEPRECATED
```python
@app.route("/email/<int:email_id>")  # Verwirrend!
def email_detail(email_id):
    processed = db.query(ProcessedEmail).filter_by(
        id=email_id  # processed_email.id ≠ raw_email.id
    ).first()
```

## Beziehungen

```
users (1) ←→ (n) mail_accounts
users (1) ←→ (n) raw_emails
users (1) ←→ (n) processed_emails

mail_accounts (1) ←→ (n) raw_emails
raw_emails (1) ←→ (1) processed_emails
raw_emails (1) ←→ (n) email_tag_assignments
email_tags (1) ←→ (n) email_tag_assignments
```

## Template-Zugriff

### In Jinja2 Templates:
```jinja2
<!-- ✅ Korrekt -->
<a href="/email/{{ email.raw_email_id }}">Details</a>

<!-- ❌ Alt - funktioniert nicht mehr -->
<a href="/email/{{ email.id }}">Details</a>
```

### In Python (list_view):
```python
# email ist ProcessedEmail Objekt
for email in mails:
    print(f"URL: /email/{email.raw_email_id}")  # ✅
    print(f"Processed ID: {email.id}")          # Nur intern!
```

## Debugging

### Finde E-Mail via URL
```bash
# URL: /email/4
sqlite3 emails.db "
  SELECT 
    r.id as raw_id,
    p.id as proc_id,
    r.mail_account_id
  FROM raw_emails r
  LEFT JOIN processed_emails p ON p.raw_email_id = r.id
  WHERE r.id = 4;
"
```

### Anonymisierungsstatus prüfen
```bash
sqlite3 emails.db "
  SELECT 
    id,
    sanitization_level,
    sanitization_entities_count,
    LENGTH(encrypted_body_sanitized) as sanitized_len
  FROM raw_emails
  WHERE id = 4;
"
```

### Anonymisierung löschen (für Neu-Anonymisierung)
```bash
sqlite3 emails.db "
  UPDATE raw_emails 
  SET 
    encrypted_subject_sanitized = NULL,
    encrypted_body_sanitized = NULL,
    sanitization_level = NULL,
    sanitization_time_ms = NULL,
    sanitization_entities_count = NULL
  WHERE id = 4;
"
```

## Migration Notes

**2026-01-09**: URL-Schema Refactoring
- Alle `/email/<int:email_id>` Routes → `/email/<int:raw_email_id>`
- Templates: `email.id` → `email.raw_email_id`
- Grund: Konsistente Zuordnung, kein ID-Mapping-Chaos

**Betroffene Dateien:**
- `src/01_web_app.py`: 14 Routes geändert
- `templates/list_view.html`: 3 Links geändert
- `templates/email_detail.html`: 2 Links geändert
- `templates/rules_execution_log.html`: 1 Link via Backend geändert

---

**Erstellt:** 2026-01-09  
**Autor:** GitHub Copilot (Claude Sonnet 4.5)  
**Version:** 1.0
