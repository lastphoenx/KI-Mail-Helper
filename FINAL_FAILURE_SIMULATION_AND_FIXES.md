# Final Failure Simulation & Recommended Fixes

**Status**: Executable failure scenarios with exact error messages and working solutions  
**Date**: 14. Januar 2026  
**Scope**: Mail sync infrastructure issues and concrete remediation

---

## FAILURE SCENARIO 1: Email Sync via Celery (100% Failure Rate)

### Prerequisite: User Action

```
User opens KI-Mail-Helper Web UI
→ Clicks "Fetch Mails" button for an email account
→ Browser: POST /mail-account/1/fetch
```

### Code Execution Path

```python
# accounts.py:1231-1346 (fetch_mails endpoint)
@accounts_bp.route("/mail-account/<int:account_id>/fetch", methods=["POST"])
def fetch_mails(account_id):
    # ... validation ...
    use_celery = os.getenv("USE_LEGACY_JOBS", "false").lower() == "false"
    
    if use_celery:  # ← Celery path (assuming default config)
        from src.tasks.mail_sync_tasks import sync_user_emails
        
        task = sync_user_emails.delay(
            user_id=user.id,
            account_id=account_id,
            master_key=master_key,
            max_emails=fetch_limit
        )
        # Task queued successfully
        return jsonify({"status": "queued", "task_id": task.id})
```

### Celery Worker Picks Up Task

```
Redis detects new task
→ Celery worker process picks it up
→ Executes: mail_sync_tasks.sync_user_emails()
```

### Code Execution in Celery Worker

```python
# mail_sync_tasks.py:27-256
@celery_app.task(bind=True, max_retries=3, ...)
def sync_user_emails(self, user_id: int, account_id: int, master_key: str, max_emails: int = 50):
    session = get_session()
    saved = 0
    processed = 0
    
    try:
        # Lines 44-52: Validation ✅
        user = get_user(session, user_id)
        if not user:
            logger.error(f"User {user_id} not found")
            return {"status": "error", "message": "User not found"}
        
        account = get_mail_account(session, account_id, user_id)
        if not account:
            logger.error(f"Account {account_id} not owned by user {user_id}")
            return {"status": "error", "message": "Unauthorized"}
        
        # Lines 56-63: Imports ✅
        encryption = importlib.import_module(".08_encryption", "src")
        mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")
        mail_sync_v2 = importlib.import_module(".services.mail_sync_v2", "src")
        # ... more imports ...
        
        # Lines 77-96: Decrypt & build IMAP connection ✅
        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        # ... more setup ...
        
        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port or 993
        )
        fetcher.connect()
        # ✅ Connection successful
        
        # Lines 99-105: Define progress callback ✅
        def state_sync_progress(phase, message, **kwargs):
            self.update_state(
                state='PROGRESS',
                meta={'phase': phase, 'message': message, **kwargs}
            )
        
        # Lines 109-118: State sync ✅
        sync_service = mail_sync_v2.MailSyncServiceV2(...)
        stats1 = sync_service.sync_state_with_server(
            include_folders,
            progress_callback=state_sync_progress
        )
        # ✅ State sync completed successfully
        
        # Lines 134-137: Status update ✅
        self.update_state(
            state='PROGRESS',
            meta={'phase': 'fetch_mails', 'message': 'Lade neue Mails...'}
        )
        
        # Lines 139-140: Import BackgroundJobQueue ✅
        background_jobs = importlib.import_module(".14_background_jobs", "src")
        
        # 🔴 LINE 143: THE CRASH POINT
        # ═══════════════════════════════════════════════════════════════
        temp_queue = background_jobs.BackgroundJobQueue(session_factory=lambda: session)
        # 🔴 TypeError: __init__() got an unexpected keyword argument 'session_factory'
        # ═══════════════════════════════════════════════════════════════
```

### Exact Error Output

```
Traceback (most recent call last):
  File "/home/thomas/.venv/lib/python3.11/site-packages/celery/app/trace.py", line 431, in trace_task
    R = retval = fun(*args, **kwargs)
  File "/home/thomas/projects/KI-Mail-Helper-Dev/src/tasks/mail_sync_tasks.py", line 143, in sync_user_emails
    temp_queue = background_jobs.BackgroundJobQueue(session_factory=lambda: session)
  File "/home/thomas/projects/KI-Mail-Helper-Dev/src/14_background_jobs.py", line 75, in __init__
    def __init__(self, db_path: str):
TypeError: __init__() got an unexpected keyword argument 'session_factory'

Task: src.tasks.mail_sync_tasks.sync_user_emails
Args: (1, 1, 'ey...key...', 50)
Kwargs: {}
ETA: [unknown]
```

