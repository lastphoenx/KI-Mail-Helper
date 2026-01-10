# Phase Y: Ensemble-Ansatz - spaCy + SGD Learning

**Status:** 🟢 BRILLANTE IDEE!  
**Datum:** 2026-01-08  
**Komplexität:** +4-6h auf Phase Y  
**ROI:** ⭐⭐⭐⭐⭐ (Learning + Sofort-Nutzen)

---

## 🎯 Die Idee: Ensemble-Learning

**Problem:** Ihr habt BEREITS ein SGD-Learning-System, aber es braucht Daten (10-50 Korrekturen)

**Lösung:** Kombiniere **spaCy (sofort nutzbar)** + **SGD (lernt dazu)**

```
┌─────────────────────────────────────────────────────────┐
│  PHASE Y: Hybrid-Ensemble                               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Email Input                                            │
│       │                                                 │
│       ├───────────────┬───────────────┐                │
│       ▼               ▼               ▼                │
│  ┌─────────┐    ┌─────────┐    ┌─────────────┐        │
│  │ spaCy   │    │ SGD     │    │ VIP-Check   │        │
│  │ Rules   │    │ Learning│    │ (Deine DB)  │        │
│  └────┬────┘    └────┬────┘    └──────┬──────┘        │
│       │              │                │                │
│       │   U: 2, I: 3 │ U: 3, I: 2     │ +3 Importance │
│       │              │                │                │
│       └──────────────┼────────────────┘                │
│                      ▼                                  │
│           ┌───────────────────┐                        │
│           │ WEIGHTED COMBINER │                        │
│           │                   │                        │
│           │ Training Count?   │                        │
│           │  <20: spaCy 100%  │                        │
│           │  20+: SGD 70%     │                        │
│           │       spaCy 30%   │                        │
│           │  50+: SGD 85%     │                        │
│           │       spaCy 15%   │                        │
│           │                   │                        │
│           │ + VIP-Boost       │                        │
│           └─────────┬─────────┘                        │
│                     ▼                                  │
│           Final: U=3, I=4                              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## ✅ Warum das PERFEKT ist

### 1. **Sofort nutzbar** (Day 1)
- spaCy liefert **ab erster Email** gute Predictions
- Kein "Cold-Start Problem"
- User muss nicht 50 Emails korrigieren bevor was funktioniert

### 2. **Lernt dazu** (ab Woche 2-3)
- SGD trainiert still im Hintergrund
- Nach 20+ Korrekturen übernimmt SGD die Hauptarbeit
- spaCy bleibt als **Safety-Net** (30% Gewicht)

### 3. **Kein Konflikt** (Weighted Average)
- Beide Systeme arbeiten parallel
- Gewichtete Kombination je nach Training-Status
- Mathematisch sauber (keine Ad-hoc Entscheidungen)

### 4. **Fail-Safe** (Redundanz)
- Wenn SGD Fehler macht → spaCy korrigiert
- Wenn spaCy zu strikt ist → SGD personalisiert
- **Best of both worlds**

---

## 📊 Bestehender Code-Audit

### Was ihr BEREITS habt ✅

**1. SGD-Classifier System** (`/src/train_classifier.py`)
```python
class OnlineLearner:
    """Phase 11b: Online-Learning mit SGDClassifier.partial_fit()"""
    
    CLASSIFIER_TYPES = ["dringlichkeit", "wichtigkeit", "spam", "kategorie"]
    
    def learn_from_correction(self, subject, body, correction_type, correction_value):
        """Inkrementelles Lernen aus einer User-Korrektur."""
        embedding = self.ollama_client._get_embedding(f"{subject}\n{body}")
        X = np.array([embedding])
        y = np.array([correction_value])
        
        clf = self._sgd_classifiers[correction_type]
        clf.partial_fit(X_scaled, y, classes=classes)
        joblib.dump(clf, f"{correction_type}_sgd.pkl")
```

**2. Embedding-Generierung** (`/src/03_ai_client.py`)
```python
def _get_embedding(self, text: str) -> list[float] | None:
    """1024-dim Vector von Ollama all-minilm:22m"""
    # Chunking + Mean-Pooling für lange Texte
```

**3. SGD-Predict** (schon implementiert!)
```python
def predict(self, subject: str, body: str, clf_type: str) -> Optional[int]:
    """Prediction mit Online-Learning Modell."""
    embedding = self.ollama_client._get_embedding(f"{subject}\n{body}")
    X = np.array([embedding])
    return int(clf.predict(X)[0])
