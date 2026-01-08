# Phase Y: spaCy Hybrid Pipeline - Implementierungskonzept

## 🎯 Übersicht

**Ziel**: Erweiterung des UrgencyBooster zu einer vollständigen Hybrid-Pipeline mit:
- Erweiterten Regel-Detektoren (5 Stufen)
- Konfigurierbaren Keyword-Sets (pro Account)
- VIP-Absender-System für automatischen Importance-Boost
- Neuer UI `/spacy-tuning` für Benutzer-Konfiguration
- Punktebasiertem Scoring (statt 0-1 Floats)

**Performance-Ziel**: 150-400ms pro Email (CPU-only)

---

## 📊 Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EMAIL INPUT                                   │
│  (subject, body, sender, account_id)                                │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STUFE 0: VORVERARBEITUNG                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ • HTML → Text (beautifulsoup)                                │   │
│  │ • Signature/Quoted-Reply Removal                             │   │
│  │ • Subject + Body Kombination                                 │   │
│  │ • Metadata Extraktion (sender, thread_depth)                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STUFE 1: spaCy CORE PIPELINE                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Model: de_core_news_md (43MB, bessere NER)                   │   │
│  │ Components: tok2vec, tagger, parser, lemmatizer, ner         │   │
│  │ Entities: DATE, MONEY, PERSON, ORG                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STUFE 2: REGEL-DETEKTOREN (5 Module)                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 1. DeadlineDetector      → time_pressure, deadline_hours     │   │
│  │ 2. UrgencyKeywordDetector → urgency_keywords                 │   │
│  │ 3. ActionRequestDetector  → has_action_request               │   │
│  │ 4. ImportanceDetector     → importance_keywords              │   │
│  │ 5. NegativeSignalDetector → is_newsletter, is_auto_reply     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STUFE 3: KONTEXT-ANALYSE                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ • VIP-Absender Check (DB: spacy_vip_senders)                 │   │
│  │ • Direct-To vs CC-Only                                       │   │
│  │ • Externe vs Interne Domain                                  │   │
│  │ • Thread-Tiefe (Reply-Count)                                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STUFE 4: SCORING & KLASSIFIKATION                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Urgency-Score:    Σ(urgency_points)    → 0-10 Scale          │   │
│  │ Importance-Score: Σ(importance_points) → 0-10 Scale          │   │
│  │                                                               │   │
│  │ Priority-Mapping:                                             │   │
│  │   P0 = wichtig & dringend (U≥6 AND I≥6)                      │   │
│  │   P1 = wichtig            (I≥6)                               │   │
│  │   P2 = dringend           (U≥6)                               │   │
│  │   P3 = normal             (else)                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Datenbank-Schema

### Neue Tabellen

