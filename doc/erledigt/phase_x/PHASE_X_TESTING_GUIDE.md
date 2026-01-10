# Phase X - Quick Testing Guide

## 🚀 Quick Start

### 1. Verify Installation

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate

# Check all modules compile
python -m py_compile src/01_web_app.py src/02_models.py src/03_ai_client.py src/12_processing.py
python -m py_compile src/services/trusted_senders.py src/services/urgency_booster.py

# Verify spaCy model
python -c "import spacy; nlp = spacy.load('de_core_news_sm'); print('✅ spaCy ready')"

# Check database
sqlite3 app.db "SELECT name FROM sqlite_master WHERE type='table' AND name='trusted_senders';" && echo "✅ Table exists"
```

Expected output:
```
✅ spaCy ready
trusted_senders
✅ Table exists
```

---

## 🧪 Testing Scenarios

### Scenario 1: Add Trusted Sender via UI

1. Start the application
2. Go to **Settings → Trusted Senders + UrgencyBooster**
3. Enter:
   - **Pattern**: `boss@company.de` or `company.de`
   - **Type**: Select appropriate type
   - **Label**: `CEO` (optional)
   - **Booster**: ✅ checked
4. Click **➕ Hinzufügen**
5. Verify sender appears in list

**Expected Result**: ✅ Sender added, shown in list with email count = 0

---

### Scenario 2: UrgencyBooster Triggers

1. Ensure trusted sender exists for `test@example.com`
2. Send email to account with:
   - **From**: test@example.com
   - **Subject**: "Dringend: Zahlung bis 15. Januar erforderlich"
   - **Body**: Contains deadline/money/action verbs
3. Fetch emails (manually or via scheduler)
4. Check email analysis result
5. Look for DEBUG log: `"UrgencyBooster: High confidence (X.XX) for trusted sender"`

**Expected Result**: 
- ✅ Email analyzed by UrgencyBooster (NOT LLM)
- ✅ Urgency score >= 0.6
- ✅ Log shows "UrgencyBooster:" instead of LLM processing time

---

### Scenario 3: Pattern Matching

#### Exact Match
- Add: `john.doe@company.de` (type: exact)
- Email from `john.doe@company.de` → ✅ Matches
- Email from `jane.doe@company.de` → ❌ No match

#### Email Domain
- Add: `@company.de` (type: email_domain)
- Email from `john@company.de` → ✅ Matches
- Email from `john@company.com` → ❌ No match

#### Domain
- Add: `company.de` (type: domain)
- Email from `john@company.de` → ✅ Matches
- Email from `support@company.de` → ✅ Matches
- Email from `john@branch.company.de` → ✅ Matches (subdomain)

**Expected Result**: ✅ All patterns match correctly

---

### Scenario 4: Suggestions

1. Go to **Settings → Trusted Senders**
2. Click **🔍 Vorschläge laden**
3. Wait for suggestions to load (may take a few seconds)
4. Click **➕ Hinzufügen** on a suggestion
5. Form should auto-fill with pattern

**Expected Result**: 
- ✅ Suggestions load from email history
- ✅ Show senders with email_count >= 2
- ✅ One-click add functionality works

---

### Scenario 5: Toggle UrgencyBooster

1. Go to **Settings → Trusted Senders**
2. Toggle **⚡ UrgencyBooster aktivieren** OFF
3. Fetch an email from trusted sender with urgent keywords
4. Check analysis result

**Expected Result**:
- ✅ When OFF: Standard LLM analysis (slow)
- ✅ When ON: UrgencyBooster (fast)
- ✅ Setting persists in database

---

## 📊 Performance Benchmarks

### Test with Urgent Email

```
Subject: "Zahlung bis morgen erforderlich - 5000€"
Body: "Bitte überweisen Sie €5000,00 bis 2025-01-13"
```

**Expected Times**:
- UrgencyBooster: **100-300ms**
- LLM (Ollama): **5-10 minutes**
- Cloud (OpenAI): **2-5 seconds** (not affected)

---

## 🔍 Database Queries

### Check Trusted Senders

```sql
SELECT id, sender_pattern, pattern_type, email_count, last_seen_at 
FROM trusted_senders 
WHERE user_id = <your_user_id>;
```

### Check Settings

```sql
SELECT urgency_booster_enabled FROM users WHERE id = <your_user_id>;
```

### Check Email Count per Sender

```sql
SELECT sender_pattern, pattern_type, COUNT(*) as email_count 
FROM trusted_senders 
GROUP BY sender_pattern 
ORDER BY email_count DESC;
```

---

## 🐛 Debugging

### Enable Debug Logging

```python
# In src/12_processing.py, set:
logger.setLevel(logging.DEBUG)
```

### Check Logs

```bash
# Tail logs
tail -f logs/app.log | grep -i "urgency\|trusted"