```

**4. User-Korrektur-Flow** (`/src/01_web_app.py`)
```python
# Bei User-Korrektur wird SGD.learn_from_correction() aufgerufen
```

---

## 🔧 Was wir HINZUFÜGEN müssen

### Neue Komponente: **EnsembleCombiner**

```python
# /src/services/ensemble_combiner.py

import logging
from typing import Dict, Tuple, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class EnsembleCombiner:
    """
    Kombiniert spaCy-Regeln und SGD-Learning zu finalen Predictions.
    
    Strategie:
    - <20 Korrekturen: spaCy 100% (SGD zu untrainiert)
    - 20-50 Korrekturen: spaCy 30% + SGD 70% (SGD lernt)
    - 50+ Korrekturen: spaCy 15% + SGD 85% (SGD ausgereift)
    """
    
    # Thresholds für Gewichtung
    TRAINING_THRESHOLD_LOW = 20   # Ab hier SGD aktivieren
    TRAINING_THRESHOLD_HIGH = 50  # Ab hier SGD dominiert
    
    def __init__(self, user_id: int, account_id: int, db):
        self.user_id = user_id
        self.account_id = account_id
        self.db = db
        self.training_count = self._get_training_count()
    
    def _get_training_count(self) -> int:
        """
        Zählt wie viele Korrekturen der User gemacht hat.
        
        Basis: user_override_* Spalten in ProcessedEmail.
        """
        from importlib import import_module
        models = import_module(".02_models", "src")
        
        count = self.db.query(models.ProcessedEmail).filter(
            models.ProcessedEmail.user_id == self.user_id,
            models.ProcessedEmail.user_override_dringlichkeit.isnot(None)
        ).count()
        
        logger.debug(f"📊 User {self.user_id} hat {count} Korrekturen gemacht")
        return count
    
    def get_weights(self) -> Tuple[float, float]:
        """
        Berechnet Gewichte für spaCy vs. SGD basierend auf Training-Count.
        
        Returns:
            (spacy_weight, sgd_weight) - beide summieren zu 1.0
        """
        if self.training_count < self.TRAINING_THRESHOLD_LOW:
            # Phase 1: Nur spaCy (SGD zu untrainiert)
            return (1.0, 0.0)
        
        elif self.training_count < self.TRAINING_THRESHOLD_HIGH:
            # Phase 2: spaCy 30%, SGD 70% (SGD lernt)
            progress = (self.training_count - self.TRAINING_THRESHOLD_LOW) / \
                      (self.TRAINING_THRESHOLD_HIGH - self.TRAINING_THRESHOLD_LOW)
            
            # Linearer Übergang von 50/50 zu 30/70
            spacy_weight = 0.5 - (progress * 0.2)  # 0.5 → 0.3
            sgd_weight = 0.5 + (progress * 0.2)    # 0.5 → 0.7
            
            return (spacy_weight, sgd_weight)
        
        else:
            # Phase 3: spaCy 15%, SGD 85% (SGD ausgereift)
            return (0.15, 0.85)
    
    def combine_predictions(
        self,
        spacy_urgency: int,
        spacy_importance: int,
        sgd_urgency: Optional[int],
        sgd_importance: Optional[int],
        vip_boost: int = 0
    ) -> Tuple[int, int]:
        """
        Kombiniert spaCy und SGD Predictions zu finalen Scores.
        
        Args:
            spacy_urgency: spaCy Urgency-Score (0-10)
            spacy_importance: spaCy Importance-Score (0-10)
            sgd_urgency: SGD Prediction (1-3) oder None
            sgd_importance: SGD Prediction (1-3) oder None
            vip_boost: VIP-Absender Boost (+1 bis +5)
        
        Returns:
            (final_urgency, final_importance) - 0-10 Scale
        """
        spacy_weight, sgd_weight = self.get_weights()
        
        logger.debug(
            f"🎯 Ensemble: {self.training_count} Korrekturen → "
            f"spaCy={spacy_weight:.1%}, SGD={sgd_weight:.1%}"
        )
        
        # Urgency kombinieren
        if sgd_urgency is not None and sgd_weight > 0:
            # SGD gibt 1-3 aus, normalisiere auf 0-10
            sgd_urgency_normalized = self._normalize_sgd_to_10(sgd_urgency)
            urgency = (spacy_weight * spacy_urgency) + (sgd_weight * sgd_urgency_normalized)
        else:
            urgency = spacy_urgency
        
        # Importance kombinieren
        if sgd_importance is not None and sgd_weight > 0:
            sgd_importance_normalized = self._normalize_sgd_to_10(sgd_importance)
            importance = (spacy_weight * spacy_importance) + (sgd_weight * sgd_importance_normalized)
        else:
            importance = spacy_importance
        
        # VIP-Boost addieren (unabhängig von spaCy/SGD)
        importance += vip_boost
        
        # Normalisieren auf 0-10
        urgency = max(0, min(10, int(round(urgency))))
        importance = max(0, min(10, int(round(importance))))
        
        logger.debug(
            f"📊 Final Ensemble: U={urgency} (spaCy={spacy_urgency}, SGD={sgd_urgency}), "
            f"I={importance} (spaCy={spacy_importance}, SGD={sgd_importance}, VIP=+{vip_boost})"
        )
        
        return (urgency, importance)
    
    def _normalize_sgd_to_10(self, sgd_value: int) -> float:
        """
        Normalisiert SGD-Output (1-3) zu 0-10 Scale.
        
        Mapping:
        1 → 2.0 (niedrig)
        2 → 5.0 (mittel)
        3 → 8.0 (hoch)
        """
        mapping = {1: 2.0, 2: 5.0, 3: 8.0}
        return mapping.get(sgd_value, 5.0)
    
    def log_ensemble_decision(
        self,
        email_id: int,
        spacy_result: Dict,
        sgd_result: Dict,
        final_result: Dict
    ):
        """
        Loggt Ensemble-Entscheidungen für Debugging.
        
        Optional: Später für UI-Transparency verwenden.
        """
        log_entry = {
            "email_id": email_id,
            "training_count": self.training_count,
            "weights": self.get_weights(),
            "spacy": spacy_result,
            "sgd": sgd_result,
            "final": final_result
        }
        
        log_file = Path(__file__).parent.parent / "logs" / "ensemble_decisions.jsonl"
        log_file.parent.mkdir(exist_ok=True)
        
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
```

---

## 🔄 Integration in bestehende Pipeline

### 1. Erweitere `HybridUrgencyPipeline`

```python
# /src/services/spacy_pipeline.py