```sql
-- ═══════════════════════════════════════════════════════════════════
-- TABELLE 1: VIP-Absender (für automatischen Importance-Boost)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE spacy_vip_senders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_id INTEGER,  -- NULL = global, sonst account-spezifisch
    
    -- Sender Pattern (wie TrustedSender)
    sender_pattern VARCHAR(255) NOT NULL,
    pattern_type VARCHAR(20) NOT NULL,  -- 'exact', 'email_domain', 'domain'
    
    -- VIP-Konfiguration
    label VARCHAR(100),  -- "Chef", "CEO", "Wichtiger Kunde"
    importance_boost INTEGER DEFAULT 3,  -- +1 bis +5 Importance-Punkte
    urgency_boost INTEGER DEFAULT 0,     -- Optional: auch Urgency boosten
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES mail_accounts(id) ON DELETE CASCADE,
    UNIQUE(user_id, sender_pattern, account_id)
);

CREATE INDEX ix_spacy_vip_user_account ON spacy_vip_senders(user_id, account_id);


-- ═══════════════════════════════════════════════════════════════════
-- TABELLE 2: Konfigurierbare Keyword-Sets (pro Account)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE spacy_keyword_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_id INTEGER,  -- NULL = global, sonst account-spezifisch
    
    -- Set-Identifikation
    set_type VARCHAR(50) NOT NULL,  -- 'urgency_high', 'urgency_low', 'action_verbs', etc.
    
    -- Keywords als JSON Array
    keywords_json TEXT NOT NULL,  -- ["dringend", "asap", "sofort"]
    
    -- Scoring-Konfiguration
    points_per_match INTEGER DEFAULT 2,  -- Punkte pro gefundenem Keyword
    max_points INTEGER DEFAULT 4,         -- Maximum für dieses Set
    
    -- Flags
    is_active BOOLEAN DEFAULT TRUE,
    is_custom BOOLEAN DEFAULT FALSE,  -- TRUE = User-definiert, FALSE = System-Default
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES mail_accounts(id) ON DELETE CASCADE,
    UNIQUE(user_id, account_id, set_type)
);

CREATE INDEX ix_spacy_keywords_user_account ON spacy_keyword_sets(user_id, account_id, set_type);


-- ═══════════════════════════════════════════════════════════════════
-- TABELLE 3: Scoring-Konfiguration (Thresholds, Weights)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE spacy_scoring_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_id INTEGER,  -- NULL = global
    
    -- Thresholds für Priority-Mapping
    urgency_high_threshold INTEGER DEFAULT 6,    -- Ab diesem Score = "dringend"
    importance_high_threshold INTEGER DEFAULT 6, -- Ab diesem Score = "wichtig"
    
    -- Deadline-Scoring
    deadline_critical_hours INTEGER DEFAULT 8,   -- ≤8h = kritisch
    deadline_urgent_hours INTEGER DEFAULT 24,    -- ≤24h = dringend
    deadline_soon_hours INTEGER DEFAULT 72,      -- ≤72h = bald
    
    deadline_critical_points INTEGER DEFAULT 4,
    deadline_urgent_points INTEGER DEFAULT 3,
    deadline_soon_points INTEGER DEFAULT 2,
    
    -- Absender-Kontext
    vip_default_importance INTEGER DEFAULT 3,
    external_sender_importance INTEGER DEFAULT 1,
    direct_to_importance INTEGER DEFAULT 1,
    cc_only_importance INTEGER DEFAULT -1,
    many_recipients_importance INTEGER DEFAULT -1,
    
    -- Negative Signale
    newsletter_urgency_penalty INTEGER DEFAULT -5,
    newsletter_importance_penalty INTEGER DEFAULT -4,
    auto_reply_penalty INTEGER DEFAULT -5,
    fyi_penalty INTEGER DEFAULT -2,
    
    -- Flags
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES mail_accounts(id) ON DELETE CASCADE,
    UNIQUE(user_id, account_id)
);


-- ═══════════════════════════════════════════════════════════════════
-- TABELLE 4: User-eigene Domains (für intern/extern Erkennung)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE spacy_user_domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_id INTEGER,
    
    domain VARCHAR(255) NOT NULL,  -- "meinefirma.de", "meinefirma.com"
    is_internal BOOLEAN DEFAULT TRUE,  -- TRUE = intern, FALSE = explizit extern
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES mail_accounts(id) ON DELETE CASCADE,
    UNIQUE(user_id, account_id, domain)
);
```

---

## 📚 Default Keyword-Sets (Best Practice)

### SET 1: `urgency_keywords_high` - Hohe Dringlichkeit
```python
URGENCY_KEYWORDS_HIGH = {
    # Deutsch
    'dringend', 'eilig', 'sofort', 'umgehend', 'unverzüglich',
    'asap', 'schnellstmöglich', 'priorität', 'kritisch',
    'notfall', 'alarm', 'eskalation',
    
    # Englisch (falls gemischt)
    'urgent', 'immediately', 'critical', 'emergency', 'escalation',
    'time-sensitive', 'high priority', 'top priority'
}
# Points: +3 per match, max +4
```

### SET 2: `urgency_keywords_low` - Niedrige Dringlichkeit
```python
URGENCY_KEYWORDS_LOW = {
    'bald', 'zeitnah', 'demnächst', 'gelegentlich',
    'wenn möglich', 'bei gelegenheit',
    'soon', 'when possible', 'at your convenience'
}
# Points: +1 per match, max +2
```

