# Phase X - Architecture & Data Flow

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                              │
│  templates/settings.html - Phase X Settings Page                   │
│  ├─ UrgencyBooster Toggle                                          │
│  ├─ Trusted Senders List (CRUD)                                    │
│  └─ Add New Sender Form                                            │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ HTTP (JSON)
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      REST API LAYER                                 │
│  src/01_web_app.py - Flask Endpoints                               │
│                                                                     │
│  GET  /api/trusted-senders                                        │
│  POST /api/trusted-senders                                        │
│  PATCH /api/trusted-senders/<id>                                  │
│  DELETE /api/trusted-senders/<id>                                 │
│  GET /api/settings/urgency-booster                                │
│  POST /api/settings/urgency-booster                               │
│  GET /api/trusted-senders/suggestions                             │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
┌──────────────────────┐    ┌─────────────────────────┐
│  SERVICE LAYER       │    │  SERVICE LAYER          │
│  trusted_senders.py  │    │  urgency_booster.py     │
│                      │    │                         │
│ TrustedSenderManager │    │ UrgencyBooster          │
│  ├─ is_trusted()     │    │  ├─ analyze_urgency()   │
│  ├─ add_sender()     │    │  ├─ detect_deadlines()  │
│  ├─ delete_sender()  │    │  ├─ detect_money()      │
│  └─ suggestions()    │    │  ├─ detect_actions()    │
└──────────────────────┘    │  ├─ detect_authority()  │
        │                   │  └─ detect_invoices()   │
        │                   │                         │
        │                   │ + spaCy NER integration │
        │                   │ + Fallback heuristics   │
        │                   └─────────────────────────┘
        │
        └──────────────────┬─────────────────────────┐
                           │                         │
                           ▼                         ▼
                    ┌──────────────┐        ┌─────────────────┐
                    │  DATABASE    │        │  OLLAMA LOCAL   │
                    │  SQLite      │        │  LLM ANALYSIS   │
                    │              │        │                 │
                    │ trusted_     │        │ (Fallback if    │
                    │ senders      │        │  confidence <   │
                    │ table        │        │  0.6)           │
                    │              │        │                 │
                    │ users        │        │ OR Cloud APIs   │
                    │ table        │        │ (unaffected)    │
                    │ (.urgency_   │        │                 │
                    │  booster_    │        │                 │
                    │  enabled)    │        │                 │
                    └──────────────┘        └─────────────────┘
```

---

## 📧 Email Processing Flow (Phase X Integration)

```
INCOMING EMAIL
    │
    ▼
┌─────────────────────────────────────────┐
│  src/12_processing.py                   │
│  process_folder_emails()                │
│                                         │
│  1. Decrypt email                       │
│  2. Sanitize body                       │
│  3. Build thread context                │
│  4. Get user settings                   │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│  Check: urgency_booster_enabled?        │
│  Check: sender is trusted?              │
└──────────┬──────────────────────────────┘
           │
        YES├─────────────────────────────────────────┐
           │                                         │
           ▼                                         ▼
     ┌─────────────────┐                  ┌──────────────────────┐
     │ UrgencyBooster  │                  │  Standard LLM Path   │
     │ analyze_urgency │                  │  (No change)         │
     │                 │                  │                      │
     │ 100-300ms       │                  │  (Faster if no       │
     │                 │                  │   Trusted Senders)   │
     │ Returns:        │                  │                      │
     │  • urgency      │                  │  Ollama → 5-10min    │
     │  • importance   │                  │  OR                  │
     │  • confidence   │                  │  Cloud → 2-5sec      │
     │  • signals      │                  │                      │
     └────┬────────────┘                  └──────────────────────┘
          │                                        │
          ▼                                        │
    ┌──────────────────┐                         │
    │ confidence >= 0.6│                         │
    └────┬──────┬──────┘                         │
         │YES   │NO                             │
         │      └─────────────────────┐         │
         │                            ▼         │
         │                  ┌──────────────────┐│
         │                  │ Use LLM Fallback ││
         │                  └──────────────────┘│
         │                            │         │
         ▼                            ▼         ▼
    ┌──────────────────────────────────────────┐
    │  ProcessedEmail created                  │
    │  • classification                        │
    │  • urgency_score                         │
    │  • importance_score                      │
    │  • detected_deadline (if any)            │
    │  • confidence                            │
    │  • ai_analysis_method (ner|heuristic|lm) │
    └──────────────────────────────────────────┘
           │
           ▼
      DATABASE
      (users → processed_emails)
```

---

## 🔄 Data Flow Diagram

```
                        USER ACTION
                            │
              ┌─────────────┴────────────────┐
              │                              │
              ▼                              ▼
      ┌──────────────┐             ┌────────────────┐
      │ Add Trusted  │             │ Toggle         │
      │ Sender via UI│             │ UrgencyBooster │
      └──────┬───────┘             └────────┬───────┘
             │                              │
             ├──────────────┬───────────────┤
             │              │               │
             ▼              ▼               ▼
        JSON POST      JSON POST       JSON POST
        API Endpoint   API Endpoint     API Endpoint
             │              │               │
             ▼              ▼               ▼
    ┌────────────────┐
    │ Validate Input │
    │ (Regex, Type)  │
    └────────┬───────┘
             │
             ▼
    ┌────────────────────┐
    │ Database Write     │
    │ (INSERT, UPDATE)   │
    └────────┬───────────┘
             │
             ▼
    ┌────────────────────┐
    │ Return JSON        │
    │ Success Response   │
    └────────┬───────────┘
             │
             ▼
       UPDATE UI
       (Reload list,
        Show message)
