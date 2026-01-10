# UrgencyBooster Optimierung – Konzept & Design

**Status:** 🟡 In Planung  
**Datum:** 2026-01-08  
**Ziel:** Verbesserte Wichtigkeits-/Dringlichkeits-Erkennung für Email-Priorisierung

---

## 🎯 Problemstellung

**Aktueller Stand:**
- UrgencyBooster nutzt `de_core_news_sm` (15 MB, sehr schnell)
- Setzt immer **W1/D1 score 3** → keine echte Differenzierung
- Verarbeitet NUR Trusted Senders (Schutz vor False-Positives)
- Performance: ~100-300ms pro Email ✅

**Hauptprobleme:**
1. **Keine echte Wichtigkeits-Einstufung** → alle Mails landen bei P0/P1
2. **Fehlende Deadline-Erkennung** → zeitkritische Mails nicht erkannt
3. **Keine Kontext-Integration** → Imperativ/Aufforderung nicht zuverlässig erkannt

---

## 📊 Analyse: Aktueller Code

### Bestehende Features (Phase X)

```python
# /src/services/urgency_booster.py
class UrgencyBooster:
    - analyze_urgency(subject, body, sender)
    - _analyze_deadlines() → erkennt "heute", "morgen", DATE entities
    - _analyze_money() → erkennt Beträge via MONEY entity + Regex
    - _extract_action_verbs() → ACTION_VERBS_SET (senden, bestätigen, ...)
    - _has_authority_person() → AUTHORITY_TITLES_SET (CEO, Direktor, ...)
    - _is_invoice() → INVOICE_KEYWORDS_SET (Rechnung, Invoice, ...)
```

**Scoring-Mechanik:**
```python
urgency_score = 0.0
- Deadline <24h: +0.4
- Deadline <48h: +0.3
- Geld >5000€: +0.2
- Invoice: +0.3
- Action-Verben: +0.15 pro Verb (max 0.4)
- Authority-Person: +0.2

→ Confidence immer >= 0.6 (Mindest-Confidence für Trusted Senders)
```

### Integration in Processing Pipeline

```python
# /src/12_processing.py
enable_ai_analysis = account.enable_ai_analysis_on_fetch
account_booster_enabled = account.urgency_booster_enabled

# /src/03_ai_client.py → _analyze_with_chat()
if trusted_result and trusted_result.get('use_urgency_booster'):
    booster_result = urgency_booster.analyze_urgency(subject, body, sender)
    if booster_result.get("confidence", 0) >= 0.6:
        return self._convert_booster_to_llm_format(booster_result, subject, body)
```

---

## 💡 Optimierungs-Strategien

### Option A: **Hybrid spaCy Pipeline (Empfohlen)** ⭐

**Konzept:**
```
Stufe 0: Vorverarbeitung
├─ HTML → Text (beautifulsoup)
├─ Signaturen entfernen (Regex)
└─ Subject + Body kombinieren

Stufe 1: spaCy Core Pipeline
├─ Modell: de_core_news_md (50 MB, schnell) + de_core_news_sm als Fallback
├─ Aktiv: tok2vec, tagger, parser, lemmatizer, ner
└─ Output: Dependencies, NER (DATE, ORG, PERSON, MONEY)

Stufe 2: Rule-Based Detektoren (spaCy Matcher)
├─ deadline_detector
├─ urgency_keywords_detector
├─ action_request_detector (Imperativ/Aufforderung)
├─ importance_context_detector (Freigabe, Kunde, Zahlung)
└─ negatives_detector (Newsletter, FYI)

Stufe 3: Scoring + Mapping
├─ UrgencyScore (zeitkritisch)
├─ ImportanceScore (impact/relevanz)
└─ Priority: P0 (wichtig & dringend), P1 (wichtig), P2 (dringend), P3 (normal)
```

**Vorteile:**
- ✅ **Deterministisch & nachvollziehbar** (Regel-basiert)
- ✅ **Schnell**: ~150-400ms (CPU-only)
- ✅ **Keine Trainingsdaten nötig**
- ✅ **Bessere Deadline-Erkennung** via Parser Dependencies
- ✅ **Imperative erkennbar** (z.B. "Bitte senden Sie...")

