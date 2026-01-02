# 🎯 Phase 13: Strategic Analysis & Implementation Roadmap

**Strategic Planning Document - Was haben wir, was brauchen wir?**

**Status:** ✅ Phase A-E + 14(a-g) + **F (komplett)** Complete | 🚀 Phase G-J Ready to Implement  
**Created:** 31. Dezember 2025  
**Updated:** 03. Januar 2026 - **Phase F: Semantic Intelligence COMPLETE (F.1 + F.2 + F.3)**  
**Recent:** Alle 3 Phasen F abgeschlossen: Semantic Search + 3-Settings + Email Similarity  
**Supersedes/Integrates:** Task 5 & Task 6

---

## 📋 Executive Summary

**Abgeschlossen (73-91h):**
- ✅ Phase A: Filter auf /liste
- ✅ Phase B: Server DELETE/FLAG/READ
- ✅ Phase C: MOVE + Multi-Folder FULL SYNC
- ✅ Phase D: ServiceToken + InitialSync Fixes
- ✅ Phase E: KI Thread-Context
- ✅ Phase 14(a-g): RFC UIDs + IMAPClient Migration
- ✅ **Phase F.1: Semantic Email Search (8-12h) - DONE!**
- ✅ **Phase F.2: 3-Settings System (12-15h) - DONE!**
- ✅ **Phase F.3: Email Similarity (2-3h) - DONE!**

**Neu geplant (22-42h):**
- 🔥 **Phase G:** AI Action Engine (10-14h) ⭐⭐⭐⭐⭐ **TOP PRIORITY**
- ⭐ **Phase H:** Action Extraction (8-12h) ⭐⭐⭐⭐
- 🟢 **Phase I:** Productivity Features (20-28h) ⭐⭐⭐ **OPTIONAL**
- 🟢 **Phase J:** SMTP Integration (6-8h) ⭐⭐⭐ **OPTIONAL**

**Total Roadmap:** 95-133 Stunden → **Completed: 73-91h** | **Remaining: 22-42h**

---

## 🎯 Warum die Umstrukturierung?

### Vorher (alte Phase F-H):
- ❌ Feature-orientiert: "SMTP", "Conversation UI", "Bulk Ops"
- ❌ Kein klarer User-Value-Focus
- ❌ Große Features am Anfang (Bulk Ops 15-20h)

### Nachher (neue Phase F-J):
- ✅ **Use-Case-orientiert:** "Semantic Intelligence", "AI Action Engine"
- ✅ **Quick Wins zuerst:** Semantic Search (8-12h) = Killer-Feature!
- ✅ **Logische Gruppierung:** Auto-Actions + Reply Draft = "AI hilft mir"
- ✅ **Optional Features am Ende:** Bulk Ops & SMTP nur bei Bedarf

---

## 🔥 Key Insights & Critical Corrections

### **Insight #1: Embedding-Generierung beim FETCH, nicht Processing!**

**Vorher (falsch gedacht):**
```
Fetch → DB (encrypted) → Processing → Decrypt → Embedding
                                      ↑ master_key nötig!
```

**Jetzt (RICHTIG!):**
```
Fetch → Klartext → Embedding → Encrypt → DB
        ↑                      ↑
        Hier!                  Dann speichern
```

**Warum das besser ist:**
- ✅ Klartext ist beim Fetch verfügbar (vom IMAP)
- ✅ Kein master_key für Embedding nötig
- ✅ Kein extra Decrypt-Pass
- ✅ Effizienter & simpler

**Implementation:** `src/14_background_jobs.py` in `_persist_raw_emails()` **VOR** Verschlüsselung!

---

### **Insight #2: Action Items = Ein Service, nicht zwei!**

**Vorher (Idee):** Separate Calendar + ToDo Services

**Jetzt (besser):** Unified Action Extractor
- ✅ Eine DB-Tabelle (`ActionItem`) mit `type` Feld
- ✅ Weniger Code-Duplikation
- ✅ Synergien: "Aufgabe VOR Termin erledigen"
- ✅ Gemeinsame UI & API

---

### **Insight #3: Semantic Search = Größter Impact/Aufwand Ratio!**

**Impact/Aufwand Matrix:**
```
         HIGH IMPACT
              │
   ┌──────────┼──────────┐
   │ Semantic │ AI       │
   │ Search   │ Actions  │
   │ 8-12h    │ 10-14h   │
   │   #1 🔥  │   #2 🔥  │
LOW├──────────┼──────────┤HIGH
EFFORT        │          │EFFORT
   │ Tag Auto │ Bulk     │
   │ 2-3h     │ 15-20h   │
   │   #3     │   #6     │
   └──────────┼──────────┘
              │
         LOW IMPACT
```

**Warum Semantic Search #1?**
- ✅ Infrastructure bereits da (`_get_embedding()` existiert!)
- ✅ Tag-Similarity Code wiederverwendbar
- ✅ Killer-Feature: "Budget" findet "Kostenplanung", "Finanzübersicht"
- ✅ Zero-Knowledge bleibt gewahrt (Embeddings nicht reversibel)

---

## 🎉 Phase 14: RFC-konformer Unique Key - COMPLETE

**Duration:** ~4 Stunden | **Status:** ✅ **ABGESCHLOSSEN**

**Problem gelöst:**
- ❌ Alte Architektur: `uid` = selbst-generierter String (UUID/Hash)
- ❌ MOVE führte zu Race-Conditions (neue UID unbekannt)
- ❌ Deduplizierung war heuristisch (content_hash)

**Neue Architektur:**
- ✅ RFC-konformer Key: `(user_id, account_id, folder, uidvalidity, imap_uid)`
- ✅ MOVE mit COPYUID (RFC 4315 UIDPLUS)
- ✅ UIDVALIDITY-Tracking pro Ordner
- ✅ Keine Deduplizierung mehr nötig

**Implemented:**
- Phase 14a: DB Schema Migration (UIDVALIDITY, Integer UIDs, Unique Constraint)
- Phase 14b: MailFetcher (UIDVALIDITY-Check, Delta-Fetch, _invalidate_folder)
- Phase 14c: MailSynchronizer (COPYUID-Parsing, MoveResult)
- Phase 14d: Web Endpoints (Direct DB Update nach MOVE)
- Phase 14e: Background Jobs (Keine Deduplizierung, IntegrityError = skip)
- Phase 14f: Cleanup (uid Feld komplett entfernt)

📄 **Detailed Documentation:** [doc/erledigt/PHASE_14_RFC_UNIQUE_KEY_COMPLETE.md](../erledigt/PHASE_14_RFC_UNIQUE_KEY_COMPLETE.md)

---

## 🚀 Phase 14g: Complete IMAPClient Migration - COMPLETE

**Duration:** ~4-5 Stunden | **Status:** ✅ **ABGESCHLOSSEN**

**Problem gelöst:**
- ❌ imaplib: Complex string parsing (regex, UTF-7, untagged_responses)
- ❌ COPYUID hidden in untagged_responses → unreliable MOVE
- ❌ Manual UTF-7 encoding/decoding for folder names
- ❌ Error-prone response parsing

**Neue Architektur:**
- ✅ IMAPClient 3.0.1: Clean Pythonic API
- ✅ COPYUID as tuple: `(uidvalidity, [old_uids], [new_uids])`
- ✅ Automatic UTF-7 handling
- ✅ Dict-based responses (no regex)
- ✅ 40% code reduction (-119 lines across 5 files)

**Implemented:**
- Migration Commit 1 (378d7b0): 4 files, -376/+295 lines
  - src/06_mail_fetcher.py: Connection, UIDVALIDITY, Search, Fetch
  - src/16_mail_sync.py: COPYUID via tuple, all flag operations
  - src/14_background_jobs.py: Folder listing with tuple unpacking
  - src/01_web_app.py: mail-count endpoint
- Migration Commit 2 (330f1b9): 1 file, -56/+18 lines
  - src/01_web_app.py: /folders + Settings endpoints
- Script Fix Commit (fa10846): scripts/reset_all_emails.py
  - Soft-delete instead of hard-delete
  - UIDVALIDITY cache clear (`folder_uidvalidity = None`)

**Bugs Fixed:**
- ✅ MOVE operation DB updates (COPYUID extraction 100% reliable)
- ✅ Delta sync search syntax (`['UID', uid_range]` list format)
- ✅ mail-count AttributeError (`list_folders()` + `folder_status()`)
- ✅ reset_all_emails.py now uses soft-delete pattern

📄 **Detailed Documentation:** [doc/erledigt/PHASE_14G_IMAPCLIENT_MIGRATION_COMPLETE.md](../erledigt/PHASE_14G_IMAPCLIENT_MIGRATION_COMPLETE.md)

---

## 🧠 Phase E: KI Thread-Context - COMPLETE

**Duration:** ~4 Stunden | **Status:** ✅ **ABGESCHLOSSEN**

**Problem gelöst:**
- ❌ AI klassifiziert Emails ohne Conversation-Context
- ❌ Newsletter-Threads nicht erkannt (einzelne Email scheint wichtig)
- ❌ Follow-ups ohne Kontext (3. Mahnung wirkt wie normale Mail)
- ❌ Attachment-Info nicht verfügbar für AI

**Neue Architektur:**
- ✅ Thread-Context Builder: Sammelt bis zu 5 vorherige Emails im Thread
- ✅ Sender-Intelligence: Erkennt Newsletter vs. Conversational Patterns
- ✅ AI Context Parameter: Alle 4 Clients (LocalOllama, OpenAI, Anthropic, Abstract)
- ✅ Attachment-Awareness: 📎 Emoji + Info für previous & current emails
- ✅ Early Context Limiting: 4500 chars (optimiert)

**Implemented:**

**Phase E.1: Thread-Context Builder (src/12_processing.py)**
- `build_thread_context()`: Collects previous emails chronologically
  - Queries by thread_id + received_at (time-based, not ID-based!)
  - Decrypts up to 5 previous emails with master_key
  - Format: `[1] 2025-01-01 10:00 | From: alice@example.com 📎`
  - Truncates body to 300 chars per email
  - Returns formatted string or empty if no history

**Phase E.2: Sender-Intelligence (src/12_processing.py)**
- `get_sender_hint_from_patterns()`: Analyzes sender behavior
  - Newsletter detection: All emails from same sender, no responses
  - Conversational detection: Mix of different senders in thread
  - Case-insensitive email comparison (alice@x.com == Alice@X.com)
  - Null-safety: Skips emails with failed decryption
  - Returns hint string: "SENDER PATTERN: automated/conversational"

**Phase E.3: AI Client Extensions (src/03_ai_client.py)**
- Added `context: Optional[str] = None` parameter to all analyze_email() methods:
  - Abstract AIClient base class (line 71)
  - LocalOllamaClient (line 814) - chat dispatcher
  - OpenAIClient (line 910) - API call
  - AnthropicClient (line 1051) - message format
- Context sanitized (max 5000 chars) for security
- Context prepended to user message in all implementations

**Phase E.4: Processing Integration (src/12_processing.py)**
- `process_pending_raw_emails()` enhanced:
  - Calls build_thread_context() + get_sender_hint_from_patterns()
  - Combines both into context_str
  - Adds current email attachment info: "📎 CURRENT EMAIL: has attachments"
  - Passes context to ai.analyze_email()
  - Logs: "📧 Thread-Context: X chars, Sender-Hint: Y chars"

**Phase E.5: Attachment-Awareness**
- Previous emails show: `📎 (has attachments)` indicator
- Current email gets: `📎 CURRENT EMAIL: This email has attachments.`
- Uses `RawEmail.imap_has_attachments` field
- Helps AI classify invoices, contracts, reports with PDFs

**Phase E.6: Early Context Limiting**
- Context limited to 4500 chars BEFORE AI call (not 5000 during sanitization)
- Saves processing time and memory
- Adds `[Context truncated due to size]` marker if trimmed
- Leaves room for current email info (~500 chars)

**Bugs Fixed During Implementation:**
1. ✅ Signature Consistency: Removed unused `sender` parameter from LocalOllamaClient
2. ✅ Thread Query: Changed from `id <` to `received_at <` (chronological ordering)
3. ✅ Case-Sensitivity: Email comparison now case-insensitive (.lower())
4. ✅ Variable Shadowing: Renamed second `sender_hint` to `classification_hint`
5. ✅ Null-Safety: Added check before email_sender.lower()
6. ✅ Pattern Logic: Uses `decryptable_count` instead of `total_count` (after filtering)
7. ✅ Logging: Improved to show char counts for both context components