### SET 3: `deadline_phrases` - Deadline-Erkennung
```python
DEADLINE_PHRASES = {
    # Relative Zeit
    'heute': 0,
    'bis heute': 0,
    'heute noch': 0,
    'heute abend': 8,
    'morgen': 24,
    'bis morgen': 24,
    'übermorgen': 48,
    'bis ende der woche': 120,
    'bis freitag': 120,  # Context-dependent
    'diese woche': 120,
    'nächste woche': 168,
    
    # Englisch
    'today': 0,
    'by today': 0,
    'tomorrow': 24,
    'by tomorrow': 24,
    'end of day': 8,
    'eod': 8,
    'cob': 8,  # Close of Business
    'end of week': 120,
    'eow': 120,
}
# Points: Based on hours (see scoring config)
```

### SET 4: `action_verbs` - Handlungsaufforderungen
```python
ACTION_VERBS = {
    # Direkte Aufforderungen
    'senden', 'schicken', 'übersenden',
    'überweisen', 'bezahlen', 'zahlen',
    'bestätigen', 'genehmigen', 'freigeben',
    'antworten', 'rückmelden', 'melden',
    'prüfen', 'checken', 'kontrollieren',
    'unterschreiben', 'signieren',
    'erledigen', 'abschließen', 'fertigstellen',
    'buchen', 'reservieren',
    'einreichen', 'übermitteln',
    
    # Höfliche Formen (Phrase-basiert)
    'bitte', 'könntest du', 'könnten sie', 'würdest du',
    'kannst du', 'können sie',
    'ich brauche', 'ich benötige', 'wir brauchen',
    
    # Englisch
    'send', 'submit', 'confirm', 'approve', 'review',
    'sign', 'complete', 'pay', 'transfer', 'forward',
    'please', 'could you', 'can you', 'would you',
    'i need', 'we need'
}
# Points: +2 urgency, +2 importance per match, max +4 each
```

### SET 5: `importance_keywords_high` - Hohe Wichtigkeit
```python
IMPORTANCE_KEYWORDS_HIGH = {
    # Business-kritisch
    'freigabe', 'genehmigung', 'entscheidung',
    'budget', 'kosten', 'investition',
    'angebot', 'auftrag', 'bestellung',
    'rechnung', 'mahnung', 'zahlung',
    'vertrag', 'vereinbarung',
    'kunde', 'klient', 'mandant',
    'eskalation', 'beschwerde',
    'incident', 'outage', 'störung',
    'datenschutz', 'compliance', 'audit',
    
    # Englisch
    'approval', 'decision', 'budget', 'cost',
    'invoice', 'payment', 'contract',
    'customer', 'client', 'escalation',
    'compliance', 'audit', 'legal'
}
# Points: +3 per match, max +4
```

### SET 6: `importance_keywords_medium` - Mittlere Wichtigkeit
```python
IMPORTANCE_KEYWORDS_MEDIUM = {
    'besprechung', 'meeting', 'termin',
    'projekt', 'aufgabe', 'task',
    'update', 'status', 'bericht', 'report',
    'feedback', 'review',
    'frage', 'anfrage', 'question'
}
# Points: +2 per match, max +3
```

### SET 7: `authority_titles` - Autoritätspersonen
```python
AUTHORITY_TITLES = {
    # C-Level
    'ceo', 'cfo', 'cto', 'coo', 'cio',
    
    # Deutsch
    'geschäftsführer', 'geschäftsführerin',
    'vorstand', 'vorständin',
    'direktor', 'direktorin',
    'präsident', 'präsidentin',
    'chef', 'chefin',
    'abteilungsleiter', 'abteilungsleiterin',
    'teamleiter', 'teamleiterin',
    'bereichsleiter', 'bereichsleiterin',
    
    # Englisch
    'director', 'president', 'vice president', 'vp',
    'manager', 'head of', 'lead'
}
# Points: +2 importance when found in sender or body
```

### SET 8: `invoice_keywords` - Rechnungserkennung
```python
INVOICE_KEYWORDS = {
    'rechnung', 'invoice',
    'rechnungsnummer', 'invoice number',
    'zahlungserinnerung', 'payment reminder',
    'mahnung', 'zahlungsaufforderung',
    'fällig', 'fälligkeit', 'due date',
    'betrag', 'summe', 'amount',
    'überweisung', 'bankverbindung', 'iban',
    'steuernummer', 'ust-id', 'vat'
}
# Trigger: ≥2 matches → invoice_detected = True
# Points: +3 urgency, +3 importance
```

