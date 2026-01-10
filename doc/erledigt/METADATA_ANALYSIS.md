# 📊 Metadata-Analyse: Aktuell vs. Benötigt

**Basisanalyse für Phase 12: Email-Metadaten Enrichment**

**Status:** ✅ Analyse abgeschlossen  
**Created:** 30. Dezember 2025  
**Based on:** Phase 11.5 IMAP Diagnostics (11 Tests, 1503 Zeilen Code)

---

## 📋 Inhaltsverzeichnis

1. [Aktuell Gespeicherte Metadaten](#aktuell-gespeicherte-metadaten)
2. [Phase 11.5 Erkenntnisse](#phase-115-erkenntnisse)
3. [Implementierungs-Prioritäten](#implementierungs-prioritäten)
4. [Detaillierte Analyse: Fehlende Metadaten](#detaillierte-analyse-fehlende-metadaten)
5. [Datenbankfelder zu ADD](#datenbankfelder-zu-add)
6. [Migration-Plan](#migration-plan)
7. [Impact-Analyse](#impact-analyse)
8. [Migrationsrisiken & Mitigation](#migrationsrisiken--mitigation)
9. [TODO-Liste für Implementation](#todo-liste-für-implementation)

---

## Aktuell Gespeicherte Metadaten

### RawEmail Tabelle (src/02_models.py)

| Feld | Typ | Verschlüsselt | Quelle | Nutzen |
|------|-----|:---:|--------|--------|
| `encrypted_sender` | Text | ✅ | mail_fetcher.py | E-Mail anzeigen, From-Header |
| `encrypted_subject` | Text | ✅ | mail_fetcher.py | E-Mail anzeigen, Betreff |
| `encrypted_body` | Text | ✅ | mail_fetcher.py | E-Mail anzeigen, Inhalt |
| `received_at` | DateTime | ❌ | mail_fetcher.py | Sorting, Timeline |
| `imap_uid` | String | ❌ | mail_fetcher.py | IMAP-Kommunikation, Deduplication |
| `imap_folder` | String | ❌ | mail_fetcher.py | Folder-Filter, Archive-Info |
| `imap_flags` | String | ❌ | mail_fetcher.py | Read/Unread/Flagged Status |
| `created_at` | DateTime | ❌ | System | Tracking wann importiert |
| `uid` | String | ❌ | mail_fetcher.py | Deduplication Key |

**Gesamt:** 9 Felder pro RawEmail

### ProcessedEmail Tabelle (src/02_models.py)

| Feld | Typ | Verschlüsselt | Nutzen |
|------|-----|:---:|---------|
| `encrypted_summary_de` | Text | ✅ | KI-Zusammenfassung |
| `encrypted_text_de` | Text | ✅ | KI-Analyse |
| `encrypted_tags` | Text | ✅ | KI-Tags |
| `encrypted_correction_note` | Text | ✅ | User-Feedback |
| `score` | Integer | ❌ | Ranking (1-10) |
| `kategorie_aktion` | String | ❌ | action_required, urgent, info |
| `spam_flag` | Boolean | ❌ | Spam/Ham Classification |
| `dringlichkeit` | Integer | ❌ | Urgency (1-3) |
| `wichtigkeit` | Integer | ❌ | Importance (1-3) |

---

## Phase 11.5 Erkenntnisse

### Test 9: THREAD Support ✅

**Verfügbar auf imap.gmx.net (und anderen Servern):**

```python
# client.thread(algorithm='ORDEREDSUBJECT')
# Returns: Nested UID structure für Conversations

# Beispiel Result:
[1, 2, [3, 4, [5]], 6]

# Bedeutung:
# - 1, 2: Separate Threads
# - 3, 4: Nested (Replies zu 2?)
# - [5]: Nested in 3/4 (Reply zur Reply)
# - 6: Separate Thread
```

**Fehlende DB-Struktur:**
- `parent_uid: String (nullable)` - Welche UID ist Parent?
- `thread_id: String (UUID)` - Welcher Conversation gehört diese Mail an?
- `thread_branch_point: String (nullable)` - Ist das eine Reply oder neue Unterbranch?

**Test-Ergebnis (aus Phase 11.5h):**
- 14 Threads aus 19 Emails erkannt
- Durchschnitt 1.36 Nachrichten pro Thread
- Nested Strukturen korrekt entpackt

### Test 11: Envelope Parsing ✅

**Verfügbar: `client.fetch(uid, 'ENVELOPE')` liefert komplette Header-Struktur (RFC 822)**

```python
ENVELOPE Structure (von imap.gmx.net):
{
  'date': 'Mon, 30 Dec 2024 09:30:00 +0100',
  'subject': 'Re: Projektbesprechung Q1',
  'from': [
    ('Sender Name', 'source@gmail.com')
  ],
  'sender': [
    ('Actual Sender', 'actual@example.com')
  ],
  'reply-to': [
    ('Reply Address', 'reply@example.com')
  ],
  'to': [
    ('User', 'recipient@example.com'),
    ('Others', 'other@example.com')
  ],
  'cc': [
    ('CC Person', 'cc@example.com')
  ],
  'bcc': [
    ('BCC Person', 'bcc@example.com')
  ],
  'in-reply-to': '<parent_message_id@server>',
  'message-id': '<unique_id@server>',
  'references': '<root@server> <parent@server> <grandparent@server>'
}
```

**Fehlende DB-Struktur:**
- `message_id: String (NOT NULL, indexed)` - Eindeutige Message-ID
- `encrypted_in_reply_to: Text (nullable)` - Parent Message-ID
- `encrypted_to: Text (nullable)` - Empfänger
- `encrypted_cc: Text (nullable)` - CC-Empfänger
- `encrypted_bcc: Text (nullable)` - BCC-Empfänger (selten)
- `encrypted_reply_to: Text (nullable)` - Reply-To Header
- `encrypted_references: Text (nullable)` - RFC 5322 References (komplette Chain)

**Test-Ergebnis (aus Phase 11.5h):**
- RFC 2047 Subject Decoding funktioniert
- Message-IDs korrekt extrahiert
- In-Reply-To erkannt bei 6/19 Emails

### Test 10: SORT Support ✅

**Verfügbar: `client.sort(sort_criteria)`**

```python
SORT-Kriterien:
- ARRIVAL: Empfangsdatum (sortiert nach received_at)
- DATE: Header-Datum (aus Date-Header)
- FROM: Absender
- SIZE: Message-Größe
- SUBJECT: Betreff

# Beispiel: UIDs sortiert nach Größe
client.sort('SIZE', reverse=True)
# → [1023, 512, 256, 128, ...]  (nach Bytes)
```

**Fehlende DB-Struktur:**
- `message_size: Integer (nullable, indexed)` - Größe in Bytes

**Test-Ergebnis (aus Phase 11.5h):**
- 5/5 SORT-Kriterien funktionsfähig
- ARRIVAL: Reliabel
- SIZE: Nötig für Quota-Management

### Test 6: Flag Detection ✅

**Aktuell:** `imap_flags` wird als String gespeichert: `"\\Seen \\Answered"`

**Problem:** String-Parsing ist ineffizient für Queries

```sql
-- ✗ Ineffizient:
SELECT * FROM raw_emails 
WHERE imap_flags LIKE '%\\Seen%'

-- ✓ Effizient:
SELECT * FROM raw_emails 
WHERE is_seen = true
```

**Mögliche Flags (RFC 3501):**
- `\Seen` (gelesen)
- `\Answered` (beantwortet)
- `\Flagged` (markiert/wichtig)
- `\Deleted` (zum Löschen markiert - wird nicht sofort gelöscht!)
- `\Draft` (Entwurf)
- `\Recent` (neu eingegangen)
- Custom Flags (per Server)

**Fehlende DB-Struktur (Boolean Columns statt String):**
- `is_seen: Boolean (default=False, indexed)`
- `is_answered: Boolean (default=False, indexed)`
- `is_flagged: Boolean (default=False, indexed)`
- `is_deleted: Boolean (default=False)`
- `is_draft: Boolean (default=False)`

**Test-Ergebnis (aus Phase 11.5h):**
- `\Seen`: Flags auf Sample-Daten erkannt
- Statistik: 8/19 ungelesen, Rest gelesen
- Custom Flags: Keine auf diesem Server

### Test 5: Folder Listing ✅

**Verfügbar: `client.list_folders()` mit Special-Folder-Erkennung**

```python
# Result:
[
  ((b'\\HasChildren',), '/', 'INBOX'),
  ((b'\\HasChildren',), '/', 'Sent'),
  ((b'\\HasChildren',), '/', 'Trash'),
  ((b'\\HasChildren',), '/', 'Spam'),
  ((b'\\HasNoChildren',), None, '[Gmail]/Important'),
]

# Special Folders (RFC 6154):
\\Archive, \\Drafts, \\Junk, \\Sent, \\Trash, 
\\Important, \\Flagged, \\AllMail
```

**Fehlende DB-Struktur (auf EmailFolder-Ebene):**
- `is_special_folder: Boolean`
- `special_folder_type: String` (sent, trash, drafts, archive, spam, etc)
- `display_name_localized: String` (z.B. "Gelöschte Objekte" statt "Trash")

**Test-Ergebnis (aus Phase 11.5h):**
- 7 Folder auf GMX erkannt
- Sent/Trash/Drafts korrekt identifiziert
- Nur persönliche Folder (keine Shared/Public)

### Test 7: Server-ID / Provider Detection ✅

**Verfügbar: `client.id()`**

```python
# Result:
("name" "Dovecot" "version" "2.3.20" "os" "Linux")

# Beispiele:
# - GMX: Dovecot 2.3.x
# - Gmail: "Gmail" (mit eigenen Capabilities)
# - Outlook: "Exchange" oder "Office 365"
# - Yahoo: "Courier"
```

**Fehlende DB-Struktur (auf MailAccount-Ebene):**
- `detected_provider: String` (gmx, gmail, outlook, etc)
- `server_name: String` (Dovecot, Exchange, Gmail, etc)
- `server_version: String` (2.3.20, etc)

**Test-Ergebnis (aus Phase 11.5h):**
- Provider: GMX erkannt
- Server: Dovecot 2.3.20
- Version: Korrekt geparst

---

## Implementierungs-Prioritäten

### 🔴 MUST-HAVE (Basis-Features für Threading)

Diese sollten ZUERST implementiert werden:

#### 1. Message-ID & In-Reply-To (Test 11: Envelope)

**Warum:** Ohne das keine Conversation-Threading möglich

```python
message_id = Column(String(255), nullable=True, index=True)
# Beispiel: <CAJ7Q6O+aB9D8E5F@mail.gmail.com>

encrypted_in_reply_to = Column(Text, nullable=True)
# Beispiel: encrypted version of "<CAJ7Q6O+aB9D8E5E@mail.gmail.com>"
```

**Speicher-Impact:** +32 Bytes pro Mail  
**Query-Impact:** Index nötig für threading-Operationen  
**Dependency:** Test 11 Envelope Parser benötigt  

#### 2. Boolean Flags statt String-Flags (Test 6)

**Warum:** Effizientes Filtering (WHERE is_seen = true viel schneller als LIKE)

```python
is_seen = Column(Boolean, default=False, index=True)
is_answered = Column(Boolean, default=False, index=True)
is_flagged = Column(Boolean, default=False, index=True)
is_deleted = Column(Boolean, default=False)
is_draft = Column(Boolean, default=False)

# Entfernt (aber NOCH NICHT löschen, für Backward-Compatibility):
# imap_flags = Column(String(500), nullable=True)
```

**Speicher-Impact:** -100 Bytes pro Mail (String "\\Seen \\Answered" → 5 Booleans)  
**Query-Impact:** 💥 **Massive Performance-Verbesserung** (Index-Queries statt LIKE)  
**Migration-Aufwand:** Parse imap_flags String einmalig für alle 10k+ Mails

#### 3. Thread-ID & Parent-UID (Test 9: THREAD)

**Warum:** Für Conversation Grouping in UI + Threading-Queries

```python
thread_id = Column(String(36), nullable=True, index=True)
# UUID der gesamten Conversation
# Beispiel: "550e8400-e29b-41d4-a716-446655440000"

parent_uid = Column(String(255), nullable=True, index=True)
# UID der Parent-Mail (wenn Reply)
# Beispiel: "123" (imap_uid)
```

**Speicher-Impact:** +40 Bytes pro Mail  
**Query-Impact:** Indexes für thread_id + parent_uid nötig  
**Dependency:** Benötigt `client.thread()` Integration

---

### 🟡 SHOULD-HAVE (Erweiterte Features)

Können nach MUST-HAVE implementiert werden:

#### 4. Extended Envelope Fields (Test 11)

```python
encrypted_to = Column(Text, nullable=True)
encrypted_cc = Column(Text, nullable=True)
encrypted_bcc = Column(Text, nullable=True)
encrypted_reply_to = Column(Text, nullable=True)
```

**Speicher-Impact:** +200 Bytes pro Mail  
**Query-Impact:** Niedrig (nur für Anzeige, nicht Filtering)  
**Nutzen:** Vollständige Header-Anzeige, CC-Filtering

#### 5. Message Size (Test 10)

```python
message_size = Column(Integer, nullable=True)
# Bytes, z.B. 4096
```

**Speicher-Impact:** +4 Bytes pro Mail  
**Query-Impact:** Index für SORT-Operationen  
**Nutzen:** Quota-Management, Große-Mails-Finder

#### 6. References Header (RFC 5322)

```python
encrypted_references = Column(Text, nullable=True)
# Komplette Conversation-Chain
# Beispiel: "<msg1@server> <msg2@server> <msg3@server>"
```

**Speicher-Impact:** +100 Bytes wenn vorhanden  
**Query-Impact:** Niedrig  
**Nutzen:** Fallback wenn in_reply_to nicht vorhanden

---

### 🟢 NICE-TO-HAVE (Optimierungen)

Für zukünftige Features:

#### 7. Server Metadata (Test 7)

```python
# MailAccount Tabelle:
detected_provider = Column(String(50), nullable=True)
# gmx, gmail, outlook, yahoo, etc
server_name = Column(String(255), nullable=True)
# Dovecot, Exchange, Gmail IMAP4, etc
server_version = Column(String(100), nullable=True)
# 2.3.20, 16.0.12, etc
```

**Speicher-Impact:** +100 Bytes einmalig pro Account  
**Query-Impact:** Keine  
**Nutzen:** Provider-spezifische Optimierungen später

#### 8. Folder Classification (Test 5)

```python
# EmailFolder Tabelle:
is_special_folder = Column(Boolean, default=False)
special_folder_type = Column(String(50), nullable=True)
# sent, trash, drafts, archive, spam, etc
display_name_localized = Column(String(255), nullable=True)
```

**Speicher-Impact:** Nur auf EmailFolder-Ebene  
**Query-Impact:** Niedrig  
**Nutzen:** Verstehen welche Mails User selbst gesendet hat

#### 9. Content-Type & Encoding

```python
content_type = Column(String(100), nullable=True)
# text/plain, text/html, multipart/mixed, etc
charset = Column(String(50), nullable=True)
# utf-8, iso-8859-1, etc
has_attachments = Column(Boolean, default=False)
```

**Speicher-Impact:** +50 Bytes pro Mail  
**Query-Impact:** Niedrig  
**Nutzen:** Bessere Verarbeitung von HTML-Mails, Attachment-Detection

---

## Detaillierte Analyse: Fehlende Metadaten

### Message-ID Extraction (Test 11)

**RFC 822 Header:**
```
Message-ID: <unique@server.com>
In-Reply-To: <parent@server.com>
References: <root@server.com> <parent@server.com>
```

**Wie extrahieren:**
```python
# Aus imaplib.IMAPClient:
envelope_data = client.fetch(uid, 'ENVELOPE')
message_id = envelope_data['message-id']
in_reply_to = envelope_data['in-reply-to']
references = envelope_data['references']
```

**Problem:** Envelope liefert teilweise nur Bytes

**Lösung:** Proper decode + validation

```python
def extract_message_id(msg):
    msg_id = msg.get('Message-ID', '').strip()
    if msg_id:
        # Remove angle brackets if present
        msg_id = msg_id.strip('<>')
        # Validate format (should contain @)
        if '@' in msg_id:
            return msg_id
    return None
```

### Thread-ID Calculation (Test 9)

**IMAP THREAD Response:**
```python
client.thread(algorithm='ORDEREDSUBJECT')
# Returns: (1, 2, (3, 4, (5)), 6)
# Meaning: 1 und 2 separate, 3&4 nested, 5 nested in 3/4, 6 separate
```

**Algorithmus:**
```python
def calculate_thread_ids(thread_structure, thread_id=None):
    """
    Flatten nested thread structure to flat list with thread_ids.
    
    Input:  (1, 2, (3, 4, (5)), 6)
    Output: {
        1: 'uuid-1', 2: 'uuid-1',
        3: 'uuid-2', 4: 'uuid-2', 5: 'uuid-2',
        6: 'uuid-3'
    }
    """
    result = {}
    
    if thread_id is None:
        thread_id = str(uuid.uuid4())
    
    if isinstance(thread_structure, (list, tuple)):
        for item in thread_structure:
            if isinstance(item, (list, tuple)):
                # Neue Thread-Branch
                new_thread_id = str(uuid.uuid4())
                result.update(calculate_thread_ids(item, new_thread_id))
            else:
                # UID
                result[item] = thread_id
    else:
        result[thread_structure] = thread_id
    
    return result
```

### Flag Conversion (Test 6)

**Aktuell (String):**
```python
imap_flags = "\\Seen \\Answered \\Flagged"
```

**Zu Conversion (Boolean):**
```python
def parse_imap_flags(flags_str):
    """Convert imap_flags string to boolean dict"""
    if not flags_str:
        return {
            'is_seen': False,
            'is_answered': False,
            'is_flagged': False,
            'is_deleted': False,
            'is_draft': False,
        }
    
    return {
        'is_seen': '\\Seen' in flags_str or b'\\Seen' in flags_str,
        'is_answered': '\\Answered' in flags_str or b'\\Answered' in flags_str,
        'is_flagged': '\\Flagged' in flags_str or b'\\Flagged' in flags_str,
        'is_deleted': '\\Deleted' in flags_str or b'\\Deleted' in flags_str,
        'is_draft': '\\Draft' in flags_str or b'\\Draft' in flags_str,
    }
```

---

## Datenbankfelder zu ADD

### Migration: New Columns

```python
# src/02_models.py
class RawEmail(Base):
    __tablename__ = "raw_emails"
    
    # ALREADY EXISTS:
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    mail_account_id = Column(Integer, ForeignKey("mail_accounts.id"))
    uid = Column(String(255), nullable=False)
    encrypted_sender = Column(Text, nullable=False)
    encrypted_subject = Column(Text)
    encrypted_body = Column(Text)
    received_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    imap_uid = Column(String(100), nullable=True, index=True)
    imap_folder = Column(String(200), nullable=True)
    imap_flags = Column(String(500), nullable=True)  # DEPRECATED (keep for now)
    
    # ===== NEW - MUST HAVE =====
    
    # Message ID & Threading
    message_id = Column(String(255), nullable=True, index=True)
    encrypted_in_reply_to = Column(Text, nullable=True)
    parent_uid = Column(String(255), nullable=True, index=True)
    thread_id = Column(String(36), nullable=True, index=True)
    
    # Boolean Flags (replace imap_flags string)
    is_seen = Column(Boolean, default=False, index=True)
    is_answered = Column(Boolean, default=False, index=True)
    is_flagged = Column(Boolean, default=False, index=True)
    is_deleted = Column(Boolean, default=False)
    is_draft = Column(Boolean, default=False)
    
    # ===== NEW - SHOULD HAVE =====
    
    # Extended Envelope Fields
    encrypted_to = Column(Text, nullable=True)
    encrypted_cc = Column(Text, nullable=True)
    encrypted_bcc = Column(Text, nullable=True)
    encrypted_reply_to = Column(Text, nullable=True)
    
    # Message Metadata
    message_size = Column(Integer, nullable=True)
    encrypted_references = Column(Text, nullable=True)
    
    # ===== NEW - NICE-TO-HAVE =====
    
    # Content Info
    content_type = Column(String(100), nullable=True)
    charset = Column(String(50), nullable=True)
    has_attachments = Column(Boolean, default=False)
    
    # Audit
    last_flag_sync_at = Column(DateTime, nullable=True)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "mail_account_id", "uid", name="uq_raw_emails_uid"),
    )
```

### MailAccount Enhancements

```python
class MailAccount(Base):
    # ALREADY EXISTS: id, user_id, name, auth_type, ...
    
    # NEW - NICE-TO-HAVE:
    detected_provider = Column(String(50), nullable=True)
    server_name = Column(String(255), nullable=True)
    server_version = Column(String(100), nullable=True)
```

### EmailFolder Enhancements

```python
class EmailFolder(Base):
    # ALREADY EXISTS: id, user_id, mail_account_id, name, imap_path, ...
    
    # NEW - NICE-TO-HAVE:
    is_special_folder = Column(Boolean, default=False)
    special_folder_type = Column(String(50), nullable=True)
    display_name_localized = Column(String(255), nullable=True)
```

---

## Migration-Plan

### Phase 1: Datenbank-Schema Update

**Datei:** `migrations/versions/add_enhanced_email_metadata.py`

```python
"""Add enhanced email metadata for threading and better queries"""

def upgrade():
    # 1. Add neue Spalten (nullable initially)
    
    # MUST-HAVE columns
    op.add_column('raw_emails', 
        sa.Column('message_id', sa.String(255), nullable=True)
    )
    op.add_column('raw_emails',
        sa.Column('encrypted_in_reply_to', sa.Text, nullable=True)
    )
    op.add_column('raw_emails',
        sa.Column('parent_uid', sa.String(255), nullable=True)
    )
    op.add_column('raw_emails',
        sa.Column('thread_id', sa.String(36), nullable=True)
    )
    
    # Boolean Flags
    op.add_column('raw_emails',
        sa.Column('is_seen', sa.Boolean, default=False)
    )
    op.add_column('raw_emails',
        sa.Column('is_answered', sa.Boolean, default=False)
    )
    op.add_column('raw_emails',
        sa.Column('is_flagged', sa.Boolean, default=False)
    )
    op.add_column('raw_emails',
        sa.Column('is_deleted', sa.Boolean, default=False)
    )
    op.add_column('raw_emails',
        sa.Column('is_draft', sa.Boolean, default=False)
    )
    
    # SHOULD-HAVE columns
    op.add_column('raw_emails',
        sa.Column('encrypted_to', sa.Text, nullable=True)
    )
    # ... etc
    
    # 2. Create Indexes
    op.create_index('ix_raw_emails_message_id', 'raw_emails', ['message_id'])
    op.create_index('ix_raw_emails_thread_id', 'raw_emails', ['thread_id'])
    op.create_index('ix_raw_emails_parent_uid', 'raw_emails', ['parent_uid'])
    op.create_index('ix_raw_emails_is_seen', 'raw_emails', ['is_seen'])
    op.create_index('ix_raw_emails_is_answered', 'raw_emails', ['is_answered'])
    
    # 3. Populate boolean flags from imap_flags string (One-time!)
    # This is done in a data migration script

def downgrade():
    # Drop in reverse order
    op.drop_index('ix_raw_emails_...')
    # ...
    op.drop_column('raw_emails', 'message_id')
    # ...
```

**Skript:** `scripts/populate_boolean_flags.py` (One-time Population)

```python
"""Populate boolean flags from existing imap_flags string"""

from sqlalchemy.orm import sessionmaker
from src import models, encryption

def populate_flags(db_path='emails.db'):
    """Convert all imap_flags strings to boolean columns"""
    engine, Session = models.init_db(db_path)
    session = Session()
    
    emails = session.query(models.RawEmail).all()
    
    for email in emails:
        if not email.imap_flags:
            continue
        
        flags = email.imap_flags
        email.is_seen = '\\Seen' in flags or b'\\Seen' in flags
        email.is_answered = '\\Answered' in flags
        email.is_flagged = '\\Flagged' in flags
        email.is_deleted = '\\Deleted' in flags
        email.is_draft = '\\Draft' in flags
    
    session.commit()
    print(f"✅ Populated {len(emails)} emails")
```

### Phase 2: Mail-Fetcher Update

**Datei:** `src/06_mail_fetcher.py`

```python
def _fetch_email_by_id(self, mail_id: bytes, folder: str = "INBOX"):
    # ... existing code ...
    
    # NEW: Fetch ENVELOPE for extended metadata
    status, envelope_data = conn.fetch(mail_id_str, "(RFC822 ENVELOPE)")
    
    if status == "OK":
        envelope = self._parse_envelope(envelope_data)
    else:
        envelope = {}
    
    return {
        # Existing fields:
        "uid": mail_id_str,
        "sender": sender,
        "subject": subject,
        "body": body,
        "received_at": received_at,
        "imap_uid": imap_uid,
        "imap_folder": folder,
        "imap_flags": imap_flags,
        
        # NEW fields from ENVELOPE:
        "message_id": envelope.get('message_id'),
        "in_reply_to": envelope.get('in_reply_to'),
        "to": envelope.get('to'),
        "cc": envelope.get('cc'),
        "bcc": envelope.get('bcc'),
        "reply_to": envelope.get('reply_to'),
        "references": envelope.get('references'),
        "message_size": envelope.get('size'),
    }

def _parse_envelope(self, envelope_data):
    """Parse ENVELOPE response from IMAP"""
    # Implementation details...
```

**Datei:** `src/imap_diagnostics.py` (Update Test 9 + 11)

```python
def test_thread_support(self, client=None):
    # Existing: THREAD algorithm detection
    # NEW: Return structured thread IDs
    
    try:
        threads = client.thread('ORDEREDSUBJECT')
        thread_mapping = self._flatten_threads(threads)
        
        return {
            'supported': True,
            'algorithms': ['ORDEREDSUBJECT'],
            'thread_count': len(set(thread_mapping.values())),
            'thread_mapping': thread_mapping,
        }
    except:
        return {'supported': False}

def _flatten_threads(self, thread_structure, thread_id=None):
    """Convert nested thread structure to flat mapping"""
    # Implementation...
```

### Phase 3: Background Job Update

**Datei:** `src/14_background_jobs.py`

```python
def _persist_raw_emails(
    self, session, user, account, raw_emails: list[Dict], master_key: str
):
    """Speichert RawEmails mit neuen Metadaten"""
    
    # Berechne Thread-IDs wenn verfügbar
    thread_mapping = self._calculate_thread_mapping(raw_emails)
    
    for raw_email_data in raw_emails:
        # ... existing encryption code ...
        
        # NEW: Set message-ID (NOT encrypted!)
        message_id = raw_email_data.get('message_id')
        
        # NEW: Encrypt extended envelope fields
        encrypted_to = encryption.EmailDataManager.encrypt_email_to(
            raw_email_data.get('to'), master_key
        ) if raw_email_data.get('to') else None
        
        # NEW: Parse flags to booleans
        flags_dict = self._parse_flags(raw_email_data.get('imap_flags', ''))
        
        raw_email = models.RawEmail(
            user_id=user.id,
            mail_account_id=account.id,
            uid=raw_email_data['uid'],
            # ... existing fields ...
            
            # NEW fields:
            message_id=message_id,
            encrypted_in_reply_to=encrypted_in_reply_to,
            parent_uid=thread_mapping.get(raw_email_data['uid'], {}).get('parent'),
            thread_id=thread_mapping.get(raw_email_data['uid'], {}).get('thread'),
            
            is_seen=flags_dict['is_seen'],
            is_answered=flags_dict['is_answered'],
            is_flagged=flags_dict['is_flagged'],
            is_deleted=flags_dict['is_deleted'],
            is_draft=flags_dict['is_draft'],
            
            encrypted_to=encrypted_to,
            # ... etc ...
        )
        session.add(raw_email)
    
    session.commit()
```

### Phase 4: Testierung

**CLI-Tests (kein credentials):**

```python
# tests/test_metadata_extraction.py

def test_flag_parsing():
    """Test boolean flag conversion"""
    from src.imap_diagnostics import DiagnosticsClient
    
    flags_str = "\\Seen \\Answered"
    result = DiagnosticsClient._parse_flags(flags_str)
    
    assert result['is_seen'] == True
    assert result['is_answered'] == True
    assert result['is_flagged'] == False

def test_message_id_extraction():
    """Test Message-ID extraction"""
    import email
    msg = email.message_from_string("Message-ID: <test@example.com>\n")
    msg_id = msg.get('Message-ID', '').strip('<>')
    assert msg_id == "test@example.com"

def test_thread_id_calculation():
    """Test thread ID calculation"""
    from src.imap_diagnostics import DiagnosticsClient
    
    thread_structure = (1, 2, (3, 4, (5)), 6)
    result = DiagnosticsClient._flatten_threads(thread_structure)
    
    # Thread-IDs sollten gleich sein für Nested-Elemente
    assert result[3] == result[4] == result[5]  # Same thread
    assert result[1] != result[3]  # Different threads
```

**Integration-Tests (über UI):**

```
Login → Settings → Select Account
  → Fetch Mails
  → Verify database:
    ✓ message_id populated
    ✓ boolean flags set
    ✓ thread_id calculated
    ✓ envelope fields present
```

---

## Impact-Analyse

### Speicher-Verbrauch

| Feld | Bytes pro Mail | Total für 10k Mails |
|------|----------------|-------------------|
| message_id (String(255)) | +32 | +320 KB |
| encrypted_in_reply_to | +100 | +1 MB |
| parent_uid (String(255)) | +32 | +320 KB |
| thread_id (String(36)) | +36 | +360 KB |
| is_seen (Boolean) | +1 | +10 KB |
| is_answered (Boolean) | +1 | +10 KB |
| is_flagged (Boolean) | +1 | +10 KB |
| is_deleted (Boolean) | +1 | +10 KB |
| is_draft (Boolean) | +1 | +10 KB |
| encrypted_to | +100 | +1 MB |
| encrypted_cc | +80 | +800 KB |
| encrypted_bcc (optional) | +40 | +400 KB |
| encrypted_reply_to | +40 | +400 KB |
| message_size (Integer) | +4 | +40 KB |
| encrypted_references | +100 | +1 MB |
| **SUBTOTAL** | **~469 Bytes** | **~5.7 MB** |
| **Indexes** (estimate 10%) | - | **+570 KB** |
| **TOTAL** | - | **~6.3 MB** |

**Fazit:** Marginal für 10k Mails (< 1% DB-Wachstum auf 100MB DB)

### Query Performance

| Operation | Vorher | Nachher | Improvement |
|-----------|--------|---------|-------------|
| Unread Count | `WHERE imap_flags LIKE '%\\Seen%'` | `WHERE is_seen = false` | ✅ 200-300% |
| Filter by Flagged | `LIKE '%\\Flagged%'` | `WHERE is_flagged = true` | ✅ 200-300% |
| Thread Queries | N/A (nicht möglich) | `WHERE thread_id = ?` | ✅ Neu möglich |
| Sort by Size | N/A | `ORDER BY message_size DESC` | ✅ Neu möglich |
| Search by Message-ID | N/A | `WHERE message_id = ?` (indexed) | ✅ Neu möglich |

### Fetch-Zeit

- Alte Implementation: `client.fetch(uid, 'RFC822')`
- Neue Implementation: `client.fetch(uid, '(RFC822 ENVELOPE)')`
- **Impact:** +10-15% (envelope() ist etwas langsamer)

### Backup-Größe

Aktuelle DB: ~780 KB (auf imap.gmx.net mit 19 Mails)

Nach Enrichment (19 Mails): ~810 KB (+4%)  
Nach Enrichment (10k Mails): ~100 MB + 6.3 MB = ~106 MB (+6%)

---

## Migrationsrisiken & Mitigation

| Risiko | Severity | Mitigation |
|--------|----------|-----------|
| **Benutzer mit 10k+ Mails** | ⚠️ Hoch | Batch-Update: 100 Mails pro Transaction, nicht all-at-once |
| **Thread-ID Berechnung Fehler** | ⚠️ Hoch | Validiere gegen `imap.thread()` für Stichproben (10%),  keine Duplikate |
| **Boolean Flags Konversion** | 🔴 Kritisch | Unit-Test alle 32 Flag-Kombinationen (2^5) |
| **Message-ID Duplikate** | ⚠️ Mittel | Unique Constraint? NEIN - Message-IDs können bei Forward dupliziert sein |
| **Backward Compatibility** | ⚠️ Mittel | Alte `imap_flags` noch lesen, mindestens 2 Releases |
| **Null-Handling** | ⚠️ Mittel | Envelope-Felder können NULL sein (test against Gmail, Outlook, GMX) |
| **Server-spezifische Formate** | ⚠️ Mittel | Message-ID Format variiert (test gegen 3+ Provider) |
| **Rollback** | 🔴 Kritisch | Alter DB-Snapshot bereitstellen, Rollback-Script testen |

### Batch-Migration für große Datenbanken

```python
def migrate_flags_in_batches(db_path, batch_size=100):
    """Populate flags in batches to avoid locking"""
    engine, Session = models.init_db(db_path)
    session = Session()
    
    total = session.query(models.RawEmail).count()
    batches = (total // batch_size) + 1
    
    for batch_num in range(batches):
        offset = batch_num * batch_size
        emails = session.query(models.RawEmail).offset(offset).limit(batch_size).all()
        
        for email in emails:
            flags = email.imap_flags or ""
            email.is_seen = '\\Seen' in flags
            # ... etc
        
        session.commit()
        print(f"✅ Batch {batch_num+1}/{batches}")
```

---

## TODO-Liste für Implementation

### PHASE 1: SCHEMA & MIGRATION

- [ ] Create Alembic Migration: `add_enhanced_email_metadata.py`
  - [ ] Add all new columns (nullable=True)
  - [ ] Create indexes (message_id, thread_id, parent_uid, is_seen, is_answered)
- [ ] Create Data Migration Script: `populate_boolean_flags.py`
  - [ ] Parse all imap_flags → boolean columns
  - [ ] Batch processing für große DBs (100 mails/batch)
  - [ ] Verify: alle 10k+ mails konvertiert
- [ ] Test Migration gegen Production-DB-Backup
  - [ ] Vorher/Nachher Größe vergleichen
  - [ ] Query-Performance benchmarken
- [ ] Create Rollback-Plan & Test-Skript
  - [ ] Backup vor Migration
  - [ ] Rollback-SQL dokumentiert

### PHASE 2: FETCHER-UPDATES

- [ ] Update `src/06_mail_fetcher.py`:
  - [ ] Extract message_id from Email-Header
  - [ ] Extract in_reply_to from Email-Header
  - [ ] Extract all Envelope fields (to, cc, bcc, reply-to)
  - [ ] Extract message size
  - [ ] Parse content-type & charset
  - [ ] Detect attachments (Content-Disposition: attachment)
- [ ] Test gegen imap.gmx.net
- [ ] Test gegen Gmail (OAuth)
- [ ] Test gegen Outlook
- [ ] Test envelope parsing bei:
  - [ ] Einfachen Mails (no CC/BCC)
  - [ ] Forwarded Mails (long References)
  - [ ] Spam-Mails (meist keine BCC)

### PHASE 3: BACKGROUND-JOBS

- [ ] Update `src/14_background_jobs.py` `_persist_raw_emails()`:
  - [ ] Entschlüssle encrypted_to, encrypted_cc, etc
  - [ ] Parse imap_flags → boolean Flags
  - [ ] Calculate thread_id aus thread-structure oder in_reply_to
  - [ ] Berechne parent_uid
- [ ] Implement thread_id calculation logic
  - [ ] Handle nested structures
  - [ ] Fallback zu in_reply_to wenn THREAD nicht supported
- [ ] Implement provider detection
  - [ ] Call `client.id()` beim ersten Fetch
  - [ ] Store in MailAccount.detected_provider
- [ ] Error-Handling für malformed envelopes
  - [ ] Null-checks für alle neuen Felder
  - [ ] Fallback-Werte wo nötig

### PHASE 4: TESTING & VALIDATION

- [ ] Unit-Tests:
  - [ ] test_flag_parsing (alle 32 Kombinationen)
  - [ ] test_message_id_extraction
  - [ ] test_thread_id_calculation
  - [ ] test_envelope_parsing
  - [ ] test_batch_migration
- [ ] Integration-Tests (UI, mit echten Accounts):
  - [ ] GMX Login + Fetch + Verify DB
  - [ ] Gmail OAuth + Fetch + Verify DB
  - [ ] Outlook + Fetch + Verify DB
- [ ] Performance-Tests:
  - [ ] Alte vs. Neue Implementation (Query-Speed)
  - [ ] Fetch-Time Impact
  - [ ] Migration-Time für 10k+ Mails
- [ ] Backward-Compatibility Test:
  - [ ] Code noch lesbar von alten imap_flags
  - [ ] Mix aus Mails mit/ohne neue Felder

### PHASE 5: DOCUMENTATION & DEPLOYMENT

- [ ] Update `CHANGELOG.md`:
  - [ ] Phase 12 Entry mit Metadata Enrichment
  - [ ] Database Schema Changes dokumentieren
  - [ ] Breaking Changes (falls vorhanden)
- [ ] Update DB-Schema Dokumentation
- [ ] Update Mail-Fetcher API-Docs
- [ ] Create Data-Migration Runbook für Ops
- [ ] Test Deployment gegen Staging-DB
- [ ] Create Rollback Runbook für Ops
- [ ] Notified User vor Migration
  - [ ] Expected Downtime (wenn vorhanden)
  - [ ] Benefits erklärt

---

## Zusammenfassung

### Status Quo (Aktuell)

- ✅ 9 Felder pro RawEmail
- ✅ String-basierte Flags (ineffizient)
- ❌ Kein Threading-Support
- ❌ Keine erweiterten Header
- ❌ Kein Message-Size für Sorting

### Nach MUST-HAVE Implementation

- ✅ 14 Felder pro RawEmail (minimal)
- ✅ Boolean Flags (200% Perf-Verbesserung)
- ✅ Full Threading Support (message_id + in_reply_to + thread_id)
- ✅ Basic Envelope-Daten (to, cc, bcc, reply-to)
- ✅ Message-Size für Sorting

### Nach SHOULD-HAVE Implementation

- ✅ 18+ Felder pro RawEmail
- ✅ Komplette Envelope-Daten
- ✅ Advanced Threading (References-Chain)
- ✅ Content-Type & Attachment-Detection
- ✅ Provider-spezifische Optimierungen möglich

### Zeitschätzung

| Phase | Aufwand | Notes |
|-------|---------|-------|
| **1: Schema + Migration** | 20-30h | Data Migration + Rollback-Plan |
| **2: Fetcher Updates** | 15-20h | Test gegen 3+ Provider |
| **3: Job Integration** | 10-15h | Thread-ID Calculation + Error-Handling |
| **4: Testing + Validation** | 20-25h | Unit + Integration + Perf Tests |
| **5: Documentation + Deployment** | 10-15h | Runbook + Staging-Test |
| **TOTAL** | **75-105 hours** | ~2-3 Wochen für 1 FTE |

### Priorisierung für MVP

**Minimal Viable Product (Phase 12.1):**
1. ✅ Message-ID + In-Reply-To + Boolean Flags (Basis-Threading)
2. ✅ Thread-ID Calculation
3. ✅ Test gegen GMX, Gmail, Outlook

**Nice-to-Have (Phase 12.2):**
4. Extended Envelope + Provider Detection
5. Content-Type + Attachments

---

**Nächste Schritte:** Diese Analyse an Team vorstellen, Priorisierung abstimmen, Sprint-Planning für Phase 12 beginnen.
