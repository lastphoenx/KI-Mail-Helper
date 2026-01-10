# Phase Y: Hybrid spaCy Pipeline - Implementierungsplan

**Status:** 🟢 Entschieden: Hybrid-Ansatz + Ensemble-Learning  
**Datum:** 2026-01-08  
**Aufwand:** 28-36h (inkl. SGD-Ensemble)  
**Qualität:** 9.5/10 ⭐⭐

---

## 🏗️ Position in bestehender Architektur

### Account-Level Toggles (bereits vorhanden)

Phase Y integriert sich **nahtlos** in das bestehende Toggle-System:

```python
# /src/02_models.py - MailAccount
class MailAccount(Base):
    enable_ai_analysis_on_fetch = Column(Boolean, default=True)
    urgency_booster_enabled = Column(Boolean, default=True)
```

**Szenarien:**

| Account-Typ | AI-Analyse | UrgencyBooster | Phase Y Effekt |
|-------------|-----------|----------------|----------------|
| **Newsletter (GMX)** | ❌ AUS | ❌ AUS | Nur Embedding → SGD lernt aus Korrekturen |
| **Business (Beispiel-Firma)** | ✅ AN | ✅ AN | **Phase Y voll aktiv** (spaCy + SGD + VIP) |
| **Hybrid** | ✅ AN | ❌ AUS | Nur LLM (langsamer, universell) |

### Wo Phase Y einhakt

```
┌─────────────────────────────────────────────────────────────┐
│  BESTEHENDE PROCESSING-PIPELINE                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Email kommt rein                                           │
│       │                                                     │
│       ▼                                                     │
│  enable_ai_analysis_on_fetch?                               │
│       │                                                     │
│       ├─ NEIN → Nur Embedding, NULL-Werte                   │
│       │         User korrigiert → SGD lernt ✅             │
│       │                                                     │
│       └─ JA → urgency_booster_enabled?                      │
│                │                                            │
│                ├─ JA + Trusted Sender:                      │
│                │  ┌──────────────────────────────────┐     │
│                │  │ PHASE Y HYBRID PIPELINE          │     │
│                │  │ ├─ spaCy (Parser/NER/Lemma)      │     │
│                │  │ ├─ Keywords (80 statt 200)       │     │
│                │  │ ├─ VIP-System (DB)               │     │
│                │  │ └─ SGD-Ensemble (Weighted)       │     │
│                │  │    └─ <20 Korr: spaCy 100%       │     │
│                │  │    └─ 20-50 Korr: spaCy 30% SGD 70% │  │
│                │  │    └─ 50+ Korr: spaCy 15% SGD 85%│     │
│                │  └──────────────────────────────────┘     │
│                │  Performance: 150-400ms                    │
│                │                                            │
│                └─ NEIN → LLM-Analyse (2-10 Min)             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Phase Y ersetzt:** Aktuellen `UrgencyBooster` (200 Keywords, keine Differenzierung)  
**Phase Y behält:** Account-Toggles, Trusted-Sender-Check, API-Kompatibilität  
**Phase Y erweitert:** SGD-Ensemble, VIP-System, UI-Konfiguration

---

## 🎯 Was ist Hybrid + Ensemble?

```
┌─────────────────────────────────────────────────────────┐
│  80% spaCy NLP (intelligent)                           │
│  ├─ Parser: Imperativ-Erkennung ohne Keyword-Liste     │
│  ├─ NER: Deadline-Extraktion mit echter Datumslogik    │
│  ├─ Lemmatizer: 1 Keyword für alle Wortformen          │
│  └─ Dependencies: Kontext-Analyse (Negation, Modal)    │
└───────────┬─────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────┐
│  20% Keywords (konfigurierbar)                          │
│  ├─ Urgency High (15 Keywords)                          │
│  ├─ Importance High (25 Keywords)                       │
│  ├─ Invoice (10 Keywords)                               │
│  ├─ Newsletter (15 Keywords)                            │
│  ├─ Auto-Reply (10 Keywords)                            │
│  └─ FYI (5 Keywords)                                    │
│  SUMME: ~80 Keywords (statt 200)                        │
└───────────┬─────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────┐
│  VIP-System (User-konfiguriert)                         │
│  └─ Absender-Boost +1 bis +5 Importance                 │
└───────────┬─────────────────────────────────────────────┘
            │
            ├──────────────────────────────────────────────┐
            │                                              │