### SET 9: `newsletter_keywords` - Newsletter-Erkennung
```python
NEWSLETTER_KEYWORDS = {
    # Abmelde-Signale
    'abmelden', 'abbestellen', 'unsubscribe',
    'newsletter abbestellen', 'newsletter preferences',
    'email preferences', 'communication preferences',
    
    # Marketing-Signale
    'newsletter', 'promotion', 'angebot',
    'rabatt', 'discount', 'sale', 'deal',
    'jetzt kaufen', 'shop now', 'buy now',
    'limited time', 'nur heute', 'nur noch',
    'exklusiv für sie', 'exclusive offer',
    
    # Absender-Patterns
    'noreply', 'no-reply', 'donotreply',
    'newsletter@', 'news@', 'marketing@',
    'promo@', 'info@', 'support@'
}
# Trigger: ≥2 matches → is_newsletter = True
# Penalty: -4 importance, -5 urgency
```

### SET 10: `auto_reply_keywords` - Auto-Reply-Erkennung
```python
AUTO_REPLY_KEYWORDS = {
    # Deutsch
    'abwesenheitsnotiz', 'abwesenheitsmeldung',
    'automatische antwort', 'auto-antwort',
    'bin nicht im büro', 'nicht erreichbar',
    'urlaub', 'außer haus',
    
    # Englisch
    'out of office', 'ooo',
    'automatic reply', 'auto-reply', 'autoreply',
    'away from office', 'on vacation', 'on leave',
    'will respond when', 'limited access'
}
# Trigger: ≥1 match → is_auto_reply = True
# Penalty: -5 importance, -5 urgency
```

### SET 11: `fyi_keywords` - FYI/Informational
```python
FYI_KEYWORDS = {
    # Deutsch
    'zur information', 'zur kenntnisnahme',
    'zur info', 'fyi', 'zur kenntnis',
    'nur zur info', 'info only',
    'kein handlungsbedarf', 'keine aktion nötig',
    
    # Englisch
    'for your information', 'for your reference',
    'fyi', 'fyr', 'no action required',
    'no action needed', 'informational'
}
# Trigger: Match in subject or first 200 chars
# Penalty: -2 importance (unless action_request detected)
```

### SET 12: `spam_keywords` - Spam-Erkennung
```python
SPAM_KEYWORDS = {
    # Deutsch
    'gewonnen', 'gewinner', 'jackpot',
    'gratis', 'kostenlos', 'geschenk',
    'millionär', 'reich werden',
    'sofort geld', 'schnell reich',
    'kredit ohne schufa', 'darlehen sofort',
    
    # Englisch  
    'winner', 'won', 'prize', 'lottery',
    'free money', 'get rich', 'millionaire',
    'viagra', 'casino', 'crypto opportunity',
    
    # Patterns
    '!!!', '€€€', '$$$', '***'
}
# Trigger: ≥2 matches → spam_suspected = True
# Penalty: -5 importance, -5 urgency
```

---

## 🔧 Scoring-System

### Urgency-Score Berechnung

```python
urgency_points = 0

# 1. Deadline-basiert (höchste Gewichtung)
if deadline_hours <= 8:
    urgency_points += config.deadline_critical_points  # +4
elif deadline_hours <= 24:
    urgency_points += config.deadline_urgent_points    # +3
elif deadline_hours <= 72:
    urgency_points += config.deadline_soon_points      # +2

# 2. Urgency-Keywords
high_matches = count_matches(text, URGENCY_KEYWORDS_HIGH)
urgency_points += min(high_matches * 3, 4)

low_matches = count_matches(text, URGENCY_KEYWORDS_LOW)
urgency_points += min(low_matches * 1, 2)

# 3. Action-Request
if has_action_request:
    urgency_points += 2

# 4. Invoice detected
if invoice_detected:
    urgency_points += 3

# 5. Negative Signale (Abzüge)
if is_newsletter:
    urgency_points += config.newsletter_urgency_penalty  # -5
if is_auto_reply:
    urgency_points += config.auto_reply_penalty          # -5

# Normalisierung auf 0-10 Scale
urgency_score = max(0, min(10, urgency_points))
```

