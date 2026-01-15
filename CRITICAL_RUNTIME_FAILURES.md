# Critical Runtime Failures Analysis

**Status**: 🔴 **WILL CRASH IN PRODUCTION**  
**Last Updated**: 14. Januar 2026  
**Severity**: CRITICAL - Task execution will fail with unhandled exceptions

---

## Identified Runtime Failures

### Failure #1: BackgroundJobQueue Instantiation Error
**File**: `src/tasks/mail_sync_tasks.py`  
**Line**: 143  
**Severity**: 🔴 **CRITICAL** - Blocks task execution

#### Error Details

```python
# CURRENT CODE (Line 143)
temp_queue = background_jobs.BackgroundJobQueue(session_factory=lambda: session)

# ACTUAL SIGNATURE
def __init__(self, db_path: str):
    self.db_path = db_path
    ...
```

#### Runtime Error
```
TypeError: __init__() got an unexpected keyword argument 'session_factory'
```

#### Impact Chain
1. User clicks "Fetch Mails" in web UI
2. `accounts.py` endpoint routes to Celery task `sync_user_emails.delay()`
3. Celery worker executes `sync_user_emails()` in `mail_sync_tasks.py`
4. **Line 143** attempts instantiation: `BackgroundJobQueue(session_factory=lambda: session)`
5. ❌ **TypeError raised** → Task execution fails
6. Celery auto-retry triggered (up to 3 times)
7. ❌ **Task marked as FAILED** after all retries exhausted
8. User sees: "Internal server error" or perpetual "loading..." state

#### Root Cause
The author confused the initialization signature:
- **Expected**: `BackgroundJobQueue(session_factory=...)`
- **Actual**: `BackgroundJobQueue(db_path="/path/to/database.db")`

The `BackgroundJobQueue` class is designed for **single-user SQLite** with a filesystem path, not multi-user PostgreSQL with session management.

---

### Failure #2: Method Dependencies on Uninitialized State
**File**: `src/tasks/mail_sync_tasks.py`  
**Lines**: 146, 151-153  
**Severity**: 🔴 **CRITICAL** - Even if instantiation works, execution will fail

#### Error Scenario

Even if the instantiation error is fixed, the methods being called have undisclosed dependencies:

```python
# Line 143 (FIXED hypothetically)
temp_queue = background_jobs.BackgroundJobQueue("/tmp/dummy.db")

# Line 146 - Will this work?
raw_emails = temp_queue._fetch_raw_emails(account, master_key, max_emails)
```

#### Issues

1. **Method expects instance state from __init__**
   - `_fetch_raw_emails()` is an instance method
   - It references `self.models`, `self.encryption`, etc.
   - These are set up during normal `BackgroundJobQueue` initialization for single-user jobs
   - In Celery context, these may not be properly initialized

2. **Missing SessionFactory for Legacy Queue**
   - `BackgroundJobQueue._init_session_factory()` calls `models.init_db(self.db_path)`
   - This creates a session connected to SQLite database
   - But the Celery task already has PostgreSQL session from `get_session()`
   - ❌ **Mismatch**: Legacy queue tries to use SQLite, Celery has PostgreSQL

3. **Undocumented State Dependencies**
   - Looking at `_fetch_raw_emails()` implementation (line 652-xxx):
   ```python
   def _fetch_raw_emails(self, account, master_key: str, limit: int) -> list[Dict]:
       # References: self.models, encryption (imported), etc.
       # But these are instance variables or module-level?
   ```
   - Not clear if all required state is initialized

---

### Failure #3: Function Signature Mismatch - _sync_folder_state Return Type

**File**: `src/services/mail_sync_v2.py`  
**Location**: Line 179 in `sync_state_with_server()`, Line 205+ in `_sync_folder_state()`  
**Severity**: 🟡 **MEDIUM** - Runtime error if not handled

#### Error Details