```

---

## 🗄️ Database Schema (Phase X)

```sql
-- EXISTING TABLE (MODIFIED)
users
  └─ urgency_booster_enabled BOOLEAN DEFAULT TRUE

-- NEW TABLE
trusted_senders
  ├─ id INTEGER PRIMARY KEY
  ├─ user_id INTEGER FK → users.id (CASCADE DELETE)
  ├─ sender_pattern VARCHAR(255) NOT NULL
  │  └─ Examples: "boss@company.de", "@company.de", "company.de"
  │
  ├─ pattern_type VARCHAR(20) NOT NULL
  │  └─ Values: "exact", "email_domain", "domain"
  │
  ├─ label VARCHAR(100) NULLABLE
  │  └─ Examples: "CEO", "Finance", "HR"
  │
  ├─ use_urgency_booster BOOLEAN DEFAULT TRUE
  │  └─ Can disable per-sender if needed
  │
  ├─ added_at DATETIME NOT NULL
  ├─ last_seen_at DATETIME NULLABLE
  ├─ email_count INTEGER DEFAULT 0
  │
  ├─ UNIQUE CONSTRAINT (user_id, sender_pattern)
  └─ INDEX ON (user_id, sender_pattern)
```

---

## 📊 Signal Detection Process (UrgencyBooster)

```
INPUT: (subject, body, sender)
  │
  ▼