### Importance-Score Berechnung

```python
importance_points = 0

# 1. VIP-Absender (höchste Gewichtung)
vip_match = check_vip_sender(sender, account_id)
if vip_match:
    importance_points += vip_match.importance_boost  # +1 bis +5

# 2. Importance-Keywords
high_matches = count_matches(text, IMPORTANCE_KEYWORDS_HIGH)
importance_points += min(high_matches * 3, 4)

medium_matches = count_matches(text, IMPORTANCE_KEYWORDS_MEDIUM)
importance_points += min(medium_matches * 2, 3)

# 3. Authority-Person im Text
if has_authority_person:
    importance_points += 2

# 4. Invoice detected
if invoice_detected:
    importance_points += 3

# 5. Action-Request
if has_action_request:
    importance_points += 2

# 6. Absender-Kontext
if is_external_sender:
    importance_points += config.external_sender_importance  # +1
if is_direct_to:
    importance_points += config.direct_to_importance        # +1
if is_cc_only:
    importance_points += config.cc_only_importance          # -1
if many_recipients:
    importance_points += config.many_recipients_importance  # -1

# 7. Negative Signale
if is_newsletter:
    importance_points += config.newsletter_importance_penalty  # -4
if is_auto_reply:
    importance_points += config.auto_reply_penalty             # -5
if is_fyi and not has_action_request:
    importance_points += config.fyi_penalty                    # -2

# Normalisierung auf 0-10 Scale
importance_score = max(0, min(10, importance_points))
```

### Priority-Mapping

```python
def calculate_priority(urgency_score: int, importance_score: int, config) -> str:
    """
    Mappt Scores auf Priority-Klassen.
    
    P0 = wichtig & dringend (sofort handeln)
    P1 = wichtig           (heute erledigen)
    P2 = dringend          (zeitnah, aber nicht kritisch)
    P3 = normal            (kann warten)
    """
    is_urgent = urgency_score >= config.urgency_high_threshold      # Default: 6
    is_important = importance_score >= config.importance_high_threshold  # Default: 6
    
    if is_urgent and is_important:
        return "P0"  # Dringend & Wichtig
    elif is_important:
        return "P1"  # Wichtig
    elif is_urgent:
        return "P2"  # Dringend
    else:
        return "P3"  # Normal
```

---

## 🖥️ UI-Design: `/spacy-tuning`

### Hauptbereiche

```
┌─────────────────────────────────────────────────────────────────────┐
│  ⚙️ spaCy Tuning - Email-Klassifikation anpassen                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Account: [▼ Alle Accounts (Global)]  [Account 1]  [Account 2]      │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  📑 TABS:                                                            │
│  ┌──────────┬──────────────┬──────────────┬──────────────┐          │
│  │ 👑 VIP   │ 🔑 Keywords  │ ⚖️ Scoring   │ 🏢 Domains   │          │
│  └──────────┴──────────────┴──────────────┴──────────────┘          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Tab 1: VIP-Absender

```
┌─────────────────────────────────────────────────────────────────────┐
│  👑 VIP-Absender                                                    │
│  Emails von VIP-Absendern erhalten automatisch Importance-Boost     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  + Neuer VIP-Absender                                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Pattern:    [chef@firma.de_________________]                 │   │
│  │ Typ:        [▼ Exakt] [Email-Domain] [Domain]               │   │
│  │ Label:      [CEO____________________________]                │   │
│  │ Importance: [▼ +3 Punkte] (+1 / +2 / +3 / +4 / +5)         │   │
│  │ Urgency:    [▼ +0 Punkte] (optional)                        │   │
│  │                                          [➕ Hinzufügen]     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Bestehende VIP-Absender:                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 👑 chef@firma.de        │ CEO     │ Imp +3 │ [✏️] [🗑️]    │   │
│  │ 👑 @buchhaltung.firma.de│ Finance │ Imp +2 │ [✏️] [🗑️]    │   │
│  │ 👑 wichtiger.kunde.de   │ Kunde A │ Imp +4 │ [✏️] [🗑️]    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Tab 2: Keyword-Sets

