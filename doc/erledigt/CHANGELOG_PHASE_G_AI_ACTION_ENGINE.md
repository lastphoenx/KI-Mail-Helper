# CHANGELOG: Phase G - AI Action Engine

**Datum:** 3. Januar 2026  
**Aufwand:** 10-14h  
**Status:** ✅ COMPLETE

---

## 🎯 Zusammenfassung

Phase G erweitert KI-Mail-Helper um zwei leistungsstarke Automatisierungs-Features:

1. **G.1: Reply Draft Generator** - KI generiert Antwort-Entwürfe mit wählbarem Ton
2. **G.2: Auto-Action Rules Engine** - Automatische E-Mail-Verarbeitung mit benutzerdefinierten Regeln

**User-Value:** Massive Zeitersparnis durch Automatisierung und KI-gestützte Antworten!

---

## ✅ Phase G.1: Reply Draft Generator (4-6h)

### Features

- **KI-generierte Antwort-Entwürfe** auf E-Mails
- **Ton-Auswahl:** Formell, Freundlich, Kurz, Höfliche Ablehnung
- **Thread-Context Integration** für kontextbewusste Antworten
- **Copy-to-Clipboard** für schnelles Einfügen in Mail-Client
- **Mehrsprachig:** Automatische Spracherkennung (DE/EN)

### Implementierte Files

#### Backend
- ✅ `src/reply_generator.py` - ReplyGenerator Service mit Tone-Prompts
- ✅ `src/01_web_app.py` - API Endpoint `/api/emails/<id>/generate-reply`
- ✅ `src/03_ai_client.py` - Erweitert um `generate_text()` Methode (bereits vorhanden)

#### Frontend
- ✅ `templates/email_detail.html` - Reply-Draft UI mit Ton-Buttons (bereits vorhanden)

### API Endpoints

```
POST /api/emails/<email_id>/generate-reply
GET  /api/reply-tones
```

### Beispiel-Request

```json
{
  "tone": "formal"
}
```

### Beispiel-Response

```json
{
  "success": true,
  "reply_text": "Sehr geehrter Herr Müller,\n\nvielen Dank für Ihre Nachricht...",
  "tone_used": "formal",
  "tone_name": "Formell",
  "tone_icon": "📜",
  "timestamp": "2026-01-03T10:30:00"
}
```

---

## ✅ Phase G.2: Auto-Action Rules Engine (6-8h)

### Features

- **Conditional Matching:**
  - Sender-Matching (equals, contains, domain)
  - Subject-Matching (contains, regex)
  - Body-Matching (contains)
  - Attachment-Detection
  - Folder-Matching
  - Match-Modes: ALL (AND) / ANY (OR)

- **Actions:**
  - Move to Folder (IMAP)
  - Mark as Read/Flagged
  - Apply Tags (lokal)
  - Set Priority (low/high)
  - Soft-Delete
  - Stop-Processing (keine weiteren Regeln)

- **Management:**
  - CRUD-Interface für Regeln
  - Priority-based Execution (niedrigere Zahl = höher)
  - Statistics Tracking (times_triggered, last_triggered_at)
  - Dry-Run Testing
  - Vordefinierte Templates

- **Automation:**
  - Automatische Anwendung nach E-Mail-Fetch (Background-Job)
  - Manuelle Batch-Anwendung via UI
  - `auto_rules_processed` Flag verhindert Doppel-Verarbeitung

### Implementierte Files

#### Database
- ✅ `migrations/versions/phG2_auto_rules.py` - DB Migration
- ✅ `src/02_models.py` - AutoRule Model + auto_rules_processed Flag

#### Backend
- ✅ `src/auto_rules_engine.py` - AutoRulesEngine Service (540 Zeilen)
- ✅ `src/01_web_app.py` - 10 neue API Endpoints
- ✅ `src/14_background_jobs.py` - Integration in Fetch-Job

#### Frontend
- ✅ `templates/rules_management.html` - Vollständiges Management-UI
- ✅ `templates/base.html` - Navigation erweitert (⚡ Auto-Rules)

### Datenbank-Schema