┌───────────▼─────────────────┐  ┌──────────────────────▼─┐
│  spaCy Scoring (0-10)       │  │  SGD Prediction (1-3)  │
│  Urgency: 7                 │  │  Urgency: 3            │
│  Importance: 6              │  │  Importance: 2         │
└───────────┬─────────────────┘  └──────────────────────┬─┘
            │                                           │
            └────────────────┬──────────────────────────┘
                             │
                  ┌──────────▼──────────┐
                  │  ENSEMBLE COMBINER  │
                  │                     │
                  │  <20 Korr: 100% spaCy
                  │  20-50:    30% spaCy, 70% SGD
                  │  50+:      15% spaCy, 85% SGD
                  │                     │
                  │  + VIP-Boost        │
                  └──────────┬──────────┘
                             │
                  ┌──────────▼──────────┐
                  │  Final: U=7, I=8    │
                  │  Priority: P1       │
                  └─────────────────────┘
```

---

## 📊 Vergleich: Phase Y vs Hybrid

| Komponente | Phase Y (Original) | Hybrid (Angepasst) |
|------------|-------------------|-------------------|
| **Keywords** | 200 | **80** (-60%) |
| **Imperativ** | 50 Verben-Keywords | **Parser** (0 Keywords) |
| **Deadlines** | 20 Phrases (fest) | **NER DATE** + Wochentagslogik |
| **Action-Verbs** | 25 Keywords | **Lemmatizer** (5 Base-Lemmas) |
| **Negation** | ❌ Nicht erkannt | **✅ Dependencies** |
| **Modalverben** | ❌ Nicht erkannt | **✅ POS-Tags** |
| **VIP-System** | ✅ | ✅ 1:1 übernommen |
| **UI (4 Tabs)** | ✅ | ✅ 1:1 übernommen |
| **0-10 Punkte** | ✅ | ✅ 1:1 übernommen |
| **DB-Schema** | 4 Tabellen | 4 Tabellen (identisch) |
| **Aufwand** | 24-34h | **20-28h** |

---

## 🗄️ Datenbank-Schema (unverändert!)

Das DB-Schema aus Phase Y bleibt **komplett identisch**:

```sql
-- Alle 4 Tabellen wie in Phase Y:
CREATE TABLE spacy_vip_senders (...)
CREATE TABLE spacy_keyword_sets (...)
CREATE TABLE spacy_scoring_config (...)
CREATE TABLE spacy_user_domains (...)
```

**Unterschied:** Weniger Default-Keywords beim Seed, aber Struktur bleibt gleich.

---

## 🧩 Hybrid-Detektoren

### 1. ImperativDetector (NLP-basiert) ⭐

**Statt:** 50 Keywords `{'senden', 'schicken', 'prüfen', 'geprüft', ...}`

**Jetzt:** spaCy Parser Dependencies

```python
class ImperativDetector:
    """
    Erkennt Handlungsaufforderungen via spaCy Parser.
    
    Beispiele:
    ✅ "Bitte prüfen Sie das Angebot" → Imperativ erkannt
    ❌ "Das Angebot wurde geprüft" → Kein Imperativ (Passiv)
    """
    
    def detect(self, doc, text: str) -> Dict:
        has_imperative = False
        imperative_verbs = []
        confidence = 0.0
        
        # Methode 1: Imperativ-Tag (VVIMP)
        for token in doc:
            if token.tag_ == "VVIMP":  # Imperativ-Tag
                has_imperative = True
                imperative_verbs.append(token.lemma_)
                confidence = 0.9
        
        # Methode 2: "bitte" + Verb
        for token in doc:
            if token.pos_ == "VERB" and token.dep_ == "ROOT":
                for child in token.children:
                    if child.lower_ in ['bitte', 'please']:
                        has_imperative = True
                        imperative_verbs.append(token.lemma_)
                        confidence = max(confidence, 0.8)
        
        # Methode 3: Modalverb + Infinitiv
        modal_verbs = {'können', 'könnten', 'würden', 'mögen'}
        for token in doc:
            if token.lemma_ in modal_verbs:
                # Prüfe ob Infinitiv folgt
                for child in token.children:
                    if child.pos_ == "VERB" and child.tag_ == "VVINF":
                        has_imperative = True
                        imperative_verbs.append(child.lemma_)
                        confidence = max(confidence, 0.7)
        
        # Methode 4: "ich brauche/benötige" + Objekt
        need_verbs = {'brauchen', 'benötigen', 'need'}
        for token in doc:
            if token.lemma_ in need_verbs and token.dep_ == "ROOT":
                # Prüfe auf direktes Objekt
                for child in token.children:
                    if child.dep_ in ["obj", "dobj"]:
                        has_imperative = True
                        imperative_verbs.append(token.lemma_)
                        confidence = max(confidence, 0.6)
        
        return {
            'has_imperative': has_imperative,
            'verbs': imperative_verbs[:3],  # Top 3
            'confidence': confidence
        }