**Nachteile:**
- ⚠️ Regelwerk muss gepflegt werden
- ⚠️ Kein Lern-Effekt (statisch)

---

### Option B: **spaCy TextCategorizer (ML-basiert)**

**Konzept:**
```python
# Training Pipeline
nlp.add_pipe("textcat_multilabel", config={
    "threshold": 0.5,
    "labels": ["urgent", "important", "low_priority", "info_only"]
})

# Benötigt:
- 300-500 gelabelte Emails (mind. 50 pro Kategorie)
- Einheitliche Label-Kriterien
- Re-Training bei Schema-Änderungen
```

**Vorteile:**
- ✅ Lernt von echten Daten
- ✅ Kann Kontext besser erfassen als Regeln

**Nachteile:**
- ⚠️ **Braucht Trainingsdaten** (keine verfügbar)
- ⚠️ Nicht sofort einsetzbar
- ⚠️ Black-Box (weniger nachvollziehbar)

---

### Option C: **Zero-Shot LLM (Fallback für schwierige Fälle)**

**Konzept:**
```python
# Nur wenn Booster Confidence <0.6
if booster_confidence < 0.6:
    llm_result = small_llm.classify(subject, body)
    # Kombination: 70% Booster + 30% LLM
```

**Wann sinnvoll:**
- Komplexe Sprache / Sarkasmus
- Mehrdeutigkeit (z.B. "FYI" vs. "FYI: Dringende Zahlung")
- Trusted Sender schreibt außerhalb des üblichen Musters

**Modell-Optionen:**
```
all-minilm:22m (Embedding) → ❌ keine Klassifikation
llama3.2:1b (Chat) → ✅ Zero-Shot capable, aber langsamer als spaCy
```

**Hybrid-Ansatz:**
```
IF booster_confidence >= 0.6:
    use booster_result
ELSE:
    use small_llm (llama3.2:1b)
```

---

## 🏗️ Design-Vorschlag: Hybrid Pipeline

### Architektur

```
┌─────────────────────────────────────────────┐
│ Email (Subject + Body + Sender)             │
└────────────────┬────────────────────────────┘
                 │
     ┌───────────▼──────────┐
     │  Vorverarbeitung     │
     │  - HTML → Text       │
     │  - Signaturen weg    │
     │  - Längen-Limit      │
     └───────────┬──────────┘
                 │
     ┌───────────▼──────────────┐
     │  spaCy Pipeline          │
     │  - de_core_news_md       │
     │  - NER, Parser, Lemma    │
     └───────────┬──────────────┘
                 │
     ┌───────────▼───────────────────┐
     │  Feature Extraction           │
     │  ┌─────────────────────────┐  │
     │  │ Deadline Detector       │  │
     │  │ - NER DATE              │  │
     │  │ - Parser Dependencies   │  │
     │  │ - Relative Zeit         │  │
     │  └─────────────────────────┘  │
     │  ┌─────────────────────────┐  │
     │  │ Action Request Detector │  │
     │  │ - Imperativ (Parser)    │  │
     │  │ - "bitte + Verb"        │  │
     │  │ - Modalverben           │  │
     │  └─────────────────────────┘  │
     │  ┌─────────────────────────┐  │
     │  │ Importance Detector     │  │
     │  │ - Business Keywords     │  │
     │  │ - Stakeholder (NER)     │  │
     │  │ - Money Amount          │  │
     │  └─────────────────────────┘  │
     │  ┌─────────────────────────┐  │
     │  │ Negative Detector       │  │
     │  │ - Newsletter Signale    │  │
     │  │ - Auto-Reply            │  │
     │  │ - FYI-only              │  │
     │  └─────────────────────────┘  │
     └───────────┬───────────────────┘
                 │
     ┌───────────▼──────────────┐
     │  Scoring Engine          │
     │  - UrgencyScore (0-10)   │
     │  - ImportanceScore (0-10)│
     └───────────┬──────────────┘
                 │
     ┌───────────▼──────────────┐
     │  Priority Mapping        │
     │  P0: U>=6 & I>=6         │
     │  P1: I>=6                │
     │  P2: U>=6                │
     │  P3: rest                │
     └───────────┬──────────────┘
                 │
     ┌───────────▼──────────────┐
     │  Confidence Check        │
     │  >= 0.6? Use result      │
     │  < 0.6? Fallback LLM     │
     └──────────────────────────┘
```