```python
# CURRENT CODE (Line 179)
folder_mail_count = self._sync_folder_state(folder, stats, progress_callback)

# But ALSO called from legacy 14_background_jobs.py
# OLD CODE (doesn't capture return value)
self._sync_folder_state(folder, stats)  # Returns None
```

#### Function Return Type Changed

```python
# BACKUP VERSION (Line 174)
def _sync_folder_state(self, folder: str, stats: SyncStats):
    # ... no return statement
    # Returns: None (implicit)

# CURRENT VERSION (Line 205-310)
def _sync_folder_state(self, folder: str, stats: SyncStats, progress_callback=None):
    # ... processing ...
    return len(server_mails)  # Line 314
    # Also returns 0 on exception (Line 318)
```

#### Impact

If legacy code in `14_background_jobs.py` was NOT updated to handle the return value:

```python
# If 14_background_jobs.py still has OLD CALLING CODE
self._sync_folder_state(folder, stats)  # No assignment
# THEN folder_mail_count is undefined → NameError
```

**Verification needed**: Check if `14_background_jobs.py` was updated for the new signature

---

### Failure #4: Incorrect Mock Patches in Tests

**File**: `tests/test_mail_sync_tasks.py`  
**Lines**: 35, 45  
**Severity**: 🟡 **MEDIUM** - Tests won't fail (but give false confidence)

#### Broken Mocks

```python
# Line 35: WRONG - Function doesn't exist
@patch('src.tasks.mail_sync_tasks.decrypt_imap_credentials')
# What SHOULD be mocked:
@patch('src.encryption.CredentialManager.decrypt_server')

# Line 45: WRONG - Not directly imported
@patch('src.tasks.mail_sync_tasks.IMAPClient')
# What SHOULD be mocked:
@patch('src.mail_fetcher.MailFetcher')
```

#### Impact

- ✅ Tests will "pass" (mocks are never actually invoked)
- ❌ Coverage is fake - real code paths never tested
- ❌ Runtime errors will only surface in production

---

## Execution Flow Analysis: Where It Breaks

```
User: Click "Fetch Mails" Button
  ↓
Blueprint accounts.py:1283
  ├─ Check: USE_LEGACY_JOBS = false → use Celery ✓
  └─ Queue: sync_user_emails.delay(user_id, account_id, master_key, max_emails)
    ↓
Celery Worker picks up task
  ↓
mail_sync_tasks.sync_user_emails() starts
  ├─ Line 38-52: Session + User/Account validation ✓
  ├─ Line 56-63: Import modules ✓
  ├─ Line 77-86: Decrypt IMAP credentials ✓
  ├─ Line 90-96: Build and connect MailFetcher ✓
  ├─ Line 109-117: Call sync_state_with_server() ✓
  ├─ Line 134-136: Update status (fetch_mails phase) ✓
  │
  ├─ ❌ Line 143: CRASH HERE ❌
  │   temp_queue = BackgroundJobQueue(session_factory=lambda: session)
  │   TypeError: __init__() got unexpected keyword argument 'session_factory'
  │
  ├─ Exception handler (Line 247-249)
  ├─ Rollback session
  ├─ Retry task with exponential backoff
  │   └─ (Retries 3 times, then gives up)
  │
  └─ Task marked as FAILED
    ↓
User sees error (no email synced)
```

---

## Dependency Chain Issues

### Issue A: Session Management Incompatibility

**Legacy Architecture** (14_background_jobs.py):
```
BackgroundJobQueue.__init__(db_path: str)
  ├─ Creates SQLite session internally
  ├─ Sets self._SessionFactory
  └─ Methods use: db_path, _SessionFactory
```

**New Architecture** (Celery):
```
sync_user_emails(self, user_id, account_id, master_key, max_emails)
  ├─ Receives PostgreSQL session from get_session()
  ├─ Wants to use BackgroundJobQueue helper methods
  ├─ But BackgroundJobQueue expects SQLite + db_path
  └─ ❌ Architectural mismatch
```