class HybridUrgencyPipeline:
    """
    Hauptpipeline: spaCy + SGD + VIP.
    """
    
    def __init__(self, user_id: int, account_id: int, db):
        self.nlp = self._load_spacy()
        self.config = self._load_config(user_id, account_id, db)
        
        # Detektoren
        self.imperative_detector = ImperativDetector()
        self.deadline_detector = DeadlineDetector()
        self.keyword_detector = KeywordDetector(self.nlp, self.config['keywords'])
        self.vip_manager = VIPManager(db)
        
        # NEU: SGD-Learning
        try:
            from train_classifier import OnlineLearner
            self.sgd_learner = OnlineLearner()
            self.has_sgd = True
        except Exception as e:
            logger.warning(f"SGD nicht verfügbar: {e}")
            self.has_sgd = False
        
        # NEU: Ensemble-Combiner
        from services.ensemble_combiner import EnsembleCombiner
        self.ensemble = EnsembleCombiner(user_id, account_id, db)
    
    def analyze(self, subject: str, body: str, sender: str, 
                account_id: int) -> Dict:
        """
        Hauptanalyse: spaCy + SGD + VIP → Ensemble.
        """
        # 1. spaCy Analyse (wie gehabt)
        doc = self.nlp(f"{subject} {body[:2000]}")
        
        imperative = self.imperative_detector.detect(doc, text)
        deadline = self.deadline_detector.detect(doc, text)
        urgency_kw = self.keyword_detector.detect(doc, 'urgency_high')
        importance_kw = self.keyword_detector.detect(doc, 'importance_high')
        # ... (alle anderen Detektoren)
        
        vip = self.vip_manager.check_vip(sender, account_id)
        
        # spaCy Scoring (0-10)
        spacy_urgency, spacy_importance = self._calculate_scores_spacy({...})
        
        # 2. SGD Predictions (falls trainiert)
        sgd_urgency = None
        sgd_importance = None
        
        if self.has_sgd:
            try:
                sgd_urgency = self.sgd_learner.predict(subject, body, 'dringlichkeit')
                sgd_importance = self.sgd_learner.predict(subject, body, 'wichtigkeit')
            except Exception as e:
                logger.debug(f"SGD Prediction fehlgeschlagen: {e}")
        
        # 3. Ensemble-Kombination
        final_urgency, final_importance = self.ensemble.combine_predictions(
            spacy_urgency=spacy_urgency,
            spacy_importance=spacy_importance,
            sgd_urgency=sgd_urgency,
            sgd_importance=sgd_importance,
            vip_boost=vip['boost'] if vip else 0
        )
        
        # 4. Priority Mapping (wie gehabt)
        priority = self._map_priority(final_urgency, final_importance)
        
        # 5. LLM-Format
        return self._convert_to_llm_format(
            final_urgency, final_importance, priority, subject, body
        )