**Git Commits:**
- edc5ab5: Thread calculation & IMAP diagnostics fixes
- 24ec3fb: Phase E: KI Thread-Context Implementation
- d9ebf90: Fix: Phase E bugs from code review (round 1)
- 366f15a: Fix: 4 critical bugs found in code review
- 67052b0: Fix: Pattern detection logic flaw (#5)
- 746aa26: Add: Attachment awareness + early context limiting

**Impact:**
- ✅ AI understands conversation history (follow-ups, replies)
- ✅ Better urgency detection (e.g., 3rd reminder)
- ✅ Newsletter thread detection: entire thread flagged as spam
- ✅ Attachment presence factored into classification
- ✅ 4500 char context limit optimizes performance

**Example Context Output:**
```
CONVERSATION CONTEXT (3 previous emails):

[1] 2025-01-01 10:00 | From: alice@example.com 📎 (has attachments)
Subject: Project Update
Body: Here are the Q4 reports in PDF format...

[2] 2025-01-01 14:30 | From: bob@example.com
Subject: Re: Project Update
Body: Thanks! I have a question about slide 5...

[3] 2025-01-01 16:00 | From: alice@example.com
Subject: Re: Project Update
Body: Good question. Let me clarify...

SENDER PATTERN: This sender is conversational - thread has 3 emails with responses

📎 CURRENT EMAIL: This email has attachments.
```

---

## 📊 Phase 12 Assets - Was wir haben, aber NICHT nutzen

| Asset | Vorhanden | Genutzt | Potential |
|-------|-----------|---------|-----------|
| `thread_id` | ✅ | ❌ | Conversation-View, KI-Kontext |
| `parent_uid` | ✅ | ❌ | Thread-Navigation |
| `imap_is_seen` | ✅ | ❌ | Filter "Ungelesen" |
| `imap_is_flagged` | ✅ | ❌ | Filter "Wichtig" |
| `message_size` | ✅ | ❌ | Sortierung, Statistiken |
| `has_attachments` | ✅ | ❌ | Filter "Mit Anhang" |
| `content_type` | ✅ | ❌ | HTML vs Text Anzeige |
| `imap_folder` | ✅ | ❌ | Ordner-Filter |
| SORT Extension | ✅ Getestet | ❌ | Server-side Sorting |
| THREAD Extension | ✅ Getestet | ❌ | Native Threading |

---

## ✅ Phase F.2: 3-Settings System (Embedding/Base/Optimize) - **COMPLETE**

**Status:** ✅ **DONE** (03. Januar 2026)  
**Effort:** 12-15 hours  
**Priority:** ⭐⭐⭐⭐⭐ **TOP PRIORITY**

**Problem Solved:**
- Original issue: Embedding dimension mismatch (384-dim vs 2048-dim) breaking tag suggestions
- Root cause: llama3.2:1b (chat model) was incorrectly used for embeddings instead of all-minilm:22m (embedding model)
- Design flaw: No separation between Embedding models (vector generation) and Chat models (scoring/analysis)

**Solution Implemented:**
Complete architectural refactoring with 3 independent AI settings:
1. **Embedding Model** (VECTORS): all-minilm:22m, mistral-embed, text-embedding-3-large
2. **Base Model** (FAST SCORING): llama3.2:1b, gpt-4o-mini, phi3:mini
3. **Optimize Model** (DEEP ANALYSIS): llama3.2:3b, gpt-4o, claude-haiku

**Database Migration:**
- `c4ab07bd3f10`: Added `User.preferred_embedding_provider`, `User.preferred_embedding_model`
- Defaults: ollama/all-minilm:22m (384-dim embeddings)

**Implementation Files:**
- `src/02_models.py`: Extended User model with 3 AI settings
- `src/03_ai_client.py`: Added MistralClient._get_embedding(), OpenAIClient._get_embedding()
- `src/01_web_app.py`: 4 new API endpoints + 3-section settings UI
- `src/14_background_jobs.py`: BatchReprocessJob with progress tracking
- `src/semantic_search.py`: generate_embedding_for_email() with model_name parameter
- `templates/settings.html`: 3 sections, dynamic dropdowns, batch-reprocess button
- `templates/email_detail.html`: Pre-check + progress modal

**Key Features:**
- ✅ 3-Settings System (Embedding/Base/Optimize) fully operational
- ✅ Dynamic model discovery from all providers (Ollama, OpenAI, Mistral, Anthropic)
- ✅ Model type filtering (embedding vs chat models)
- ✅ Pre-check validates embedding dimension compatibility before reprocessing
- ✅ Async batch-reprocess with real-time progress tracking (BackgroundJobQueue)
- ✅ Increased max_body_length from 500 → 1000 characters for better context

**Performance:**
- Ollama (local): 15-50ms per email (47 emails in 2-5s)
- Context: 1000 chars (~140-160 words) vs previous 500 chars

**Git Commits:**
- 6dad224: Migration c4ab07bd3f10 - Add embedding settings
- f7a8319: Feat: 3-Settings System implementation
- 388d0c8: Tune: Erhöhe max_body_length auf 1000 Zeichen

**Documentation:**
- `doc/erledigt/PHASE_F2_3_SETTINGS_SYSTEM_COMPLETE.md`: Comprehensive technical documentation

**Impact:**
- ✅ Fixed tag suggestions (correct embedding dimensions)
- ✅ Semantic search ready for Phase F.1 implementation
- ✅ User can choose best model per use case (speed vs quality)
- ✅ Zero-Knowledge principle maintained (embeddings not reversible)
- ✅ Production-ready infrastructure for semantic intelligence features

---

## 🏗️ 3-Säulen Roadmap

### **Säule 1: 🔍 Filter & Suche (UX)**

#### `/liste` Verbesserungen:

```
Filter-Leiste
├── Account-Dropdown (mail_account_id)
├── Ordner-Dropdown (imap_folder)
├── Status-Toggle: Gelesen/Ungelesen/Alle
├── Flag-Toggle: Geflaggt/Nicht/Alle
└── Anhang-Toggle: Mit/Ohne/Alle

Erweiterte Suche
├── Subject (aktuell ✅)
├── Sender (aktuell ✅)
├── Body (NEU - nach Entschlüsselung)
└── Datums-Range (von/bis)

Sortierung
├── Datum (neu→alt, alt→neu)
├── Score (hoch→niedrig)
├── Größe (groß→klein)
└── Absender (A-Z)
```

---

### **Säule 2: ⚡ Server-Aktionen (Core Feature)**

#### IMAP Server-Sync:

```
DELETE - Spam löschen
└── conn.store(uid, '+FLAGS', '\\Deleted')
└── conn.expunge()

MOVE - In Ordner verschieben
└── conn.copy(uid, 'Spam')
└── conn.store(uid, '+FLAGS', '\\Deleted')

FLAGS - Markierungen setzen
└── Als gelesen: +FLAGS \\Seen
└── Als wichtig: +FLAGS \\Flagged

SMTP - Antworten senden
└── smtplib.SMTP_SSL()
└── In-Reply-To Header setzen
```

---

### **Säule 3: 🧠 KI-Verbesserungen**

#### Besserer KI-Kontext:

```
Thread-Context
└── "Dies ist Mail 3/5 in einer Konversation"
└── Vorherige Mails als Kontext mitgeben

Sender-Intelligence
└── "Von diesem Absender: 47 Mails, 45 Newsletter"
└── Automatisch als Newsletter markieren

Attachment-Awareness
└── "Hat 3 Anhänge (PDF, XLSX, PNG)"
└── Höhere Wichtigkeit bei Dokumenten

Response-Suggestions
└── KI schlägt Antwort vor
└── User kann bearbeiten → SMTP senden
```

---

## 📋 Konkrete Implementation

### **Phase A: Filter auf /liste ✅ COMPLETED**

**Implementation Details:**
- ✅ Backend: `list_view()` erweitert mit 7 Filter-Parametern
- ✅ Filter: Account, Folder, Seen, Flagged, Attachments, DateRange
- ✅ Sortierung: By date/score/size/sender mit asc/desc
- ✅ Frontend: Progressive Disclosure UI mit Compact-Bar + Erweitert-Section
- ✅ JavaScript: Live AJAX-filtering (debounced 500ms), URL-Parameter, no page reload
- ✅ UX: Filter-Badge zeigt aktive Filter-Count

**Files Modified:**
- `src/01_web_app.py:816-150` - list_view() mit 7 Filter-Parametern
- `templates/list_view.html:1-170` - Filter-Bar UI + JavaScript
- `templates/list_view.html:234-170` - Live-filtering AJAX Handler

---

### **Phase B: Server-Aktionen (DELETE/FLAG/READ) ✅ COMPLETED**

**Implementation Details:**
- ✅ Backend: 3 REST-Endpoints (`/email/<id>/delete`, `/email/<id>/mark-read`, `/email/<id>/mark-flag`)
- ✅ MailSynchronizer: `src/16_mail_sync.py` with delete_email(), mark_as_read(), set_flag(), unset_flag()
- ✅ Frontend: Action-Buttons im Email-Detail mit Confirmation-Dialogs
- ✅ Status-Sync: Button-Text und Badge aktualisieren ohne Page-Reload
- ✅ UX: Klarer Dialog (erklärt was Flag bedeutet), visuelles Feedback sofort

**Fixed Issues (Session 2):**
1. ✅ IMAP-Flags "Wird abgerufen..." endlos Loading → zeigt jetzt aktuellen Status aus DB
2. ✅ "Flag toggeln?" unklar → Dialog erklärt jetzt konkret: "Flag setzen (als wichtig markieren)?"
3. ✅ getCsrfToken() undefined → hinzugefügt in email_detail.html:344
4. ✅ AttributeError 'MailAccount' has no attribute 'imap_server' → decrypt_server() + decrypt_email_address()
5. ✅ imap_uid vs uid mismatch → Fallback logic (imap_uid or uid)
6. ✅ Doppelte Dialoge nach Toggle → entfernt location.reload(), direktes UI-Update

**Files Modified:**
- `src/01_web_app.py:3366-3620` - 3 Endpoints mit vollständiger IMAP-Integration
- `src/16_mail_sync.py:1-233` - MailSynchronizer Class
- `templates/email_detail.html:207-216` - Server-Status Display (no loading)
- `templates/email_detail.html:307-320` - Action-Buttons
- `templates/email_detail.html:344-346` - getCsrfToken() Function
- `templates/email_detail.html:869-880` - Improved Flag-Dialog Messaging
- `templates/email_detail.html:904-925` - Flag-Toggle Handler (no reload, live UI update)

---

### **Phase D: Option D ServiceToken Refactor + Initial Sync Detection ✅ COMPLETED**

**Implementation Details:**
- ✅ **Option D Architecture**: DEK copied as value into FetchJob at job creation time (not stored in DB)
  - Security: Complete removal of plaintext DEK from database (zero-knowledge maintained)
  - Reliability: Background jobs work after server restart (DEK from session, not DB lookup)
  - Simplicity: No token lifecycle, expiry checks, or renewal logic
  - Root Cause Fix: Solved "mail fetch fails after server restart unless re-login" problem
  
- ✅ **Initial Sync Detection Flag**:
  - `initial_sync_done` boolean added to MailAccount model
  - Initial fetch (first run): 500 mails (complete sync, faster onboarding)
  - Regular fetch: 50 mails (bandwidth efficient, incremental)
  - Flag set atomically only once after successful processing
  - Root Cause Fix: Solved "is_initial always True" bug (last_fetch_at never updated)

**Files Modified:**
- `src/14_background_jobs.py`: FetchJob.master_key (line 32), enqueue_fetch_job() validation (lines 86-87), _execute_job() state updates (lines 204-210)
- `src/01_web_app.py`: fetch_mails() endpoint (lines 3288-3313), removed ServiceToken creation from login/2FA
- `src/02_models.py`: initial_sync_done column (line 394)
- `migrations/versions/ph13_initial_sync_tracking.py`: Alembic migration

**Migration Applied:**
- Command: `alembic upgrade head`
- Sets existing accounts with last_fetch_at data to initial_sync_done=True (preserves behavior)
- New accounts default to initial_sync_done=False (triggers 500-mail first fetch)

---

### **Phase C: MOVE + Multi-Folder FULL SYNC ✅ COMPLETED**

**Implementation Details (Part 1 - MOVE):**
- ✅ Backend: `/email/<id>/move` endpoint in web_app.py
- ✅ MailSynchronizer: move_to_folder() mit IMAP COPY + DELETE + EXPUNGE
- ✅ DB Update: raw_email.imap_folder wird aktualisiert (nicht deleted_at!)
- ✅ Frontend: Folder-Dropdown lädt Server-Ordner via AJAX, nicht DB-Ordner
- ✅ UX: Disabled-State wenn kein Account ausgewählt

**Implementation Details (Part 3 - FULL SYNC Architecture Fix):**
- ✅ **KRITISCHER ARCHITEKTUR-FIX**: IMAP UID ist eindeutig pro (account, folder, uid)!
  - INBOX/UID=123 ≠ Archiv/UID=123 (verschiedene IMAP-Objekte)
  - UniqueConstraint: (user_id, mail_account_id, imap_folder, imap_uid)
  - Migration: ph13c_fix_unique_constraint_folder_uid
- ✅ **Multi-Folder FULL SYNC**: Keine UNSEEN-Filter mehr
  - Alle Ordner werden komplett synchronisiert
  - Server ist Single Source of Truth, nicht DB
  - Kein INBOX-Bias mehr (vorher: nur 2/20 Mails wegen UNSEEN-Filter)
- ✅ **INSERT/UPDATE Logic**: Korrekte IMAP-Synchronisierung
  - Lookup: SELECT WHERE (account_id, imap_folder, imap_uid)
  - Exists? → UPDATE (Flags/Status können sich ändern)
  - Not Exists? → INSERT (neues Mail)
  - KEINE MESSAGE-ID-Deduplizierung! (Mail kann in mehreren Ordnern sein)
- ✅ **SQLAlchemy Fix**: session.no_autoflush Block verhindert IntegrityError

**Files Modified:**
- `src/01_web_app.py:3797` - MOVE endpoint mit imap_folder update
- `src/01_web_app.py:1086-1093` - available_folders von allen Mails (nicht nur visible)
- `src/01_web_app.py:933-982` - Server folder listing via IMAP
- `src/14_background_jobs.py:240-319` - Multi-folder fetch (ALL mails, no UNSEEN filter)
- `src/14_background_jobs.py:345-477` - INSERT/UPDATE logic mit (account, folder, uid)
- `src/02_models.py:534-540` - UniqueConstraint mit imap_folder
- `src/16_mail_sync.py` - move_to_folder() implementation
- `templates/list_view.html:30-48` - Server folder dropdown
- `migrations/versions/ph13c_fix_unique_constraint_folder_uid.py` - DB migration

**Root Cause Fixed:**
- Problem: UNSEEN-Filter zeigte nur 2/20 Mails in INBOX (nur ungelesene)
- Problem: Mails in mehreren Ordnern überschrieben sich gegenseitig (falsche UniqueConstraint)
- Problem: Ordner-Dropdown zeigte stale DB-Daten, nicht aktuelle Server-Ordner
- Lösung: FULL SYNC aller Ordner + korrekte (account, folder, uid) Identity

---

### **Phase C: Gefilterter Fetch (Optional - Future Enhancement)**

```python
# 06_mail_fetcher.py - fetch_new_emails() erweitern

def fetch_new_emails(
    self, 
    folder: str = "INBOX",
    limit: int = 50,
    # NEU: Filter-Optionen
    since: datetime = None,      # SEARCH SINCE
    before: datetime = None,     # SEARCH BEFORE  
    unseen_only: bool = False,   # SEARCH UNSEEN
    flagged_only: bool = False,  # SEARCH FLAGGED
) -> List[Dict]:
    
    # IMAP SEARCH Query bauen
    search_criteria = []
    
    if unseen_only:
        search_criteria.append("UNSEEN")
    if flagged_only:
        search_criteria.append("FLAGGED")
    if since:
        search_criteria.append(f"SINCE {since.strftime('%d-%b-%Y')}")
    if before:
        search_criteria.append(f"BEFORE {before.strftime('%d-%b-%Y')}")
    
    criteria = " ".join(search_criteria) if search_criteria else "ALL"
    status, messages = conn.search(None, criteria)
```

### **Phase C: Server-Sync (8-10h)**

```python
# NEU: src/16_mail_sync.py

class MailSynchronizer:
    """IMAP Server-Sync für Aktionen"""
    
    def __init__(self, connection: imaplib.IMAP4_SSL):
        self.conn = connection
    
    def delete_email(self, uid: str, folder: str = "INBOX") -> bool:
        """Löscht Mail auf Server (EXPUNGE)"""
        self.conn.select(folder)
        self.conn.uid('store', uid, '+FLAGS', '\\Deleted')
        self.conn.expunge()
        return True
    
    def move_to_folder(self, uid: str, target: str, source: str = "INBOX") -> bool:
        """Verschiebt Mail in anderen Ordner"""
        self.conn.select(source)
        self.conn.uid('copy', uid, target)
        self.conn.uid('store', uid, '+FLAGS', '\\Deleted')
        self.conn.expunge()
        return True
    
    def mark_as_read(self, uid: str, folder: str = "INBOX") -> bool:
        """Markiert als gelesen"""
        self.conn.select(folder)
        self.conn.uid('store', uid, '+FLAGS', '\\Seen')
        return True
    
    def mark_as_flagged(self, uid: str, folder: str = "INBOX") -> bool:
        """Markiert als wichtig"""
        self.conn.select(folder)
        self.conn.uid('store', uid, '+FLAGS', '\\Flagged')
        return True
```

### **Phase E: KI Thread-Context ✅ GEPLANT (4-6h)**

**Ziel:** Verbesserte KI-Klassifizierung durch Kontext-Enrichment

#### **E.1: Thread-Context für KI (2-3h)**

**Problem:** KI sieht nur einzelne Mail, keine Konversations-Historie
**Lösung:** Thread-Historie als Kontext an KI übergeben

```python
# 12_processing.py - analyze_email() erweitern

def build_thread_context(session, raw_email: RawEmail, master_key: str) -> str:
    """Baut Thread-Kontext für KI-Analyse"""
    if not raw_email.thread_id:
        return ""
    
    # Hole vorherige Mails im Thread (max 5, chronologisch)
    thread_emails = session.query(RawEmail).filter(
        RawEmail.thread_id == raw_email.thread_id,
        RawEmail.id != raw_email.id,
        RawEmail.deleted_at.is_(None)
    ).order_by(RawEmail.received_at.desc()).limit(5).all()
    
    if not thread_emails:
        return ""
    
    context = f"📧 KONVERSATIONS-KONTEXT (Mail {len(thread_emails) + 1} im Thread):\n\n"
    
    encryption = importlib.import_module(".08_encryption", "src")
    for i, prev in enumerate(reversed(thread_emails), 1):
        try:
            sender = encryption.EmailDataManager.decrypt_email_sender(
                prev.encrypted_sender, master_key
            )
            subject = encryption.EmailDataManager.decrypt_email_subject(
                prev.encrypted_subject, master_key
            )
            body = encryption.EmailDataManager.decrypt_email_body(
                prev.encrypted_body, master_key
            )
            
            # Kürze Body auf 150 Zeichen
            body_preview = body[:150].replace("\n", " ") + "..." if len(body) > 150 else body
            
            context += f"{i}. Von: {sender}\n"
            context += f"   Betreff: {subject}\n"
            context += f"   Inhalt: {body_preview}\n\n"
        except Exception as e:
            logger.warning(f"Thread-Mail {prev.id} nicht entschlüsselbar: {e}")
            continue
    
    return context


# In process_pending_raw_emails():
thread_context = build_thread_context(session, raw_email, master_key)

ai_result = active_ai.analyze_email(
    subject=decrypted_subject or "",
    body=clean_body,
    sender=decrypted_sender or "",
    context=thread_context  # NEU!
)
```

**Impact:**
- ✅ KI versteht Konversations-Kontext (Follow-ups, Antworten)
- ✅ Bessere Dringlichkeit-Einschätzung (z.B. 3. Mahnung)
- ✅ Spam-Erkennung: Newsletter-Thread = alle Mails Spam

---

#### **E.2: Sender-Intelligence (1-2h)**

**Problem:** KI kennt Absender-Historie nicht
**Lösung:** Sender-Pattern Detection (bereits vorhanden, erweitern!)

```python
# Bereits vorhanden in 12_processing.py:
# get_sender_hint_from_patterns()

# ERWEITERN um Thread-Awareness:
def get_sender_hint_from_patterns(
    session, 
    user_id: int, 
    sender: str,
    thread_id: Optional[str] = None,  # NEU
    min_confidence: int = 70,
    min_emails: int = 3
) -> Optional[Dict]:
    """Analysiert Sender-Pattern + Thread-Pattern"""
    
    # 1) Bestehende Sender-Pattern-Logik (wie bisher)
    sender_stats = get_sender_stats(session, user_id, sender, min_emails)
    
    # 2) NEU: Thread-Pattern Detection
    if thread_id:
        thread_stats = get_thread_stats(session, user_id, thread_id)
        if thread_stats and thread_stats["email_count"] >= 3:
            # Wenn 80%+ der Thread-Mails Newsletter sind → ganzer Thread Spam
            if thread_stats["spam_rate"] > 0.8:
                return {
                    "category": "nur_information",
                    "priority": 1,
                    "is_newsletter": True,
                    "reason": f"Thread-Pattern: {thread_stats['spam_rate']:.0%} Newsletter"
                }
    
    return sender_stats  # Fallback zu Sender-Pattern


def get_thread_stats(session, user_id: int, thread_id: str) -> Dict:
    """Analysiert Thread-Statistiken"""
    thread_emails = session.query(ProcessedEmail).join(RawEmail).filter(
        RawEmail.user_id == user_id,
        RawEmail.thread_id == thread_id,
        RawEmail.deleted_at.is_(None)
    ).all()
    
    if not thread_emails:
        return None
    
    spam_count = sum(1 for e in thread_emails if e.spam_flag)
    
    return {
        "email_count": len(thread_emails),
        "spam_rate": spam_count / len(thread_emails),
        "avg_score": sum(e.score for e in thread_emails) / len(thread_emails)
    }
```

**Impact:**
- ✅ Newsletter-Thread-Erkennung (ganzer Thread als Spam)
- ✅ Sender-Historie fließt in Klassifizierung ein
- ✅ Weniger False-Positives bei bekannten Absendern

---

#### **E.3: Attachment-Awareness (0.5-1h)**

**Problem:** KI weiß nicht, ob Mail Anhänge hat
**Lösung:** Attachment-Info an KI übergeben

```python
# In process_pending_raw_emails():

attachment_context = ""
if raw_email.has_attachments:
    attachment_context = "\n\n📎 ANHANG-INFO: Diese Mail hat Anhänge."
    # Optional: Attachment-Typen analysieren (wenn vorhanden)
    # attachment_types = parse_attachment_types(raw_email)
    # attachment_context += f" Typen: {', '.join(attachment_types)}"

full_context = thread_context + attachment_context

ai_result = active_ai.analyze_email(
    subject=decrypted_subject or "",
    body=clean_body,
    sender=decrypted_sender or "",
    context=full_context
)
```

**Impact:**
- ✅ Mails mit Anhängen bekommen höhere Wichtigkeit
- ✅ KI kann besser zwischen Info-Mail und Action-Mail unterscheiden

---

#### **E.4: AI Client Context-Parameter (1h)**

**Problem:** `analyze_email()` hat kein `context` Parameter
**Lösung:** API erweitern

```python
# src/03_ai_client.py - AIClient.analyze_email() erweitern

class AIClient(ABC):
    @abstractmethod
    def analyze_email(
        self, 
        subject: str, 
        body: str, 
        sender: str = "",
        language: str = "de",
        context: str = ""  # NEU!
    ) -> Dict[str, Any]:
        """Analysiert Mail mit optionalem Kontext"""
        pass


# In LocalOllamaClient, OpenAIClient, AnthropicClient:

def analyze_email(
    self, 
    subject: str, 
    body: str, 
    sender: str = "",
    language: str = "de",
    context: str = ""
) -> Dict[str, Any]:
    # Wenn context vorhanden, an Prompt anhängen
    full_prompt = f"{SYSTEM_PROMPT}\n\n"
    
    if context:
        full_prompt += f"ZUSÄTZLICHER KONTEXT:\n{context}\n\n"
    
    full_prompt += f"BETREFF: {subject}\nABSENDER: {sender}\n\nTEXT:\n{body}"
    
    # ... Rest wie bisher
```

**Files zu ändern:**
- `src/03_ai_client.py`: AIClient Interface + alle 3 Implementierungen
- `src/12_processing.py`: `process_pending_raw_emails()` erweitern
- `src/01_web_app.py`: `/email/<id>/reprocess` und `/email/<id>/optimize` erweitern

**Testing:**
- Unit-Test: `build_thread_context()` mit Mock-Daten
- Integration: Test mit echter 5-Mail-Konversation
- Performance: Kontext sollte < 1000 Zeichen sein

---

#### **Aufwands-Breakdown:**

| Task | Aufwand | Schwierigkeit |
|------|---------|---------------|
| E.1: Thread-Context Builder | 2h | Mittel (DB-Query + Encryption) |
| E.2: Sender-Intelligence erweitern | 1.5h | Einfach (Pattern bereits da) |
| E.3: Attachment-Awareness | 0.5h | Einfach (Flag bereits in DB) |
| E.4: AI Client API erweitern | 1h | Einfach (Parameter + String-Concat) |
| Testing & Integration | 1h | Mittel |

**Total:** 4-6 Stunden

---

#### **Expected Impact:**

**Vorher:**
- KI sieht nur einzelne Mail isoliert
- Newsletter-Follow-ups werden nicht erkannt
- Konversations-Kontext fehlt

**Nachher:**
- ✅ KI versteht Thread-Historie (bis zu 5 vorherige Mails)
- ✅ Newsletter-Threads automatisch als Spam
- ✅ Dringlichkeit basiert auf Konversations-Kontext
- ✅ Bessere Kategorisierung (z.B. "3. Mahnung" → dringend)
- ✅ Attachment-Flag beeinflusst Wichtigkeit

**Performance:**
- +200-500ms pro Mail (Thread-Query + Decryption)
- Akzeptabel, da nur bei Processing (nicht bei jedem View)
```

---

## 🎯 Priorisierte Reihenfolge (Nach Use-Cases)

### ✅ Phase 1-5 & 14: Core Infrastructure (COMPLETE)

| Status | Prio | Feature | Aufwand | Impact | Notes |
|--------|------|---------|--------|--------|-------|
| ✅ DONE | 1 | Filter auf /liste | 4-6h | Sofort nutzbar | Phase A |
| ✅ DONE | 2 | Server DELETE/FLAG/READ | 3-4h | KI→Action möglich | Phase B |
| ✅ DONE | 2a | Option D ServiceToken + InitialSync | 2-3h | Kritische Infra-Fixes | Phase D |
| ✅ DONE | 3 | Server MOVE | 2-3h | Spam-Ordner etc. | Phase C Part 1 |
| ✅ DONE | 4 | Multi-Folder FULL SYNC | 6-8h | Korrekte IMAP-Architektur | Phase C Part 3 |
| ✅ DONE | 4a | Delta-Sync + Fetch Config | 8-10h | 30-60x Speedup, Quick Count | Phase C Part 4 COMPLETE |
| ✅ DONE | 4b | RFC-Compliant IMAP UIDs | 4-6h | Eliminiert Race-Conditions | Phase 14 (a-f) COMPLETE |
| ✅ DONE | 4c | IMAPClient Migration | 4-5h | 40% Code-Reduktion, 100% Reliability | Phase 14g COMPLETE |
| ✅ DONE | 4d | reset_all_emails.py Fix | 0.5h | Soft-Delete + UIDVALIDITY Cache Clear | Phase 14g COMPLETE |
| ✅ DONE | 5 | KI Thread-Context | 4h | Bessere Klassifizierung | Phase E COMPLETE |
| ✅ DONE | 6 | **Semantic Intelligence (F.1+F.2+F.3)** | 22-30h | Semantische Suche komplett | Phase F COMPLETE |

**Abgeschlossen:** 73-91h (Phase A-E + 14a-g + F.1-3)

---

### 🚀 Phase F: Semantic Intelligence (22-30h) ⭐⭐⭐⭐⭐ **COMPLETE!**

| Status | Prio | Feature | Aufwand | Impact | Notes |
|--------|------|---------|---------|--------|-------|
| ✅ DONE | F.1 | **Semantic Email Search** | 8-12h | ⭐⭐⭐⭐⭐ | Vector-based search, 47/47 embeddings |
| ✅ DONE | F.2 | **3-Settings System (Embedding/Base/Optimize)** | 12-15h | ⭐⭐⭐⭐⭐ | Separate models, batch-reprocess, pre-checks |
| ✅ DONE | F.3 | **Email Similarity Detection** | 2-3h | ⭐⭐⭐ | "Similar emails" card with scores |

**Total:** 22-30h | **Status: COMPLETE!** | **User Value:** Massive (semantische Suche funktioniert!)

---

### 🤖 Phase G: AI Action Engine (10-14h) ⭐⭐⭐⭐⭐

| Prio | Feature | Aufwand | Impact | Notes |
|------|---------|---------|--------|-------|
| 🔥 G.1 | **Reply Draft Generator** | 4-6h | ⭐⭐⭐⭐⭐ | Mit Ton-Auswahl & Thread-Context |
| 🔥 G.2 | **Auto-Action Rules Engine** | 6-8h | ⭐⭐⭐⭐⭐ | Newsletter-Problem endlich gelöst! |

**Total:** 10-14h | **User Value:** Massive (Automation + Draft-Generator!)

---

### 📅 Phase H: Action Extraction (8-12h) ⭐⭐⭐⭐

| Prio | Feature | Aufwand | Impact | Notes |
|------|---------|---------|--------|-------|
| 🟡 H.1 | **Unified Action Extractor** | 5-7h | ⭐⭐⭐⭐ | Termine + Aufgaben in einem Service |
| 🟡 H.2 | Action Items DB & UI | 3-5h | ⭐⭐⭐ | DB-Tabelle + Management-UI |

**Total:** 8-12h | **User Value:** Hoch (Termine & ToDos aus Mails!)

---

### 🔧 Phase I: Productivity Features (20-28h) ⭐⭐⭐

| Prio | Feature | Aufwand | Impact | Notes |
|------|---------|---------|--------|-------|
| 🟢 I.1 | Thread Summarization | 3-4h | ⭐⭐⭐ | KI fasst Konversationen zusammen |
| 🟢 I.2 | **Bulk Email Operations** | 15-20h | ⭐⭐⭐⭐ | Multi-Select + Batch-Actions |
| 🟢 I.3 | Enhanced Conversation UI | 2-4h | ⭐⭐⭐ | Thread-View Improvements |

**Total:** 20-28h | **User Value:** Mittel-Hoch (Produktivität)

---

### ✉️ Phase J: SMTP Integration (6-8h) ⭐⭐⭐

| Prio | Feature | Aufwand | Impact | Notes |
|------|---------|---------|--------|-------|
| 🟢 J.1 | SMTP Send & Threading | 6-8h | ⭐⭐⭐ | Antworten direkt aus App senden |

**Total:** 6-8h | **User Value:** Mittel (Reply Draft + Copy reicht für 80%)

---

### 📊 Gesamtübersicht (Phase F-J)

**Abgeschlossen (A-E + 14):** 39-49h  
**Geplant Phase F-J:** 56-80h  
**Phase 13 Total:** 95-129h  

**Empfohlene Reihenfolge:**
1. **Phase F** (Semantic Intelligence) - Größter Impact, Infrastructure ready
2. **Phase G** (AI Actions) - Auto-Actions löst Newsletter-Problem!
3. **Phase H** (Action Extraction) - Synergien mit Phase G
4. **Phase I** (Bulk Ops) - Wenn Core-Features stable
5. **Phase J** (SMTP) - Optional, Reply Draft reicht meist

**Phase D Justification (Critical Infrastructure):**
- Moved ahead of Phase C due to critical nature
- Fixed architectural flaw: DEK storage violating zero-knowledge principle
- Solved "mail fetch fails after server restart" blocking production use
- Improved initial sync detection for better UX (500 vs 50 mails)

---

## � Phase F: Semantic Intelligence - DETAILLIERT

### **Phase F.1: Semantic Email Search (8-12h)** ⭐⭐⭐⭐⭐

**Problem:** Text-Suche findet nur exakte Keywords → "Budget" findet nicht "Kostenplanung"

**Lösung:** Vektorbasierte Suche mit Embeddings (Semantische Ähnlichkeit)

#### ✅ Warum das funktioniert

```
USER-QUERY: "Projektbudget"
   ↓ Embedding
   [0.12, 0.85, -0.34, ...]  (384-dim Vektor)
   ↓ Cosine Similarity
   ┌─────────────────────────────────────┐
   │ Email 1: "Kostenplanung Q1"  → 0.89 │ ← MATCH! (trotz anderer Wörter)
   │ Email 2: "Finanzübersicht"    → 0.82 │ ← MATCH!
   │ Email 3: "Meeting-Protokoll"  → 0.23 │ ← Kein Match
   └─────────────────────────────────────┘
```

**Zero-Knowledge kompatibel:** Embeddings sind **nicht reversibel** zu Klartext!

---

#### 🔄 Der RICHTIGE Flow (Embedding-Generierung beim Fetch)

```
┌─────────────────────────────────────────────────────────────┐
│  IMAP FETCH (14_background_jobs.py → _persist_raw_emails)   │
│                                                             │
│  1. Email vom Server holen                                  │
│     └── subject = "Projektbudget Q1"      ← KLARTEXT! ✅    │
│     └── body = "Hallo, anbei..."          ← KLARTEXT! ✅    │
│     └── sender = "alice@example.com"      ← KLARTEXT! ✅    │
│                                                             │
│  2. 🔥 HIER Embedding generieren! ←──────────────────────   │
│     └── embedding = ai_client._get_embedding(               │
│             f"{subject}\n{body[:500]}"                      │
│         )                                                   │
│     └── embedding_bytes = np.array(                         │
│             embedding, dtype=np.float32                     │
│         ).tobytes()                                         │
│                                                             │
│  3. DANN erst verschlüsseln für DB                          │
│     └── encrypted_subject = encrypt(subject, master_key)    │
│     └── encrypted_body = encrypt(body, master_key)          │
│     └── email_embedding = embedding_bytes  ← NICHT encrypt! │
│                                                             │
│  4. In DB speichern                                         │
│     └── RawEmail(                                           │
│             encrypted_subject=...,                          │
│             encrypted_body=...,                             │
│             email_embedding=embedding_bytes,  ← 1.5KB       │
│             embedding_model="all-minilm:22m",               │
│             embedding_generated_at=now()                    │
│         )                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Warum NICHT beim Processing?**

| Aspekt | Beim Fetch ✅ | Beim Processing ❌ |
|--------|--------------|-------------------|
| Klartext verfügbar? | ✅ Ja (vom IMAP) | ⚠️ Muss erst decrypt |
| Extra Decrypt nötig? | ❌ Nein | ✅ Ja (unnötig!) |
| Zeitpunkt | Sofort bei Ankunft | Später (Verzögerung) |
| master_key nötig? | ❌ Nein | ✅ Ja |
| Code-Änderung | `14_background_jobs.py` | `12_processing.py` + Decrypt |

---

#### 📁 Files to Modify/Create

| Datei | Änderung | Aufwand |
|-------|----------|---------|
| `migrations/versions/ph15_semantic_search.py` | DB Migration: `email_embedding`, `embedding_model`, `embedding_generated_at` | 0.5h |
| `src/02_models.py` | `RawEmail`: 3 neue Felder | 0.5h |
| `src/semantic_search.py` | **NEU**: Service mit `generate_embedding()`, `search()`, `find_similar()` | 3-4h |
| `src/14_background_jobs.py` | `_persist_raw_emails()`: Embedding VOR encrypt generieren | 2-3h |
| `src/01_web_app.py` | 4 API Endpoints: `/api/search/semantic`, `/api/emails/<id>/similar`, `/api/embeddings/stats`, `/api/embeddings/generate` | 2-3h |
| `templates/liste.html` | Search UI: Toggle "Text" / "Semantisch", Ähnlichkeit-Score | 1h |
| `scripts/generate_embeddings.py` | **NEU**: Bestehende Emails nachträglich mit Embeddings versehen | 1-2h |

**Total:** 8-12h

---

#### 🛠️ Implementation Steps

**Step 1: DB Migration (30 min)**

```bash
# Erstelle Migration
cp doc/semantic_search_examples/ph15_semantic_search.py \
   migrations/versions/

# Anpassen down_revision falls nötig
# down_revision = 'ph14g_imapclient_migration'  # Letzte Migration

# Backup + Migration
cp emails.db emails.db.backup_phase15
alembic upgrade head

# Verify
sqlite3 emails.db ".schema raw_emails" | grep embedding
# → email_embedding BLOB
# → embedding_model VARCHAR(50)
# → embedding_generated_at DATETIME
```

**Step 2: Model erweitern (30 min)**

```python
# In src/02_models.py, class RawEmail:

    # ===== PHASE 15: SEMANTIC SEARCH =====
    # Embedding für semantische Suche (NICHT verschlüsselt!)
    # Embeddings sind nicht zu Klartext reversibel → Zero-Knowledge OK
    # 384 floats × 4 bytes = 1536 bytes pro Email
    email_embedding = Column(LargeBinary, nullable=True)
    embedding_model = Column(String(50), nullable=True)  # "all-minilm:22m"
    embedding_generated_at = Column(DateTime, nullable=True)
```

**Step 3: Service erstellen (3-4h)**

```python
# src/semantic_search.py (NEU)

class SemanticSearchService:
    def generate_embedding(self, subject: str, body: str) -> Optional[bytes]:
        """Generiert Embedding (beim Fetch aufrufen!)"""
        text = f"{subject}\n{body[:500]}"
        embedding_list = self.ai_client._get_embedding(text)
        return np.array(embedding_list, dtype=np.float32).tobytes()
    
    def search(self, query: str, user_id: int, limit: int = 20) -> List[Dict]:
        """Semantische Suche über alle Emails"""
        # 1. Query-Embedding generieren
        # 2. Alle User-Emails mit Embeddings laden
        # 3. Cosine Similarity berechnen
        # 4. Top-K zurückgeben
    
    def find_similar(self, email_id: int, limit: int = 5) -> List[Dict]:
        """Findet ähnliche Emails"""
```

**Step 4: Background Jobs patchen (2-3h)**

```python
# src/14_background_jobs.py, in _persist_raw_emails():

# ⚠️ WICHTIG: VOR der Verschlüsselung!
def _persist_raw_emails(self, session, user, account, raw_emails, master_key):
    # AI-Client einmal laden
    embedding_client = ai_client_mod.LocalOllamaClient(model="all-minilm:22m")
    
    for raw_email_data in raw_emails:
        # Klartext noch verfügbar!
        subject_plain = raw_email_data.get("subject", "")
        body_plain = raw_email_data.get("body", "")
        
        # 🔥 Embedding generieren (VOR encrypt!)
        embedding_bytes = None
        if embedding_client and (subject_plain or body_plain):
            embedding_bytes, model, timestamp = generate_embedding_for_email(
                subject=subject_plain,
                body=body_plain,
                ai_client=embedding_client
            )
        
        # DANN verschlüsseln (wie bisher)
        encrypted_subject = encrypt(subject_plain, master_key)
        # ...
        
        # In DB speichern
        raw_email = models.RawEmail(
            # ... encrypted fields ...
            email_embedding=embedding_bytes,  # ← NEU!
            embedding_model="all-minilm:22m" if embedding_bytes else None,
            embedding_generated_at=datetime.now(UTC) if embedding_bytes else None
        )
```

**Step 5: API Endpoints (2-3h)**

```python
# src/01_web_app.py

@app.route("/api/search/semantic", methods=["GET"])
@login_required
def semantic_search():
    """GET /api/search/semantic?q=Budget&limit=20"""
    query = request.args.get("q", "")
    limit = int(request.args.get("limit", 20))
    
    service = SemanticSearchService(db.session, get_active_ai_client())
    results = service.search(query, current_user.id, limit)
    
    # Decrypt results für Anzeige
    master_key = session.get("master_key")
    for r in results:
        r["subject_decrypted"] = decrypt(r["encrypted_subject"], master_key)
        r["sender_decrypted"] = decrypt(r["encrypted_sender"], master_key)
    
    return jsonify({"results": results, "query": query})


@app.route("/api/emails/<int:email_id>/similar", methods=["GET"])
@login_required
def find_similar_emails(email_id):
    """GET /api/emails/123/similar?limit=5"""
    limit = int(request.args.get("limit", 5))
    
    service = SemanticSearchService(db.session, get_active_ai_client())
    similar = service.find_similar(email_id, limit)
    
    # Decrypt + return
    return jsonify({"similar": similar})


@app.route("/api/embeddings/stats", methods=["GET"])
@login_required
def embedding_stats():
    """GET /api/embeddings/stats → Wie viele Emails haben Embeddings?"""
    total = db.session.query(models.RawEmail).filter_by(
        user_id=current_user.id, deleted_at=None
    ).count()
    
    with_embedding = db.session.query(models.RawEmail).filter_by(
        user_id=current_user.id, deleted_at=None
    ).filter(models.RawEmail.email_embedding.isnot(None)).count()
    
    return jsonify({
        "total": total,
        "with_embedding": with_embedding,
        "percentage": round(with_embedding / total * 100, 1) if total > 0 else 0
    })


@app.route("/api/embeddings/generate", methods=["POST"])
@login_required
def trigger_embedding_generation():
    """POST /api/embeddings/generate → Script starten für alte Emails"""
    # Trigger scripts/generate_embeddings.py via subprocess
    # Oder in Background Job enqueue
    return jsonify({"status": "started"})
```

**Step 6: Frontend (1h)**

```html
<!-- templates/liste.html, Search-Bar erweitern -->

<div class="search-box">
    <input type="text" id="search-query" placeholder="Suche...">
    
    <!-- NEU: Toggle zwischen Text/Semantisch -->
    <div class="search-mode">
        <label>
            <input type="radio" name="search-mode" value="text" checked>
            Text (exakt)
        </label>
        <label>
            <input type="radio" name="search-mode" value="semantic">
            🔍 Semantisch (ähnlich)
        </label>
    </div>
    
    <button onclick="performSearch()">Suchen</button>
</div>

<script>
function performSearch() {
    const query = document.getElementById('search-query').value;
    const mode = document.querySelector('input[name="search-mode"]:checked').value;
    
    if (mode === 'semantic') {
        fetch(`/api/search/semantic?q=${encodeURIComponent(query)}&limit=20`)
            .then(r => r.json())
            .then(data => {
                displayResults(data.results);  // Mit Similarity-Score!
            });
    } else {
        // Bestehende Text-Suche
        performTextSearch(query);
    }
}

function displayResults(results) {
    // Jedes Result hat: { id, subject_decrypted, similarity_score }
    // Score anzeigen: "📊 92% Ähnlichkeit"
}
</script>
```

**Step 7: Bestehende Emails nachträglich (1-2h)**

```python
# scripts/generate_embeddings.py (NEU)

"""
Generiert Embeddings für bestehende Emails ohne Embedding.
Run: python scripts/generate_embeddings.py --user-id 1 --batch-size 50
"""

def generate_embeddings_for_existing_emails(user_id: int):
    # 1. Alle Emails ohne email_embedding laden
    # 2. Decrypt mit master_key
    # 3. Embedding generieren
    # 4. Update DB
    
    emails_without = db.query(RawEmail).filter_by(
        user_id=user_id, deleted_at=None
    ).filter(RawEmail.email_embedding.is_(None)).all()
    
    for email in emails_without:
        subject = decrypt(email.encrypted_subject, master_key)
        body = decrypt(email.encrypted_body, master_key)
        
        embedding = service.generate_embedding(subject, body)
        email.email_embedding = embedding
        email.embedding_model = "all-minilm:22m"
        email.embedding_generated_at = datetime.now(UTC)
    
    db.commit()
```

---

#### 🎯 Expected Results

**Vorher (Text-Suche):**
- Query "Budget" → findet nur "Budget" (1 Email)
- Sucht nach "Kosten" → andere Email, nicht gefunden

**Nachher (Semantic Search):**
```
Query: "Projektbudget"

📊 Ergebnisse (Top 5):
1. [95%] "Kostenplanung Q1 2026" - alice@x.com
2. [88%] "Finanzübersicht Jahresabschluss" - bob@x.com
3. [82%] "Budget-Meeting Protokoll" - carol@x.com
4. [78%] "Ausgaben-Report Dezember" - dave@x.com
5. [72%] "Investitionsplan 2026" - eve@x.com
```

**Zusatz-Feature: "Ähnliche Mails"**
- Beim Betrachten einer Email: Button "🔍 Ähnliche Mails finden"
- Zeigt 5 ähnlichste Emails basierend auf Embedding
- Nutzen: Duplikat-Erkennung, Kontext-Suche

---

#### ⚠️ Critical Notes

1. **Embedding-Modell:** `all-minilm:22m` (384-dim, 1.5KB/Email)
   - Bei 1000 Emails: 1.5 MB zusätzlich (minimal!)
   - Bei 10000 Emails: 15 MB (noch OK für SQLite)

2. **Performance:** Cosine Similarity für N Emails = O(N)
   - Mit 1000 Emails: ~50ms (schnell genug)
   - Mit 10000+ Emails: Evtl. FAISS-Index erwägen (später)

3. **Ollama Required:** `all-minilm:22m` muss lokal laufen
   - Fallback: Embedding-Generierung optional (kein Crash!)

4. **Zero-Knowledge:** Embeddings sind **nicht reversibel**
   - Man kann aus `[0.12, 0.85, ...]` NICHT den Originaltext rekonstruieren
   - ✅ Zero-Knowledge bleibt gewahrt!

---

### **Phase F.2: Smart Tag Auto-Suggestions (2-3h)** ⭐⭐⭐⭐

**Problem:** User muss Tags manuell zuweisen, auch wenn ähnliche Emails bereits getaggt sind

**Lösung:** Nutze existierenden Tag-Embedding Code für Auto-Vorschläge!

**Files:** `src/services/tag_manager.py` (bereits 80% fertig!), `src/12_processing.py`

**Implementation:**
```python
# In processing.py, nach AI-Klassifizierung:

# Auto-Suggest Tags basierend auf Email-Embedding
if raw_email.email_embedding:
    from src.services.tag_manager import suggest_similar_tags
    
    suggested = suggest_similar_tags(
        session=db.session,
        user_id=user.id,
        email_embedding=raw_email.email_embedding,
        threshold=0.85,  # Hohe Similarity = Auto-Assign
        limit=3
    )
    
    for tag_name, similarity in suggested:
        if similarity >= 0.85:
            # Auto-assign bei hoher Similarity
            assign_tag(db.session, user.id, raw_email.id, tag_name)
            logger.info(f"Auto-assigned Tag '{tag_name}' ({similarity:.2f})")
```

**Result:** Emails mit ähnlichem Inhalt bekommen automatisch passende Tags!

---

### **Phase F.3: Email Similarity Detection (2-3h)** ⭐⭐⭐

**Use Cases:**
1. **Duplikat-Erkennung:** "Diese Email ist zu 95% ähnlich zu Email #123"
2. **Thread-Completion:** "Möglicherweise gehört diese Email zu Thread XYZ"
3. **Related Emails:** "Andere Emails zu diesem Thema: ..."

**Files:** `src/semantic_search.py`, `templates/email_detail.html`

**Implementation:**
```python
# In email_detail view:
similar_emails = semantic_service.find_similar(email_id, limit=5, threshold=0.7)

# Frontend:
if similar_emails:
    <div class="similar-emails-box">
        <h4>📎 Ähnliche Emails (könnte zusammengehören)</h4>
        <ul>
            {% for similar in similar_emails %}
            <li>
                <a href="/email/{{ similar.id }}">
                    {{ similar.subject_decrypted }}
                </a>
                <span class="similarity">{{ similar.similarity }}% ähnlich</span>
            </li>
            {% endfor %}
        </ul>
    </div>
```

---

## 🤖 Phase G: AI Action Engine - DETAILLIERT

### **Phase G.1: Reply Draft Generator (4-6h)** ⭐⭐⭐⭐⭐

**Problem:** User muss Antworten manuell schreiben, auch für Standard-Situationen

**Lösung:** KI generiert Antwort-Entwurf mit wählbarem Ton

#### Features

```
┌─────────────────────────────────────────────────────────────┐
│  EMAIL: "Können Sie mir bis Freitag das Angebot schicken?"  │
│                                                             │
│  [✍️ Antwort-Entwurf generieren]                            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Ton: [📜 Formell ▼] [😊 Freundlich] [⚡ Kurz] [❌ Nein] │ │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  📝 ENTWURF (editierbar):                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Sehr geehrte Frau Müller,                           │    │
│  │                                                     │    │
│  │ vielen Dank für Ihre Anfrage. Ich werde Ihnen das  │    │
│  │ Angebot bis Freitag, den 10.01. zukommen lassen.   │    │
│  │                                                     │    │
│  │ Mit freundlichen Grüßen                             │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  [📋 In Zwischenablage kopieren] [✉️ In Mail-Client öffnen]│
└─────────────────────────────────────────────────────────────┘
```

#### Tone Options

| Ton | Beschreibung | Beispiel |
|-----|--------------|----------|
| **Formell** | Geschäftlich, Sie-Form, mit Grußformel | "Sehr geehrte/r ..., Mit freundlichen Grüßen" |
| **Freundlich** | Warm aber professionell | "Hallo ..., Liebe Grüße" |
| **Kurz** | Maximal 2-3 Sätze | "Danke für die Anfrage. Erledige ich bis Freitag." |
| **Ablehnend** | Höfliche Absage | "Vielen Dank für Ihr Interesse, leider..." |

#### Files to Create/Modify

| Datei | Änderung | Aufwand |
|-------|----------|---------|
| `src/services/reply_draft.py` | **NEU**: ReplyDraftGenerator mit 4 Ton-Prompts | 2-3h |
| `src/01_web_app.py` | API Endpoint: `POST /api/emails/<id>/draft-reply` | 1h |
| `templates/email_detail.html` | Button + Modal für Draft-Generation | 1-2h |

#### Implementation

**Service:**
```python
# src/services/reply_draft.py (NEU)

REPLY_DRAFT_PROMPT = """
Du bist ein Assistent, der professionelle E-Mail-Antworten verfasst.

KONTEXT:
- Original-Mail von: {sender}
- Betreff: {subject}
- Inhalt: {body}
{thread_context}

AUFGABE:
Verfasse eine Antwort im Ton: {tone}

TÖNE:
- "formell": Geschäftlich, Sie-Form, mit Grußformel
- "freundlich": Warm aber professionell, kann Du sein
- "kurz": Maximal 2-3 Sätze, auf den Punkt
- "ablehnend": Höfliche Absage mit Begründungsplatzhalter

REGELN:
- Antworte NUR mit dem E-Mail-Text (keine Erklärung)
- Beginne mit passender Anrede
- Ende mit passender Grußformel
- Platzhalter für fehlende Infos: [HIER ERGÄNZEN]
- Sprache: Deutsch
""".strip()


class ReplyDraftGenerator:
    TONES = {
        "formell": "Geschäftlich formell mit Sie-Form",
        "freundlich": "Freundlich-professionell",
        "kurz": "Kurz und prägnant (2-3 Sätze)",
        "ablehnend": "Höfliche Absage"
    }
    
    def __init__(self, ai_client):
        self.ai_client = ai_client
    
    def generate_draft(
        self, 
        sender: str, 
        subject: str, 
        body: str, 
        tone: str = "formell",
        thread_context: str = ""
    ) -> dict:
        """Generiert Antwort-Entwurf"""
        prompt = REPLY_DRAFT_PROMPT.format(
            sender=sender,
            subject=subject,
            body=body[:1500],
            tone=self.TONES.get(tone, self.TONES["formell"]),
            thread_context=thread_context or "(Keine vorherigen Mails)"
        )
        
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Verfasse die Antwort."}
        ]
        
        response = self.ai_client._call_model(messages)
        
        return {
            "draft": response,
            "tone": tone,
            "suggested_subject": f"Re: {subject}" if not subject.startswith("Re:") else subject,
            "recipient": self._extract_email(sender)
        }
```

**API Endpoint:**
```python
# src/01_web_app.py

@app.route("/api/emails/<int:email_id>/draft-reply", methods=["POST"])
@login_required
def generate_reply_draft(email_id):
    """Generiert KI-Antwort-Entwurf für Email"""
    data = request.get_json() or {}
    tone = data.get("tone", "formell")
    
    # Email laden & entschlüsseln
    email = db.session.query(models.RawEmail).filter_by(
        id=email_id, user_id=current_user.id
    ).first_or_404()
    
    master_key = session.get("master_key")
    sender = decrypt_email_sender(email.encrypted_sender, master_key)
    subject = decrypt_email_subject(email.encrypted_subject, master_key)
    body = decrypt_email_body(email.encrypted_body, master_key)
    
    # Thread-Context holen (Phase E!)
    from src.services import processing
    thread_context = processing.build_thread_context(db.session, email, master_key)
    
    # Draft generieren
    from src.services.reply_draft import ReplyDraftGenerator
    generator = ReplyDraftGenerator(get_active_ai_client())
    result = generator.generate_draft(
        sender=sender,
        subject=subject,
        body=body,
        tone=tone,
        thread_context=thread_context
    )
    
    return jsonify(result)
```

**Frontend:**
```javascript
// In email_detail.html

async function generateReplyDraft(tone = 'formell') {
    const emailId = {{ email.id }};
    const btn = document.getElementById('btn-draft-reply');
    btn.disabled = true;
    btn.innerHTML = '⏳ Generiere...';
    
    try {
        const response = await fetch(`/api/emails/${emailId}/draft-reply`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ tone })
        });
        
        const data = await response.json();
        
        // Modal mit Entwurf anzeigen
        document.getElementById('draft-text').value = data.draft;
        document.getElementById('draft-recipient').textContent = data.recipient;
        document.getElementById('draft-subject').textContent = data.suggested_subject;
        
        // mailto: Link
        const mailtoLink = `mailto:${data.recipient}?subject=${encodeURIComponent(data.suggested_subject)}&body=${encodeURIComponent(data.draft)}`;
        document.getElementById('btn-open-mail-client').href = mailtoLink;
        
        document.getElementById('draft-modal').classList.remove('hidden');
        
    } catch (error) {
        showToast('Fehler beim Generieren', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '✍️ Antwort-Entwurf generieren';
    }
}

function copyDraftToClipboard() {
    const text = document.getElementById('draft-text').value;
    navigator.clipboard.writeText(text);
    showToast('📋 In Zwischenablage kopiert!', 'success');
}
```

---

### **Phase G.2: Auto-Action Rules Engine (6-8h)** ⭐⭐⭐⭐⭐

**Problem:** Newsletter landen im Posteingang, User muss manuell archivieren/löschen

**Lösung:** IF/THEN Rules basierend auf KI-Klassifizierung

#### Rule Examples

```
┌─────────────────────────────────────────────────────────────┐
│  REGEL 1: Newsletter Auto-Archive                           │
│                                                             │
│  IF:                                                        │
│    spam_flag = true                                         │
│    AND dringlichkeit = 1                                    │
│    AND kategorie = "nur_information"                        │
│                                                             │
│  THEN:                                                      │
│    ✅ auto_archive = true                                   │
│    ✅ move_to_folder = "Archiv"                             │
│    ✅ mark_as_read = true                                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  REGEL 2: Dringend → Pin + Notify                          │
│                                                             │
│  IF:                                                        │
│    kategorie = "dringend"                                   │
│    AND wichtigkeit >= 2                                     │
│                                                             │
│  THEN:                                                      │
│    ✅ flag_as_important = true                              │
│    ✅ notify = true (Push-Benachrichtigung)                │
│    ✅ add_tag = "Dringend"                                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  REGEL 3: Sender-basiert                                    │
│                                                             │
│  IF:                                                        │
│    sender LIKE "%newsletter%"                               │
│    OR sender IN ["marketing@x.com", "promo@y.com"]         │
│                                                             │
│  THEN:                                                      │
│    ✅ move_to_folder = "Newsletter"                         │
│    ✅ add_tag = "Marketing"                                 │
└─────────────────────────────────────────────────────────────┘
```

#### DB Schema

```python
# src/02_models.py

class AutoActionRule(Base):
    """Auto-Action Rules für Emails (Phase G.2)"""
    
    __tablename__ = "auto_action_rules"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Rule Metadata
    name = Column(String(100), nullable=False)  # "Newsletter Auto-Archive"
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, index=True)
    priority = Column(Integer, default=100)  # Niedrigere Zahl = höhere Prio
    
    # Conditions (JSON)
    # {"spam_flag": true, "dringlichkeit": 1, "kategorie": "nur_information"}
    conditions = Column(JSON, nullable=False)
    
    # Actions (JSON)
    # {"auto_archive": true, "move_to_folder": "Archiv", "mark_as_read": true}
    actions = Column(JSON, nullable=False)
    
    # Stats
    times_triggered = Column(Integer, default=0)
    last_triggered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    user = relationship("User", backref="auto_action_rules")
```

#### Rule Engine

```python
# src/services/rule_engine.py (NEU)

class RuleEngine:
    """Evaluiert und führt Auto-Action Rules aus"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    def evaluate_rules(
        self, 
        user_id: int, 
        processed_email: models.ProcessedEmail,
        raw_email: models.RawEmail
    ) -> List[Dict]:
        """
        Evaluiert alle Rules für eine Email.
        
        Returns:
            Liste der ausgeführten Actions
        """
        rules = self.db.query(models.AutoActionRule).filter_by(
            user_id=user_id,
            enabled=True
        ).order_by(models.AutoActionRule.priority.asc()).all()
        
        executed_actions = []
        
        for rule in rules:
            if self._check_conditions(rule.conditions, processed_email, raw_email):
                logger.info(f"Rule '{rule.name}' triggered for email {raw_email.id}")
                
                # Actions ausführen
                actions_executed = self._execute_actions(
                    rule.actions, 
                    raw_email,
                    processed_email
                )
                
                executed_actions.extend(actions_executed)
                
                # Stats updaten
                rule.times_triggered += 1
                rule.last_triggered_at = datetime.now(UTC)
        
        self.db.commit()
        return executed_actions
    
    def _check_conditions(
        self, 
        conditions: dict, 
        processed: models.ProcessedEmail,
        raw: models.RawEmail
    ) -> bool:
        """Prüft ob alle Conditions erfüllt sind (AND-Verknüpfung)"""
        
        for key, expected_value in conditions.items():
            # Processed Email Fields
            if key == "spam_flag":
                if processed.spam_flag != expected_value:
                    return False
            
            elif key == "dringlichkeit":
                if processed.dringlichkeit != expected_value:
                    return False
            
            elif key == "wichtigkeit":
                op = conditions.get(f"{key}_op", "==")
                actual = processed.wichtigkeit
                if not self._compare(actual, op, expected_value):
                    return False
            
            elif key == "kategorie":
                if processed.kategorie_aktion != expected_value:
                    return False
            
            # Raw Email Fields
            elif key == "imap_folder":
                if raw.imap_folder != expected_value:
                    return False
            
            elif key == "sender_like":
                # Need to decrypt sender (TODO: Pass master_key!)
                # For now, skip encrypted fields in conditions
                pass
            
            elif key == "has_attachments":
                if raw.imap_has_attachments != expected_value:
                    return False
        
        return True  # Alle Conditions erfüllt
    
    def _execute_actions(
        self, 
        actions: dict, 
        raw_email: models.RawEmail,
        processed: models.ProcessedEmail
    ) -> List[str]:
        """Führt Actions aus"""
        executed = []
        
        # Archive
        if actions.get("auto_archive"):
            raw_email.deleted_at = datetime.now(UTC)
            executed.append("archived")
        
        # Move to Folder
        if actions.get("move_to_folder"):
            folder = actions["move_to_folder"]
            # TODO: IMAP MOVE ausführen
            raw_email.imap_folder = folder
            executed.append(f"moved_to_{folder}")
        
        # Mark as Read
        if actions.get("mark_as_read"):
            raw_email.imap_is_seen = True
            # TODO: IMAP Sync
            executed.append("marked_read")
        
        # Flag
        if actions.get("flag_as_important"):
            raw_email.imap_is_flagged = True
            # TODO: IMAP Sync
            executed.append("flagged")
        
        # Add Tag
        if actions.get("add_tag"):
            tag_name = actions["add_tag"]
            from src.services.tag_manager import assign_tag
            assign_tag(self.db, raw_email.user_id, raw_email.id, tag_name)
            executed.append(f"tag_{tag_name}")
        
        return executed
    
    def _compare(self, actual, op: str, expected) -> bool:
        """Vergleichsoperatoren"""
        if op == "==":
            return actual == expected
        elif op == ">=":
            return actual >= expected
        elif op == "<=":
            return actual <= expected
        elif op == ">":
            return actual > expected
        elif op == "<":
            return actual < expected
        elif op == "!=":
            return actual != expected
        return False
```

#### Integration in Processing

```python
# src/12_processing.py, in process_pending_raw_emails():

# NACH AI-Klassifizierung:
processed_email = models.ProcessedEmail(
    raw_email_id=raw_email.id,
    dringlichkeit=ai_result["dringlichkeit"],
    wichtigkeit=ai_result["wichtigkeit"],
    kategorie_aktion=ai_result["kategorie_aktion"],
    spam_flag=ai_result["spam_flag"],
    # ...
)
session.add(processed_email)
session.flush()  # Um ID zu bekommen

# NEU: Auto-Actions anwenden
from src.services.rule_engine import RuleEngine
rule_engine = RuleEngine(session)
actions_executed = rule_engine.evaluate_rules(
    user_id=user.id,
    processed_email=processed_email,
    raw_email=raw_email
)

if actions_executed:
    logger.info(f"Auto-Actions für Email {raw_email.id}: {actions_executed}")
```

#### UI for Rule Management

```python
# src/01_web_app.py

@app.route("/settings/rules")
@login_required
def rules_view():
    """Rule-Management UI"""
    rules = db.session.query(models.AutoActionRule).filter_by(
        user_id=current_user.id
    ).order_by(models.AutoActionRule.priority).all()
    
    return render_template("rules.html", rules=rules)


@app.route("/api/rules", methods=["POST"])
@login_required
def create_rule():
    """Neue Rule erstellen"""
    data = request.get_json()
    
    rule = models.AutoActionRule(
        user_id=current_user.id,
        name=data["name"],
        description=data.get("description"),
        conditions=data["conditions"],
        actions=data["actions"],
        priority=data.get("priority", 100)
    )
    
    db.session.add(rule)
    db.session.commit()
    
    return jsonify({"id": rule.id, "success": True})
```

---

## 📅 Phase H: Action Extraction - DETAILLIERT

### **Konzept: Unified Action Extractor**

**Idee:** Termine + Aufgaben sind beide "Actions" → Ein Service, eine DB-Tabelle!

```
┌─────────────────────────────────────────────────────────────┐
│  EMAIL: "Meeting am 15.01. um 14:00, bitte Vertrag prüfen" │
│                                                             │
│  [📋 Actions erkennen]                                      │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 📅 Erkannte Actions:                                │    │
│  │                                                     │    │
│  │ ☑️ [TERMIN] Meeting                                 │    │
│  │    📆 15.01.2026, 14:00 - 15:00                     │    │
│  │    ✏️ [Bearbeiten] [.ics Download]                  │    │
│  │                                                     │    │
│  │ ☑️ [AUFGABE] Vertrag prüfen                         │    │
│  │    📅 Fällig: 14.01.2026 (vor Meeting)             │    │
│  │    🔴 Priorität: Hoch                              │    │
│  │                                                     │    │
│  │ [✅ Actions übernehmen]                             │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

### **Phase H.1: Unified Action Extractor (5-7h)**

#### DB Schema (One Table for All)

```python
# src/02_models.py

class ActionItem(Base):
    """Action Items aus Emails - Termine + Aufgaben (Phase H)"""
    
    __tablename__ = "action_items"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    email_id = Column(Integer, ForeignKey("raw_emails.id"), nullable=True)
    
    # Action Type
    action_type = Column(String(20), nullable=False, index=True)
    # "calendar" = Termin, "todo" = Aufgabe, "deadline" = Frist
    
    # Zero-Knowledge: Verschlüsselte Daten
    encrypted_title = Column(Text, nullable=False)
    encrypted_description = Column(Text, nullable=True)
    encrypted_location = Column(Text, nullable=True)  # Für Termine
    
    # Zeitliche Daten
    due_date = Column(DateTime, nullable=True, index=True)
    due_time_start = Column(Time, nullable=True)  # Für Termine
    due_time_end = Column(Time, nullable=True)  # Für Termine
    
    # Status & Priorität
    is_done = Column(Boolean, default=False, index=True)
    priority = Column(Integer, default=2)  # 1=niedrig, 2=mittel, 3=hoch
    
    # KI-Metadaten
    ai_extracted = Column(Boolean, default=False)
    confidence = Column(Float, nullable=True)  # 0.0 - 1.0
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", backref="action_items")
    email = relationship("RawEmail", backref="action_items")
```

#### Service: Action Extractor

```python
# src/services/action_extractor.py (NEU)

ACTION_EXTRACTION_PROMPT = """
Analysiere diese E-Mail und extrahiere ALLE Termine und Aufgaben.

E-MAIL:
Von: {sender}
Betreff: {subject}
Inhalt: {body}

Antworte als JSON-Array. Für jeden Eintrag:
{{
  "type": "calendar|todo",
  "title": "Kurzer Titel (max 100 Zeichen)",
  "description": "Details",
  "date": "2026-01-15 oder null",
  "time_start": "14:00 oder null",
  "time_end": "15:00 oder null",
  "location": "Ort oder null",
  "priority": 1-3,
  "confidence": 0.9
}}

REGELN:
- type="calendar": Termine, Meetings, Veranstaltungen (feste Uhrzeit)
- type="todo": Aufgaben, Tasks, Deadlines (ohne feste Uhrzeit oder vor Termin)
- Wenn Deadline genannt: due_date setzen
- Wenn "bald", "diese Woche": date = +7 Tage
- Wenn "vor dem Meeting": date = Meeting-Datum minus 1 Tag
- priority: 1=niedrig, 2=mittel, 3=hoch (Dringlichkeit aus Kontext)
- confidence: 0.0-1.0 wie sicher du bist
- Leeres Array [] wenn keine Actions

NUR JSON-Array ausgeben, keine Erklärung!
""".strip()


class ActionExtractor:
    """Extrahiert Termine + Aufgaben aus Emails"""
    
    def __init__(self, db_session, ai_client):
        self.db = db_session
        self.ai_client = ai_client
    
    def extract_actions(
        self,
        sender: str,
        subject: str,
        body: str
    ) -> List[Dict[str, Any]]:
        """Extrahiert alle Actions (Termine + Aufgaben)"""
        
        prompt = ACTION_EXTRACTION_PROMPT.format(
            sender=sender,
            subject=subject,
            body=body[:2000]
        )
        
        try:
            response = self.ai_client._call_model([
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Extrahiere die Actions."}
            ])
            
            import json
            actions = json.loads(response) if isinstance(response, str) else []
            
            return [self._validate_action(a) for a in actions if self._validate_action(a)]
            
        except Exception as e:
            logger.warning(f"Action-Extraktion fehlgeschlagen: {e}")
            return []
    
    def _validate_action(self, action: dict) -> Optional[dict]:
        """Validiert Action-Dict"""
        if not action.get('title') or action.get('type') not in ['calendar', 'todo']:
            return None
        
        result = {
            'type': action['type'],
            'title': action['title'][:100],
            'description': action.get('description', '')[:500],
            'location': action.get('location', '')[:200],
            'priority': max(1, min(3, int(action.get('priority', 2)))),
            'confidence': float(action.get('confidence', 0.5)),
            'due_date': None,
            'time_start': None,
            'time_end': None
        }
        
        # Parse Datum
        if action.get('date'):
            try:
                result['due_date'] = datetime.strptime(
                    action['date'], '%Y-%m-%d'
                ).date()
            except:
                pass
        
        # Parse Zeiten (nur für Termine)
        if action['type'] == 'calendar':
            if action.get('time_start'):
                try:
                    result['time_start'] = datetime.strptime(
                        action['time_start'], '%H:%M'
                    ).time()
                except:
                    pass
            
            if action.get('time_end'):
                try:
                    result['time_end'] = datetime.strptime(
                        action['time_end'], '%H:%M'
                    ).time()
                except:
                    # Default: +1 Stunde
                    if result['time_start']:
                        start_dt = datetime.combine(
                            result['due_date'] or datetime.now().date(),
                            result['time_start']
                        )
                        end_dt = start_dt + timedelta(hours=1)
                        result['time_end'] = end_dt.time()
        
        return result
    
    def create_action_item(
        self,
        user_id: int,
        action_dict: dict,
        master_key: str,
        email_id: Optional[int] = None
    ) -> models.ActionItem:
        """Erstellt ActionItem in DB (verschlüsselt)"""
        
        encrypted_title = encryption.EncryptionManager.encrypt_data(
            action_dict['title'], master_key
        )
        encrypted_description = None
        if action_dict.get('description'):
            encrypted_description = encryption.EncryptionManager.encrypt_data(
                action_dict['description'], master_key
            )
        encrypted_location = None
        if action_dict.get('location'):
            encrypted_location = encryption.EncryptionManager.encrypt_data(
                action_dict['location'], master_key
            )
        
        action_item = models.ActionItem(
            user_id=user_id,
            email_id=email_id,
            action_type=action_dict['type'],
            encrypted_title=encrypted_title,
            encrypted_description=encrypted_description,
            encrypted_location=encrypted_location,
            due_date=action_dict.get('due_date'),
            due_time_start=action_dict.get('time_start'),
            due_time_end=action_dict.get('time_end'),
            priority=action_dict['priority'],
            ai_extracted=True,
            confidence=action_dict['confidence']
        )
        
        self.db.add(action_item)
        self.db.commit()
        
        return action_item
    
    def generate_ical(self, action_item: models.ActionItem, master_key: str) -> str:
        """Generiert .ics für Termin"""
        if action_item.action_type != 'calendar':
            raise ValueError("Nur Termine können als .ics exportiert werden")
        
        title = encryption.EncryptionManager.decrypt_data(
            action_item.encrypted_title, master_key
        )
        description = ""
        if action_item.encrypted_description:
            description = encryption.EncryptionManager.decrypt_data(
                action_item.encrypted_description, master_key
            )
        location = ""
        if action_item.encrypted_location:
            location = encryption.EncryptionManager.decrypt_data(
                action_item.encrypted_location, master_key
            )
        
        # Datetime kombinieren
        dt_start = datetime.combine(action_item.due_date, action_item.due_time_start)
        dt_end = datetime.combine(action_item.due_date, action_item.due_time_end)
        
        import uuid
        uid = str(uuid.uuid4())
        
        ical = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//KI-Mail-Helper//DE",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{dt_start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{dt_end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{self._escape_ical(title)}",
        ]
        
        if location:
            ical.append(f"LOCATION:{self._escape_ical(location)}")
        
        if description:
            ical.append(f"DESCRIPTION:{self._escape_ical(description)}")
        
        ical.extend([
            "END:VEVENT",
            "END:VCALENDAR"
        ])
        
        return "\r\n".join(ical)
    
    def _escape_ical(self, text: str) -> str:
        """Escaped Text für iCal-Format"""
        return (text
            .replace("\\", "\\\\")
            .replace(",", "\\,")
            .replace(";", "\\;")
            .replace("\n", "\\n")
        )
