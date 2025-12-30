# 🚀 Phase 12: Email Metadata Enrichment - Implementation Guide

**Status:** ✅ Ready for Implementation  
**Created:** 30. Dezember 2025  
**Target Duration:** 75-105 hours (~2-3 Wochen)  
**Based on:** METADATA_ANALYSIS.md + Phase 11.5 Diagnostics

---

## 📋 Überblick

Phase 12 erweitert die Datenbankstruktur mit essentiellen Metadaten für:
- ✅ **Conversation Threading** (message_id, in_reply_to, thread_id)
- ✅ **Effiziente Queries** (Boolean Flags statt LIKE '%Seen%')
- ✅ **Full Envelope Data** (To, CC, BCC, Reply-To)
- ✅ **Message Metadata** (Size, Content-Type, Attachments)
- ✅ **Server Insights** (Provider-Detection, Folder Classification)

---

## ✅ What's Already Done (Pre-Implementation)

### 1. Database Migration erstellt
**File:** `migrations/versions/ph12_metadata_enrichment.py`

```python
# Fügt folgende Spalten hinzu:
- message_id (String(255), indexed)
- encrypted_in_reply_to (Text)
- parent_uid (String(255), indexed)
- thread_id (String(36), indexed)
- is_seen, is_answered, is_flagged, is_deleted, is_draft (Boolean)
- encrypted_to, encrypted_cc, encrypted_bcc, encrypted_reply_to (Text)
- message_size (Integer)
- encrypted_references (Text)
- content_type, charset, has_attachments (String/Boolean)
- detected_provider, server_name, server_version (MailAccount)
- is_special_folder, special_folder_type, display_name_localized (EmailFolder)
```

### 2. Data Migration Script erstellt
**File:** `scripts/populate_metadata_phase12.py`

```bash
# Batch-Population mit Validierung
python scripts/populate_metadata_phase12.py --batch-size 100
```

Features:
- ✅ Konvertiert `imap_flags` String → Boolean-Spalten
- ✅ Setzt Placeholder-Werte für neue Felder
- ✅ Validiert Daten nach Migration
- ✅ Batch-Processing (keine DB-Locks)
- ✅ Comprehensive Logging

### 3. Envelope-Parsing Test erstellt
**File:** `tests/test_envelope_parsing.py`

```bash
# Testet gegen echte IMAP-Server
python tests/test_envelope_parsing.py
```

Features:
- ✅ Extrahiert Message-ID, In-Reply-To, References
- ✅ Parst To, CC, BCC, Reply-To Header
- ✅ Erkennt Content-Type & Attachments
- ✅ Schätzt Message-Size
- ✅ Test gegen GMX, Gmail, Outlook

---

## 🔧 Implementation Roadmap

### PHASE 12.1: Models Update (2-3h)

**Datei:** `src/02_models.py`

Update RawEmail-Klasse mit neuen Feldern:

```python
class RawEmail(Base):
    # ... existing fields ...
    
    # MUST-HAVE (Threading)
    message_id = Column(String(255), nullable=True, index=True)
    encrypted_in_reply_to = Column(Text, nullable=True)
    parent_uid = Column(String(255), nullable=True, index=True)
    thread_id = Column(String(36), nullable=True, index=True)
    
    # Boolean Flags
    is_seen = Column(Boolean, default=False, index=True)
    is_answered = Column(Boolean, default=False, index=True)
    is_flagged = Column(Boolean, default=False, index=True)
    is_deleted = Column(Boolean, default=False)
    is_draft = Column(Boolean, default=False)
    
    # SHOULD-HAVE (Envelope)
    encrypted_to = Column(Text, nullable=True)
    encrypted_cc = Column(Text, nullable=True)
    encrypted_bcc = Column(Text, nullable=True)
    encrypted_reply_to = Column(Text, nullable=True)
    
    # Message Metadata
    message_size = Column(Integer, nullable=True)
    encrypted_references = Column(Text, nullable=True)
    
    # NICE-TO-HAVE (Content)
    content_type = Column(String(100), nullable=True)
    charset = Column(String(50), nullable=True)
    has_attachments = Column(Boolean, default=False)
    last_flag_sync_at = Column(DateTime, nullable=True)
```

### PHASE 12.2: Mail Fetcher Update (15-20h)

**Datei:** `src/06_mail_fetcher.py`

Erweitere `_fetch_email_by_id()` um Envelope-Parsing:

