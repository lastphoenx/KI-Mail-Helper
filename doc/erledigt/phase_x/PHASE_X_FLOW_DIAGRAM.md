# Phase X Flow Diagram

```
═══════════════════════════════════════════════════════════════════════════
                          PHASE X ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────┐
│                         USER EMAIL PROCESSING                            │
└─────────────────────────────────────────────────────────────────────────┘

                              📧 New Email Arrives
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │  src/12_processing.py            │
                    │  process_raw_emails_batch()      │
                    └──────────────────────────────────┘
                                      │
                                      ├─ Decrypt subject, body, sender
                                      ├─ Fetch user.urgency_booster_enabled
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │  active_ai.analyze_email(        │
                    │    subject, body, sender,        │
                    │    user_id, db, booster_enabled  │
                    │  )                                │
                    └──────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
              Cloud Client?                    Local Client?
                    │                                   │
                    ▼                                   ▼
        ┌───────────────────────┐         ┌────────────────────────┐
        │  OpenAI/Anthropic/    │         │  LocalOllamaClient     │
        │  Mistral              │         │  (Phase X enabled)     │
        │                       │         └────────────────────────┘
        │  **kwargs ignored     │                    │
        │  → Standard LLM Call  │                    │
        └───────────────────────┘                    ▼
                    │              ┌──────────────────────────────────┐
                    │              │  PHASE X PRE-CHECK:              │
                    │              │  1. Is sender Trusted?           │
                    │              │  2. Is booster enabled?          │
                    │              └──────────────────────────────────┘
                    │                             │
                    │              ┌──────────────┴──────────────┐
                    │              │                             │
                    │           YES (Trusted + Enabled)        NO
                    │              │                             │
                    │              ▼                             ▼
                    │    ┌──────────────────────┐    ┌──────────────────┐
                    │    │  UrgencyBooster      │    │  Standard LLM    │
                    │    │  (spaCy NER)         │    │  (Ollama Chat)   │
                    │    │  100-300ms           │    │  5-10min (CPU)   │
                    │    └──────────────────────┘    └──────────────────┘
                    │              │                             │
                    │              ├─ Analyze with spaCy         │
                    │              ├─ Extract NER entities       │
                    │              ├─ Calculate confidence       │
                    │              │                             │
                    │              ▼                             │
                    │    ┌──────────────────────┐               │
                    │    │  Confidence >= 0.6?  │               │
                    │    └──────────────────────┘               │
                    │         YES │      │ NO                    │
                    │             │      └────────────┬──────────┘
                    │             │                   │
                    │             ▼                   ▼
                    │    ┌──────────────────┐  ┌─────────────────┐
                    │    │  Return Result   │  │  Standard LLM   │
                    │    │  (Early Exit)    │  │  (Fallback)     │
                    │    └──────────────────┘  └─────────────────┘
                    │             │                   │
                    └─────────────┴───────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────────────┐
                    │  Classification Result:          │
                    │  - urgency_score                 │
                    │  - importance_score              │
                    │  - category                      │
                    │  - confidence                    │
                    │  - signals                       │
                    │  - method (spacy_ner/llm)        │
                    └──────────────────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────────────┐
                    │  Save to ProcessedEmail          │
                    └──────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════
                        TRUSTED SENDER MANAGEMENT
═══════════════════════════════════════════════════════════════════════════

                              User in Settings UI
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
        ┌───────────────────┐  ┌──────────────┐  ┌──────────────┐
        │  Add Trusted      │  │  Toggle      │  │  Load        │
        │  Sender           │  │  Booster     │  │  Suggestions │
        └───────────────────┘  └──────────────┘  └──────────────┘
                    │                 │                 │
                    ▼                 ▼                 ▼
        ┌───────────────────┐  ┌──────────────┐  ┌──────────────┐
        │  POST /api/       │  │  POST /api/  │  │  GET /api/   │
        │  trusted-senders  │  │  settings/   │  │  trusted-    │
        │                   │  │  urgency-    │  │  senders/    │
        │                   │  │  booster     │  │  suggestions │
        └───────────────────┘  └──────────────┘  └──────────────┘
                    │                 │                 │
                    ▼                 ▼                 ▼
        ┌───────────────────────────────────────────────────────┐
        │  src/services/trusted_senders.py                      │
        │  TrustedSenderManager                                 │
        │                                                        │
        │  ┌─────────────────────────────────────────────────┐ │
        │  │  add_trusted_sender()                           │ │
        │  │  - Validate pattern (regex)                     │ │
        │  │  - Check limit (max 500)                        │ │
        │  │  - Check uniqueness                             │ │
        │  │  - Normalize (lowercase)                        │ │
        │  │  - Save to DB                                   │ │
        │  └─────────────────────────────────────────────────┘ │
        │                                                        │
        │  ┌─────────────────────────────────────────────────┐ │
        │  │  is_trusted_sender()                            │ │
        │  │  - Query trusted_senders table                  │ │
        │  │  - Match: exact/email_domain/domain             │ │
        │  │  - Return True/False                            │ │
        │  └─────────────────────────────────────────────────┘ │
        │                                                        │
        │  ┌─────────────────────────────────────────────────┐ │
        │  │  get_suggestions_from_emails()                  │ │
        │  │  - Query RawEmail history                       │ │
        │  │  - Group by sender                              │ │
        │  │  - Count emails                                 │ │
        │  │  - Filter: min_email_count >= 2                 │ │
        │  │  - Exclude existing trusted senders             │ │
        │  │  - Return top 10                                │ │
        │  └─────────────────────────────────────────────────┘ │
        └───────────────────────────────────────────────────────┘
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │  Database: trusted_senders       │
                    │  - user_id                       │
                    │  - sender_pattern                │
                    │  - pattern_type                  │
                    │  - use_urgency_booster           │
                    │  - email_count                   │
                    │  - last_seen_at                  │
                    └──────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════
                        URGENCYBOOSTER ANALYSIS
═══════════════════════════════════════════════════════════════════════════

                Email Subject + Body + Sender
                              │
                              ▼
        ┌────────────────────────────────────────────────┐
        │  src/services/urgency_booster.py               │
        │  UrgencyBooster.analyze_urgency()              │
        └────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  spaCy NER    │   │  Regex        │   │  Keyword      │
│  Entities     │   │  Patterns     │   │  Matching     │
└───────────────┘   └───────────────┘   └───────────────┘
        │                     │                     │
        │  Extract:           │  Extract:           │  Detect:
        │  - DATE             │  - Money (€, EUR)   │  - Action Verbs
        │  - MONEY            │  - Time Patterns    │  - Authority
        │  - PERSON           │                     │  - Invoice
        │  - ORG              │                     │
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
                              ▼
        ┌────────────────────────────────────────────────┐
        │  Signal Detection                              │
        │                                                 │
        │  ┌───────────────────────────────────────────┐ │
        │  │  time_pressure: Bool                      │ │
        │  │  - Keywords: "dringend", "eilig", "sofort"│ │
        │  │  - Deadline: < 7 days                     │ │
        │  └───────────────────────────────────────────┘ │
        │                                                 │
        │  ┌───────────────────────────────────────────┐ │
        │  │  deadline_hours: int|None                 │ │
        │  │  - DATE entity in next 7 days             │ │
        │  │  - Relative: "morgen", "heute"            │ │
        │  └───────────────────────────────────────────┘ │
        │                                                 │
        │  ┌───────────────────────────────────────────┐ │
        │  │  money_amount: float|None                 │ │
        │  │  - MONEY entity or regex                  │ │
        │  │  - Formats: 500€, EUR 500                 │ │
        │  └───────────────────────────────────────────┘ │
        │                                                 │
        │  ┌───────────────────────────────────────────┐ │
        │  │  action_verbs: List[str]                  │ │
        │  │  - senden, überweisen, bestätigen, ...    │ │
        │  └───────────────────────────────────────────┘ │
        │                                                 │
        │  ┌───────────────────────────────────────────┐ │
        │  │  authority_person: Bool                   │ │
        │  │  - Titles: Geschäftsführer, Direktor, ... │ │
        │  └───────────────────────────────────────────┘ │
        │                                                 │
        │  ┌───────────────────────────────────────────┐ │
        │  │  invoice_detected: Bool                   │ │
        │  │  - Keywords: Rechnung, Mahnung, ...       │ │
        │  └───────────────────────────────────────────┘ │
        └────────────────────────────────────────────────┘
                              │
                              ▼
        ┌────────────────────────────────────────────────┐
        │  Confidence Calculation                        │
        │                                                 │
        │  Base: 5 signals × 0.15 = 0.75 max            │
        │                                                 │
        │  Modifiers:                                    │
        │  + time_pressure: +0.15                        │
        │  + deadline < 24h: +0.10                       │
        │  + money > 1000€: +0.10                        │
        │  + authority_person: +0.05                     │
        │                                                 │
        │  Final: min(1.0, sum)                          │
        └────────────────────────────────────────────────┘
                              │
                              ▼
        ┌────────────────────────────────────────────────┐
        │  Return:                                       │
        │  {                                             │
        │    "urgency_score": 0-10,                      │
        │    "importance_score": 0-10,                   │
        │    "category": "aktion_erforderlich",          │
        │    "confidence": 0.0-1.0,                      │
        │    "signals": {... all detected signals ...},  │
        │    "method": "spacy_ner" | "fallback"          │
        │  }                                             │
        └────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════
                        PATTERN MATCHING LOGIC
═══════════════════════════════════════════════════════════════════════════

Trusted Sender Pattern Types:

┌─────────────────────────────────────────────────────────────────────────┐
│  1. EXACT (pattern_type="exact")                                        │
│                                                                          │
│  Pattern: "rechnung@firma.de"                                           │
│  Matches:                                                                │
│    ✓ rechnung@firma.de                                                  │
│    ✗ info@firma.de                                                      │
│    ✗ rechnung@other.de                                                  │
│                                                                          │
│  SQL: WHERE sender_pattern = LOWER(sender_email)                        │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  2. EMAIL_DOMAIN (pattern_type="email_domain")                          │
│                                                                          │
│  Pattern: "@firma.de"                                                   │
│  Matches:                                                                │
│    ✓ rechnung@firma.de                                                  │
│    ✓ info@firma.de                                                      │
│    ✗ rechnung@other.de                                                  │
│                                                                          │
│  SQL: WHERE LOWER(sender_email) LIKE '%' || sender_pattern             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  3. DOMAIN (pattern_type="domain")                                      │
│                                                                          │
│  Pattern: "firma.de"                                                    │
│  Matches:                                                                │
│    ✓ rechnung@firma.de                                                  │
│    ✓ info@firma.de                                                      │
│    ✓ sub@mail.firma.de                                                  │
│    ✗ rechnung@other.de                                                  │
│                                                                          │
│  SQL: WHERE LOWER(sender_email) LIKE '%@%' || sender_pattern           │
│            OR LOWER(sender_email) LIKE '%@%.' || sender_pattern         │
└─────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════
                        PERFORMANCE COMPARISON
═══════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────┐
│  SCENARIO 1: Trusted Sender Email (UrgencyBooster)                      │
│                                                                          │
│  Steps:                                                                  │
│    1. Decrypt email:                ~10ms                               │
│    2. Check trusted sender:         ~5ms   (DB query)                   │
│    3. Load spaCy (first time):      ~500ms (cached after)               │
│    4. NER analysis:                 ~150ms                              │
│    5. Signal extraction:            ~50ms                               │
│    6. Confidence calculation:       ~10ms                               │
│    ─────────────────────────────────────────                            │
│    TOTAL:                           ~725ms (first) / ~225ms (cached)    │
│                                                                          │
│  Average: 200-300ms per email after cache                               │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  SCENARIO 2: Non-Trusted Email (Standard LLM)                           │
│                                                                          │
│  Steps:                                                                  │
│    1. Decrypt email:                ~10ms                               │
│    2. Check trusted sender:         ~5ms   (not found)                  │
│    3. Build LLM prompt:             ~20ms                               │
│    4. Ollama inference:             ~300,000ms (5min CPU-only)          │
│       OR                            ~20,000ms (20s with GPU)            │
│    5. Parse JSON response:          ~10ms                               │
│    ─────────────────────────────────────────                            │
│    TOTAL:                           ~5-10 minutes (CPU)                 │
│                                     ~20-30 seconds (GPU)                │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  PERFORMANCE GAIN                                                        │
│                                                                          │
│  CPU-only System:                                                        │
│    Standard: 300s (5min)                                                │
│    UrgencyBooster: 0.3s                                                 │
│    Speedup: 1000x faster 🚀🚀🚀                                          │
│                                                                          │
│  GPU System:                                                             │
│    Standard: 25s                                                         │
│    UrgencyBooster: 0.3s                                                 │
│    Speedup: 83x faster 🚀                                                │
│                                                                          │
│  Trusted Sender Ratio: 30% of emails                                    │
│  Batch processing 100 emails:                                           │
│    - 30 Trusted: 30 × 0.3s = 9s                                         │
│    - 70 Non-Trusted: 70 × 300s = 21,000s (CPU)                         │
│    - TOTAL: 21,009s (~5.8 hours)                                        │
│                                                                          │
│  Without Phase X:                                                        │
│    - 100 × 300s = 30,000s (~8.3 hours)                                  │
│                                                                          │
│  Time Saved: 30% faster overall (8.3h → 5.8h)                          │
└─────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════
                        DATABASE SCHEMA
═══════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────┐
│  TABLE: trusted_senders                                                 │
│                                                                          │
│  ┌────────────────────┬──────────────────┬──────────────────────────┐  │
│  │ Column             │ Type             │ Constraints              │  │
│  ├────────────────────┼──────────────────┼──────────────────────────┤  │
│  │ id                 │ INTEGER          │ PRIMARY KEY              │  │
│  │ user_id            │ INTEGER          │ FK(users.id), NOT NULL   │  │
│  │ sender_pattern     │ VARCHAR(255)     │ NOT NULL                 │  │
│  │ pattern_type       │ VARCHAR(20)      │ NOT NULL                 │  │
│  │ label              │ VARCHAR(100)     │ NULL                     │  │
│  │ use_urgency_booster│ BOOLEAN          │ NOT NULL, DEFAULT TRUE   │  │
│  │ added_at           │ DATETIME         │ NOT NULL                 │  │
│  │ last_seen_at       │ DATETIME         │ NULL                     │  │
│  │ email_count        │ INTEGER          │ NOT NULL, DEFAULT 0      │  │
│  └────────────────────┴──────────────────┴──────────────────────────┘  │
│                                                                          │
│  INDEXES:                                                                │
│    - PRIMARY: id                                                         │
│    - COMPOSITE: (user_id, sender_pattern)  ← Performance optimization   │
│    - UNIQUE: (user_id, sender_pattern)     ← Prevent duplicates         │
│                                                                          │
│  CONSTRAINTS:                                                            │
│    - FOREIGN KEY: user_id → users.id (CASCADE DELETE)                   │
│    - UNIQUE: (user_id, sender_pattern)                                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  TABLE: users (extended)                                                │
│                                                                          │
│  New Column:                                                             │
│  ┌─────────────────────────┬──────────┬─────────────────────────────┐  │
│  │ urgency_booster_enabled │ BOOLEAN  │ NOT NULL, DEFAULT TRUE      │  │
│  └─────────────────────────┴──────────┴─────────────────────────────┘  │
│                                                                          │
│  Purpose: Global toggle for UrgencyBooster per user                     │
└─────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════
```
