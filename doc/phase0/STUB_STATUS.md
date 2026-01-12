# STUB_STATUS.md

**Status:** Audit-Report für Soll/Ist-Abgleich  
**Datum:** 12. Januar 2026  
**Zweck:** Schnelle Übersicht welche Routes/Functions implementiert vs. Stubs sind

---

## 🟢 FULLY IMPLEMENTED (110+ Routes)

### auth.py (7/7 ✅)
- [x] `/` - index
- [x] `/login` - login
- [x] `/register` - register
- [x] `/2fa/verify` - verify_2fa
- [x] `/logout` - logout
- [x] `/settings/2fa/setup` - setup_2fa
- [x] `/settings/2fa/recovery-codes/regenerate` - regenerate_recovery_codes

### emails.py (5/5 ✅)
- [x] `/dashboard` - dashboard
- [x] `/list` - list_view
- [x] `/threads` - threads_view
- [x] `/email/<id>` - email_detail
- [x] `/email/<id>/render-html` - render_email_html

### email_actions.py (11/11 ✅)
- [x] `/email/<id>/done` - mark_done
- [x] `/email/<id>/undo` - mark_undone
- [x] `/email/<id>/reprocess` - reprocess_email ⚠️ (TODO in implementation)
- [x] `/email/<id>/optimize` - optimize_email
- [x] `/email/<id>/correct` - correct_email
- [x] `/email/<id>/delete` - delete_email
- [x] `/email/<id>/move-trash` - move_email_to_trash
- [x] `/email/<id>/move-to-folder` - move_email_to_folder
- [x] `/email/<id>/mark-read` - mark_email_read
- [x] `/email/<id>/toggle-read` - toggle_email_read
- [x] `/email/<id>/mark-flag` - toggle_email_flag

### tags.py (2/2 ✅)
- [x] `/tags` - tags_view
- [x] `/tag-suggestions` - tag_suggestions_page

### rules.py (10/10 ✅)
- [x] `/rules` - rules_management
- [x] `/api/rules` GET - api_get_rules
- [x] `/api/rules` POST - api_create_rule
- [x] `/api/rules/<id>` PUT - api_update_rule
- [x] `/api/rules/<id>` DELETE - api_delete_rule
- [x] `/api/rules/<id>/test` POST - api_test_rule
- [x] `/api/rules/apply` POST - api_apply_rules
- [x] `/api/rules/templates` GET - api_get_rule_templates
- [x] `/api/rules/templates/<name>` POST - api_create_rule_from_template
- [x] `/rules/execution-log` GET - rules_execution_log

### training.py (1/1 ✅)
- [x] `/retrain` POST - retrain_models

### admin.py (1/1 ✅)
- [x] `/api/debug-logger-status` GET - api_debug_logger_status

### accounts.py (20/22 ⚠️)
- [x] `/reply-styles` - reply_styles_page
- [x] `/settings` - settings
- [x] `/mail-fetch-config` - mail_fetch_config
- [x] `/whitelist` - whitelist
- [x] `/ki-prio` - ki_prio
- [x] `/settings/fetch-config` POST - save_fetch_config
- [x] `/account/<id>/fetch-filters` GET - get_account_fetch_filters
- [x] `/settings/ai` POST - save_ai_preferences
- [x] `/settings/password` GET/POST - change_password
- [x] `/settings/mail-account/select-type` GET - select_account_type
- [x] `/settings/mail-account/google-setup` GET/POST - google_oauth_setup
- [x] `/settings/mail-account/google/callback` GET - google_oauth_callback
- [ ] `/settings/mail-account/add` GET/POST - add_mail_account ❌ STUB
- [ ] `/settings/mail-account/<id>/edit` GET/POST - edit_mail_account ❌ STUB
- [x] `/settings/mail-account/<id>/delete` POST - delete_mail_account
- [x] `/imap-diagnostics` GET - imap_diagnostics
- [x] `/mail-account/<id>/fetch` POST - fetch_mails
- [x] `/mail-account/<id>/purge` POST - purge_mail_account
- [x] `/jobs/<job_id>` GET - job_status
- [ ] `/account/<id>/mail-count` GET - get_account_mail_count ❌ TODO
- [ ] `/account/<id>/folders` GET - get_account_folders ❌ TODO
- [x] `/whitelist-imap-setup` GET - whitelist_imap_setup_page

### api.py (58/65 ❌)

**Fully Implemented (58):**
- [x] Email operations (flags, tags, suggestions)
- [x] Tag CRUD (create, read, update, delete)
- [x] VIP Senders (create, read, update, delete)
- [x] Keyword Sets (get, save)
- [x] Scoring Config (get, save)
- [x] User Domains (get, create, delete)
- [x] Reply Styles (get, save, delete, preview)
- [x] Rule Management (get, create, update, delete, test, apply, templates)
- [x] Accounts (get)
- [x] Models (get, available)
- [x] Providers (available)
- [x] Training Stats (get)
- [x] IMAP Diagnostics (get)
- [x] Trusted Senders (get, add, update, delete)
- [x] Urgency Booster (get, save, settings, per-account)
- [x] Trusted Sender Suggestions (get)