---

## 📝 Regel-Beispiele (Deutsch)

### A) Urgency: Deadline & Zeitfenster

**Signale:**
```python
DEADLINE_KEYWORDS = {
    "bis heute", "bis morgen", "bis spätestens",
    "EOD", "COB", "heute noch", "asap",
    "deadline", "frist", "termin"
}

# Scoring
Deadline ≤ 8h: +4 urgency
Deadline ≤ 24h: +3 urgency
Deadline ≤ 72h: +2 urgency
"bald", "zeitnah": +1 urgency
```

**Matcher (spaCy):**
```python
from spacy.matcher import Matcher

matcher = Matcher(nlp.vocab)
pattern = [
    {"LOWER": {"IN": ["bis", "spätestens"]}},
    {"ENT_TYPE": "DATE"}
]
matcher.add("DEADLINE", [pattern])
```

### B) Urgency: Dringlichkeits-Keywords

```python
URGENCY_STRONG = {
    "dringend", "eilig", "asap", "sofort", 
    "umgehend", "unverzüglich", "heute noch"
}
# Scoring: +2 urgency (max +4)

URGENCY_MEDIUM = {
    "bald", "zeitnah", "schnell möglich"
}
# Scoring: +1 urgency
```

### C) Action Request (To-Do Erkennung)

**Imperativ via Dependency Parser:**
```python
# Beispiel: "Bitte senden Sie die Unterlagen."
# ROOT → senden (VERB) mit "bitte" als advmod

def detect_imperative(doc):
    for token in doc:
        if token.pos_ == "VERB" and token.dep_ == "ROOT":
            # Prüfe auf "bitte" in Children
            for child in token.children:
                if child.lower_ == "bitte":
                    return True
    return False

# Scoring: +2 urgency, +2 importance
```

**Modalverben + Infinitiv:**
```python
MODAL_PATTERNS = [
    "kannst du", "könnten Sie", "würden Sie",
    "bitte senden", "bitte prüfen", "bitte freigeben"
]
# Scoring: +2 urgency, +1 importance
```

### D) Importance: Business Impact

```python
IMPORTANCE_HIGH = {
    "mahnung", "outage", "eskalation", "incident",
    "kritisch", "vertrag", "unterschrift"
}
# Scoring: +3 importance

IMPORTANCE_MEDIUM = {
    "freigabe", "entscheidung", "budget", 
    "angebot", "rechnung", "zahlung", "kunde"
}
# Scoring: +2 importance

IMPORTANCE_LOW = {
    "info", "update", "fyi", "nur zur info"
}
# Scoring: 0 oder -1 importance
```

### E) Importance: Sender Context

**Außerhalb spaCy (in processing.py):**
```python
# VIP-Liste aus DB
if sender in user_vip_list:
    importance += 3

# External vs. Internal
if is_external_sender(sender, user_domain):
    importance += 1

# Direct vs. CC
if user_email in email_to:
    importance += 1
elif user_email in email_cc:
    importance += 0

# Viele Empfänger (Verteiler)
if len(email_to) > 10:
    importance -= 1
```

### F) Negative Signale (Downgrade)

```python
# Auto-Reply Detection
AUTO_REPLY_PATTERNS = {
    "out of office", "abwesenheit", "auto-reply",
    "automatische antwort", "nicht im büro"
}
# Scoring: -5 urgency, -5 importance

# Newsletter (bereits via Trusted Senders gefiltert)
if has_unsubscribe_link(body):
    importance -= 4
    category = "nur_information"

# FYI-only (wenn KEINE Action-Request)
if "fyi" in subject.lower() and not has_action_request:
    importance -= 2
```