```

---

### **Phase H.2: Action Items UI & Management (3-5h)**

#### API Endpoints

```python
# src/01_web_app.py

@app.route("/actions")
@login_required
def actions_view():
    """Action Items Liste (Termine + Aufgaben)"""
    return render_template("actions.html")


@app.route("/api/actions", methods=["GET"])
@login_required
def get_actions():
    """GET /api/actions?type=calendar&done=false"""
    action_type = request.args.get("type")  # calendar, todo, or None (all)
    include_done = request.args.get("done", "false").lower() == "true"
    
    master_key = session.get("master_key")
    
    query = db.session.query(models.ActionItem).filter_by(user_id=current_user.id)
    
    if action_type:
        query = query.filter_by(action_type=action_type)
    
    if not include_done:
        query = query.filter_by(is_done=False)
    
    actions = query.order_by(
        models.ActionItem.is_done.asc(),
        models.ActionItem.due_date.asc().nullslast(),
        models.ActionItem.priority.desc()
    ).all()
    
    # Decrypt
    result = []
    for action in actions:
        try:
            title = encryption.EncryptionManager.decrypt_data(
                action.encrypted_title, master_key
            )
            description = ""
            if action.encrypted_description:
                description = encryption.EncryptionManager.decrypt_data(
                    action.encrypted_description, master_key
                )
            location = ""
            if action.encrypted_location:
                location = encryption.EncryptionManager.decrypt_data(
                    action.encrypted_location, master_key
                )
            
            result.append({
                'id': action.id,
                'type': action.action_type,
                'title': title,
                'description': description,
                'location': location,
                'due_date': action.due_date.isoformat() if action.due_date else None,
                'time_start': action.due_time_start.strftime('%H:%M') if action.due_time_start else None,
                'time_end': action.due_time_end.strftime('%H:%M') if action.due_time_end else None,
                'priority': action.priority,
                'is_done': action.is_done,
                'email_id': action.email_id,
                'ai_extracted': action.ai_extracted,
                'created_at': action.created_at.isoformat()
            })
        except Exception as e:
            logger.warning(f"Action {action.id} decryption failed: {e}")
    
    return jsonify({"actions": result})


