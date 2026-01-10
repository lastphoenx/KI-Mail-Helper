# Phase X: Account-Based Trusted Senders + UrgencyBooster - Complete Implementation

## Overview

The Phase X whitelist system has been fully implemented with **account-based architecture** as requested. The system maintains both:
- **Global Whitelists** (account_id = NULL): Apply to all mail accounts
- **Account-Specific Whitelists** (account_id = specific ID): Apply only to that account

Account-specific whitelists are prioritized and checked first.

## Architecture

```
┌─────────────────────────────────────────────┐
│         Frontend (templates/settings.html)   │
│  Account Selector + Form + JS Functions     │
└────────────────┬────────────────────────────┘
                 │ account_id parameter
                 ▼
┌─────────────────────────────────────────────┐
│    REST API Endpoints (src/01_web_app.py)   │
│  7 Account-Aware Endpoints                  │
└────────────────┬────────────────────────────┘
                 │ account_id parameter
                 ▼
┌─────────────────────────────────────────────┐
│  Service Layer (src/services/trusted_senders.py)
│  Account-Aware Business Logic               │
└────────────────┬────────────────────────────┘
                 │ account_id FK
                 ▼
┌─────────────────────────────────────────────┐
│  ORM Models (src/02_models.py)              │
│  TrustedSender with account_id FK           │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│  Database (emails.db)                       │
│  trusted_senders table with account_id      │
└─────────────────────────────────────────────┘
```

## Database Schema

```sql
CREATE TABLE trusted_senders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_id INTEGER,  -- NULL = global, NOT NULL = account-specific
    sender_pattern TEXT NOT NULL,
    pattern_type TEXT NOT NULL,  -- 'exact', 'email_domain', 'domain_with_subdomains'
    label TEXT,
    email_count INTEGER DEFAULT 0,
    last_seen_at TIMESTAMP,
    use_urgency_booster BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES mail_accounts(id) ON DELETE CASCADE,
    UNIQUE(user_id, sender_pattern, account_id),
    KEY (user_id, sender_pattern),
    KEY (account_id, sender_pattern)
);
```

## ORM Model

```python
class TrustedSender(Base):
    __tablename__ = 'trusted_senders'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=True)
    sender_pattern = Column(String(255), nullable=False)
    pattern_type = Column(String(50), nullable=False)  # exact, email_domain, domain_with_subdomains
    label = Column(String(255))
    email_count = Column(Integer, default=0)
    last_seen_at = Column(DateTime)
    use_urgency_booster = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="trusted_senders")
    mail_account = relationship("MailAccount", foreign_keys=[account_id])
```

## API Endpoints (Account-Aware)

### 1. List Trusted Senders
```bash
# Get all global senders
curl -X GET "http://localhost:5000/api/trusted-senders" \
  -H "Content-Type: application/json"

# Get senders for specific account (includes global)
curl -X GET "http://localhost:5000/api/trusted-senders?account_id=1" \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "success": true,
  "senders": [
    {
      "id": 1,
      "sender_pattern": "john@example.com",
      "pattern_type": "exact",
      "label": "Important Contact",
      "email_count": 15,
      "last_seen_at": "2024-12-19T10:30:00",
      "use_urgency_booster": true,
      "account_id": 1
    },
    {
      "id": 2,
      "sender_pattern": "@example.com",
      "pattern_type": "email_domain",
      "label": "Company Domain",
      "email_count": 42,
      "last_seen_at": "2024-12-19T09:15:00",
      "use_urgency_booster": false,
      "account_id": null
    }
  ]
}
```

### 2. Add Trusted Sender
```bash
# Add global sender
curl -X POST "http://localhost:5000/api/trusted-senders" \
  -H "Content-Type: application/json" \
  -d '{
    "sender_pattern": "@example.com",
    "pattern_type": "email_domain",
    "label": "Company Domain",
    "use_urgency_booster": true,
    "account_id": null
  }'

# Add account-specific sender
curl -X POST "http://localhost:5000/api/trusted-senders" \
  -H "Content-Type: application/json" \
  -d '{
    "sender_pattern": "john@example.com",
    "pattern_type": "exact",
    "label": "John Doe",
    "use_urgency_booster": true,
    "account_id": 1
  }'
```

**Response:**
```json
{
  "success": true,
  "sender": {
    "id": 3,
    "sender_pattern": "john@example.com",
    "pattern_type": "exact",
    "label": "John Doe",
    "use_urgency_booster": true,
    "account_id": 1
  }
}
```