┌──────────────────────────┐
│ Load spaCy Model         │
│ (de_core_news_sm)        │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│ SIGNAL DETECTION                         │
│                                          │
│ 1. DEADLINE SIGNAL                       │
│    ├─ Extract: DATE entities (spaCy)     │
│    ├─ Relative: "bis morgen" → hours     │
│    ├─ Keywords: "dringend", "sofort"     │
│    └─ Score: base 0.15 + modifiers       │
│                                          │
│ 2. MONEY SIGNAL                          │
│    ├─ Detect: MONEY entities (spaCy)     │
│    ├─ Parse: €100, 100 EUR, 5000€        │
│    ├─ Regex: \€|\bEUR\b                  │
│    └─ Score: base 0.15 + amount          │
│                                          │
│ 3. ACTION VERB SIGNAL                    │
│    ├─ Detect: 10 action verbs            │
│    │  (senden, zahlen, überweisen, etc.) │
│    ├─ Case-insensitive matching          │
│    └─ Score: base 0.15 per verb (max 1)  │
│                                          │
│ 4. AUTHORITY SIGNAL                      │
│    ├─ Detect: Person titles (spaCy)      │
│    ├─ Keywords: CEO, CFO, Director       │
│    ├─ German: Geschäftsführer, Vorstand  │
│    └─ Score: base 0.15                   │
│                                          │
│ 5. INVOICE SIGNAL                        │
│    ├─ Keywords: Rechnung, Invoice, Bill  │
│    ├─ Regex patterns for amounts         │
│    └─ Score: base 0.15                   │
│                                          │
└──────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│ CONFIDENCE CALCULATION                   │
│                                          │
│ base_confidence = sum(signals) / 5       │
│ max_base = 0.75 (5 signals × 0.15)       │
│                                          │
│ modifiers:                               │
│  • +0.05 if multiple signals             │
│  • +0.10 if strong signal (e.g. deadline │
│  • -0.10 if newsletter detected          │
│  • +0.05 if sender is known (trusted)    │
│                                          │
│ final_confidence = clamp(base + modifiers, 0, 1)
│                                          │
└──────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│ DECISION                                 │
│                                          │
│ IF confidence >= 0.6:                    │
│   RETURN UrgencyBooster result           │
│   (100-300ms total)                      │
│                                          │
│ ELSE:                                    │
│   RETURN result but indicate             │
│   confidence low                         │
│   (May trigger LLM fallback)             │
│                                          │
└──────────────────────────────────────────┘
           │
           ▼
OUTPUT: {
  urgency_score: float,        # 0-1
  importance_score: float,     # 0-1
  category: str,               # category name
  confidence: float,           # 0-1
  signals: {                   # Detected signals
    time_pressure: bool,
    deadline_hours: int,
    money_amount: float,
    action_verbs: [str],
    authority_person: bool,
    invoice_detected: bool
  },
  method: str                  # "ner" or "heuristic"
}
```

---

## 🔐 Security & Isolation

```
USER A
  │
  ├─ API Request: /api/trusted-senders
  │  └─ @login_required decorator
  │     └─ current_user.id = A
  │
  ├─ Query Filter:
  │  WHERE user_id = A  ← ENFORCED
  │
  ├─ Can Access:
  │  ✓ Own trusted senders
  │  ✓ Own settings
  │
  └─ Cannot Access:
     ✗ User B's senders
     ✗ User B's settings

USER B
  │
  ├─ API Request: /api/trusted-senders
  │  └─ @login_required decorator
  │     └─ current_user.id = B
  │
  ├─ Query Filter:
  │  WHERE user_id = B  ← ENFORCED
  │
  └─ Isolated from User A
```

---

## ⚡ Performance Characteristics

```
SCENARIO: Email from Trusted Sender with UrgencyBooster

Timing Breakdown:
  │
  ├─ Decrypt email          → 10-50ms
  ├─ Load spaCy model       → 100-200ms (first time only)
  ├─ Parse subject/body     → 20-50ms
  ├─ NER processing         → 30-100ms
  ├─ Signal detection       → 20-50ms
  ├─ Confidence calculation → 5-10ms
  └─ Database write         → 10-20ms
     ─────────────────────────────────
     TOTAL:                 → 100-300ms

COMPARISON:
┌──────────────────┬──────────────────┬──────────────────┐
│ Method           │ Time             │ Improvement      │
├──────────────────┼──────────────────┼──────────────────┤
│ LLM (Ollama)     │ 5-10 minutes     │ BASELINE         │
│ LLM (Cloud API)  │ 2-5 seconds      │ ---              │
│ UrgencyBooster   │ 100-300ms        │ 70-80% FASTER    │
└──────────────────┴──────────────────┴──────────────────┘

SYSTEM IMPACT:
  • CPU: Minimal (spaCy uses efficient algorithms)
  • Memory: spaCy model ~50MB (one-time load)
  • Network: None (all local processing)
  • Database: Single transactional write per email
  • Scaling: O(1) per email, O(n) for n trusted senders
```

---

## 🧪 Testing Scenarios

```
SCENARIO 1: Exact Email Match
  trusted_sender: boss@company.de (type: exact)
  incoming_email: boss@company.de
  ─────────────────────────────────────────
  Result: ✓ MATCHES → UrgencyBooster runs

SCENARIO 2: Email Domain Match
  trusted_sender: @company.de (type: email_domain)
  incoming_email: john@company.de
  incoming_email: sarah@company.de
  ─────────────────────────────────────────
  Result: ✓ BOTH MATCH → UrgencyBooster runs

SCENARIO 3: Domain Subdomain Match
  trusted_sender: company.de (type: domain)
  incoming_email: ceo@company.de
  incoming_email: hr@branch.company.de
  ─────────────────────────────────────────
  Result: ✓ BOTH MATCH → UrgencyBooster runs

SCENARIO 4: Confidence Below Threshold
  Email from trusted sender
  Confidence: 0.45
  ─────────────────────────────────────────
  Result: ✗ Below 0.6 → Fall through to LLM

SCENARIO 5: Non-Trusted Sender
  Email from unknown@hotmail.com
  Trusted senders: all from company.de
  ─────────────────────────────────────────
  Result: ✗ NOT TRUSTED → Skip UrgencyBooster, use LLM
```

---

## 🔗 Component Dependencies

```
templates/settings.html
  ├─ src/01_web_app.py (API)
  │   ├─ src/02_models.py (ORM)
  │   │   ├─ migrations/ph18_trusted_senders.py (Schema)
  │   │   └─ SQLite database
  │   │
  │   ├─ src/services/trusted_senders.py
  │   │   └─ src/02_models.py
  │   │
  │   └─ src/services/urgency_booster.py
  │       ├─ spacy >= 3.7.0
  │       ├─ de_core_news_sm (German model)
  │       └─ importlib (dynamic loading)
  │
  └─ src/03_ai_client.py (Integration)
      ├─ src/12_processing.py
      │   ├─ src/02_models.py
      │   ├─ src/services/trusted_senders.py
      │   ├─ src/services/urgency_booster.py
      │   └─ src/03_ai_client.py
      │
      ├─ src/services/trusted_senders.py
      └─ src/services/urgency_booster.py
```

---

## 📈 Scalability

```
USER SCALE:
  • 100 users with 50 trusted senders each
    → 5,000 total trusted senders
    → Database lookup: O(log n) with index
    → Impact: Negligible

TRUSTED SENDERS SCALE:
  • User with 500 trusted senders (max)
    → Pattern matching: O(n) = 500 comparisons
    → Time: <10ms (regex is fast)
    → Impact: Still in 100-300ms envelope

EMAIL SCALE:
  • 1000s emails per user
    → UrgencyBooster runs per trusted sender email
    → spaCy model loaded once per process
    → Memory: ~50MB (constant)
    → CPU: 100-300ms per email (parallel if async)

STORAGE:
  • 500 trusted senders per user
  • ~100 bytes per row
  • 500 users max: 25MB total
  • No issue for SQLite
```

---

**End of Architecture Documentation**

For implementation details, see: PHASE_X_IMPLEMENTATION_FINAL.md
For testing instructions, see: PHASE_X_TESTING_GUIDE.md