@app.route("/api/emails/<int:email_id>/extract-actions", methods=["POST"])
@login_required
def extract_actions_from_email(email_id):
    """POST /api/emails/123/extract-actions"""
    email = db.session.query(models.RawEmail).filter_by(
        id=email_id, user_id=current_user.id
    ).first_or_404()
    
    master_key = session.get("master_key")
    sender = decrypt_email_sender(email.encrypted_sender, master_key)
    subject = decrypt_email_subject(email.encrypted_subject, master_key)
    body = decrypt_email_body(email.encrypted_body, master_key)
    
    from src.services.action_extractor import ActionExtractor
    extractor = ActionExtractor(db.session, get_active_ai_client())
    actions = extractor.extract_actions(sender, subject, body)
    
    return jsonify({
        "actions": actions,
        "email_id": email_id,
        "email_subject": subject
    })


@app.route("/api/actions/<int:action_id>/mark-done", methods=["POST"])
@login_required
def mark_action_done(action_id):
    """POST /api/actions/123/mark-done"""
    action = db.session.query(models.ActionItem).filter_by(
        id=action_id, user_id=current_user.id
    ).first_or_404()
    
    action.is_done = True
    action.completed_at = datetime.now(UTC)
    db.session.commit()
    
    return jsonify({"success": True})