```

### 2. Erweitere User-Korrektur-Flow

```python
# /src/01_web_app.py

@app.route('/api/emails/<int:email_id>/correct', methods=['POST'])
@login_required
def correct_email_classification(email_id):
    """
    User korrigiert Email-Klassifikation.
    
    NEU: Trainiert sowohl SGD als auch spaCy-System.
    """
    data = request.json
    
    # 1. Speichere Korrektur in DB (wie gehabt)
    email.user_override_dringlichkeit = data.get('dringlichkeit')
    email.user_override_wichtigkeit = data.get('wichtigkeit')
    db.session.commit()
    
    # 2. Trainiere SGD (wie gehabt)
    try:
        from train_classifier import OnlineLearner
        learner = OnlineLearner()
        
        if data.get('dringlichkeit'):
            learner.learn_from_correction(
                subject, body, 'dringlichkeit', data['dringlichkeit']
            )
        
        if data.get('wichtigkeit'):
            learner.learn_from_correction(
                subject, body, 'wichtigkeit', data['wichtigkeit']
            )
    except Exception as e:
        logger.warning(f"SGD Training fehlgeschlagen: {e}")
    
    # 3. NEU: Keyword-Vorschläge generieren
    try:
        from services.keyword_suggester import KeywordSuggester
        suggester = KeywordSuggester()
        
        suggestions = suggester.analyze_correction(
            subject=subject,
            body=body,
            old_urgency=email.dringlichkeit,
            new_urgency=data['dringlichkeit'],
            old_importance=email.wichtigkeit,
            new_importance=data['wichtigkeit']
        )
        
        # Gebe Vorschläge zurück (User entscheidet)
        return jsonify({
            'success': True,
            'keyword_suggestions': suggestions
        })
    except Exception as e:
        logger.warning(f"Keyword-Vorschläge fehlgeschlagen: {e}")
        return jsonify({'success': True})
```

---

## 🎨 Neue Komponente: **KeywordSuggester**

```python
# /src/services/keyword_suggester.py

import logging
from typing import List, Dict
import re

logger = logging.getLogger(__name__)