```
┌─────────────────────────────────────────────────────────────────────┐
│  🔑 Keyword-Sets                                                    │
│  Passe die Erkennungs-Keywords für deine Bedürfnisse an            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Set auswählen: [▼ Dringlichkeit (Hoch)]                           │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 🏷️ urgency_keywords_high                                    │   │
│  │                                                               │   │
│  │ Aktive Keywords:                                             │   │
│  │ ┌─────────────────────────────────────────────────────────┐ │   │
│  │ │ dringend ✕ │ eilig ✕ │ sofort ✕ │ asap ✕ │ kritisch ✕ │ │   │
│  │ │ umgehend ✕ │ priorität ✕ │ notfall ✕ │ eskalation ✕   │ │   │
│  │ └─────────────────────────────────────────────────────────┘ │   │
│  │                                                               │   │
│  │ Neues Keyword: [________________] [➕]                       │   │
│  │                                                               │   │
│  │ Scoring:                                                      │   │
│  │   Punkte pro Match: [▼ 3]                                    │   │
│  │   Maximum Punkte:   [▼ 4]                                    │   │
│  │                                                               │   │
│  │ [🔄 Auf Standard zurücksetzen]        [💾 Speichern]        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Verfügbare Sets:                                                   │
│  ├─ 🔴 Dringlichkeit (Hoch)    ✅ Aktiv                            │
│  ├─ 🟡 Dringlichkeit (Niedrig) ✅ Aktiv                            │
│  ├─ ⏰ Deadline-Phrasen        ✅ Aktiv                            │
│  ├─ 🎯 Handlungsaufforderungen ✅ Aktiv                            │
│  ├─ ⭐ Wichtigkeit (Hoch)      ✅ Aktiv                            │
│  ├─ 📊 Wichtigkeit (Mittel)    ✅ Aktiv                            │
│  ├─ 👔 Autoritätspersonen      ✅ Aktiv                            │
│  ├─ 💰 Rechnungs-Keywords      ✅ Aktiv                            │
│  ├─ 📰 Newsletter-Erkennung    ✅ Aktiv                            │
│  ├─ 🤖 Auto-Reply-Erkennung    ✅ Aktiv                            │
│  ├─ ℹ️ FYI-Keywords            ✅ Aktiv                            │
│  └─ 🚫 Spam-Keywords           ✅ Aktiv                            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Tab 3: Scoring-Konfiguration

```
┌─────────────────────────────────────────────────────────────────────┐
│  ⚖️ Scoring-Konfiguration                                          │
│  Passe Schwellenwerte und Punktevergabe an                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Priority-Schwellenwerte:                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Dringend ab:  [▼ 6] Punkte  (Urgency ≥ X → "dringend")     │   │
│  │ Wichtig ab:   [▼ 6] Punkte  (Importance ≥ X → "wichtig")   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Deadline-Scoring:                                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Kritisch (≤ X Stunden): [▼ 8]h   → [▼ +4] Punkte          │   │
│  │ Dringend (≤ X Stunden): [▼ 24]h  → [▼ +3] Punkte          │   │
│  │ Bald     (≤ X Stunden): [▼ 72]h  → [▼ +2] Punkte          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Absender-Kontext:                                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ VIP-Standard:        [▼ +3] Importance                      │   │
│  │ Externer Absender:   [▼ +1] Importance                      │   │
│  │ Direkter Empfänger:  [▼ +1] Importance                      │   │
│  │ Nur in CC:           [▼ -1] Importance                      │   │
│  │ Viele Empfänger:     [▼ -1] Importance                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Negative Signale (Abzüge):                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Newsletter:   Urgency [▼ -5]  Importance [▼ -4]            │   │
│  │ Auto-Reply:   Urgency [▼ -5]  Importance [▼ -5]            │   │
│  │ FYI:          Urgency [▼  0]  Importance [▼ -2]            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│                              [🔄 Standard]  [💾 Speichern]          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Tab 4: Eigene Domains