@app.route("/api/actions/<int:action_id>/ical", methods=["GET"])
@login_required
def download_action_ical(action_id):
    """GET /api/actions/123/ical → Download .ics"""
    action = db.session.query(models.ActionItem).filter_by(
        id=action_id, user_id=current_user.id, action_type='calendar'
    ).first_or_404()
    
    master_key = session.get("master_key")
    
    from src.services.action_extractor import ActionExtractor
    extractor = ActionExtractor(db.session, get_active_ai_client())
    ical_content = extractor.generate_ical(action, master_key)
    
    response = make_response(ical_content)
    response.headers['Content-Type'] = 'text/calendar; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=termin.ics'
    
    return response
```

#### Frontend UI

```html
<!-- templates/actions.html -->

<div class="actions-container">
    <h2>📅 Termine & 📋 Aufgaben</h2>
    
    <!-- Filter -->
    <div class="action-filter">
        <button onclick="filterActions('all')">Alle</button>
        <button onclick="filterActions('calendar')">📅 Nur Termine</button>
        <button onclick="filterActions('todo')">📋 Nur Aufgaben</button>
        <label>
            <input type="checkbox" id="show-done"> Erledigte anzeigen
        </label>
    </div>
    
    <!-- Liste -->
    <div id="actions-list">
        <!-- Dynamisch gefüllt via JavaScript -->
    </div>