```python
def _fetch_email_by_id(self, mail_id: bytes, folder: str = "INBOX") -> Optional[Dict]:
    # ... existing code ...
    
    # NEW: Fetch ENVELOPE für erweiterte Metadaten
    status, envelope_data = conn.fetch(mail_id_str, "(RFC822 ENVELOPE)")
    
    if status == "OK":
        envelope = self._parse_envelope(envelope_data)
    else:
        envelope = {}
    
    # Parse Boolean-Flags
    flags_dict = self._parse_flags(imap_flags)
    
    return {
        # ... existing fields ...
        
        # NEW fields
        "message_id": envelope.get('message_id'),
        "in_reply_to": envelope.get('in_reply_to'),
        "to": envelope.get('to'),
        "cc": envelope.get('cc'),
        "bcc": envelope.get('bcc'),
        "reply_to": envelope.get('reply_to'),
        "references": envelope.get('references'),
        "message_size": envelope.get('size'),
        "content_type": envelope.get('content_type'),
        "charset": envelope.get('charset'),
        "has_attachments": envelope.get('has_attachments'),
        
        # Boolean flags
        **flags_dict,  # is_seen, is_answered, is_flagged, is_deleted, is_draft
    }

def _parse_envelope(self, envelope_data) -> Dict:
    """Parse ENVELOPE response from IMAP"""
    # Implementation

def _parse_flags(self, flags_str: str) -> Dict[str, bool]:
    """Convert imap_flags string to boolean dict"""
    return {
        'is_seen': '\\Seen' in flags_str,
        'is_answered': '\\Answered' in flags_str,
        'is_flagged': '\\Flagged' in flags_str,
        'is_deleted': '\\Deleted' in flags_str,
        'is_draft': '\\Draft' in flags_str,
    }
```

**Tests:**
- Test gegen imap.gmx.net
- Test gegen Gmail (OAuth)
- Test gegen Outlook
- Test Envelope-Parsing bei einfachen/forwarded Mails
- Test Null-Handling (leere To/CC/BCC)

### PHASE 12.3: Background Jobs Update (10-15h)

**Datei:** `src/14_background_jobs.py`

Update `_persist_raw_emails()` für neue Felder:

```python
def _persist_raw_emails(
    self, session, user, account, raw_emails: list[Dict], master_key: str
):
    """Persist RawEmails mit neuen Metadaten"""
    
    # Calculate thread-IDs wenn THREAD unterstützt
    thread_mapping = self._calculate_thread_mapping(raw_emails)
    
    for raw_email_data in raw_emails:
        # ... existing encryption ...
        
        # NEW: Extract & store message-ID
        message_id = raw_email_data.get('message_id')
        
        # NEW: Encrypt extended envelope fields
        encrypted_to = encryption.EmailDataManager.encrypt_email_to(
            raw_email_data.get('to'), master_key
        ) if raw_email_data.get('to') else None
        
        encrypted_cc = encryption.EmailDataManager.encrypt_email_cc(
            raw_email_data.get('cc'), master_key
        ) if raw_email_data.get('cc') else None
        
        # ... etc for bcc, reply_to, references ...
        
        # NEW: Encrypt in_reply_to
        encrypted_in_reply_to = encryption.EmailDataManager.encrypt_email_in_reply_to(
            raw_email_data.get('in_reply_to'), master_key
        ) if raw_email_data.get('in_reply_to') else None
        
        # Create RawEmail with new fields
        raw_email = models.RawEmail(
            user_id=user.id,
            mail_account_id=account.id,
            uid=raw_email_data['uid'],
            
            # ... existing fields ...
            
            # NEW MUST-HAVE fields
            message_id=message_id,
            encrypted_in_reply_to=encrypted_in_reply_to,
            parent_uid=thread_mapping.get(raw_email_data['uid'], {}).get('parent'),
            thread_id=thread_mapping.get(raw_email_data['uid'], {}).get('thread'),
            
            is_seen=raw_email_data.get('is_seen', False),
            is_answered=raw_email_data.get('is_answered', False),
            is_flagged=raw_email_data.get('is_flagged', False),
            is_deleted=raw_email_data.get('is_deleted', False),
            is_draft=raw_email_data.get('is_draft', False),
            
            # NEW SHOULD-HAVE fields
            encrypted_to=encrypted_to,
            encrypted_cc=encrypted_cc,
            encrypted_bcc=encrypted_bcc,
            encrypted_reply_to=encrypted_reply_to,
            
            message_size=raw_email_data.get('message_size'),
            encrypted_references=encrypted_references,
            
            # NEW NICE-TO-HAVE fields
            content_type=raw_email_data.get('content_type', 'text/plain'),
            charset=raw_email_data.get('charset', 'utf-8'),
            has_attachments=raw_email_data.get('has_attachments', False),
        )
        session.add(raw_email)

def _calculate_thread_mapping(self, raw_emails: list[Dict]) -> Dict:
    """Calculate thread_id und parent_uid aus Message-ID Chain"""
    # Implementation basierend auf in_reply_to + references Headers
```

**Tests:**
- Persist neue Felder in DB
- Encryption/Decryption funktioniert
- Thread-ID Berechnung ist korrekt
- Null-Handling bei fehlenden Envelope-Daten

### PHASE 12.4: Encryption Updates (5-8h)

**Datei:** `src/08_encryption.py`

Neue Encryption-Methods:

```python
class EmailDataManager:
    @staticmethod
    def encrypt_email_to(addresses_json: str, master_key: str) -> str:
        """Encrypt To header"""
        
    @staticmethod
    def encrypt_email_cc(addresses_json: str, master_key: str) -> str:
        """Encrypt Cc header"""
    
    # ... etc ...
```