---

## 🎯 Score-Mapping (Beispiel)

```python
# Nach Feature-Extraction
urgency_score = sum([
    deadline_score,      # 0-4
    urgency_kw_score,    # 0-4
    action_request_score # 0-2
])  # Max: 10

importance_score = sum([
    business_impact_score, # 0-3
    sender_context_score,  # 0-3
    money_amount_score,    # 0-3
    action_request_score   # 0-2
])  # Max: 11 → normalize to 10

# Priority Mapping
if urgency_score >= 6 and importance_score >= 6:
    priority = "P0"  # Wichtig & Dringend
elif importance_score >= 6:
    priority = "P1"  # Wichtig (nicht dringend)
elif urgency_score >= 6:
    priority = "P2"  # Dringend (nicht wichtig)
else:
    priority = "P3"  # Normal/Low
```

**Mapping zu LLM-Format:**
```python
# UrgencyScore → dringlichkeit (1-3)
dringlichkeit = 1 if urgency_score < 4 else (2 if urgency_score < 7 else 3)

# ImportanceScore → wichtigkeit (1-3)
wichtigkeit = 1 if importance_score < 4 else (2 if importance_score < 7 else 3)

# Priority → kategorie_aktion
kategorie_map = {
    "P0": "dringend",
    "P1": "aktion_erforderlich",
    "P2": "dringend",
    "P3": "nur_information"
}
```

---

## 🔧 Implementierungs-Plan

### Phase 1: Model-Upgrade (minimal)

```bash
# In venv
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
python -m spacy download de_core_news_md
```

**Code-Änderung:**
```python
# /src/services/urgency_booster.py
def _load_spacy_de():
    try:
        import spacy
        _spacy_de = spacy.load("de_core_news_md")  # Upgrade von sm → md
        logger.info("✅ spaCy Deutsch-Model geladen (de_core_news_md)")
    except:
        # Fallback auf sm
        _spacy_de = spacy.load("de_core_news_sm")
        logger.warning("⚠️ Fallback auf de_core_news_sm")
```

### Phase 2: Erweiterte Detektoren

**Neue Dateien:**
```
/src/services/urgency_booster_v2.py
├─ DeadlineDetector
│  ├─ _extract_dates_with_context()
│  ├─ _calculate_hours_until()
│  └─ score: 0-4
│
├─ ActionRequestDetector
│  ├─ _detect_imperativ()
│  ├─ _detect_modal_verbs()
│  └─ score: 0-2
│
├─ ImportanceDetector
│  ├─ _detect_business_keywords()
│  ├─ _detect_stakeholders()
│  └─ score: 0-3
│
└─ NegativeDetector
   ├─ _detect_autoreply()
   ├─ _detect_newsletter()
   └─ score: -5 to 0
```

### Phase 3: Scoring Engine Refactor

```python
class UrgencyBoosterV2:
    def analyze_urgency(self, subject, body, sender, metadata=None):
        doc = self.nlp(f"{subject} {body[:2000]}")
        
        # Feature Extraction
        features = {
            'deadline': self.deadline_detector.extract(doc, text),
            'action_request': self.action_detector.extract(doc, text),
            'importance': self.importance_detector.extract(doc, text, sender),
            'negatives': self.negative_detector.extract(doc, text, metadata)
        }
        
        # Scoring
        urgency_score = self._calculate_urgency(features)
        importance_score = self._calculate_importance(features)
        
        # Confidence
        confidence = self._calculate_confidence(features)
        
        # Fallback to LLM if low confidence
        if confidence < 0.6 and self.llm_fallback:
            return self._llm_fallback(subject, body)
        
        return {
            'urgency_score': urgency_score,
            'importance_score': importance_score,
            'priority': self._map_priority(urgency_score, importance_score),
            'confidence': confidence,
            'features': features
        }
```

