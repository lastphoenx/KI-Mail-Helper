# Quick Test Guide: Phase X Account-Based Implementation

## What Was Implemented ✅

**Complete account-based whitelist system** for Phase X with:
- ✅ Database migration (ph19) deployed
- ✅ ORM model with account_id foreign key
- ✅ Service layer with account-aware methods
- ✅ 7 REST API endpoints updated with account_id handling
- ✅ Frontend UI with account selector
- ✅ JavaScript functions with account context

## Architecture

```
User selects account in UI
    ↓
Account ID passed to JavaScript
    ↓
JavaScript adds ?account_id=X to API calls
    ↓
API endpoint filters TrustedSender by (account_id=X OR account_id=NULL)
    ↓
Results returned with account context
```

## Quick Test: Browser

### Test 1: Add Global Sender
1. Open Settings → Phase X
2. In "Für welches Account?" select: **🌍 Global**
3. Enter pattern: `@example.com`
4. Click "Hinzufügen"
5. Expected: Sender appears with badge "Global"

### Test 2: Add Account-Specific Sender
1. Open Settings → Phase X
2. In "Für welches Account?" select: **📧 Account 2**
3. In form "Für welches Account?" select: **📧 Account 2**
4. Enter pattern: `john@test.com`
5. Click "Hinzufügen"
6. Expected: Sender appears with badge "Account 2"

### Test 3: Account Selector Filter
1. Add 1 global sender and 1 account-1 sender
2. Click account selector and change to "📧 Account 1"
3. Expected: See both senders (account-1 + global)
4. Click account selector and change to "📧 Account 2"
5. Expected: See only global sender

### Test 4: Toggle UrgencyBooster
1. Have a sender in account-1 list
2. Click ⚡ button next to sender
3. Expected: Button changes to ⭕ (disabled state)
4. Switch to account 2
5. Expected: Same sender's ⚡ button is unchanged

## Quick Test: Terminal/curl

### List Senders - Account 1
```bash
curl "http://localhost:5000/api/trusted-senders?account_id=1" \
  -H "Content-Type: application/json" | python -m json.tool
```
Expected: Shows account_id field in response

### Add Sender - Account 2
```bash
curl -X POST "http://localhost:5000/api/trusted-senders" \
  -H "Content-Type: application/json" \
  -d '{
    "sender_pattern": "@test.com",
    "pattern_type": "email_domain",
    "label": "Test Domain",
    "use_urgency_booster": true,
    "account_id": 2
  }' | python -m json.tool
```

### Delete Sender - Account 2
```bash
# First get the sender ID from list endpoint, then:
curl -X DELETE "http://localhost:5000/api/trusted-senders/{ID}?account_id=2" \
  -H "Content-Type: application/json"
```

### Get Suggestions - Account 1
```bash
curl "http://localhost:5000/api/trusted-senders/suggestions?account_id=1" \
  -H "Content-Type: application/json" | python -m json.tool
```

## Key Differences from Old Implementation

| Old | New |
|-----|-----|
| No account context | Account selector in UI |
| All API calls without account_id | All API calls with optional account_id |
| Could not isolate senders by account | Senders stored per account |
| No account badges in list | Shows "Account X" or "Global" badges |
| Single whitelist | Dual whitelists: global + per-account |

## Files Modified

1. **migrations/versions/ph19_trusted_senders_account_id.py** - Migration deployed
2. **src/02_models.py** - TrustedSender model updated
3. **src/services/trusted_senders.py** - Service methods updated
4. **src/01_web_app.py** - 7 API endpoints updated
5. **templates/settings.html** - UI account selector + JS functions

## Troubleshooting

### Issue: Account selector dropdown is empty
**Solution:** Check that mail_accounts table has entries
```bash
sqlite3 emails.db "SELECT id, name FROM mail_accounts;"
```

### Issue: Adding sender returns 400 error
**Solution:** Check that account_id (if provided) exists in mail_accounts
```bash
# Valid: no account_id
{"sender_pattern": "@test.com", "account_id": null}

# Valid: account exists
curl -X POST ... -d '{"sender_pattern": "@test.com", "account_id": 1}'
```

### Issue: JavaScript error "Cannot read property 'value' of null"
**Solution:** Ensure HTML elements exist:
- `#whitelistAccountSelector` - Account selector dropdown
- `#trustedSenderPattern` - Pattern input field
- `#trustedSenderType` - Type selector
- `#trustedSenderAccountId` - Account selector in form
- `#trustedSendersList` - List container
- `#addTrustedSenderBtn` - Add button

### Issue: Function name conflict
**Solution:** Check for duplicate function names
- ✅ Fixed: `toggleUrgencyBooster()` → renamed to `toggleUrgencyBoosterGlobal()` for global toggle
- ✅ Kept: `toggleUrgencyBooster(senderId, newValue)` for per-sender toggle

## Verification

### Python Syntax ✅
```bash
cd /home/thomas/projects/KI-Mail-Helper
python -m py_compile src/01_web_app.py src/services/trusted_senders.py
# Should exit with code 0
```

### Database Schema ✅
```bash
sqlite3 emails.db ".schema trusted_senders"
# Should show: account_id INTEGER FK
```

### Migration Status ✅
```bash
alembic current
# Should show: ph19_trusted_senders_account_id
```

## Implementation Summary

| Component | Status | Details |
|-----------|--------|---------|
| **Database** | ✅ | Migration ph19 deployed, account_id column added |
| **ORM** | ✅ | TrustedSender model updated with FK relationship |
| **Services** | ✅ | 3 methods account-aware (is_trusted, add, suggestions) |
| **API** | ✅ | 7 endpoints updated with account_id handling |
| **Frontend** | ✅ | Account selector added, JS functions updated |
| **Documentation** | ✅ | PHASE_X_ACCOUNT_BASED_COMPLETE.md created |

**Overall Status: 100% Complete** ✅

All components are implemented, syntax verified, and ready for testing.