### 3. Update Trusted Sender
```bash
# Update sender (with account_id verification)
curl -X PATCH "http://localhost:5000/api/trusted-senders/1?account_id=1" \
  -H "Content-Type: application/json" \
  -d '{
    "use_urgency_booster": false,
    "label": "Updated Label"
  }'

# Update global sender
curl -X PATCH "http://localhost:5000/api/trusted-senders/2" \
  -H "Content-Type: application/json" \
  -d '{
    "use_urgency_booster": true
  }'
```

### 4. Delete Trusted Sender
```bash
# Delete account-specific sender
curl -X DELETE "http://localhost:5000/api/trusted-senders/1?account_id=1" \
  -H "Content-Type: application/json"

# Delete global sender
curl -X DELETE "http://localhost:5000/api/trusted-senders/2" \
  -H "Content-Type: application/json"
```

### 5. Get Suggestions
```bash
# Get suggestions for all global accounts
curl -X GET "http://localhost:5000/api/trusted-senders/suggestions" \
  -H "Content-Type: application/json"

# Get suggestions specific to an account
curl -X GET "http://localhost:5000/api/trusted-senders/suggestions?account_id=1" \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "success": true,
  "suggestions": [
    {
      "sender": "marie@example.com",
      "email_count": 5,
      "suggested_pattern_type": "exact",
      "account_id": 1
    }
  ]
}
```

## Service Layer Implementation

### `is_trusted_sender()`
```python
def is_trusted_sender(
    self,
    sender_email: str,
    account_id: Optional[int] = None
) -> dict:
    """
    Check if a sender is trusted.
    
    Priority order:
    1. Account-specific whitelist (if account_id provided)
    2. Global whitelist (account_id = NULL)
    
    Returns: {'is_trusted': bool, 'account_id': int|None, 'use_urgency_booster': bool}
    """
```

### `add_trusted_sender()`
```python
def add_trusted_sender(
    self,
    sender_pattern: str,
    pattern_type: str,
    user_id: int,
    label: Optional[str] = None,
    use_urgency_booster: bool = False,
    account_id: Optional[int] = None
) -> 'TrustedSender':
    """
    Add a new trusted sender.
    
    Validation:
    - Pattern must be unique per (user_id, account_id) combination
    - Per-account limit: 500 senders max
    - Pattern validation per type
    """
```

### `get_suggestions_from_emails()`
```python
def get_suggestions_from_emails(
    self,
    user_id: int,
    account_id: Optional[int] = None
) -> List[dict]:
    """
    Get suggestions from received emails.
    
    Returns senders that appear in emails but aren't whitelisted yet.
    Filters by account_id (or global) based on parameter.
    """
```

## Frontend Implementation

### Account Selector
Located at top of Phase X section in `templates/settings.html`:
```html
<select id="whitelistAccountSelector" class="form-select">
    <option value="">🌍 Global (alle Accounts)</option>
    <option value="1">📧 Account: martina</option>
    <option value="2">📧 Account: thomas-beispiel-firma</option>
</select>
```

### Add Sender Form
Three-column layout with account selector:
```html
<div class="row g-3">
    <div class="col-md-4">
        <input id="trustedSenderPattern" type="text" class="form-control" 
               placeholder="Absender-Muster">
    </div>
    <div class="col-md-4">
        <select id="trustedSenderType" class="form-select">
            <option value="exact">🔒 Exakt</option>
            <option value="email_domain">👥 Domain</option>
            <option value="domain_with_subdomains">🏢 Domain+Subs</option>
        </select>
    </div>
    <div class="col-md-4">
        <select id="trustedSenderAccountId" class="form-select">
            <option value="">🌍 Global</option>
            <option value="1">📧 Account 1</option>
            <option value="2">📧 Account 2</option>
        </select>
    </div>
</div>
```

### JavaScript Functions (Account-Aware)

#### `loadTrustedSendersList()`
- Reads selected account from `#whitelistAccountSelector`
- Adds `?account_id=X` to API call if account selected
- Displays account context badges next to each sender
- Includes UrgencyBooster toggle button (⚡)

#### `addTrustedSender()`
- Reads account from `#trustedSenderAccountId` form field
- Passes `account_id` in POST body to API
- Resets form after successful add
- Reloads list to show new entry

#### `deleteTrustedSender(senderId)`
- Reads account from `#whitelistAccountSelector`
- Includes `?account_id=X` in DELETE request
- Removes sender after confirmation

#### `toggleUrgencyBooster(senderId, newValue)`
- Reads account from `#whitelistAccountSelector`
- Includes `?account_id=X` in PATCH request
- Updates button state after successful toggle