```
┌─────────────────────────────────────────────────────────────────────┐
│  🏢 Eigene Domains                                                  │
│  Definiere interne/externe Domains für die Absender-Analyse        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  + Neue Domain                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Domain:  [meinefirma.de______________]                       │   │
│  │ Typ:     (●) Intern  ( ) Extern                              │   │
│  │                                          [➕ Hinzufügen]     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Konfigurierte Domains:                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 🏢 meinefirma.de      │ Intern  │ [✏️] [🗑️]                │   │
│  │ 🏢 meinefirma.com     │ Intern  │ [✏️] [🗑️]                │   │
│  │ 🏢 tochter.gruppe.de  │ Intern  │ [✏️] [🗑️]                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ℹ️ Absender von internen Domains erhalten keinen                   │
│     "Externer Absender"-Bonus.                                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Dateistruktur

```
src/
├── services/
│   ├── urgency_booster.py          # Bestehend → Erweitern
│   ├── spacy_pipeline.py           # NEU: Hauptpipeline
│   ├── spacy_detectors.py          # NEU: Regel-Detektoren
│   ├── spacy_scoring.py            # NEU: Scoring-Logik
│   ├── spacy_config_manager.py     # NEU: Config-Verwaltung
│   └── spacy_defaults.py           # NEU: Default Keyword-Sets
│
├── 02_models.py                     # Erweitern: Neue Tabellen
└── 01_web_app.py                    # Erweitern: /spacy-tuning Routes

templates/
├── spacy_tuning.html               # NEU: Haupt-Template
├── partials/
│   ├── spacy_vip_tab.html          # NEU: VIP-Tab
│   ├── spacy_keywords_tab.html     # NEU: Keywords-Tab
│   ├── spacy_scoring_tab.html      # NEU: Scoring-Tab
│   └── spacy_domains_tab.html      # NEU: Domains-Tab

migrations/versions/
└── ph_y_spacy_hybrid_pipeline.py   # NEU: Migration
```

---

## 🚀 Implementierungsphasen

### Phase Y1: Grundlagen (4-6h)
- [ ] Migration erstellen (alle 4 Tabellen)
- [ ] ORM-Models hinzufügen
- [ ] Default-Keyword-Sets als Python-Konstanten
- [ ] spaCy Model Upgrade (sm → md)

### Phase Y2: Detektoren (6-8h)
- [ ] `spacy_detectors.py` implementieren
  - DeadlineDetector
  - UrgencyKeywordDetector
  - ActionRequestDetector
  - ImportanceDetector
  - NegativeSignalDetector
- [ ] Unit-Tests für jeden Detektor

### Phase Y3: Scoring & Pipeline (4-6h)
- [ ] `spacy_scoring.py` implementieren
- [ ] `spacy_pipeline.py` als Orchestrator
- [ ] `spacy_config_manager.py` für DB-Config
- [ ] Integration in bestehenden UrgencyBooster

### Phase Y4: UI (6-8h)
- [ ] `/spacy-tuning` Route
- [ ] Template mit 4 Tabs
- [ ] JavaScript für CRUD-Operationen
- [ ] API-Endpoints für alle Konfigs

### Phase Y5: Testing & Feintuning (4-6h)
- [ ] End-to-End Tests mit echten Emails
- [ ] Performance-Benchmarks
- [ ] Default-Werte anpassen
- [ ] Dokumentation

---

## ✅ Zusammenfassung

| Komponente | Status | Beschreibung |
|------------|--------|--------------|
| **Keyword-Sets** | 📋 Definiert | 12 Sets mit ~200 Keywords |
| **VIP-System** | 📋 Definiert | Pro-Account Absender-Boost |
| **Scoring** | 📋 Definiert | Punktebasiert (0-10) |
| **Detektoren** | 📋 Definiert | 5 Regel-Module |
| **UI** | 📋 Definiert | 4-Tab Interface |
| **DB-Schema** | 📋 Definiert | 4 neue Tabellen |

**Geschätzter Aufwand**: 24-34 Stunden

**Nächster Schritt**: Soll ich mit Phase Y1 (Migration + Models) beginnen?