</div>

<script>
async function loadActions(type = 'all', includeDone = false) {
    const params = new URLSearchParams({
        done: includeDone
    });
    if (type !== 'all') {
        params.append('type', type);
    }
    
    const response = await fetch(`/api/actions?${params}`);
    const data = await response.json();
    
    displayActions(data.actions);
}

function displayActions(actions) {
    const list = document.getElementById('actions-list');
    list.innerHTML = '';
    
    // Gruppiere nach Datum
    const grouped = groupByDate(actions);
    
    for (const [date, items] of Object.entries(grouped)) {
        const section = document.createElement('div');
        section.className = 'action-section';
        section.innerHTML = `<h3>${formatDate(date)}</h3>`;
        
        items.forEach(action => {
            const card = createActionCard(action);
            section.appendChild(card);
        });
        
        list.appendChild(section);
    }
}

function createActionCard(action) {
    const icon = action.type === 'calendar' ? '📅' : '📋';
    const timeStr = action.time_start ? ` ${action.time_start}-${action.time_end}` : '';
    
    const card = document.createElement('div');
    card.className = `action-card priority-${action.priority} ${action.is_done ? 'done' : ''}`;
    card.innerHTML = `
        <div class="action-header">
            <span class="action-icon">${icon}</span>
            <strong>${escapeHtml(action.title)}</strong>
            ${action.location ? `<span class="location">📍 ${escapeHtml(action.location)}</span>` : ''}
        </div>
        <div class="action-time">${timeStr}</div>
        ${action.description ? `<div class="action-desc">${escapeHtml(action.description)}</div>` : ''}
        <div class="action-actions">
            ${!action.is_done ? `<button onclick="markDone(${action.id})">✅ Erledigt</button>` : ''}
            ${action.type === 'calendar' ? `<button onclick="downloadIcal(${action.id})">📥 .ics</button>` : ''}
            ${action.email_id ? `<a href="/email/${action.email_id}">📧 Zur Email</a>` : ''}
        </div>
    `;
    return card;
}