```

**Vorteile:**
- ✅ Erkennt **Grammatik-Struktur** (nicht nur Keywords)
- ✅ Unterscheidet **Aktiv/Passiv**
- ✅ Versteht **Höflichkeitsformen** ("könnten Sie")
- ✅ **Keine 50 Keywords** nötig!

### 2. DeadlineDetector (NER + Logik) ⭐

**Statt:** Feste Stunden-Mappings
```python
DEADLINE_PHRASES = {
    'heute': 0,
    'morgen': 24,
    'bis freitag': 120  # FALSCH wenn heute Donnerstag ist!
}
```

**Jetzt:** spaCy NER DATE + Wochentagslogik

```python
from datetime import datetime, timedelta

class DeadlineDetector:
    """
    Extrahiert Deadlines via NER und berechnet exakte Stunden.
    
    Beispiele:
    - "bis Freitag" am Montag → 96h
    - "bis Freitag" am Donnerstag → 24h (kritisch!)
    - "bis 15. Januar" → exakte Berechnung
    """
    
    WEEKDAY_MAP = {
        'montag': 0, 'monday': 0,
        'dienstag': 1, 'tuesday': 1,
        'mittwoch': 2, 'wednesday': 2,
        'donnerstag': 3, 'thursday': 3,
        'freitag': 4, 'friday': 4,
        'samstag': 5, 'saturday': 5,
        'sonntag': 6, 'sunday': 6
    }
    
    RELATIVE_TIMES = {
        'heute': 0, 'today': 0,
        'morgen': 24, 'tomorrow': 24,
        'übermorgen': 48,
    }
    
    def detect(self, doc, text: str) -> Dict:
        deadline_hours = None
        deadline_text = None
        confidence = 0.0
        
        text_lower = text.lower()
        
        # Methode 1: Relative Zeit (heute, morgen)
        for phrase, hours in self.RELATIVE_TIMES.items():
            if phrase in text_lower:
                deadline_hours = hours
                deadline_text = phrase
                confidence = 1.0
                return {
                    'has_deadline': True,
                    'hours_until': deadline_hours,
                    'text': deadline_text,
                    'confidence': confidence
                }
        
        # Methode 2: NER DATE Entities
        for ent in doc.ents:
            if ent.label_ == "DATE":
                deadline_text = ent.text
                deadline_hours = self._parse_date_entity(ent.text)
                if deadline_hours is not None:
                    confidence = 0.8
                    return {
                        'has_deadline': True,
                        'hours_until': deadline_hours,
                        'text': deadline_text,
                        'confidence': confidence
                    }
        
        # Methode 3: Wochentags-Erkennung (dynamisch!)
        for weekday, target_day in self.WEEKDAY_MAP.items():
            if weekday in text_lower:
                now = datetime.now()
                current_day = now.weekday()
                
                # Berechne Tage bis Ziel-Wochentag
                days_until = (target_day - current_day) % 7
                if days_until == 0:
                    days_until = 7  # Nächste Woche
                
                deadline_hours = days_until * 24
                deadline_text = weekday.capitalize()
                confidence = 0.7
                
                return {
                    'has_deadline': True,
                    'hours_until': deadline_hours,
                    'text': deadline_text,
                    'confidence': confidence
                }
        
        # Methode 4: Keywords für Dringlichkeit (ohne genaue Zeit)
        urgency_keywords = ['asap', 'sofort', 'dringend', 'urgent', 'eilig']
        if any(kw in text_lower for kw in urgency_keywords):
            return {
                'has_deadline': True,
                'hours_until': 24,  # Default: 1 Tag
                'text': 'urgency_keyword',
                'confidence': 0.5
            }
        
        return {
            'has_deadline': False,
            'hours_until': None,
            'text': None,
            'confidence': 0.0
        }
    
    def _parse_date_entity(self, date_text: str) -> Optional[int]:
        """
        Versucht DATE entity in Stunden umzuwandeln.
        
        Beispiele:
        - "15. Januar" → berechne Differenz zu heute
        - "01.02.2026" → berechne Differenz
        """
        from dateutil import parser
        
        try:
            # Versuche Datum zu parsen
            deadline_date = parser.parse(date_text, dayfirst=True, fuzzy=True)
            now = datetime.now()
            
            # Wenn Datum in Vergangenheit, nehme nächstes Jahr
            if deadline_date < now:
                deadline_date = deadline_date.replace(year=now.year + 1)
            
            delta = deadline_date - now
            hours = delta.total_seconds() / 3600
            
            return int(hours) if hours > 0 else None
        except:
            return None