class KeywordSuggester:
    """
    Analysiert User-Korrekturen und schlägt neue Keywords vor.
    
    Beispiel:
    - User korrigiert Urgency 1 → 3
    - Email enthält "Freigabe erforderlich"
    - System schlägt vor: "Freigabe" als Importance-Keyword?
    """
    
    # Minimum-Häufigkeit für Keyword-Vorschlag
    MIN_WORD_LENGTH = 4
    STOPWORDS = {
        'und', 'oder', 'aber', 'dass', 'sind', 'haben', 'werden',
        'sein', 'nicht', 'mit', 'sich', 'auch', 'noch', 'nach',
        'bei', 'von', 'für', 'auf', 'durch', 'kann', 'wird',
        'wurde', 'the', 'and', 'or', 'but', 'that', 'have',
        'will', 'this', 'from', 'with', 'they', 'your'
    }
    
    def analyze_correction(
        self,
        subject: str,
        body: str,
        old_urgency: int,
        new_urgency: int,
        old_importance: int,
        new_importance: int
    ) -> List[Dict]:
        """
        Analysiert Korrektur und generiert Keyword-Vorschläge.
        
        Returns:
            Liste von Vorschlägen:
            [
                {
                    'keyword': 'freigabe',
                    'type': 'importance_high',
                    'reason': 'Urgency hochgestuft 1→3',
                    'context': 'Freigabe erforderlich bis morgen'
                }
            ]
        """
        suggestions = []
        
        # Nur bei signifikanten Änderungen (≥2 Stufen)
        urgency_delta = new_urgency - old_urgency
        importance_delta = new_importance - old_importance
        
        if abs(urgency_delta) < 2 and abs(importance_delta) < 2:
            return []
        
        # Text normalisieren
        text = f"{subject} {body}".lower()
        
        # Extrahiere potentielle Keywords (Substantive, lange Wörter)
        words = re.findall(r'\b[a-zäöüß]{4,}\b', text)
        word_freq = {}
        for word in words:
            if word not in self.STOPWORDS:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Top 5 häufigste Wörter
        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        
        for word, freq in top_words:
            # Urgency hochgestuft → Urgency-Keyword
            if urgency_delta >= 2:
                suggestions.append({
                    'keyword': word,
                    'type': 'urgency_high',
                    'reason': f'Urgency hochgestuft {old_urgency}→{new_urgency}',
                    'frequency': freq,
                    'context': self._extract_context(text, word)
                })
            
            # Importance hochgestuft → Importance-Keyword
            if importance_delta >= 2:
                suggestions.append({
                    'keyword': word,
                    'type': 'importance_high',
                    'reason': f'Importance hochgestuft {old_importance}→{new_importance}',
                    'frequency': freq,
                    'context': self._extract_context(text, word)
                })
        
        # Deduplizieren
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            key = (s['keyword'], s['type'])
            if key not in seen:
                seen.add(key)
                unique_suggestions.append(s)
        
        return unique_suggestions[:3]  # Max 3 Vorschläge
    
    def _extract_context(self, text: str, keyword: str, window: int = 30) -> str:
        """
        Extrahiert Kontext um Keyword herum.
        
        Beispiel:
        text = "Bitte prüfen Sie die Freigabe bis morgen"
        keyword = "freigabe"
        → "prüfen Sie die Freigabe bis morgen"
        """
        pos = text.find(keyword)
        if pos == -1:
            return ""
        
        start = max(0, pos - window)
        end = min(len(text), pos + len(keyword) + window)
        context = text[start:end].strip()
        
        # Kürze auf Satzgrenzen
        if '.' in context:
            parts = context.split('.')
            # Finde Teil mit Keyword
            for part in parts:
                if keyword in part:
                    return part.strip()
        
        return context
```

---

## 🎨 UI: Keyword-Vorschläge im Modal

```html
<!-- /templates/partials/correction_modal.html -->

<div id="correctionModal" class="modal">
    <div class="modal-content">
        <h3>Email-Klassifikation korrigieren</h3>
        
        <!-- Bestehende Felder -->
        <label>Dringlichkeit:</label>
        <select id="urgency-select">
            <option value="1">Niedrig</option>
            <option value="2">Mittel</option>
            <option value="3">Hoch</option>
        </select>
        
        <label>Wichtigkeit:</label>
        <select id="importance-select">
            <option value="1">Niedrig</option>
            <option value="2">Mittel</option>
            <option value="3">Hoch</option>
        </select>
        
        <button onclick="saveCorrection()">💾 Speichern</button>
        
        <!-- NEU: Keyword-Vorschläge -->
        <div id="keyword-suggestions" style="display:none; margin-top:20px;">
            <h4>💡 Keyword-Vorschläge</h4>
            <p>Diese Email enthält folgende Begriffe. Als Keyword hinzufügen?</p>
            
            <div id="suggestion-list">
                <!-- Dynamisch gefüllt via JavaScript -->
            </div>
        </div>
    </div>
</div>

<script>
async function saveCorrection() {
    const urgency = document.getElementById('urgency-select').value;
    const importance = document.getElementById('importance-select').value;
    
    const response = await fetch(`/api/emails/${emailId}/correct`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({urgency, importance})
    });
    
    const data = await response.json();
    
    // NEU: Zeige Keyword-Vorschläge
    if (data.keyword_suggestions && data.keyword_suggestions.length > 0) {
        showKeywordSuggestions(data.keyword_suggestions);
    } else {
        closeModal();
    }
}