async function markDone(actionId) {
    await fetch(`/api/actions/${actionId}/mark-done`, {
        method: 'POST',
        headers: {'X-CSRFToken': getCsrfToken()}
    });
    loadActions();  // Refresh
}

function downloadIcal(actionId) {
    window.location.href = `/api/actions/${actionId}/ical`;
}
</script>
```

---

## 🔧 Phase I: Productivity Features - DETAILLIERT

### **Phase I.1: Thread Summarization (3-4h)** ⭐⭐⭐

**Use Case:** Lange Threads (10+ Emails) sind schwer zu überblicken

```python
# src/services/thread_summarizer.py (NEU)

THREAD_SUMMARY_PROMPT = """
Fasse diese Email-Konversation zusammen:

{thread_emails}

Erstelle eine strukturierte Zusammenfassung mit:
1. HAUPTTHEMA (1 Satz)
2. WICHTIGSTE PUNKTE (Stichpunkte)
3. ENTSCHEIDUNGEN/ERGEBNISSE (falls vorhanden)
4. OFFENE PUNKTE (falls vorhanden)
5. NÄCHSTE SCHRITTE (falls vorhanden)

Halte dich kurz (max. 200 Wörter).
""".strip()


class ThreadSummarizer:
    def summarize_thread(self, thread_id: str, user_id: int, master_key: str) -> dict:
        """Fasst Thread zusammen"""
        emails = self._get_thread_emails(thread_id, user_id, master_key)
        
        if len(emails) < 3:
            return {"error": "Thread zu kurz für Zusammenfassung"}
        
        # Format für AI
        context = self._format_thread_for_ai(emails)
        
        # AI call
        summary = self.ai_client._call_model([
            {"role": "system", "content": THREAD_SUMMARY_PROMPT.format(thread_emails=context)},
            {"role": "user", "content": "Fasse zusammen."}
        ])
        
        return {
            "summary": summary,
            "email_count": len(emails),
            "participants": list(set(e['sender'] for e in emails)),
            "date_range": f"{emails[0]['date']} - {emails[-1]['date']}"
        }
```

---

### **Phase I.2: Bulk Email Operations (15-20h)** ⭐⭐⭐⭐

**Already documented in Phase H section of original roadmap.**

See lines 767-806 for full implementation details.

---

### **Phase I.3: Enhanced Conversation UI (2-4h)** ⭐⭐⭐

- Thread view mit kollapierbaren Emails
- Visual indicators (read/unread, flagged)
- Quick actions (reply, forward, delete)
- Thread-Navigation (vorherige/nächste)

---

## ✉️ Phase J: SMTP Integration - DETAILLIERT

### **Phase J.1: SMTP Send & Threading (6-8h)** ⭐⭐⭐

**Note:** 80% der User reichen Reply Draft + Copy. SMTP nur bei explizitem Bedarf!

**Features:**
- Antworten direkt aus App senden
- In-Reply-To Header für korrekte Threading
- SMTP-Konfiguration pro Account
- Sent-Items Synchronisierung

```python
# src/services/smtp_sender.py (NEU)

class SMTPSender:
    def send_reply(
        self,
        account: models.MailAccount,
        original_email: models.RawEmail,
        reply_text: str,
        master_key: str
    ) -> bool:
        """Sendet Antwort via SMTP"""
        
        # Decrypt SMTP credentials
        smtp_server = decrypt(account.smtp_server, master_key)
        smtp_email = decrypt(account.email_address, master_key)
        smtp_password = decrypt(account.email_password, master_key)
        
        # Original Email Details
        to_address = decrypt(original_email.encrypted_sender, master_key)
        subject = decrypt(original_email.encrypted_subject, master_key)
        message_id = original_email.message_id
        
        # Build Reply
        msg = MIMEMultipart()
        msg['From'] = smtp_email
        msg['To'] = to_address
        msg['Subject'] = f"Re: {subject}" if not subject.startswith("Re:") else subject
        msg['In-Reply-To'] = message_id
        msg['References'] = message_id
        
        msg.attach(MIMEText(reply_text, 'plain', 'utf-8'))
        
        # Send via SMTP
        with smtplib.SMTP_SSL(smtp_server, 465) as server:
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        
        return True
```

---

## 📊 Zusammenfassung & Next Steps

### ✅ Was bisher geschafft wurde (Phase A-E + 14)

- **Phase A:** Filter auf /liste (4-6h) ✅
- **Phase B:** Server DELETE/FLAG/READ (3-4h) ✅
- **Phase C:** MOVE + Multi-Folder FULL SYNC (8-11h) ✅
- **Phase D:** ServiceToken Refactor + InitialSync (2-3h) ✅
- **Phase E:** KI Thread-Context (4h) ✅
- **Phase 14 (a-g):** RFC UIDs + IMAPClient (9-11h) ✅

**Total:** 39-49 Stunden ✅ COMPLETE

---

### 🚀 Empfohlene Implementierungs-Reihenfolge (Phase F-J)

#### **Sprint 1: Semantic Intelligence (12-18h)** 🔥 **START HERE!**

| Feature | Aufwand | Warum zuerst? |
|---------|---------|--------------|
| F.1 Semantic Search | 8-12h | Killer-Feature, Infrastructure ready, größter User-Value |
| F.2 Smart Tag Suggestions | 2-3h | 80% fertig, nutzt Tag-Embeddings |
| F.3 Email Similarity | 2-3h | Synergien mit F.1 |

**Impact:** Nutzer findet Mails ohne exakte Keywords → Game-Changer!

---

#### **Sprint 2: AI Action Engine (10-14h)** 🔥 **HIGH VALUE!**

| Feature | Aufwand | Warum wichtig? |
|---------|---------|---------------|
| G.1 Reply Draft Generator | 4-6h | Spart massiv Zeit, mit Thread-Context |
| G.2 Auto-Action Rules | 6-8h | Löst Newsletter-Problem endlich! |

**Impact:** Automation + Draft-Generator → Newsletter weg, Antworten schnell!

---

#### **Sprint 3: Action Extraction (8-12h)** ⭐⭐⭐⭐

| Feature | Aufwand | Notes |
|---------|---------|-------|
| H.1 Unified Action Extractor | 5-7h | Termine + Aufgaben in einem Service |
| H.2 Action Items UI | 3-5h | Management-Interface |

**Impact:** Termine & ToDos automatisch aus Mails extrahiert!

---

#### **Sprint 4: Productivity (Optional, 20-28h)**

| Feature | Aufwand | Priority |
|---------|---------|----------|
| I.1 Thread Summarization | 3-4h | Medium |
| I.2 Bulk Operations | 15-20h | High (aber aufwändig) |
| I.3 Enhanced Conversation UI | 2-4h | Low |

**Impact:** Produktivität, aber nicht kritisch

---

#### **Sprint 5: SMTP (Optional, 6-8h)**

| Feature | Aufwand | Notes |
|---------|---------|-------|
| J.1 SMTP Send | 6-8h | Reply Draft reicht für 80% der Nutzer |

**Impact:** Nice-to-have, aber Reply Draft + Copy ist meist genug

---

### 🎯 Kritische Entscheidungspunkte

#### **Entscheidung 1: Embedding-Generierung**

✅ **RICHTIG:** Beim IMAP Fetch (14_background_jobs.py), **BEVOR** verschlüsselt wird
- Klartext ist da, kein master_key nötig für Embedding
- Effizienter (kein zweiter Pass)

❌ **FALSCH:** Beim Processing mit Decrypt
- Unnötiger Decrypt-Overhead
- master_key nötig

#### **Entscheidung 2: Action Items - Eine Tabelle oder Zwei?**

✅ **EMPFOHLEN:** Eine Tabelle (`ActionItem`) mit `type` Feld
- Weniger Code-Duplikation
- Gemeinsame UI/API
- Synergien (z.B. "Aufgabe vor Termin")

❌ **Alternative:** Zwei Tabellen (`CalendarEvent`, `TodoItem`)
- Mehr Flexibilität
- Aber mehr Code

#### **Entscheidung 3: Auto-Actions - Wann aktivieren?**

✅ **EMPFOHLEN:** Opt-In per User
- User erstellt Rules manuell
- Sicher, keine unerwarteten Aktionen

⚠️ **Alternative:** Default-Rules
- Newsletter auto-archive by default
- Risiko: False-Positives

---

### 📁 File-Struktur nach Phase F-J

```
src/
├── 01_web_app.py                    # +150 lines (API Endpoints)
├── 02_models.py                     # +60 lines (2 neue Tabellen)
├── 03_ai_client.py                  # Unverändert (schon alles da!)
├── 12_processing.py                 # +50 lines (Rule Engine Integration)
├── 14_background_jobs.py            # +80 lines (Embedding Generation)
├── services/
│   ├── action_extractor.py          # NEU (350 lines)
│   ├── reply_draft.py               # NEU (200 lines)
│   ├── rule_engine.py               # NEU (300 lines)
│   ├── semantic_search.py           # NEU (400 lines)
│   ├── smtp_sender.py               # NEU (150 lines) - Optional
│   ├── tag_manager.py               # +50 lines (Tag Auto-Suggest)
│   └── thread_summarizer.py         # NEU (150 lines) - Optional
├── migrations/versions/
│   ├── ph15_semantic_search.py      # NEU (Migration)
│   ├── ph16_auto_actions.py         # NEU (Migration)
│   └── ph17_action_items.py         # NEU (Migration)
└── scripts/
    └── generate_embeddings.py       # NEU (Backfill Script)

templates/
├── actions.html                     # NEU (Action Items UI)
├── rules.html                       # NEU (Rule Management)
├── email_detail.html                # +100 lines (Reply Draft Button)
└── liste.html                       # +50 lines (Semantic Search Toggle)