```

**Vorteile:**
- ✅ **Exakte Datumsberechnung** (nicht mehr feste 120h)
- ✅ **Wochentag-Kontext** ("Freitag" ist dynamisch)
- ✅ **NER erkennt auch "15. Januar", "01.02.2026"**
- ✅ **Nur 3 Keywords** (heute, morgen, übermorgen)

### 3. KeywordDetector (Lemmatizer-basiert) ⭐

**Statt:** 25 Verb-Varianten
```python
ACTION_VERBS = {
    'prüfen', 'prüfe', 'prüfst', 'prüft', 
    'geprüft', 'prüfend', 'prüftest', ...  # 10+ Formen!
}
```

**Jetzt:** 5 Base-Lemmas
```python
ACTION_LEMMAS = {
    'prüfen',      # matcht: prüfe, prüfst, prüft, geprüft, ...
    'senden',      # matcht: sende, sendest, gesendet, ...
    'bestätigen',  # matcht: bestätige, bestätigst, bestätigt, ...
    'freigeben',   # matcht: gebe frei, gibst frei, freigegeben, ...
    'bezahlen'     # matcht: bezahle, bezahlst, bezahlt, ...
}
```

```python
class KeywordDetector:
    """
    Keyword-Matching mit Lemmatizer (1 Keyword für alle Formen).
    """
    
    def __init__(self, nlp, keyword_sets: Dict):
        self.nlp = nlp
        self.keyword_sets = keyword_sets
    
    def detect(self, doc, set_name: str) -> Dict:
        """
        Findet Keywords in Text (lemmatisiert).
        
        Args:
            doc: spaCy Doc
            set_name: 'urgency_high', 'importance_high', etc.
        
        Returns:
            {
                'matches': ['prüfen', 'senden'],
                'count': 2,
                'matched_tokens': ['prüfen', 'gesendet']
            }
        """
        keywords = self.keyword_sets.get(set_name, set())
        matches = set()
        matched_tokens = []
        
        for token in doc:
            # Lemmatisiere Token
            lemma = token.lemma_.lower()
            
            # Prüfe ob Lemma in Keyword-Set
            if lemma in keywords:
                matches.add(lemma)
                matched_tokens.append(token.text)
        
        return {
            'matches': list(matches),
            'count': len(matches),
            'matched_tokens': matched_tokens[:5]  # Top 5
        }
```

**Beispiel:**
```python
# Email: "Bitte prüfen Sie das Angebot und senden die geprüften Unterlagen."

# Ohne Lemmatizer (25 Keywords):
ACTION_VERBS = {'prüfen', 'prüfe', 'geprüft', 'prüfend', 'senden', 'sende', 'gesendet', ...}
# Matches: 'prüfen' ✅, 'geprüften' ❌ (nicht in Liste!), 'senden' ✅