# Search for specific sender
grep "test@example.com" logs/app.log
```

### Test API Endpoints

```bash
# List trusted senders
curl -H "Cookie: session=..." http://localhost:5000/api/trusted-senders

# Add trusted sender
curl -X POST http://localhost:5000/api/trusted-senders \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -d '{"sender_pattern":"test@example.com","pattern_type":"exact"}'

# Get suggestions
curl http://localhost:5000/api/trusted-senders/suggestions \
  -H "Cookie: session=..."

# Check UrgencyBooster status
curl http://localhost:5000/api/settings/urgency-booster \
  -H "Cookie: session=..."
```

---

## ⚠️ Common Issues

### Issue: spaCy model not found

**Solution**:
```bash
python -m spacy download de_core_news_sm -q
```

### Issue: "Trusted sender not found" error

**Check**:
1. Is sender in `trusted_senders` table?
2. Is `user_id` correct?
3. Is pattern case-sensitive? (Should be auto-normalized to lowercase)

```sql
SELECT * FROM trusted_senders WHERE sender_pattern LIKE '%test%';
```

### Issue: UrgencyBooster not triggering

**Check**:
1. Is `urgency_booster_enabled = 1` for user?
2. Is sender actually trusted?
3. Is confidence >= 0.6?

```bash
# Add debug print in src/services/urgency_booster.py
result = booster.analyze_urgency(subject, body, sender)
print(f"DEBUG: confidence={result['confidence']}, signals={result['signals']}")
```

### Issue: API returns 404

**Check**:
1. Are you logged in? (Check cookie)
2. Does route exist in `src/01_web_app.py`?
3. Check application logs for import errors

```bash
grep -i "route\|endpoint" logs/app.log
```

---

## 📋 Testing Checklist

### Basic Functionality
- [ ] Add trusted sender (all 3 types)
- [ ] Delete trusted sender
- [ ] List shows all senders
- [ ] Email count increments
- [ ] Last seen date updates

### UrgencyBooster
- [ ] Detects deadlines (relative: "bis morgen", "bis Freitag")
- [ ] Detects money (€100, 100 EUR)
- [ ] Detects action verbs (senden, überweisen, etc.)
- [ ] Detects authority (CEO, CFO, Geschäftsführer)
- [ ] Detects invoices
- [ ] Confidence scoring works
- [ ] Confidence >= 0.6 returns UrgencyBooster result

### API Endpoints
- [ ] GET /api/trusted-senders returns list
- [ ] POST /api/trusted-senders adds sender
- [ ] PATCH /api/trusted-senders/<id> updates sender
- [ ] DELETE /api/trusted-senders/<id> deletes sender
- [ ] GET /api/settings/urgency-booster returns setting
- [ ] POST /api/settings/urgency-booster saves setting
- [ ] GET /api/trusted-senders/suggestions returns suggestions

### UI/UX
- [ ] Form validates empty pattern
- [ ] Form accepts Enter key
- [ ] Suggestions load and populate form
- [ ] Delete button requires confirmation
- [ ] Toggle switch works smoothly
- [ ] List updates after add/delete

### Edge Cases
- [ ] Domain pattern with subdomain (branch.company.de)
- [ ] Case-insensitive matching
- [ ] 500 senders limit enforced
- [ ] Duplicate sender rejected
- [ ] Decryption error handled in suggestions

---

## 🎯 Success Criteria

✅ **Phase X is successfully implemented when**:

1. **Database**: trusted_senders table exists with all columns
2. **Models**: TrustedSender class works with relationships
3. **Services**: TrustedSenderManager & UrgencyBooster functional
4. **Integration**: Processing passes Phase X parameters to analyze_email()
5. **API**: All 7 endpoints accessible and return correct data
6. **UI**: Settings page displays and allows CRUD operations
7. **Performance**: UrgencyBooster processes email in 100-300ms
8. **Fallback**: LLM analysis still works for low-confidence results
9. **Backwards Compat**: Cloud clients unaffected
10. **Logging**: Debug messages indicate UrgencyBooster activation

---

## 📞 Support

**For issues, check**:
1. Application logs: `logs/app.log`
2. Database schema: `sqlite3 app.db ".schema trusted_senders"`
3. spaCy model: `python -c "import spacy; spacy.load('de_core_news_sm')"`
4. Python syntax: `python -m py_compile src/services/urgency_booster.py`

**Performance Profile** (with Python cProfile):
```python
import cProfile
profiler = cProfile.Profile()
profiler.enable()
result = booster.analyze_urgency(subject, body, sender)
profiler.disable()
profiler.print_stats(sort='cumulative')
```

---

**Good luck testing! 🚀**