**Total New Files:** 10  
**Total New Lines:** ~2500  
**Modified Files:** 6  
**Modified Lines:** ~430
```

---

### ⚠️ Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|-------------------|------------|
| Embeddings zu groß für SQLite | Niedrig | 1.5KB/Email → bei 10k Emails nur 15MB |
| Ollama nicht verfügbar | Mittel | Fallback: Keine Embeddings, App läuft weiter |
| Auto-Actions löschen wichtige Mails | Mittel | Opt-In, User muss Rules aktivieren |
| Performance bei Similarity Search | Mittel | Bei >10k Emails: FAISS Index erwägen |
| Zero-Knowledge durch Embeddings gefährdet? | Niedrig | Embeddings sind NICHT reversibel |

---

### 🧪 Testing-Strategie

#### **Phase F (Semantic Search):**
1. Unit-Test: Embedding-Generierung
2. Integration: Search mit 100 Test-Emails
3. Performance: 1000 Emails, Similarity-Berechnung < 100ms
4. Zero-Knowledge: Embeddings nicht zu Klartext dekodierbar

#### **Phase G (AI Actions):**
1. Unit-Test: Reply Draft mit verschiedenen Tönen
2. Integration: Rule Engine mit Test-Rules
3. E2E: Newsletter → Auto-Archive → Verify

#### **Phase H (Action Extraction):**
1. Unit-Test: Action-Extraktion mit Mock-Emails
2. Integration: .ics Generation
3. E2E: Email mit Termin → Extrahieren → Kalender-Import

---

### 📈 Success Metrics

| Phase | Key Metric | Target |
|-------|-----------|--------|
| F.1 | Search Precision@5 | >80% relevante Ergebnisse |
| F.2 | Tag Auto-Assign Rate | >60% korrekt |
| G.1 | Draft Acceptance Rate | >70% nutzen Draft |
| G.2 | Newsletter Auto-Archive | >90% korrekt |
| H.1 | Action Extraction Accuracy | >85% |

---

## 🎓 Lessons Learned & Best Practices

### ✅ Was gut funktioniert hat (A-E + 14)

1. **Zero-Knowledge bleibt gewahrt:** Embeddings/Actions/Rules funktionieren mit Encryption
2. **Schrittweise Migration:** Alembic + Backups = keine Datenverluste
3. **Thread-Context:** Massiv bessere AI-Klassifizierung
4. **IMAPClient:** 40% weniger Code, 100% Reliability

### 🔧 Was wir in Phase F-J anders machen

1. **Embedding beim Fetch:** NICHT beim Processing (effizienter!)
2. **Unified Services:** Action Extractor statt separate Calendar+Todo
3. **Opt-In Features:** Auto-Actions nur mit User-Consent
4. **Performance Testing:** Vor Rollout mit 1000+ Emails testen

---

## 📞 Support & Documentation

**Neue Docs erstellen:**
- `/doc/erledigt/PHASE_F_SEMANTIC_SEARCH_COMPLETE.md` (nach Fertigstellung)
- `/doc/erledigt/PHASE_G_AI_ACTIONS_COMPLETE.md` (nach Fertigstellung)
- `/doc/erledigt/PHASE_H_ACTION_EXTRACTION_COMPLETE.md` (nach Fertigstellung)

**User-Dokumentation:**
- README erweitern mit Semantic Search Beispielen
- Settings-Seite: "Auto-Actions aktivieren" Tutorial
- Action Items: Kalender-Export Anleitung

---

## 🚀 Ready to Start!

**Nächster Schritt:** Phase F.1 - Semantic Search implementieren! 🔍

1. Migration erstellen
2. Model erweitern  
3. Service implementieren
4. Background Jobs patchen (Embedding beim Fetch!)
5. API Endpoints
6. Frontend UI
7. Testing
8. Backfill bestehender Emails

**Geschätzter Aufwand:** 8-12h für vollständige Implementation

---

**END OF ROADMAP UPDATE**

---

## 🔗 Phase I: Bulk Email Operations (Integriert aus Task 5)

**Status:** 🟢 TODO | **Effort:** 15-20h | **Priority:** High (Produktivität)

### Kernfunktionalität

```
User selekt mehrere Mails per Checkbox
   ↓
Toolbar zeigt "X Mails ausgewählt"
   ↓
User wählt Aktion (Delete, Move, Flag, Read)
   ↓
Bestätigungs-Dialog (besonders für destruktive Aktionen)
   ↓
Server führt Batch-Operation durch
   ↓
Progress-Indicator zeigt Fortschritt
   ↓
Feedback: "5/5 erfolgreich" oder "4/5 erfolgreich, 1 Fehler"
```

### Implementation Breakdown (15-20h)

| Task | Aufwand | Details |
|------|---------|---------|
| Multi-Select UI | 3-4h | Checkboxen pro Mail, Select-All, Bulk-Toolbar |
| Batch Actions | 4-5h | DELETE, MOVE, FLAG, READ für multiple UIDs |
| Confirmation Dialogs | 2-3h | Destruktive Aktionen bestätigen (DELETE) |
| Progress Tracking | 3-4h | Server-Progress + Frontend-Animation |
| Error Handling | 2-3h | Partial failures, Retry-Logic, Error-Reports |
| Testing | 1-2h | Unit + Integration Tests für Batch-Ops |

### Expected Scope (aus Task 5 Analysis)

- ✅ Checkboxen für jede E-Mail in der Liste
- ✅ Individual + "Select All" / "Deselect All" Toggle
- ✅ Bulk-Action Toolbar mit Aktion-Dropdown
- ✅ Actions: Archive, Spam, Delete, Mark Read/Unread, Flag/Unflag
- ✅ Mandatory confirmation für destruktive Aktionen
- ✅ Partial failure handling (continue, not abort)
- ✅ Network error retry logic (3 attempts with backoff)

---

## 📍 Phase 14 Forward Reference (Zu planen nach Phase 13)

**Status:** ↪️ TODO | **Target Timeline:** Nach Phase 13 Completion (A-H)  
**Purpose:** Infrastructure, Monitoring, Multi-Account Orchestration

### Items aus Task 6: Pipeline Integration (60-80h Total)

#### 1. **Pipeline Broker & Job Orchestration** (15-20h)

```python
# Zentralisierte Job-Queue Verwaltung
┌─────────────────────────────────┐
│  Pipeline Broker (NEW)           │
├─────────────────────────────────┤
│ ├─ Job Queue Management          │
│ ├─ Performance Metrics           │
│ ├─ Error Recovery                │
│ ├─ Account State Management      │
│ └─ Progress Tracking             │
└────┬──────────────┬──────────────┘
     │              │
     ▼              ▼
┌──────────────┐ ┌─────────────────┐
│ Diagnostics  │ │ Mail-Fetcher    │
│ (Tests)      │ │ (Production)    │
└──────────────┘ └─────────────────┘
```

**Anforderungen:**
- Zentrale Queue für alle Mail-Fetch-Jobs
- Job-Lifecycle Management (queued → running → completed/failed)
- Retry-Logic mit Exponential Backoff
- State persistence für Crash-Recovery

#### 2. **Multi-Account Orchestration** (10-15h)

```
Current: Accounts sequenziell (GMX: 5s + Gmail: 8s + Outlook: 3s = 16s)
Desired: Parallelisiert mit Fehlerbehandlung (max 8s, mit Fallback)
```

**Anforderungen:**
- Parallele Job-Submission für multiple Accounts
- Graceful failure handling (einzelner Account-Fehler stoppt nicht alles)
- Queue-Priority für wichtige Accounts
- Load-Balancing (nicht alle gleichzeitig starten)

#### 3. **Performance Monitoring & Metrics** (10-15h)

**Zu tracken:**
- Fetch-Dauer pro Account (min/max/avg)
- Mail-Durchsatz (mails/sec)
- Error-Rate pro Account & Provider
- Queue-Backlog & Processing-Time
- Resource-Usage (Memory, CPU, I/O)

**UI:**
- Diagnostics Dashboard mit Performance-Charts
- Alert-System für anomale Performance
- Historical Metrics für Trend-Analysis

#### 4. **Error Recovery & Intelligent Retry** (8-12h)

**Fehlertypen & Recovery-Strategien:**

| Fehler | Strategy | Max Retries |
|--------|----------|-------------|
| Network Timeout | Exponential Backoff | 3 |
| IMAP Protocol Error | Reconnect + Retry | 2 |
| Authentication Failed | Fail (user action needed) | 0 |
| Rate Limited | Delay 5s then retry | 5 |
| Server Down | Exponential Backoff | 5 |

**Anforderungen:**
- Automatische Retry-Logic mit Jitter
- Dead-Letter Queue für permanently failed jobs
- Manual Retry UI für failed Accounts
- Detailed Error-Logging für Debugging

#### 5. **Job Queue System** (8-10h)

```python
# Potential: Redis/RQ or SQLAlchemy-based Queue
class JobQueue:
    def enqueue(job: FetchJob) -> str:
        # Speichern + Event-Tracking
        pass
    
    def dequeue() -> FetchJob:
        # Höchste Priorität zuerst
        pass
    
    def update_status(job_id: str, status: str, meta: dict):
        # Progress-Tracking
        pass
    
    def get_metrics() -> dict:
        # Performance + Queue Stats
        pass
```

**Anforderungen:**
- FIFO Queue mit Prioritäts-Support
- Atomic Status-Updates
- Dead-Letter Queue für failed Jobs
- Persistent Storage (SQLite oder Redis)

---

## 📋 Phase 14 Planning Notes

**To be determined during Phase 13:**
- Welche Monitoring-Metriken sind am wertvollsten?
- Redis vs SQLAlchemy für Job-Queue? (Komplexität vs Features)
- Brauchen wir Load-Balancing zwischen multiple Worker-Processes?
- Welche SLA-Targets für Fetch-Performance?

**New Requirements (werden während Phase 13 gesammelt):**
- [ ] TBD - Placeholder für neue Items

---

## 🔗 Beziehung zu bestehenden Tasks

### Task 5: Bulk Email Operations
- **Integration:** Phase I.2 - Vollständig aufgenommen in Phase 13 Roadmap
- **Status:** ✅ Geplant als Phase I.2 (15-20h)
- **Priority:** Medium (nach Phase F+G)

### Task 6: Pipeline Integration  
- **Integration:** Phase 14 Forward Reference - Aufgeschoben nach Phase 13 Completion
- **Status:** ↪️ Basis für Phase 14 Roadmap (60-80h)
- **Priority:** Low (Infrastructure-Focus, nicht User-Feature)

---

## 🎯 QUICK REFERENCE: Was machen in welcher Reihenfolge?

### **Woche 1-2: Phase F - Semantic Intelligence (12-18h)** 🔥

**Start here!** Größter User-Value, Infrastructure ready.

```bash
# Day 1-2: Semantic Search (8-12h)
1. Migration: ph15_semantic_search.py
2. Model: RawEmail.email_embedding
3. Service: src/semantic_search.py
4. Background: Embedding in _persist_raw_emails() VOR encrypt!
5. API: /api/search/semantic
6. Frontend: Search Toggle

# Day 3: Smart Tag Auto-Suggestions (2-3h)
7. Erweitere tag_manager.py
8. Integration in processing.py

# Day 3-4: Email Similarity (2-3h)
9. API: /api/emails/<id>/similar
10. Frontend: "Ähnliche Mails" Button
```

---

### **Woche 3: Phase G - AI Action Engine (10-14h)** 🔥

**High Value:** Automation + Reply Draft = massive Zeitersparnis!

```bash
# Day 1-2: Reply Draft Generator (4-6h)
1. Service: src/services/reply_draft.py
2. API: POST /api/emails/<id>/draft-reply
3. Frontend: Modal mit Ton-Auswahl

# Day 3-4: Auto-Action Rules (6-8h)
4. Migration: ph16_auto_actions.py
5. Model: AutoActionRule
6. Service: src/services/rule_engine.py
7. Integration: processing.py calls rule_engine
8. API: /api/rules (CRUD)
9. Frontend: Rule-Builder UI
```

---

### **Woche 4: Phase H - Action Extraction (8-12h)** ⭐

**Practical:** Termine + Aufgaben automatisch extrahieren.

```bash
# Day 1-2: Unified Action Extractor (5-7h)
1. Migration: ph17_action_items.py
2. Model: ActionItem
3. Service: src/services/action_extractor.py
4. API: POST /api/emails/<id>/extract-actions

# Day 3: Action Items UI (3-5h)
5. Template: actions.html
6. API: GET /api/actions
7. API: GET /api/actions/<id>/ical
8. Frontend: Actions-Liste mit Filter
```

---

### **Optional: Phase I+J (26-36h)**

Nur wenn Phase F-H fertig und Zeit vorhanden!

---

## 🛠️ Development Workflow

### **Vor jeder Phase:**
```bash
# 1. Backup
cp emails.db emails.db.backup_phase_X

# 2. Alembic Check
alembic current
alembic history

# 3. Test Environment
# Teste mit Test-User, nicht Production!
```

### **Nach jeder Phase:**
```bash
# 1. Migration anwenden
alembic upgrade head

# 2. Verify Schema
sqlite3 emails.db ".schema TABLE_NAME"

# 3. Smoke Test
# - Login
# - Mail fetch
# - Neue Feature testen
# - Keine Errors in logs

# 4. Git Commit
git add .
git commit -m "Phase X: FEATURE_NAME - COMPLETE"

# 5. Documentation
# Erstelle doc/erledigt/PHASE_X_COMPLETE.md
```

---

## 📚 Code-Beispiele verfügbar in:

`/home/thomas/projects/KI-Mail-Helper/doc/semantic_search_examples/`

- ✅ `PHASE_15_SEMANTIC_SEARCH_CHECKLIST.md` - Schritt-für-Schritt Anleitung
- ✅ `PATCH_background_jobs.py` - Embedding beim Fetch
- ✅ `PATCH_models_semantic_search.py` - Model-Erweiterung
- ✅ `semantic_search.py` - Kompletter Service
- ✅ `ph15_semantic_search.py` - Migration
- ✅ `generate_embeddings.py` - Backfill-Script

**Vorsicht:** Code nicht 1:1 übernehmen, aktuelle Versionen der Files berücksichtigen!

---

## ⚠️ CRITICAL: Do NOT Break Existing Features!

### **Before ANY change:**
1. ✅ Backup DB
2. ✅ Read current file version (nicht nur Beispiel-Code!)
3. ✅ Test auf Test-User, nicht Production
4. ✅ Verify keine Regression (Login, Fetch, View funktionieren)

### **Zero-Knowledge Principle:**
- ✅ Embeddings sind OK (nicht reversibel)
- ✅ Action Titles müssen encrypted sein
- ✅ Reply Drafts temporär (nicht in DB speichern!)
- ❌ NIEMALS Klartext in Logs ohne Masking!

---

## 🎓 Final Thoughts

**Diese Roadmap ist:**
- ✅ Use-Case-orientiert (nicht Feature-Liste)
- ✅ Priorisiert nach Impact/Aufwand
- ✅ Mit konkreten Code-Beispielen
- ✅ Zero-Knowledge compliant
- ✅ Schrittweise testbar

**Start with Phase F (Semantic Search)** - das ist der Game-Changer! 🚀

---

**END OF STRATEGIC ROADMAP - READY TO IMPLEMENT!**
