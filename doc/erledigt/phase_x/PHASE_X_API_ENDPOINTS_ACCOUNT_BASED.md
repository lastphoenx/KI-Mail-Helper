# 🚀 Phase X - Account-Based Whitelist API Endpoints

## ✅ Alle 7 Endpoints aktualisiert

### **1. LIST - Trusted Senders**

```bash
# Global Whitelists (alle Accounts)
curl -X GET "http://localhost:5001/api/trusted-senders" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"

# Account-spezifische (Account 1: martina)
curl -X GET "http://localhost:5001/api/trusted-senders?account_id=1" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"

# Account-spezifische (Account 2: thomas-beispiel-firma)  
curl -X GET "http://localhost:5001/api/trusted-senders?account_id=2" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "success": true,
  "senders": [
    {
      "id": 1,
      "sender_pattern": "boss@firma.de",
      "pattern_type": "exact",
      "label": "CEO",
      "use_urgency_booster": true,
      "account_id": null,
      "email_count": 42,
      "added_at": "2026-01-07T10:30:00"
    },
    {
      "id": 2,
      "sender_pattern": "@example.com",
      "pattern_type": "email_domain",
      "label": "University",
      "use_urgency_booster": true,
      "account_id": 2,
      "email_count": 150,
      "added_at": "2026-01-07T11:00:00"
    }
  ]
}
```

---

### **2. ADD - New Trusted Sender**

```bash
# Add GLOBAL (account_id=null)
curl -X POST "http://localhost:5001/api/trusted-senders" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json" \
  -d '{
    "sender_pattern": "boss@firma.de",
    "pattern_type": "exact",
    "label": "CEO",
    "use_urgency_booster": true
  }'

# Add for ACCOUNT 1 ONLY
curl -X POST "http://localhost:5001/api/trusted-senders" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json" \
  -d '{
    "sender_pattern": "@gmail.com",
    "pattern_type": "email_domain",
    "label": "Friends",
    "use_urgency_booster": true,
    "account_id": 1
  }'

# Add for ACCOUNT 2 ONLY
curl -X POST "http://localhost:5001/api/trusted-senders" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json" \
  -d '{
    "sender_pattern": "@example.com",
    "pattern_type": "email_domain",
    "label": "University",
    "use_urgency_booster": true,
    "account_id": 2
  }'
```

**Response:**
```json
{
  "success": true,
  "sender": {
    "id": 3,
    "sender_pattern": "@example.com",
    "pattern_type": "email_domain",
    "label": "University",
    "use_urgency_booster": true,
    "account_id": 2
  }
}
```

---

### **3. UPDATE - Trusted Sender**

```bash
# Update global sender
curl -X PATCH "http://localhost:5001/api/trusted-senders/1" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json" \
  -d '{
    "use_urgency_booster": false,
    "label": "Boss (disabled urgency)"
  }'

# Update account-specific sender
curl -X PATCH "http://localhost:5001/api/trusted-senders/2?account_id=2" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json" \
  -d '{
    "use_urgency_booster": true,
    "label": "Beispiel-Firma (always check urgency)"
  }'
```

**Response:**
```json
{
  "success": true,
  "sender": {
    "id": 2,
    "sender_pattern": "@example.com",
    "pattern_type": "email_domain",
    "label": "Beispiel-Firma (always check urgency)",
    "use_urgency_booster": true,
    "account_id": 2
  }
}
```

---

### **4. DELETE - Trusted Sender**

```bash
# Delete global sender
curl -X DELETE "http://localhost:5001/api/trusted-senders/1" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"

# Delete account-specific sender
curl -X DELETE "http://localhost:5001/api/trusted-senders/2?account_id=2" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "success": true
}
```

---

### **5. GET SUGGESTIONS**

```bash
# Get suggestions for GLOBAL whitelist (all accounts)
curl -X GET "http://localhost:5001/api/trusted-senders/suggestions" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"

# Get suggestions for ACCOUNT 1
curl -X GET "http://localhost:5001/api/trusted-senders/suggestions?account_id=1" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"

# Get suggestions for ACCOUNT 2
curl -X GET "http://localhost:5001/api/trusted-senders/suggestions?account_id=2" \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "success": true,
  "account_id": 2,
  "suggestions": [
    {
      "sender": "prof.mueller@example.com",
      "email_count": 34,
      "suggested_pattern_type": "exact"
    },
    {
      "sender": "admin@example.com",
      "email_count": 28,
      "suggested_pattern_type": "exact"
    }
  ]
}
```

---

## 📋 Neue API Query Parameter

| Endpoint | Parameter | Type | Default | Beschreibung |
|----------|-----------|------|---------|-------------|
| GET /api/trusted-senders | `account_id` | int | NULL | Filter für spezifisches Account |
| POST /api/trusted-senders | `account_id` (body) | int | NULL | Speichern für spezifisches Account |
| PATCH /api/trusted-senders/{id} | `account_id` | int | NULL | Sicherheitsfilter (nur wenn gehört zu Account) |
| DELETE /api/trusted-senders/{id} | `account_id` | int | NULL | Sicherheitsfilter (nur wenn gehört zu Account) |
| GET /api/trusted-senders/suggestions | `account_id` | int | NULL | Filter Vorschläge nach Account |

---

## 🔐 Security Notes

### **Scenario: User hat 2 Accounts + Global + Account-spezifische Whitelists**

```
User ID: 1
Account 1 (martina@gmail.com): ID=1
Account 2 (thomas@example.com): ID=2

Whitelists:
- ID=10: pattern="boss@firma.de" | account_id=NULL (GLOBAL)
- ID=11: pattern="@gmail.com" | account_id=1 (GMAIL only)
- ID=12: pattern="@example.com" | account_id=2 (BEISPIEL only)
```

**Query: /api/trusted-senders?account_id=1**
→ Returns: ID=10 (global) + ID=11 (account 1)
→ Ausschluss: ID=12 (das ist für Account 2!)

**Query: /api/trusted-senders?account_id=2**
→ Returns: ID=10 (global) + ID=12 (account 2)
→ Ausschluss: ID=11 (das ist für Account 1!)

**Query: /api/trusted-senders** (no account_id)
→ Returns: ID=10 (global only)
→ Ausschluss: ID=11, ID=12 (account-spezifisch)

---

## ⚠️ Error Handling

```json
// Invalid pattern_type
{
  "success": false,
  "error": "Invalid pattern_type"
}

// Sender already exists
{
  "success": false,
  "error": "Sender bereits in Liste",
  "existing_id": 5
}

// Limit reached (500 per account)
{
  "success": false,
  "error": "Limit erreicht (500 Sender maximum)"
}

// Access denied (sender belongs to different account)
{
  "success": false,
  "error": "Trusted sender not found"
}

// No master key
{
  "success": false,
  "error": "Master key not available"
}
```

---

## ✅ Implementation Checklist

- [x] Migration ph19 deployed (account_id added)
- [x] TrustedSender model updated
- [x] is_trusted_sender() account-aware
- [x] add_trusted_sender() account-aware
- [x] api_list_trusted_senders() account-aware
- [x] api_add_trusted_sender() account-aware
- [x] api_update_trusted_sender() account-aware
- [x] api_delete_trusted_sender() account-aware
- [x] api_get_trusted_senders_suggestions() account-aware
- [x] Syntax verified & compiled

---

## 🎯 Next: UI Account Selector

Die Endpoints sind ready! Nächster Schritt ist die **UI** mit Account-Dropdown erweitern in `templates/settings.html`