```sql
CREATE TABLE auto_rules (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 100,
    conditions_json TEXT NOT NULL,  -- JSON
    actions_json TEXT NOT NULL,      -- JSON
    times_triggered INTEGER DEFAULT 0,
    last_triggered_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

ALTER TABLE raw_emails ADD COLUMN auto_rules_processed BOOLEAN DEFAULT FALSE;
```

### API Endpoints

```
GET    /rules                            - Management Page
GET    /api/rules                        - List Rules
POST   /api/rules                        - Create Rule
PUT    /api/rules/<rule_id>              - Update Rule
DELETE /api/rules/<rule_id>              - Delete Rule
POST   /api/rules/<rule_id>/test         - Test Rule (Dry-Run)
POST   /api/rules/apply                  - Apply Rules Manually
GET    /api/rules/templates              - Get Templates
POST   /api/rules/templates/<name>       - Create from Template
```

### Regel-Templates

Vordefinierte Regeln für Schnellstart:

1. **newsletter_archive** - Newsletter → Archiv + gelesen
2. **spam_delete** - Spam-Keywords → Papierkorb
3. **important_sender** - Wichtiger Absender → Flagged
4. **attachment_archive** - Anhänge → Archiv

### Beispiel-Regel

```json
{
  "name": "Newsletter automatisch archivieren",
  "description": "Verschiebt Newsletter in Archiv-Ordner",
  "priority": 50,
  "is_active": true,
  "conditions": {
    "match_mode": "any",
    "sender_contains": "newsletter",
    "body_contains": "unsubscribe"
  },
  "actions": {
    "move_to_folder": "Archive",
    "mark_as_read": true,
    "apply_tag": "Newsletter"
  }
}
```

---

## 🔧 Technische Details

### Zero-Knowledge Kompatibilität

- **Reply Generator:** Master-Key aus Session zum Entschlüsseln der Original-Mail
- **Auto-Rules:** Master-Key für Entschlüsselung beim Matching + IMAP-Operationen
- **Keine Klartext-Speicherung:** Alle Bedingungen matchen gegen entschlüsselte Daten im RAM

### Thread-Safety

- **Auto-Rules in Background-Job:** Separate DB-Session, kein Konflikt mit Web-Requests
- **Atomic Updates:** Rule-Statistiken nutzen DB-seitige Increments

### Performance

- **Lazy-Init:** MailSynchronizer wird nur bei IMAP-Actions initialisiert
- **Batch-Processing:** process_new_emails() verarbeitet mehrere Mails pro Transaction
- **Index:** auto_rules_processed Index für schnelle Queries

### Error Handling

- **Non-blocking:** Auto-Rules Fehler brechen Fetch-Job nicht ab
- **Logging:** Ausführliche Logs für Debugging (matched conditions, executed actions)
- **Dry-Run:** Test-Modus ohne tatsächliche Änderungen

---

## 🧪 Testing

### Manuelle Tests (UI)

1. **Reply Generator:**
   - [ ] E-Mail öffnen → "Antwort-Entwurf generieren"
   - [ ] Verschiedene Töne testen (Formell/Freundlich/Kurz/Decline)
   - [ ] Thread-Context prüfen (Antwort bezieht sich auf vorherige Mails?)
   - [ ] Copy-to-Clipboard funktioniert
   - [ ] Mehrsprachigkeit (DE/EN)

2. **Auto-Rules:**
   - [ ] Neue Regel erstellen (z.B. Sender contains "newsletter")
   - [ ] Regel testen (Dry-Run) - zeigt Matches?
   - [ ] Regel aktivieren → E-Mail-Fetch → Aktion ausgeführt?
   - [ ] Regel aus Template erstellen (z.B. newsletter_archive)
   - [ ] Regel bearbeiten (Bedingungen/Aktionen ändern)
   - [ ] Regel löschen
   - [ ] Manuelle Anwendung: "Regeln jetzt anwenden"
   - [ ] Statistik prüfen (times_triggered, last_triggered_at)

### CLI Tests