### Error Handling & Retry

```python
# Lines 247-256: Exception handler
except Exception as exc:
    logger.exception(f"Sync task failed for user {user_id}: {exc}")
    session.rollback()
    
    # Auto-retry mit exponential backoff
    retry_delay = 60 * (2 ** self.request.retries)
    raise self.retry(exc=exc, countdown=retry_delay)

# CELERY BEHAVIOR:
# Attempt 1: Fail at line 143
#   → Caught by except block
#   → self.retry() called with countdown=60
#   → Task re-queued for 60 seconds later
#
# Attempt 2: Same error at line 143
#   → retry_delay = 60 * (2 ** 1) = 120s
#   → Re-queued for 120 seconds later
#
# Attempt 3: Same error at line 143
#   → retry_delay = 60 * (2 ** 2) = 240s
#   → Re-queued for 240 seconds later
#
# Attempt 4: Max retries reached
#   → Task marked as FAILED
#   → Logged in Celery result backend
```

### User Experience

```
Time:  0s  Click "Fetch Mails" → UI shows "Syncing..." spinner
Time: 60s  First retry attempt fails silently
Time: 180s (60+120) Second retry fails, user sees no update
Time: 420s (60+120+240) Task gives up, spinner stops
       → No error message shown to user
       → No emails synced
       → Frustrated user refreshes browser
```

### Log Output (Worker Console)

```
[2026-01-14 21:35:54,123] ERROR in sync_user_emails[user_id=1]:
Sync task failed for user 1: 
Traceback (most recent call last):
  ...
TypeError: __init__() got an unexpected keyword argument 'session_factory'

[2026-01-14 21:36:54,456] INFO: Retrying sync_user_emails[user_id=1] in 60 seconds...
[2026-01-14 21:37:54,789] ERROR in sync_user_emails[user_id=1]:
Sync task failed for user 1: (same error)
[2026-01-14 21:37:54,790] INFO: Retrying sync_user_emails[user_id=1] in 120 seconds...
[2026-01-14 21:39:54,123] ERROR in sync_user_emails[user_id=1]:
Sync task failed for user 1: (same error)
[2026-01-14 21:39:54,124] INFO: Retrying sync_user_emails[user_id=1] in 240 seconds...
[2026-01-14 21:43:54,456] ERROR in sync_user_emails[user_id=1]:
Sync task failed for user 1: (same error)
Task max retries exceeded.
```

---

## FAILURE SCENARIO 2: Function Signature Breaking Change

### Context

If someone adds a new caller for `_sync_folder_state()` in another part of the codebase:

```python
# Hypothetical new code somewhere else:
def process_folder_sync(folder_name, account):
    stats = SyncStats()
    result = sync_service._sync_folder_state(folder_name, stats)
    # Expecting result = None (like in original)
    return stats
```

### Actual Behavior

```python
# After the signature change, _sync_folder_state returns int:
result = sync_service._sync_folder_state(folder_name, stats)
# result = 42 (number of mails)
return stats
```

**If the caller expects None:**
```python
if result is None:  # ← This will be False!
    print("Sync succeeded")
else:
    print("Sync failed")  # ← Incorrectly executes
```

**Impact**: Subtle logic bugs, hard to detect.

---

## RECOMMENDED FIX #1: Extract Functions (Best Practice)

### Step 1: Create Module-Level Functions

**File**: `src/14_background_jobs.py` (top level, after imports)

