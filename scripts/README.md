# Scripts Overview

Utility scripts for maintenance, debugging, testing, and documentation.

## 🔧 Maintenance & Operations

### `manage_users.py`
User management for invite-whitelist and IMAP-diagnostics access (Phase INV).
```bash
# Whitelist Management
python3 scripts/manage_users.py add-whitelist user@example.com
python3 scripts/manage_users.py remove-whitelist user@example.com
python3 scripts/manage_users.py list-whitelist

# IMAP-Diagnostics Access
python3 scripts/manage_users.py enable-diagnostics admin@example.com
python3 scripts/manage_users.py disable-diagnostics admin@example.com
python3 scripts/manage_users.py list-diagnostics
```
**Use cases:** Invite new users after first registration, grant/revoke IMAP-diagnostics access.  
**Note:** First user can register freely, all subsequent users need whitelist entry.

### `backup_database.sh`
Automated database backups with WAL-checkpoint, compression, and validation.

🐛 **Bug-015 Fix:** Enhanced validation ensures backup integrity.

```bash
chmod +x scripts/backup_database.sh
./backup_database.sh          # Daily backup (30-day retention)
./backup_database.sh weekly   # Weekly backup (90-day retention)
```

**Features:**
- WAL checkpoint before backup (ensures consistency)
- PRAGMA integrity_check validation
- Compression (gzip)
- Table count verification
- Data sanity checks (users, emails counts)
- Automatic cleanup of old backups

**Crontab setup (optional):**
```bash
0 2 * * * /path/to/scripts/backup_database.sh         # Daily 2:00 AM
0 3 * * 0 /path/to/scripts/backup_database.sh weekly  # Sunday 3:00 AM
```

### `test_backup_restore.sh`
Test if backups are actually restorable (Bug-015 Fix).

🐛 **Bug-015 Fix:** Validates that backups can be restored successfully.

```bash
chmod +x scripts/test_backup_restore.sh
./test_backup_restore.sh                           # Test newest backup
./test_backup_restore.sh backups/daily/emails_*.gz # Test specific backup
```

**Tests performed:**
1. ✅ Decompression (gzip)
2. ✅ SQLite Integrity Check
3. ✅ Schema Validation (13 tables expected)
4. ✅ Critical tables exist (users, raw_emails, processed_emails, etc.)
5. ✅ Schema version (Alembic)
6. ✅ Data sanity checks (counts)
7. ✅ Complex queries (JOINs)
8. ✅ Encryption schema intact

**Output:**
```
✅ Backup Restore Test PASSED

📊 Summary:
   Backup File: emails_20260105_143456.db.gz
   Database Size: 1.3M
   Tables: 13
   Users: 1
   Emails: 47
   Schema Version: ph_inv_001

✅ This backup is RESTORABLE and VALID
```

**Best Practice:** Run after every backup before major development work:
```bash
./scripts/backup_database.sh && ./scripts/test_backup_restore.sh
```

### `reset_base_pass.py`
Clear all ProcessedEmail entries to trigger re-analysis by AI.
```bash
python3 scripts/reset_base_pass.py              # All emails
python3 scripts/reset_base_pass.py --account=1  # Specific account
python3 scripts/reset_base_pass.py --force      # Skip confirmation
```
**Use cases:** After AI provider/model change, prompt tuning, or quality issues.

### `reset_all_emails.py`
Delete ALL emails (Raw + Processed) for complete account reset.
```bash
python3 scripts/reset_all_emails.py --account=1
python3 scripts/reset_all_emails.py --account=1 --hard-delete --force
```
**Use cases:** Corrupted data, UIDVALIDITY conflicts, factory reset.  
**Note:** Use `--hard-delete` for clean re-fetch without UID conflicts.

### `clear_tag_embedding_cache.py`
Clear tag embedding cache.
```bash
python3 scripts/clear_tag_embedding_cache.py
```
**Use cases:** After embedding model change, tag suggestion issues.

---

## 🔍 Debug & Verification

### `check_db.py`
Quick database status check (users, accounts, email counts).
```bash
python3 scripts/check_db.py
```

### `encrypt_db_verification.py`
Comprehensive Zero-Knowledge encryption verification.
```bash
python3 scripts/encrypt_db_verification.py
```
**Checks:** Salt, Master-Key, 2FA status, encrypted account credentials.

### `verify_wal_mode.py`
Verify SQLite WAL configuration and settings.
```bash
python3 scripts/verify_wal_mode.py
python3 scripts/verify_wal_mode.py emails.db
```
**Checks:** journal_mode=WAL, busy_timeout, wal_autocheckpoint, synchronous.  
**Use cases:** SQLITE_BUSY errors, concurrent access issues.

### `list_openai_models.py`
List and probe OpenAI API models.
```bash
python3 scripts/list_openai_models.py
python3 scripts/list_openai_models.py --probe  # API testing
python3 scripts/list_openai_models.py --json   # JSON output
```
**Requires:** `OPENAI_API_KEY` in `.env`

---

## 📝 Documentation & Review

### `automated_code_review.py`
AI-powered code review using Claude API (45KB comprehensive tool).
```bash
python3 scripts/automated_code_review.py                # Standard review
python3 scripts/automated_code_review.py --context deep # Deep review
```
**Requires:** `ANTHROPIC_API_KEY` in `.env`  
**See:** [CODE_REVIEW_TOOL.md](CODE_REVIEW_TOOL.md) for details.

### `merge_files_for_review.py`
Merge multiple files for manual AI review.
```bash
python3 scripts/merge_files_for_review.py src templates
python3 scripts/merge_files_for_review.py "*.md"
```
**Output:** `review_merged_python.txt`, `review_merged_html.txt`, etc.

### `extract_commits.py`
Extract Git history to structured Markdown.
```bash
python3 scripts/extract_commits.py
python3 scripts/extract_commits.py --since="2025-01-01"
```

---

## 🧪 Tests

### `test_race_condition_lockout.py`
Test race condition protection in account lockout mechanism.
```bash
python3 scripts/test_race_condition_lockout.py
```

### `test_redos_protection.py`
Test ReDoS (Regex Denial of Service) protection.
```bash
python3 scripts/test_redos_protection.py
```

### `test_concurrent_access.py`
Test multi-threaded database access with WAL mode.
```bash
python3 scripts/test_concurrent_access.py
```

### `test_audit_logs.py`
Test audit logging functionality.
```bash
python3 scripts/test_audit_logs.py
```

---

## 🤖 ML/Future

### `train_classifier.py`
Machine learning classifier training skeleton (for future features).
```bash
python3 scripts/train_classifier.py
```
**Requires:** `scikit-learn`, `joblib` (see `requirements-ml.txt`)  
**Status:** Prepared for Phase 11 ML features.

---

## 📦 Archive

`_archive/` contains completed one-time migration scripts:
- `migrate_account_lockout.py` - Phase 9: Account lockout columns
- `migrate_to_dek_kek.py` - Phase 8: DEK/KEK encryption
- `migrate_uidvalidity_data.py` - Phase 14a: UIDVALIDITY backfill
- `populate_metadata_phase12.py` - Phase 12: Boolean flags from imap_flags
- `backfill_phase12_threads.py` - Phase 12: Thread IDs backfill

These scripts were used for database migrations and are kept for reference only.