# Mit Lemmatizer (5 Keywords):
ACTION_LEMMAS = {'prüfen', 'senden'}
# Matches: 'prüfen' ✅, 'geprüften' → Lemma 'prüfen' ✅, 'senden' ✅
```

**Reduktion: 25 Keywords → 5 Base-Lemmas = **-80%**!**

---

## 📚 Default Keyword-Sets (Hybrid)

### SET 1: `urgency_keywords_high` (15 statt 18)

```python
URGENCY_KEYWORDS_HIGH = {
    # Core Keywords (Lemmatizer matcht alle Formen)
    'dringend',       # → dringender, dringende, dringenden
    'eilig',          # → eiliger, eilige
    'sofort',
    'umgehend',
    'asap',
    'kritisch',       # → kritischer, kritische
    'notfall',        # → Notfalls, Notfalls
    'eskalation',     # → eskalieren, eskaliert
    'priorität',      # → prioritär
    
    # Englisch
    'urgent',
    'immediately',
    'critical',
    'emergency',
    'escalation',
    'priority'
}
# Punkte: +3 per match, max +4
```

**Reduziert von 18 auf 15** (weil Lemmatizer Wortformen automatisch matcht)

### SET 2: `action_lemmas` (5 statt 50!)

```python
ACTION_LEMMAS = {
    'prüfen',      # matcht: prüfe, prüfst, prüft, geprüft, prüfend
    'senden',      # matcht: sende, sendest, sendet, gesendet
    'bestätigen',  # matcht: bestätige, bestätigst, bestätigt
    'freigeben',   # matcht: gebe frei, gibst frei, freigegeben
    'bezahlen'     # matcht: bezahle, bezahlst, bezahlt
}
```

**ABER:** Parser erkennt Imperativ besser → diese Lemmas nur als **Fallback**!

### SET 3: `importance_keywords_high` (25 → bleibt)

```python
IMPORTANCE_KEYWORDS_HIGH = {
    'freigabe', 'genehmigung', 'entscheidung',
    'budget', 'kosten', 'investition',
    'angebot', 'auftrag', 'bestellung',
    'rechnung', 'mahnung', 'zahlung',
    'vertrag', 'vereinbarung',
    'kunde', 'klient', 'mandant',
    'eskalation', 'beschwerde',
    'incident', 'outage', 'störung',
    'datenschutz', 'compliance', 'audit',
    'approval', 'decision', 'customer'
}
# Punkte: +3 per match, max +4
```

**Business-kritische Keywords bleiben!**

### SET 4: `invoice_keywords` (10 → bleibt)

```python
INVOICE_KEYWORDS = {
    'rechnung', 'invoice',
    'rechnungsnummer', 'invoice number',
    'zahlungserinnerung', 'payment reminder',
    'mahnung', 'fällig', 'due date',
    'iban'
}
# Trigger: ≥2 matches → invoice_detected = True
```

### SET 5: `newsletter_keywords` (15 statt 20)

```python
NEWSLETTER_KEYWORDS = {
    'unsubscribe', 'abmelden',
    'newsletter', 'promotion',
    'rabatt', 'discount', 'sale',
    'jetzt kaufen', 'shop now',
    'exklusiv', 'exclusive',
    'noreply', 'no-reply',
    'newsletter@', 'marketing@',
    'promo@'
}
# Penalty: -4 importance, -5 urgency
```

### SET 6: `auto_reply_keywords` (10 → bleibt)

```python
AUTO_REPLY_KEYWORDS = {
    'abwesenheitsnotiz', 'out of office',
    'automatische antwort', 'auto-reply',
    'nicht erreichbar', 'urlaub',
    'vacation', 'on leave',
    'limited access', 'außer haus'
}
# Penalty: -5 importance, -5 urgency
```

### SET 7: `fyi_keywords` (5 statt 8)

```python
FYI_KEYWORDS = {
    'zur information', 'fyi',
    'nur zur info', 'no action required',
    'informational'
}
# Penalty: -2 importance (wenn kein Imperativ)
```

### SET 8: VIP & Domains (aus UI konfigurierbar)

```python
# VIP-Absender: User definiert via UI
# Eigene Domains: User definiert via UI
```

**SUMME: ~80 Keywords** (statt 200)

---

## 🔧 Hybrid-Pipeline Orchestrator

```python
class HybridUrgencyPipeline:
    """
    Hauptpipeline: Kombiniert NLP-Detektoren + Keyword-Detektoren.
    """
    
    def __init__(self, user_id: int, account_id: int, db):
        self.nlp = self._load_spacy()
        self.config = self._load_config(user_id, account_id, db)
        
        # Detektoren
        self.imperative_detector = ImperativDetector()
        self.deadline_detector = DeadlineDetector()
        self.keyword_detector = KeywordDetector(self.nlp, self.config['keywords'])
        
        self.vip_manager = VIPManager(db)
    
    def analyze(self, subject: str, body: str, sender: str, 
                account_id: int) -> Dict:
        """
        Hauptanalyse: 80% NLP + 20% Keywords.
        """
        # 1. spaCy Doc erstellen
        text = f"{subject} {body[:2000]}"
        doc = self.nlp(text)
        
        # 2. NLP-Detektoren (intelligent)
        imperative = self.imperative_detector.detect(doc, text)
        deadline = self.deadline_detector.detect(doc, text)
        
        # 3. Keyword-Detektoren (konfigurierbar)
        urgency_kw = self.keyword_detector.detect(doc, 'urgency_high')
        importance_kw = self.keyword_detector.detect(doc, 'importance_high')
        invoice_kw = self.keyword_detector.detect(doc, 'invoice')
        newsletter_kw = self.keyword_detector.detect(doc, 'newsletter')
        auto_reply_kw = self.keyword_detector.detect(doc, 'auto_reply')
        fyi_kw = self.keyword_detector.detect(doc, 'fyi')
        
        # 4. VIP-Check
        vip = self.vip_manager.check_vip(sender, account_id)
        
        # 5. Scoring
        urgency_score, importance_score = self._calculate_scores({
            'imperative': imperative,
            'deadline': deadline,
            'urgency_kw': urgency_kw,
            'importance_kw': importance_kw,
            'invoice': invoice_kw,
            'newsletter': newsletter_kw,
            'auto_reply': auto_reply_kw,
            'fyi': fyi_kw,
            'vip': vip
        })
        
        # 6. Priority Mapping
        priority = self._map_priority(urgency_score, importance_score)
        
        # 7. LLM-Format
        return self._convert_to_llm_format(
            urgency_score, importance_score, priority, subject, body
        )
    
    def _calculate_scores(self, features: Dict) -> Tuple[int, int]:
        """
        Berechnet Urgency & Importance Scores (0-10).
        """
        urgency = 0
        importance = 0
        
        config = self.config['scoring']
        
        # URGENCY
        # 1. Deadline (höchste Gewichtung)
        if features['deadline']['has_deadline']:
            hours = features['deadline']['hours_until']
            if hours <= config['deadline_critical_hours']:  # ≤8h
                urgency += config['deadline_critical_points']  # +4
            elif hours <= config['deadline_urgent_hours']:  # ≤24h
                urgency += config['deadline_urgent_points']  # +3
            elif hours <= config['deadline_soon_hours']:  # ≤72h
                urgency += config['deadline_soon_points']  # +2
        
        # 2. Imperativ (Parser)
        if features['imperative']['has_imperative']:
            urgency += 2  # +2 für Handlungsaufforderung
        
        # 3. Urgency-Keywords
        urgency += min(features['urgency_kw']['count'] * 3, 4)
        
        # 4. Invoice
        if features['invoice']['count'] >= 2:
            urgency += 3
        
        # IMPORTANCE
        # 1. VIP-Absender
        if features['vip']:
            importance += features['vip']['boost']  # +1 bis +5
        
        # 2. Importance-Keywords
        importance += min(features['importance_kw']['count'] * 3, 4)
        
        # 3. Imperativ (auch Importance)
        if features['imperative']['has_imperative']:
            importance += 2
        
        # 4. Invoice
        if features['invoice']['count'] >= 2:
            importance += 3
        
        # NEGATIVE SIGNALE
        if features['newsletter']['count'] >= 2:
            urgency += config['newsletter_urgency_penalty']  # -5
            importance += config['newsletter_importance_penalty']  # -4
        
        if features['auto_reply']['count'] >= 1:
            urgency += config['auto_reply_penalty']  # -5
            importance += config['auto_reply_penalty']  # -5
        
        if features['fyi']['count'] >= 1 and not features['imperative']['has_imperative']:
            importance += config['fyi_penalty']  # -2
        
        # Normalisierung 0-10
        urgency = max(0, min(10, urgency))
        importance = max(0, min(10, importance))
        
        return urgency, importance
    
    def _map_priority(self, urgency: int, importance: int) -> str:
        """
        P0 = wichtig & dringend (U≥6 AND I≥6)
        P1 = wichtig (I≥6)
        P2 = dringend (U≥6)
        P3 = normal (else)
        """
        config = self.config['scoring']
        u_thresh = config['urgency_high_threshold']  # 6
        i_thresh = config['importance_high_threshold']  # 6
        
        if urgency >= u_thresh and importance >= i_thresh:
            return "P0"
        elif importance >= i_thresh:
            return "P1"
        elif urgency >= u_thresh:
            return "P2"
        else:
            return "P3"