### PHASE 12.5: IMAP Diagnostics Update (8-12h)

**Datei:** `src/imap_diagnostics.py`

Update bestehende Tests für neue Metadaten:

```python
def test_thread_support(self, client=None) -> Dict:
    """Test THREAD Support & Return structured thread IDs"""
    # Existing test + return mapping
    
def test_envelope_parsing(self, client=None) -> Dict:
    """NEW: Test Envelope Parsing gegen echten Server"""
    # Extract all envelope fields
    # Return structured data
    
def test_provider_detection(self, client=None) -> Dict:
    """NEW: Detect Server/Provider"""
    # Call client.id()
    # Parse responses
    # Detect GMX/Gmail/Outlook
```

### PHASE 12.6: Testing & Validation (20-25h)

**Unit Tests:** `tests/test_metadata_extraction.py`

```python
def test_flag_parsing():
    """Test boolean flag conversion (32 combinations)"""
    
def test_message_id_extraction():
    """Test Message-ID extraction"""
    
def test_thread_id_calculation():
    """Test thread ID calculation from nested structure"""
    
def test_envelope_parsing():
    """Test To/CC/BCC/Reply-To parsing"""
    
def test_flag_migration():
    """Test imap_flags → boolean migration"""
```

**Integration Tests:** Via UI
- Login → Settings → Select Account
- Fetch Mails
- Verify in Database:
  - message_id populated
  - Boolean flags set correctly
  - thread_id calculated
  - Envelope fields present

**Performance Tests:**
- Query speed: Old (LIKE) vs. New (index)
- Fetch time impact: +10-15% overhead acceptable
- Migration time für 10k+ Mails

### PHASE 12.7: Deployment (10-15h)

**Schritte:**
1. Backup aktueller DB
2. Run Alembic Migration
3. Run populate_metadata_phase12.py Script
4. Validation gegen Staging-DB
5. Rollback-Test durchführen
6. Deploy zu Production
7. Monitor Logs nach Errors

---

## 🔄 Migration Execution Checklist

### Pre-Migration (Vorbereitung)

- [ ] Backup aktuelle DB: `cp emails.db emails.db.backup_phase12_$(date +%s)`
- [ ] Test Migration gegen Backup-DB
- [ ] Rollback-Script vorbereiten
- [ ] Team benachrichtigen (wenn Production)
- [ ] Maintenance-Window planen (wenn nötig)

### During Migration

- [ ] Run Alembic upgrade: `alembic upgrade head`
- [ ] Verify columns added: `sqlite3 emails.db ".schema raw_emails"`
- [ ] Run data migration: `python scripts/populate_metadata_phase12.py`
- [ ] Monitor Logs für Errors
- [ ] Check Validation Results

### Post-Migration

- [ ] Verify Data Integrity
- [ ] Performance Benchmarks
- [ ] Query Tests (new indexes working)
- [ ] Keep Backup für ~7 Tage
- [ ] Document Migration Time
- [ ] Update Deployment Log

---

## 🚨 Rollback Plan

Falls Fehler auftreten:

```bash
# Option 1: Alembic Downgrade
alembic downgrade -1

# Option 2: Restore from Backup
rm emails.db
cp emails.db.backup_phase12_TIMESTAMP emails.db

# Option 3: Manual SQL Rollback
sqlite3 emails.db < rollback_phase12.sql
```

---

## 📊 Impact Summary

| Aspect | Before | After | Gain |
|--------|--------|-------|------|
| DB Size (10k Mails) | 100 MB | 106 MB | +6% |
| Unread Query | `LIKE '%Seen%'` | `is_seen = false` | 200-300% faster |
| Threading | Impossible | `thread_id = ?` | ✅ New Feature |
| Fetch Time | 100% | ~110% | +10% acceptable |
| Message-Size Sorting | N/A | `ORDER BY size DESC` | ✅ New Feature |

---

## 🎯 Success Criteria

Phase 12 ist **DONE** wenn:

- ✅ All new columns added & indexed
- ✅ Data migration completed without errors
- ✅ Boolean flags working correctly
- ✅ Thread-ID calculation validated
- ✅ Envelope-parsing tested against 3+ providers
- ✅ Query performance improved 200%+
- ✅ CHANGELOG.md updated
- ✅ Backward-compatibility maintained (imap_flags still readable)
- ✅ Zero data loss
- ✅ Rollback tested & working

---

## 📚 Reference Files

- `doc/next_steps/METADATA_ANALYSIS.md` - Full Analysis & Requirements
- `migrations/versions/ph12_metadata_enrichment.py` - Database Migration
- `scripts/populate_metadata_phase12.py` - Data Migration Script
- `tests/test_envelope_parsing.py` - Envelope Parsing Tests
- `tests/test_metadata_extraction.py` - Unit Tests (TBD)

---

**Ready to begin?** Start with PHASE 12.1 (Models Update) 🚀