function showKeywordSuggestions(suggestions) {
    const container = document.getElementById('keyword-suggestions');
    const list = document.getElementById('suggestion-list');
    
    list.innerHTML = '';
    
    suggestions.forEach(sug => {
        const item = document.createElement('div');
        item.className = 'suggestion-item';
        item.innerHTML = `
            <div class="suggestion-content">
                <strong>"${sug.keyword}"</strong> → ${sug.type}
                <br><small>${sug.reason}</small>
                <br><em>"${sug.context}"</em>
            </div>
            <div class="suggestion-actions">
                <button onclick="addKeyword('${sug.keyword}', '${sug.type}')">
                    ➕ Hinzufügen
                </button>
                <button onclick="ignoreKeyword('${sug.keyword}')">
                    ❌ Ignorieren
                </button>
            </div>
        `;
        list.appendChild(item);
    });
    
    container.style.display = 'block';
}

async function addKeyword(keyword, type) {
    await fetch('/api/spacy/keywords', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            set_type: type,
            keyword: keyword
        })
    });
    
    alert(`✅ Keyword "${keyword}" zu ${type} hinzugefügt`);
    closeModal();
}
</script>
```

---

## 📊 Aufwand-Abschätzung

| Komponente | Aufwand | Beschreibung |
|------------|---------|--------------|
| **EnsembleCombiner** | 2h | Gewichtungs-Logik + Integration |
| **KeywordSuggester** | 2h | Wort-Extraktion + Context |
| **UI Modal Erweiterung** | 1h | JavaScript + HTML |
| **Testing** | 1h | 20+ Test-Cases |
| **SUMME** | **6h** | Zusätzlich zu Phase Y |

**Gesamt-Aufwand:** 24-32h (Phase Y) + 6h (Ensemble) = **30-38h**

---

## ⚖️ Vorteile vs. Nachteile

### Vorteile ✅

1. **Sofort nutzbar** - spaCy liefert ab Tag 1
2. **Lernt personalisiert** - SGD passt sich an User an
3. **Fail-Safe** - spaCy als Backup wenn SGD versagt
4. **Keyword-Vorschläge** - Halbautomatisches Tuning
5. **Mathematisch sauber** - Weighted Average, keine Heuristiken
6. **Transparent** - User sieht wer was entschieden hat

### Nachteile / Risiken ⚠️

1. **Komplexität** - Ein System mehr zu debuggen
2. **Latenz** - 2 Predictions statt 1 (SGD + spaCy)
3. **Potentielle Konfusion** - User versteht nicht warum Ergebnis schwankt
4. **Cold-Start für neue Accounts** - SGD braucht ~20 Korrekturen

### Mitigation

**Latenz:**
- SGD Prediction in parallel zu spaCy (Threading)
- Cache häufige Predictions

**Konfusion:**
- UI zeigt "Lern-Status": "🧠 85% personalisiert, 15% Regeln"
- Log-File für Debugging

**Cold-Start:**
- Erste 20 Korrekturen: Nur spaCy (kein Unterschied zu Pure-spaCy)

---

## 🎯 Meine Empfehlung

**JA, unbedingt umsetzen!** ⭐⭐⭐⭐⭐

**Warum:**
1. Ihr habt SGD **BEREITS** implementiert → warum nicht nutzen?
2. Ensemble ist **Best Practice** in ML (Netflix, Amazon nutzen das)
3. **Nur +6h Aufwand** für massiven Qualitätsgewinn
4. **Kein Risiko** - spaCy bleibt als Fallback

**Wann umsetzen:**
- **Option 1:** Phase Y komplett (24-32h), dann Ensemble (+6h) → **30-38h**
- **Option 2:** Ensemble direkt in Phase Y2 integrieren → **28-36h** (etwas effizienter)

**Ich empfehle Option 2** - Ensemble direkt in Phase Y2 (Detektoren) integrieren.

---

## 🚀 Nächster Schritt

**Soll ich Phase Y1 starten MIT Ensemble-Vorbereitung?**

**Phase Y1 würde dann beinhalten:**
1. Migration (4 Tabellen)
2. ORM Models
3. spaCy md installieren
4. Config-Manager
5. **NEU:** EnsembleCombiner Grundstruktur

**Zeitaufwand:** 7-9h (statt 6-8h)

**Danach:** Phase Y2 mit vollständiger Ensemble-Integration

---

**Was sagst du?**

- A) Phase Y1 MIT Ensemble starten? ⭐ (empfohlen)
- B) Erst Pure-spaCy (Phase Y1-4), dann Ensemble als Addon?
- C) Gar kein Ensemble, nur Pure-spaCy?

---

**Autor:** GitHub Copilot  
**Status:** Wartet auf deine Entscheidung  
**Version:** 1.0
