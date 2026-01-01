# 🎯 Phase 13: Strategic Analysis & Implementation Roadmap

**Strategic Planning Document - Was haben wir, was brauchen wir?**

**Status:** ✅ Phase A, B, C, D Abgeschlossen | ✅ Phase 14 Complete | 🟡 Phase E-H In Planung  
**Created:** 31. Dezember 2025  
**Updated:** 01. Januar 2026  
**Recent:** Phase 14 Complete - RFC-konformer Unique Key (folder, uidvalidity, imap_uid)  
**Supersedes/Integrates:** Task 5 & Task 6

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

## 🎯 Priorisierte Reihenfolge

| Status | Prio | Feature | Aufwand | Impact | Notes |
|--------|------|---------|--------|--------|-------|
| ✅ DONE | 1 | Filter auf /liste | 4-6h | Sofort nutzbar | Phase A |
| ✅ DONE | 2 | Server DELETE/FLAG/READ | 3-4h | KI→Action möglich | Phase B |
| ✅ DONE | 2a | Option D ServiceToken + InitialSync | 2-3h | Kritische Infra-Fixes | Phase D |
| ✅ DONE | 3 | Server MOVE | 2-3h | Spam-Ordner etc. | Phase C Part 1 |
| ✅ DONE | 4 | Multi-Folder FULL SYNC | 6-8h | Korrekte IMAP-Architektur | Phase C Part 3 |
| ✅ DONE | 4a | Delta-Sync + Fetch Config | 8-10h | 30-60x Speedup, Quick Count | Phase C Part 4 COMPLETE |
| ✅ DONE | 4b | RFC-Compliant IMAP UIDs | 4-6h | Eliminiert Race-Conditions | Phase 14 (a-f) COMPLETE |
| 🟡 TODO | 5 | KI Thread-Context | 4-6h | Bessere Klassifizierung | Phase E |
| 🟡 TODO | 6 | SMTP Antworten | 6-8h | Vollständige Automation | Phase F |
| 🟢 TODO | 7 | Conversation UI | 8-10h | Nice-to-have | Phase G |
| 🟢 TODO | 8 | Bulk Email Operations | 15-20h | Produktive Batch-Verarbeitung | Phase H |

**Abgeschlossen:** 30-40h (Phase A + B + C + D + 14)  
**Geplant Phase 13 (E-H):** ~33-44 Stunden  
**Phase 13 Gesamt:** ~63-84 Stunden

**Phase D Justification (Critical Infrastructure):**
- Moved ahead of Phase C due to critical nature
- Fixed architectural flaw: DEK storage violating zero-knowledge principle
- Solved "mail fetch fails after server restart" blocking production use
- Improved initial sync detection for better UX (500 vs 50 mails)

---

## 🔗 Phase H: Bulk Email Operations (Integriert aus Task 5)

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
- **Integration:** Phase H - Vollständig aufgenommen in Phase 13 Roadmap
- **Status:** ✅ Geplant als Phase 13.H

### Task 6: Pipeline Integration  
- **Integration:** Phase 14 Forward Reference - Aufgeschoben nach Phase 13 Completion
- **Status:** ↪️ Basis für Phase 14 Roadmap