```

---

## 🚀 Implementierungsphasen

### Phase Y1: Core (7-9h)

**Ziel:** Grundlagen + Migration + Ensemble-Vorbereitung

- [ ] **Migration erstellen** (2h)
  - 4 Tabellen (wie Phase Y)
  - Default-Keywords (80 statt 200)
  - Seed-Daten für VIP/Scoring
  
- [ ] **ORM Models** (1h)
  ```python
  # /src/02_models.py
  class SpacyVIPSender(Base): ...
  class SpacyKeywordSet(Base): ...
  class SpacyScoringConfig(Base): ...
  class SpacyUserDomain(Base): ...
  ```

- [ ] **spaCy Model Upgrade** (1h)
  ```bash
  python -m spacy download de_core_news_md
  ```

- [ ] **Config Manager** (2h)
  ```python
  # /src/services/spacy_config_manager.py
  class SpacyConfigManager:
      def load_keywords(user_id, account_id)
      def load_scoring_config(user_id, account_id)
      def load_vip_senders(user_id, account_id)
      def load_user_domains(user_id, account_id)
  ```

- [ ] **Ensemble-Combiner Grundstruktur** (1h)
  ```python
  # /src/services/ensemble_combiner.py
  class EnsembleCombiner:
      def get_weights() -> (spacy_weight, sgd_weight)
      def combine_predictions(spacy, sgd, vip_boost)
      def _get_training_count(user_id) -> int
  ```

- [ ] **Testing** (2h)
  - Unit-Tests für Config-Manager
  - Unit-Tests für Ensemble-Combiner
  - Migration testen

### Phase Y2: Hybrid Detektoren + Ensemble (8-10h)

**Ziel:** NLP-Detektoren + SGD-Integration

- [ ] **ImperativDetector** (2h)
  - Parser-basierte Erkennung
  - Unit-Tests mit 20+ Beispielen

- [ ] **DeadlineDetector** (2h)
  - NER DATE + Wochentagslogik
  - Unit-Tests mit Datums-Beispielen

- [ ] **KeywordDetector** (1h)
  - Lemmatizer-Integration
  - Unit-Tests

- [ ] **HybridPipeline mit SGD** (3h)
  - Orchestrator implementieren
  - spaCy Scoring-Engine (0-10)
  - SGD-Prediction Integration
  - Ensemble-Combiner aufrufen
  - Account-Toggle Kompatibilität

- [ ] **Testing** (2h)
  - Integration-Tests (spaCy + SGD + VIP)
  - Performance-Benchmarks
  - Cold-Start Tests (<20 Korrekturen)
  - Learning-Phase Tests (20-50 Korrekturen)

### Phase Y3: UI mit 4 Tabs + Keyword-Vorschläge (9-11h)

**Ziel:** Benutzer-Interface + Learning-Features

- [ ] **Backend-Routes** (3h)
  ```python
  # /src/01_web_app.py
  @app.route('/spacy-tuning')
  @app.route('/api/spacy/vip-senders', methods=['GET', 'POST', 'DELETE'])
  @app.route('/api/spacy/keywords', methods=['GET', 'POST'])
  @app.route('/api/spacy/scoring', methods=['GET', 'POST'])
  @app.route('/api/spacy/domains', methods=['GET', 'POST', 'DELETE'])
  
  # NEU: Keyword-Vorschläge
  @app.route('/api/emails/<id>/correct', methods=['POST'])
  # → Gibt keyword_suggestions zurück
  ```

- [ ] **KeywordSuggester** (2h)
  ```python
  # /src/services/keyword_suggester.py
  class KeywordSuggester:
      def analyze_correction(subject, body, old, new)
      # → Generiert Keyword-Vorschläge
  ```

- [ ] **Frontend Templates** (4h)
  ```html
  <!-- /templates/spacy_tuning.html -->
  <div class="tabs">
    <div id="vip-tab">...</div>
    <div id="keywords-tab">...</div>
    <div id="scoring-tab">...</div>
    <div id="domains-tab">...</div>
  </div>
  
  <!-- NEU: Keyword-Vorschläge Modal -->
  <!-- /templates/partials/correction_modal.html -->
  <div id="keyword-suggestions">...</div>
  ```

- [ ] **JavaScript** (2h)
  - Tab-Navigation
  - CRUD-Operationen
  - Live-Validierung
  - Keyword-Vorschläge UI

- [ ] **CSS** (1h)
  - Responsive Design
  - Tab-Styling

- [ ] **Testing** (1h)
  - UI-Tests im Browser
  - CRUD-Flows testen
  - Keyword-Vorschläge Flow

### Phase Y4: Integration & Testing (4-6h)

**Ziel:** Integration in bestehende App

- [ ] **UrgencyBooster erweitern** (2h)
  ```python
  # /src/services/urgency_booster.py
  class UrgencyBooster:
      def __init__(self, use_hybrid=True):
          if use_hybrid:
              self.pipeline = HybridUrgencyPipeline(...)
          else:
              # Fallback auf alten Code
  ```

- [ ] **Integration in Processing** (1h)
  ```python
  # /src/12_processing.py
  # Keine Änderung nötig - UrgencyBooster bleibt API-kompatibel
  ```

- [ ] **End-to-End Tests** (2h)
  - 30+ Real-World Email-Cases
  - Performance-Benchmarks
  - Vergleich Alt vs. Neu

- [ ] **Dokumentation** (1h)
  - User-Guide für UI
  - Admin-Guide für Defaults

---

## 📊 Performance-Ziele

| Metrik | Ziel | Aktuell (sm) | Erwartet (md + Hybrid) |
|--------|------|--------------|------------------------|
| **Latenz** | <500ms | 100-300ms | 150-400ms |
| **Accuracy** | >85% | ~70% | **>90%** |
| **False Positives** | <5% | ~15% | **<5%** |
| **Keyword-Pflege** | Minimal | N/A | **80 statt 200** |

---

## ✅ Checkliste

- [ ] Phase Y1: Core + Ensemble (7-9h)
- [ ] Phase Y2: Detektoren + SGD (8-10h)
- [ ] Phase Y3: UI + Keyword-Vorschläge (9-11h)
- [ ] Phase Y4: Testing (4-6h)

**Gesamt: 28-36h** (inkl. SGD-Ensemble + Learning-Features)

**Vergleich:**
- Pure-Keywords (ohne Ensemble): 24-32h
- Hybrid ohne Ensemble: 24-32h
- **Hybrid + Ensemble + Learning: 28-36h** ⭐ (empfohlen)

---

## 🚀 Nächster Schritt

Soll ich mit **Phase Y1 (Migration + Models)** starten?

**Aufgaben:**
1. Migration erstellen (4 Tabellen)
2. ORM Models hinzufügen
3. spaCy md installieren
4. Config-Manager implementieren

**Zeitaufwand:** 6-8h

**Danach:** Phase Y2 (Detektoren) → 6-8h

---

**Autor:** GitHub Copilot  
**Entscheidung:** Thomas → ✅ Hybrid-Ansatz  
**Version:** 1.0