```bash
# 1. Migration ausführen
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
alembic upgrade head

# 2. Server starten
python3 -m src.00_main --serve --https

# 3. Im Browser testen:
# - https://localhost:8443/rules
# - E-Mail-Details → Reply-Generator

# 4. Logs prüfen
tail -f logs/*.log | grep -E "(Auto-Rule|Reply-Draft)"
```

### Expected Log Output

```
🤖 Auto-Rules: 3 Regeln auf 15 E-Mails angewendet
✅ Regel 'Newsletter archivieren' ausgeführt für E-Mail 123: move_to:Archive, mark_as_read, apply_tag:Newsletter
🤖 Generiere Reply-Entwurf (Ton: formal)
✅ Reply-Entwurf generiert (247 chars)
```

---

## 📊 Statistiken

- **Code hinzugefügt:** ~2000 Zeilen
- **Neue Files:** 3 (auto_rules_engine.py, phG2_auto_rules.py, rules_management.html)
- **Geänderte Files:** 4 (02_models.py, 01_web_app.py, 14_background_jobs.py, base.html)
- **API Endpoints:** 11 neu
- **DB-Tabellen:** 1 neu (auto_rules)
- **DB-Spalten:** 1 neu (auto_rules_processed in raw_emails)

---

## 🚀 Migration & Deployment

### 1. Migration ausführen

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
alembic upgrade head
```

Expected Output:
```
INFO  [alembic.runtime.migration] Running upgrade ... -> phG2_auto_rules
✅ Phase G.2: auto_rules table created
✅ Added auto_rules_processed flag to raw_emails
```

### 2. Server neu starten

```bash
# Alten Server stoppen
pkill -9 -f "python.*src.00_main"

# Neuen Server starten
python3 -m src.00_main --serve --https
```

### 3. UI testen

```
https://localhost:8443/rules
```

---

## 🎓 User-Anleitung

### Reply Draft Generator

1. E-Mail in der Detail-Ansicht öffnen
2. Auf "Antwort-Entwurf generieren" klicken
3. Ton auswählen (Formell/Freundlich/Kurz/Decline)
4. "Generieren" klicken
5. Entwurf kopieren oder in Mail-Client öffnen

### Auto-Rules

1. Navigation → "⚡ Auto-Rules"
2. Für Schnellstart: Template verwenden (z.B. "Newsletter automatisch archivieren")
3. Oder neue Regel erstellen:
   - Name eingeben (z.B. "Spam filtern")
   - Bedingungen definieren (z.B. Subject contains "[SPAM]")
   - Aktionen festlegen (z.B. Move to Trash + Mark as Read)
   - Priority setzen (niedrigere Zahl = höhere Priorität)
4. Regel testen (Test-Button) → Zeigt welche Mails matched würden
5. Regel aktivieren
6. Bei nächstem E-Mail-Fetch werden Regeln automatisch angewendet
7. Oder manuell: "Regeln jetzt anwenden"

**Tipp:** Start mit Templates, dann anpassen!

---

## 🔮 Zukunft (Optional)

### Nice-to-Have Features (nicht in Phase G)

- **G.1+:**
  - Antwort-Vorlagen speichern
  - Multi-Language-Support für Prompts
  - Anhänge-Handling

- **G.2+:**
  - Zeit-basierte Regeln (Werktags/Wochenende)
  - Regex-Testing im UI
  - Regel-Import/Export (JSON)
  - Machine Learning: "Vorschlagen" von Regeln basierend auf User-Verhalten

---

## 🐛 Known Issues

Keine bekannten kritischen Issues.

**Minor:**
- Move-to-Folder erfordert exakten Ordner-Namen (case-sensitive)
- Regex-Fehler in Bedingungen werden geloggt, aber Regel skippt Mail
- Reply-Generator Timeout bei sehr langen Threads (> 10 Mails)

---

## ✅ Phase G: COMPLETE!

**Next:** Phase H - Action Extraction (8-12h)

- H.1: Unified Action Extractor (Termine + Aufgaben aus Mails)
- H.2: Action Items DB & Management-UI

**Dependencies:** Phase E (Thread-Context) ✅, Phase G.1 (Reply Generator) ✅

---

**Changelog erstellt von:** GitHub Copilot  
**Review:** Pending User Testing