**Missing/Stubs (7):**
- [ ] `/emails/<id>/similar` GET ❌ TODO
- [ ] `/emails/<id>/generate-reply` POST ❌ 501 Not Implemented
- [ ] `/emails/<id>/reprocess` POST ❌ TODO  
- [ ] `/tag-suggestions/<id>/approve` POST ❌ 501
- [ ] `/tag-suggestions/<id>/reject` POST ❌ 501
- [ ] `/tag-suggestions/<id>/merge` POST ❌ 501
- [ ] `/tag-suggestions/batch-reject` POST ❌ 501
- [ ] `/tag-suggestions/batch-approve` POST ❌ 501
- [ ] `/phase-y/keyword-sets` POST ❌ 501
- [ ] `/phase-y/user-domains` POST ❌ 501
- [ ] `/search/semantic` GET ❌ TODO

---

## 🔴 CRITICAL MISSING ROUTES (Not in blueprints at all)

| Route | Original Line | Status | Impact |
|-------|--------------|--------|--------|
| `/api/scan-account-senders` POST | 9035 | ❌ MISSING | Trusted-Sender Workflow broken |
| `/api/bulk-add-trusted-senders` POST | 9156 | ❌ MISSING | Whitelist setup incomplete |

---

## 🟡 STUBS WITH 501 (Placeholders)

```python
# These return HTTP 501 "Not Implemented"
api_reject_tag_suggestion()           # Line 856
api_merge_tag_suggestion()            # Line 893
api_batch_reject_suggestions()        # Line 943
api_batch_approve_suggestions()       # Line 982
# ... plus Phase Y endpoints
```

---

## 🟠 STUBS WITH TODO (Partial Implementation)

```python
# These have code but marked with TODO
api_semantic_search()                 # Line 1544: "TODO: Embedding-basierte Suche"
api_get_similar_emails()              # Line 478: "TODO: Embedding-basierte Suche"
api_generate_reply()                  # Line 501: "TODO: Vollständige AI-Reply Generation"
api_reprocess_email()                 # Line 557: "TODO: Full reprocessing pipeline"

# accounts.py stubs
add_mail_account()                    # Line 724: "Feature wird implementiert"
edit_mail_account()                   # Line 734: "Feature wird implementiert"
get_account_mail_count()              # Line 936: "TODO: IMAP-Abfrage"
get_account_folders()                 # Line 967: "TODO: IMAP-Ordner-Abfrage"
```

---

## 📊 SUMMARY BY STATUS

| Status | Count | Blueprint | Details |
|--------|-------|-----------|---------|
| ✅ Fully Implemented | 110+ | All | Ready for production |
| ⚠️ Partial/TODO | 13 | api, accounts | Needs completion |
| ❌ 501 Stubs | 7 | api | Feature not available |
| ❌ MISSING | 2 | - | Never in blueprints |
| **TOTAL** | **123** | 9 | |

---

## 🔧 QUICK TEST COMMANDS

```bash
# Test missing routes (should 404)
curl http://localhost:5000/api/scan-account-senders
curl http://localhost:5000/api/bulk-add-trusted-senders

# Test 501 routes
curl http://localhost:5000/api/emails/123/generate-reply

# Test TODO routes
curl http://localhost:5000/api/emails/123/similar
curl http://localhost:5000/api/account/1/mail-count
curl http://localhost:5000/api/account/1/folders

# Test stubs (GET /settings/mail-account/add should show form)
curl http://localhost:5000/settings/mail-account/add

# Test 403 on auth=false
curl -H "Authorization: Bearer invalid" http://localhost:5000/api/tags
```

---

## 📋 REFERENCE: Where to Find Implementations

| Feature | Original File | Lines | Stub Location |
|---------|--------------|-------|----------------|
| Generate Reply | 01_web_app.py | 4278-4600 | api.py:487 |
| Similar Emails | 01_web_app.py | 4126-4280 | api.py:464 |
| Scan Senders | 01_web_app.py | 9035-9155 | ❌ MISSING |
| Bulk Add Senders | 01_web_app.py | 9156-9300 | ❌ MISSING |
| Add Mail Account | 01_web_app.py | 6809-6939 | accounts.py:720 |
| Edit Mail Account | 01_web_app.py | 6941-7153 | accounts.py:731 |
| Mail Count | 01_web_app.py | 7763-7960 | accounts.py:909 |
| Folders | 01_web_app.py | 7955-8020 | accounts.py:947 |

---

**For detailed analysis, see: IMPLEMENTATION_STATUS.md**