**Solution Required**:
Either:
1. Extract `_fetch_raw_emails()` and `_persist_raw_emails()` as standalone functions
2. Create a new `CeleryCompatibleQueue` class for PostgreSQL/Redis
3. Rewrite the logic directly in Celery task (no reuse of BackgroundJobQueue)

---

### Issue B: Progress Callback Design Flaw

**Callback Definition** (mail_sync_tasks.py Line 99-105):
```python
def state_sync_progress(phase, message, **kwargs):
    self.update_state(
        state='PROGRESS',
        meta={'phase': phase, 'message': message, **kwargs}
    )
```

**Problem**: Uses `self.update_state()` which is:
- ✓ Available in Celery task context
- ✗ NOT available in `MailSyncServiceV2.sync_state_with_server()` context

**Usage** (mail_sync_v2.py Line 169-175):
```python
progress_callback(
    phase="state_sync_folder_start",
    message=f"Scanne Ordner '{folder}'...",
    folder_idx=idx,
    total_folders=total_folders,
    folder=folder
)
```

**The Callback Receives Arguments But:**
- It's a lambda-like closure in Celery context
- Calls `self.update_state()` where `self` = Celery task instance ✓
- This *should* work, but the test mocks won't catch issues

---

## Verification Checklist

- [ ] Verify `BackgroundJobQueue.__init__()` actually requires `db_path` or accepts `session_factory`
- [ ] Verify `_fetch_raw_emails()` signature matches usage: `(account, master_key, max_emails)`
- [ ] Verify `_persist_raw_emails()` signature matches usage: `(session, user, account, raw_emails, master_key)`
- [ ] Verify `14_background_jobs.py` was updated to capture return value from `_sync_folder_state()`
- [ ] Run Celery task in test environment and capture actual error messages
- [ ] Verify mock patches in tests actually intercept the right functions
- [ ] Test progress callback mechanism end-to-end
- [ ] Test with actual PostgreSQL + Redis + Celery worker

---

## Recommended Immediate Actions

### Priority 1: Fix Blocking Errors
1. **Fix instantiation** (Line 143):
   ```python
   # Option A: Don't use BackgroundJobQueue, extract methods
   from src.14_background_jobs import _fetch_raw_emails_standalone
   
   # Option B: Use correct initialization
   temp_queue = background_jobs.BackgroundJobQueue("/tmp/dummy.db")
   # BUT: This won't work with PostgreSQL
   
   # Option C: Rewrite logic directly in Celery task
   raw_emails = _fetch_raw_emails_from_imap(account, master_key, max_emails)
   ```

2. **Test immediately**:
   ```bash
   # Test the failing function in Celery context
   celery -A src.celery_app worker --loglevel=debug
   # Queue test task and observe actual error
   ```

### Priority 2: Fix Test Mocks
```python
# In test_mail_sync_tasks.py

# WRONG (Current):
@patch('src.tasks.mail_sync_tasks.decrypt_imap_credentials')

# CORRECT:
@patch('src.encryption.CredentialManager.decrypt_server')
@patch('src.encryption.CredentialManager.decrypt_email_address')
@patch('src.encryption.CredentialManager.decrypt_imap_password')
```

### Priority 3: Document Architecture Decision
Choose one approach:
- **A**: Keep using `BackgroundJobQueue` (refactor for multi-user/PostgreSQL)
- **B**: Extract helper methods and use in Celery
- **C**: Rewrite email sync logic entirely for Celery

Document the choice and update all related code.

---

## Conclusion

The current implementation has **multiple critical blocking errors** that will cause task failures at runtime. The code was not tested end-to-end with Celery and PostgreSQL, resulting in:

1. ✗ Type errors in initialization
2. ✗ Architectural mismatch (SQLite queue vs PostgreSQL session)
3. ✗ Untested mock paths (false test confidence)
4. ✗ Undefined function dependencies

**Recommendation**: Do not deploy to production without fixing these issues. The email sync feature will fail for all users attempting to fetch mails via the Celery path.