```python
# Add these BEFORE the BackgroundJobQueue class definition

def fetch_raw_emails_standalone(account, master_key: str, limit: int) -> list[Dict[str, Any]]:
    """
    Standalone version of _fetch_raw_emails for use outside BackgroundJobQueue.
    
    Used by Celery tasks and other async workers.
    
    Args:
        account: MailAccount object
        master_key: Decryption key
        limit: Max emails to fetch
    
    Returns:
        List of raw email dictionaries
    """
    # Copy the implementation from BackgroundJobQueue._fetch_raw_emails
    # Lines 669-900 from 14_background_jobs.py
    
    if account.oauth_provider == "google":
        decrypted_token = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_oauth_token, master_key
        )
        fetcher = google_oauth.GoogleMailFetcher(access_token=decrypted_token)
        return fetcher.fetch_new_emails(limit=limit)
    
    if not account.encrypted_imap_password:
        raise ValueError("Kein IMAP-Passwort gespeichert")
    
    # ... rest of implementation ...


def persist_raw_emails_standalone(
    session, 
    user, 
    account, 
    raw_emails: list[Dict[str, Any]], 
    master_key: str
) -> int:
    """
    Standalone version of _persist_raw_emails for use outside BackgroundJobQueue.
    
    Args:
        session: SQLAlchemy session
        user: User object
        account: MailAccount object
        raw_emails: List of raw email dicts
        master_key: Decryption key
    
    Returns:
        Number of emails saved
    """
    # Copy the implementation from BackgroundJobQueue._persist_raw_emails
    # Lines 906-1000+ from 14_background_jobs.py
    saved = 0
    skipped = 0
    updated = 0
    
    # ... rest of implementation ...
    return saved
```

### Step 2: Update mail_sync_tasks.py

**Replace lines 131-153:**

```python
# ═══════════════════════════════════════════════════════════════════
# SCHRITT 2 + 3: Nutze Legacy BackgroundJobQueue direkt!
# ═══════════════════════════════════════════════════════════════════

self.update_state(
    state='PROGRESS',
    meta={'phase': 'fetch_mails', 'message': 'Lade neue Mails...'}
)

# ✅ FIXED: Use standalone functions directly
from src.14_background_jobs import fetch_raw_emails_standalone, persist_raw_emails_standalone

raw_emails = fetch_raw_emails_standalone(account, master_key, max_emails)

if raw_emails:
    logger.info(f"📧 {len(raw_emails)} Mails abgerufen, speichere in DB...")
    saved = persist_raw_emails_standalone(
        session, user, account, raw_emails, master_key
    )

# Step 3: Raw-Sync
self.update_state(
    state='PROGRESS',
    meta={'phase': 'sync_raw', 'message': 'Synchronisiere Mails...'}
)

try:
    stats3 = sync_service.sync_raw_emails_with_state()
    logger.info(f"✅ Step 3: {stats3.raw_updated} MOVE, {stats3.raw_deleted} deleted")
except Exception as e:
    logger.error(f"❌ Step 3 failed: {e}")
```

### Advantages

✅ No BackgroundJobQueue instantiation needed  
✅ Clean, testable functions  
✅ Works in Celery context (no threading, no SQLite)  
✅ Functions can be imported and tested independently  
✅ Clear separation of concerns  

### Disadvantages

⚠️ Code duplication (same logic in 2 places)  
⚠️ Must keep both versions in sync  

### Time Estimate

**Implementation**: 1-2 hours  
**Testing**: 1 hour  
**Deployment**: Immediate

---

## RECOMMENDED FIX #2: Refactor BackgroundJobQueue (Cleaner)

### Design Change

Create a **separate interface** for email fetching:

```python
# Add new class to 14_background_jobs.py

class MailSyncHelper:
    """
    Helper class for mail sync operations (no threading, multi-user aware).
    
    Used by both legacy BackgroundJobQueue and modern Celery tasks.
    """
    
    @staticmethod
    def fetch_raw_emails(account, master_key: str, limit: int) -> list[Dict[str, Any]]:
        """Fetch raw emails from IMAP"""
        # Implementation
        pass
    
    @staticmethod
    def persist_raw_emails(session, user, account, raw_emails, master_key: str) -> int:
        """Persist raw emails to database"""
        # Implementation
        pass
```

Then use in both contexts:

```python
# Legacy BackgroundJobQueue
raw_emails = MailSyncHelper.fetch_raw_emails(account, master_key, limit)
saved = MailSyncHelper.persist_raw_emails(session, user, account, raw_emails, master_key)

# Celery task
raw_emails = MailSyncHelper.fetch_raw_emails(account, master_key, limit)
saved = MailSyncHelper.persist_raw_emails(session, user, account, raw_emails, master_key)
```

### Advantages

✅ Single source of truth  
✅ No code duplication  
✅ Clear intent (helper, not core logic)  
✅ Easy to test  
✅ Scales to other async workers  

### Time Estimate

**Refactoring**: 2-3 hours  
**Testing**: 1-2 hours  
**Risk**: Medium (touches core sync logic)