#### `loadSuggestions()`
- Reads account from `#whitelistAccountSelector`
- Adds `?account_id=X` to API call if account selected
- Shows all suggestions relevant to that context

### Event Listeners
```javascript
// Account selector change listener
document.getElementById('whitelistAccountSelector')
    .addEventListener('change', loadTrustedSendersList);

// Form submission
document.getElementById('addTrustedSenderBtn')
    .addEventListener('click', addTrustedSender);

// Enter key in pattern input
document.getElementById('trustedSenderPattern')
    .addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addTrustedSender();
    });
```

## User Workflow

### Scenario 1: Add Global Sender
1. User opens Settings → Phase X
2. Account selector set to "🌍 Global"
3. Enter pattern: `@example.com`
4. Select type: `👥 Domain`
5. Click "Hinzufügen"
6. Sender added globally (visible in all accounts)

### Scenario 2: Add Account-Specific Sender
1. User opens Settings → Phase X
2. Account selector set to "📧 Account: thomas-beispiel-firma"
3. In form, select account: "📧 Account 2"
4. Enter pattern: `marie@example.com`
5. Enable UrgencyBooster toggle
6. Click "Hinzufügen"
7. Sender added to thomas-beispiel-firma account only
8. Badge shows "Account 2" next to sender name

### Scenario 3: View Account-Specific List
1. User opens Settings → Phase X
2. Changes account selector to "📧 Account: martina"
3. List automatically reloads and shows:
   - All senders for martina account
   - All global senders (with "Global" badge)
   - No senders from other accounts

### Scenario 4: Toggle UrgencyBooster Per Account
1. User has sender in both global and martina account lists
2. Selects "📧 Account: martina"
3. Clicks ⚡ button next to sender
4. Updates only martina's entry (not global)
5. Returns to "🌍 Global" selector
6. Same sender still has original UrgencyBooster state (unchanged)

## Query Logic (Priority Order)

When filtering senders for display/matching:

```python
# Account-aware query
query = db.query(TrustedSender).filter_by(user_id=current_user.id)

if account_id:
    # Account context selected: show account-specific + global
    query = query.filter(
        (TrustedSender.account_id == account_id) |
        (TrustedSender.account_id.is_(None))
    ).order_by(TrustedSender.account_id.desc())  # Account-specific first
else:
    # No account context: show global only
    query = query.filter(TrustedSender.account_id.is_(None))

results = query.all()
```

## Limits & Constraints

| Constraint | Value | Scope |
|-----------|-------|-------|
| Max senders per user | Unlimited | Global |
| Max senders per account | 500 | Account-specific |
| Max label length | 255 chars | N/A |
| Pattern uniqueness | (user_id, sender_pattern, account_id) | N/A |
| Cascade delete | YES | When account deleted |

## Testing Checklist

- [ ] Add global sender visible in all account views
- [ ] Add account-specific sender visible only in that account
- [ ] Account-specific sender takes priority over global match
- [ ] Delete account sender doesn't affect global
- [ ] Delete global sender leaves account-specific intact
- [ ] UrgencyBooster toggle works per account
- [ ] Suggestions show account context
- [ ] Account selector change reloads list
- [ ] API returns account_id in response
- [ ] Migrations deployed successfully
- [ ] No duplicate function names in JS
- [ ] Form resets after successful add
- [ ] Enter key submits form

## File Changes Summary

| File | Changes |
|------|---------|
| `migrations/versions/ph19_trusted_senders_account_id.py` | Migration deployed ✅ |
| `src/02_models.py` | TrustedSender model updated with account_id FK ✅ |
| `src/services/trusted_senders.py` | All methods account-aware ✅ |
| `src/01_web_app.py` | 7 API endpoints updated ✅ |
| `templates/settings.html` | Account selector + JS functions updated ✅ |

## Verification Commands

```bash
# Check database schema
sqlite3 /home/thomas/projects/KI-Mail-Helper/emails.db ".schema trusted_senders"

# Check Python syntax
python -m py_compile src/01_web_app.py src/services/trusted_senders.py

# View migration status
alembic current

# List all migrations
alembic history
```

## Next Steps (Optional Enhancements)

- [ ] Bulk import/export whitelists per account
- [ ] Whitelist templates for common domains
- [ ] Sharing whitelists between accounts
- [ ] Whitelist backup/restore functionality
- [ ] Analytics on trusted sender usage per account
- [ ] Auto-whitelist frequently trusted senders