### Phase 4: Testing & Validation

**Test-Szenarien:**
```python
# /scripts/test_urgency_booster_v2.py

test_cases = [
    {
        "subject": "Rechnung 2024-001: Zahlung bis heute 17:00",
        "body": "Sehr geehrte Damen und Herren, bitte überweisen Sie €1.234,56 bis heute 17:00.",
        "expected": {"urgency": 3, "importance": 3, "priority": "P0"}
    },
    {
        "subject": "FYI: Neuer Blog-Artikel",
        "body": "Nur zur Info: Unser neuester Artikel ist online.",
        "expected": {"urgency": 1, "importance": 1, "priority": "P3"}
    },
    {
        "subject": "Bitte Freigabe bis morgen",
        "body": "Könnten Sie bitte das Budget bis morgen freigeben?",
        "expected": {"urgency": 2, "importance": 2, "priority": "P1"}
    },
    # ... weitere 20-30 Test-Cases
]
```

---

## ⚖️ Vergleich: Optionen

| Kriterium | A) Hybrid spaCy | B) TextCategorizer | C) Zero-Shot LLM |
|-----------|-----------------|--------------------|--------------------|
| **Geschwindigkeit** | ⚡ 150-400ms | ⚡ 100-300ms | 🐌 2-5 Sek |
| **Trainingsdaten** | ❌ Nicht nötig | ⚠️ 300-500 Emails | ❌ Nicht nötig |
| **Nachvollziehbar** | ✅ Regeln | ⚠️ Black-Box | ⚠️ Black-Box |
| **Deterministisch** | ✅ Ja | ⚠️ Nein | ⚠️ Nein |
| **Pflegeaufwand** | ⚠️ Regeln pflegen | ✅ Nur Re-Training | ✅ Minimal |
| **Sofort einsetzbar** | ✅ Ja | ❌ Nein | ✅ Ja |
| **CPU-Only** | ✅ Ja | ✅ Ja | ✅ Ja (lokal) |

---

## 🎬 Empfehlung

**Starten mit Option A (Hybrid spaCy Pipeline):**

1. **Phase 1** (1-2h): Model-Upgrade `sm` → `md` + Testing
2. **Phase 2** (3-4h): Erweiterte Detektoren (Deadline, Action, Importance)
3. **Phase 3** (2-3h): Scoring-Engine Refactor + Confidence-Berechnung
4. **Phase 4** (2-3h): Test-Suite mit 30+ Real-World Cases

**Später (Optional):**
- **Option B**: Wenn 500+ gelabelte Emails vorhanden → TextCategorizer trainieren
- **Option C**: LLM-Fallback für Confidence <0.6 (hybrid approach)

---

## 📚 Dependencies

**Bereits vorhanden:**
```
spacy>=3.5.0
de_core_news_sm (15 MB) ✅
```

**Neu installieren:**
```bash
python -m spacy download de_core_news_md  # 50 MB
```

**Optional (für Option B):**
```bash
# Für TextCategorizer Training
pip install spacy-transformers  # Wenn GPU verfügbar
# ODER bleiben bei CPU-only mit de_core_news_md
```

---

## 🚀 Next Steps

1. **Review** dieses Konzept mit dir
2. **Entscheidung** welche Option(en) umgesetzt werden
3. **Implementierung** Phase 1-4
4. **Testing** im UI mit echten Emails
5. **Fine-Tuning** basierend auf Feedback

---

## 📝 Offene Fragen

1. **Model-Größe**: Ist `de_core_news_md` (50 MB) OK oder zu groß?
   - Alternative: Bleiben bei `sm` + bessere Regeln
2. **Sender Context**: VIP-Liste in DB speichern? Oder nur via Trusted Senders?
3. **LLM-Fallback**: Aktivieren für Low-Confidence Cases? (Latenz-Erhöhung)
4. **Test-Daten**: Können wir 30-50 anonymisierte Emails für Tests nutzen?

---

**Autor:** GitHub Copilot  
**Review:** Thomas  
**Version:** 1.0