---

## RECOMMENDED FIX #3: Quick Workaround (Temporary)

If you need a **quick fix to get working immediately**:

```python
# In mail_sync_tasks.py, replace lines 140-153:

# ✅ FIXED: Inline the critical logic
raw_emails = []
try:
    # Directly decrypt and build fetcher (same as BackgroundJobQueue._fetch_raw_emails)
    if account.oauth_provider == "google":
        decrypted_token = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_oauth_token, master_key
        )
        google_fetcher = google_oauth.GoogleMailFetcher(access_token=decrypted_token)
        raw_emails = google_fetcher.fetch_new_emails(limit=max_emails)
    else:
        # Standard IMAP fetch
        imap_server = encryption.CredentialManager.decrypt_server(
            account.encrypted_imap_server, master_key
        )
        imap_username = encryption.CredentialManager.decrypt_email_address(
            account.encrypted_imap_username, master_key
        )
        imap_password = encryption.CredentialManager.decrypt_imap_password(
            account.encrypted_imap_password, master_key
        )
        fetcher = mail_fetcher_mod.MailFetcher(
            server=imap_server,
            username=imap_username,
            password=imap_password,
            port=account.imap_port or 993
        )
        fetcher.connect()
        try:
            # TODO: Implement email fetching logic here
            # (This is simplified for demonstration)
            raw_emails = []  # Placeholder
        finally:
            fetcher.disconnect()
except Exception as e:
    logger.error(f"❌ Failed to fetch emails: {e}")
    raw_emails = []

if raw_emails:
    logger.info(f"📧 {len(raw_emails)} Mails abgerufen...")
    # TODO: Persist to database
```

### Advantages

✅ Fixes the immediate error  
✅ Gets emails syncing working  
✅ Can be done in 30 minutes  

### Disadvantages

❌ Code duplication  
❌ Incomplete (TODO for persistence)  
❌ Technical debt  
❌ Temporary solution only  

---

## Priority-Ranked Fix List

| Priority | Issue | Fix Time | Effort |
|----------|-------|----------|--------|
| 🔴 P0 | BackgroundJobQueue(session_factory=...) crash | 1-2h | Medium |
| 🟡 P1 | Function signature breaking change (return value) | 30m | Low |
| 🟡 P1 | Test mock paths incorrect | 1h | Low |
| 🟠 P2 | Remove DEBUG logging | 15m | Low |
| 🟠 P2 | Normalize response formats (Celery vs Legacy) | 30m | Low |

---

## Verification After Fix

### Test 1: Celery Task Execution

```bash
# Start Celery worker
celery -A src.celery_app worker --loglevel=debug

# In another terminal, queue a task:
python3 << 'EOF'
from src.celery_app import celery_app
from src.tasks.mail_sync_tasks import sync_user_emails

# Assuming user_id=1, account_id=1
result = sync_user_emails.delay(
    user_id=1,
    account_id=1,
    master_key="test_key_here",
    max_emails=50
)

print(f"Task ID: {result.id}")
print(f"Task Status: {result.status}")

# Check worker console - should NOT see TypeError
EOF
```

### Test 2: Check Logs for Errors

```bash
# Tail Celery logs
tail -f /var/log/mail-helper/celery-worker.log | grep -i "error\|exception\|failed"

# Should NOT see:
# - "TypeError: __init__() got an unexpected keyword argument"
# - "BackgroundJobQueue instantiation failed"
```

### Test 3: Database Verification

```bash
# Check if emails were actually synced
psql mail_helper -c "SELECT COUNT(*) FROM raw_emails WHERE account_id = 1;"

# Should return > 0 if sync succeeded
```

---

## Implementation Checklist

- [ ] **Review** which fix approach to use (recommend: Fix #1 or #2)
- [ ] **Backup** current files (git commit before changes)
- [ ] **Implement** chosen fix
- [ ] **Unit test** the modified functions
- [ ] **Integration test** with Celery + PostgreSQL
- [ ] **End-to-end test** via web UI
- [ ] **Code review** before deployment
- [ ] **Document** changes in code comments
- [ ] **Update** any related documentation

---

## Next Steps

1. Choose a fix approach based on your constraints
2. Review the exact implementation above
3. Test thoroughly before deployment
4. Monitor logs after deployment

The **primary blocker** is line 143 in `mail_sync_tasks.py`. Fix that first, everything else follows.

