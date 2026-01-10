# Feature: Negativ-Feedback für Tag-Learning (v2.0)

> **Version:** 2.0 (überarbeitet nach 3 unabhängigen Code-Reviews)  
> **Status:** Bereit für Implementierung  
> **Abhängigkeit:** PATCH_PHASE_F2_QUEUE_FLAG_BUG.md muss ZUERST implementiert werden!

---

## 🎯 Übersicht

Erweiterung des Tag-Learning-Systems um **Negativ-Feedback**: User können Tags als "passt nicht" markieren, was die Suggestion-Qualität verbessert.

### Warum Embedding-basiert (NICHT Counter)?

Ein einfacher `rejection_count` wurde in Reviews vorgeschlagen, aber **funktioniert nicht**:

```
Tag "Rechnung": 50 positive, 5 rejections

MIT COUNTER (FALSCH):
Newsletter (PayPal): 72% - 2% = 70% → VORGESCHLAGEN ❌
Echte Rechnung:      88% - 2% = 86% → VORGESCHLAGEN ✓
→ GLEICHE Penalty für UNTERSCHIEDLICHE Emails!

MIT EMBEDDING (RICHTIG):
Newsletter (PayPal): 72% - 15% = 57% → SKIP ✓ (82% ähnlich zu Rejection)
Echte Rechnung:      88% - 0% = 88% → VORGESCHLAGEN ✓ (40% ähnlich zu Rejection)
→ Penalty basiert auf ÄHNLICHKEIT zur Rejection!
```

**Counter berücksichtigt NICHT die Ähnlichkeit** - Embedding-basiert ist essentiell.

---

## 📊 Konzept

```
VORHER (nur Positiv-Learning):
┌─────────────────────────────────────────────────────────────┐
│  Tag "Rechnung" learned_embedding = avg(email1, email2)     │
│  Neue Email → Similarity 75% → SUGGEST ✓                    │
│  User: "Passt nicht!" → ??? (nichts passiert)               │
└─────────────────────────────────────────────────────────────┘

NACHHER (mit Negativ-Feedback):
┌─────────────────────────────────────────────────────────────┐
│  Tag "Rechnung" learned_embedding = avg(email1, email2)     │
│  Tag "Rechnung" negative_embedding = avg(neg1, neg2, neg3)  │
│  Neue Email:                                                │
│    1. Positive Similarity: 75%                              │
│    2. Negative Similarity: 82% → SKIP! (>80% Threshold)     │
│    ODER                                                     │
│    2. Negative Similarity: 65% → Penalty -10%               │
│    3. Adjusted: 65% → SUGGEST (nicht auto-assign)           │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗄️ Datenbank-Schema

### Option A: Aggregiertes Embedding (EMPFOHLEN - performanter)

Erweiterung von `EmailTag`:

```python
# src/02_models.py - EmailTag erweitern

class EmailTag(Base):
    # ... bestehende Felder ...
    
    # 🆕 NEU: Aggregiertes Negativ-Embedding
    negative_embedding = Column(LargeBinary, nullable=True)
    negative_updated_at = Column(DateTime, nullable=True)
    negative_count = Column(Integer, default=0)  # Anzahl Negativ-Beispiele
```

### Option B: Separate Tabelle (flexibler, für Debugging)

```python
# src/02_models.py - NEUE KLASSE

class TagNegativeExample(Base):
    """Negativ-Beispiele für Tag-Learning"""
    
    __tablename__ = "tag_negative_examples"
    
    id = Column(Integer, primary_key=True)
    tag_id = Column(Integer, ForeignKey("email_tags.id", ondelete="CASCADE"), nullable=False)
    email_id = Column(Integer, ForeignKey("processed_emails.id", ondelete="CASCADE"), nullable=False)
    
    # Embedding-Kopie (da Email-Embedding sich ändern könnte)
    negative_embedding = Column(LargeBinary, nullable=False)
    
    # Metadaten
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    rejection_source = Column(String(20), default="suggestion")  # "suggestion" | "auto_assign"
    
    # Relationships
    tag = relationship("EmailTag", backref="negative_examples")
    email = relationship("ProcessedEmail", backref="negative_tag_examples")
    
    __table_args__ = (
        UniqueConstraint("tag_id", "email_id", name="uq_tag_negative_email"),
        Index("ix_tag_negative_tag_id", "tag_id"),
    )
```

### Empfehlung: **Beides implementieren**

- `TagNegativeExample`: Speichert einzelne Rejections (für Debugging, Undo)
- `EmailTag.negative_embedding`: Aggregat für schnelle Berechnung (1x statt N Vergleiche)

---

## 📋 Migration

```python
# migrations/versions/xxx_add_negative_feedback.py

"""Add negative feedback support for tag learning

Revision ID: xxx
"""

from alembic import op
import sqlalchemy as sa

def upgrade():
    # Option A: EmailTag erweitern
    op.add_column('email_tags', sa.Column('negative_embedding', sa.LargeBinary(), nullable=True))
    op.add_column('email_tags', sa.Column('negative_updated_at', sa.DateTime(), nullable=True))
    op.add_column('email_tags', sa.Column('negative_count', sa.Integer(), server_default='0'))
    
    # Option B: Separate Tabelle
    op.create_table(
        'tag_negative_examples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.Column('email_id', sa.Integer(), nullable=False),
        sa.Column('negative_embedding', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_source', sa.String(20), nullable=True, server_default='suggestion'),
        sa.ForeignKeyConstraint(['tag_id'], ['email_tags.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['email_id'], ['processed_emails.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tag_id', 'email_id', name='uq_tag_negative_email')
    )
    op.create_index('ix_tag_negative_tag_id', 'tag_negative_examples', ['tag_id'])


def downgrade():
    op.drop_index('ix_tag_negative_tag_id')
    op.drop_table('tag_negative_examples')
    op.drop_column('email_tags', 'negative_count')
    op.drop_column('email_tags', 'negative_updated_at')
    op.drop_column('email_tags', 'negative_embedding')
```

**⚠️ WICHTIG: Migration MUSS vor Code-Änderungen laufen!**

```bash
cd /home/mailhelper/projects/KI-Mail-Helper
source venv/bin/activate
alembic revision --autogenerate -m "Add negative feedback support"
alembic upgrade head
```

---

## 🔧 Konstanten & Konfiguration

```python
# src/services/tag_manager.py - Nach bestehenden Konstanten

# ============================================
# Negativ-Feedback Konfiguration
# ============================================

# SKIP-Threshold: Ab dieser Negativ-Similarity wird Tag komplett übersprungen
NEGATIVE_SKIP_THRESHOLD = 0.80  # 80% → Komplett skip (kein Suggest, kein Auto-Assign)

# Penalty-Threshold: Ab hier wird Penalty berechnet
NEGATIVE_PENALTY_THRESHOLD = 0.60  # 60% → Penalty beginnt

# Maximale Penalty (bei 100% Negativ-Similarity)
NEGATIVE_MAX_PENALTY = 0.25  # 25% Abzug maximal

# Limit für Performance
MAX_NEGATIVE_EXAMPLES_PER_TAG = 20
```

---

## 🔧 Tag-Manager Methoden

### 1. `add_negative_example()` - Negativ-Feedback speichern

```python
@staticmethod
def add_negative_example(
    db: Session, 
    tag_id: int, 
    email_id: int, 
    user_id: int,
    rejection_source: str = "suggestion"
) -> bool:
    """Markiert eine Email als Negativ-Beispiel für einen Tag
    
    Args:
        db: SQLAlchemy Session
        tag_id: EmailTag ID
        email_id: ProcessedEmail ID
        user_id: User ID (zur Validierung)
        rejection_source: "suggestion" | "auto_assign" (NICHT "manual"!)
        
    Returns:
        True wenn erfolgreich
    """
    # 1. Validierung: Tag gehört User
    tag = db.query(models.EmailTag).filter(
        models.EmailTag.id == tag_id,
        models.EmailTag.user_id == user_id
    ).first()
    
    if not tag:
        logger.warning(f"❌ Negativ-Feedback: Tag {tag_id} nicht gefunden")
        return False
    
    # 2. Email und Embedding holen
    processed = db.query(models.ProcessedEmail).filter(
        models.ProcessedEmail.id == email_id
    ).first()
    
    if not processed:
        logger.warning(f"❌ Negativ-Feedback: Email {email_id} nicht gefunden")
        return False
    
    raw_email = db.query(models.RawEmail).filter(
        models.RawEmail.id == processed.raw_email_id,
        models.RawEmail.user_id == user_id
    ).first()
    
    if not raw_email or not raw_email.email_embedding:
        logger.warning(f"❌ Negativ-Feedback: Email {email_id} hat kein Embedding")
        return False
    
    # 3. Check ob bereits existiert
    existing = db.query(models.TagNegativeExample).filter(
        models.TagNegativeExample.tag_id == tag_id,
        models.TagNegativeExample.email_id == email_id
    ).first()
    
    if existing:
        logger.info(f"ℹ️ Negativ-Beispiel existiert bereits: Tag {tag_id}, Email {email_id}")
        return True
    
    # 4. Limit prüfen - ältestes löschen wenn nötig
    count = db.query(models.TagNegativeExample).filter(
        models.TagNegativeExample.tag_id == tag_id
    ).count()
    
    if count >= MAX_NEGATIVE_EXAMPLES_PER_TAG:
        oldest = db.query(models.TagNegativeExample).filter(
            models.TagNegativeExample.tag_id == tag_id
        ).order_by(models.TagNegativeExample.created_at.asc()).first()
        
        if oldest:
            db.delete(oldest)
            logger.info(f"🗑️ Ältestes Negativ-Beispiel gelöscht für Tag {tag_id}")
    
    # 5. Negativ-Beispiel erstellen
    negative = models.TagNegativeExample(
        tag_id=tag_id,
        email_id=email_id,
        negative_embedding=raw_email.email_embedding,  # Kopie!
        rejection_source=rejection_source
    )
    
    db.add(negative)
    
    # 6. Aggregiertes Negativ-Embedding aktualisieren
    TagManager.update_negative_embedding(db, tag_id)
    
    db.commit()
    
    logger.info(f"✅ Negativ-Beispiel hinzugefügt: Tag '{tag.name}', Email {email_id} ({rejection_source})")
    return True
```

### 2. `update_negative_embedding()` - Aggregat berechnen

```python
@staticmethod
def update_negative_embedding(db: Session, tag_id: int) -> None:
    """Aktualisiert das aggregierte Negativ-Embedding eines Tags
    
    Berechnet Durchschnitt aller Negativ-Beispiele.
    Analog zu update_learned_embedding(), aber für Negative.
    """
    tag = db.query(models.EmailTag).filter(
        models.EmailTag.id == tag_id
    ).first()
    
    if not tag:
        return
    
    # Alle Negativ-Beispiele holen
    negatives = db.query(models.TagNegativeExample).filter(
        models.TagNegativeExample.tag_id == tag_id
    ).all()
    
    if not negatives:
        # Keine Negativen → Embedding löschen
        tag.negative_embedding = None
        tag.negative_count = 0
        tag.negative_updated_at = None
        logger.info(f"🗑️ Tag '{tag.name}': Negativ-Embedding gelöscht (keine Beispiele)")
        return
    
    # Embeddings sammeln
    embeddings = []
    for neg in negatives:
        try:
            emb = np.frombuffer(neg.negative_embedding, dtype=np.float32)
            embeddings.append(emb)
        except Exception as e:
            logger.warning(f"⚠️ Fehler bei Negativ-Embedding {neg.id}: {e}")
            continue
    
    if not embeddings:
        tag.negative_embedding = None
        tag.negative_count = 0
        return
    
    # Durchschnitt berechnen
    avg_embedding = np.mean(embeddings, axis=0).astype(np.float32)
    
    # Normalisieren
    norm = np.linalg.norm(avg_embedding)
    if norm > 0:
        avg_embedding = avg_embedding / norm
    
    # Speichern
    tag.negative_embedding = avg_embedding.tobytes()
    tag.negative_count = len(embeddings)
    tag.negative_updated_at = datetime.now(UTC)
    
    logger.info(f"🎓 Tag '{tag.name}': Negativ-Embedding aktualisiert ({len(embeddings)} Beispiele)")
```

### 3. `get_negative_similarity()` - Ähnlichkeit zu Negativen prüfen

```python
@staticmethod
def get_negative_similarity(
    tag: models.EmailTag,
    email_embedding: np.ndarray
) -> float:
    """Berechnet Ähnlichkeit einer Email zum Negativ-Aggregat
    
    Args:
        tag: Tag mit potenziellem negative_embedding
        email_embedding: Normalisiertes Email-Embedding
        
    Returns:
        Similarity (0.0 - 1.0), 0.0 wenn kein Negativ-Embedding
    """
    if not tag.negative_embedding:
        return 0.0
    
    try:
        neg_emb = np.frombuffer(tag.negative_embedding, dtype=np.float32)
        
        # Normalisieren falls nötig
        norm = np.linalg.norm(neg_emb)
        if norm > 0 and abs(norm - 1.0) > 0.001:
            neg_emb = neg_emb / norm
        
        similarity = float(np.dot(email_embedding, neg_emb))
        return max(0.0, similarity)
        
    except Exception as e:
        logger.warning(f"⚠️ Fehler bei Negativ-Similarity: {e}")
        return 0.0
```

### 4. `calculate_negative_penalty()` - Penalty berechnen

```python
@staticmethod
def calculate_negative_penalty(negative_similarity: float) -> float:
    """Berechnet Penalty basierend auf Negativ-Similarity
    
    Verwendet quadratische Skalierung für sanfteren Start und 
    härtere Penalty bei hohen Werten.
    
    Args:
        negative_similarity: Ähnlichkeit zum Negativ-Aggregat (0.0 - 1.0)
        
    Returns:
        Penalty (0.0 - NEGATIVE_MAX_PENALTY)
    """
    if negative_similarity < NEGATIVE_PENALTY_THRESHOLD:
        return 0.0
    
    # Quadratische Skalierung
    factor = (negative_similarity - NEGATIVE_PENALTY_THRESHOLD) / (1.0 - NEGATIVE_PENALTY_THRESHOLD)
    penalty = (factor ** 2) * NEGATIVE_MAX_PENALTY
    
    return min(penalty, NEGATIVE_MAX_PENALTY)

# Beispiele:
# 60% Negativ-Sim → 0% Penalty
# 70% Negativ-Sim → 1.6% Penalty  
# 80% Negativ-Sim → 6.3% Penalty
# 90% Negativ-Sim → 14% Penalty
# 100% Negativ-Sim → 25% Penalty
```

---

## 🔄 Integration in `suggest_tags_by_email_embedding()`

```python
# In der for-loop über user_tags (ca. Zeile 580-620)

for tag in user_tags:
    # ... bestehende Embedding-Berechnung ...
    
    tag_emb = TagEmbeddingCache.get_tag_embedding(tag, db)
    if tag_emb is None:
        continue
    
    # Positive Similarity
    raw_similarity = float(np.dot(email_emb, tag_emb))
    
    # 🆕 NEGATIV-CHECK (VOR Threshold-Prüfung!)
    negative_similarity = TagManager.get_negative_similarity(tag, email_emb)
    
    # SKIP-Check: Zu ähnlich zu Negativ → komplett überspringen
    if negative_similarity >= NEGATIVE_SKIP_THRESHOLD:
        logger.info(
            f"❌ SKIP '{tag.name}': zu ähnlich zu Negativ-Beispielen "
            f"(neg_sim={negative_similarity:.0%} >= {NEGATIVE_SKIP_THRESHOLD:.0%})"
        )
        continue  # Komplett überspringen!
    
    # Penalty berechnen
    penalty = TagManager.calculate_negative_penalty(negative_similarity)
    
    # Adjusted Similarity
    similarity = max(0.0, raw_similarity - penalty)
    
    # Logging
    if penalty > 0:
        logger.info(
            f"📉 Tag '{tag.name}': raw={raw_similarity:.2%}, "
            f"neg_sim={negative_similarity:.2%}, penalty=-{penalty:.2%}, "
            f"adjusted={similarity:.2%}"
        )
    
    # Rest wie gehabt: Threshold-Checks mit adjusted similarity
    suggest_threshold, auto_assign_threshold = TagEmbeddingCache._get_thresholds_for_tag(tag)
    # ...
```

---

## 🌐 API-Endpoints

### POST `/api/tags/<tag_id>/reject/<email_id>`

```python
@app.route("/api/tags/<int:tag_id>/reject/<int:email_id>", methods=["POST"])
@login_required
def api_reject_tag_for_email(tag_id: int, email_id: int):
    """Markiert Tag als 'passt nicht' für diese Email
    
    Body (optional): {"source": "suggestion" | "auto_assign"}
    """
    try:
        data = request.get_json() or {}
        source = data.get("source", "suggestion")
        
        # Validierung: Nur erlaubte Sources
        if source not in ("suggestion", "auto_assign"):
            source = "suggestion"
        
        success = TagManager.add_negative_example(
            db=db_session,
            tag_id=tag_id,
            email_id=email_id,
            user_id=current_user.id,
            rejection_source=source
        )
        
        if success:
            return jsonify({
                "success": True,
                "message": "Tag wird für ähnliche Emails nicht mehr vorgeschlagen"
            })
        else:
            return jsonify({"success": False, "error": "Konnte Feedback nicht speichern"}), 400
            
    except Exception as e:
        logger.error(f"Reject tag error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
```

### DELETE `/api/tags/<tag_id>/reject/<email_id>` (Undo)

```python
@app.route("/api/tags/<int:tag_id>/reject/<int:email_id>", methods=["DELETE"])
@login_required
def api_unreject_tag_for_email(tag_id: int, email_id: int):
    """Entfernt Negativ-Markierung (Undo)"""
    try:
        success = TagManager.remove_negative_example(
            db=db_session,
            tag_id=tag_id,
            email_id=email_id,
            user_id=current_user.id
        )
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

---

## 🖼️ UI-Integration

### ⚠️ WICHTIG: NUR an 2 Stellen (NICHT bei manuellem Tagging!)

Basierend auf Reviews: "Passt nicht" bei manuellem Tagging ist **kontraintuitiv** und wurde entfernt.

### 1. Bei Tag-Suggestions (Email-Detail)

```html
<!-- Tag-Suggestion mit Reject-Button -->
<div class="tag-suggestion flex items-center gap-2 p-2 bg-gray-50 rounded" 
     data-suggestion-tag="{{ suggestion.id }}">
    <span class="tag-badge" style="background: {{ suggestion.color }}">
        {{ suggestion.name }}
    </span>
    <span class="text-sm text-gray-500">{{ (suggestion.similarity * 100)|round }}%</span>
    
    <!-- Accept Button -->
    <button onclick="assignTag({{ suggestion.id }})" 
            class="btn-sm btn-success" title="Tag zuweisen">
        <i class="fas fa-check"></i>
    </button>
    
    <!-- Reject Button -->
    <button onclick="rejectTagSuggestion({{ suggestion.id }}, {{ email.id }})" 
            class="btn-sm btn-outline-danger" title="Passt nicht">
        <i class="fas fa-times"></i>
    </button>
</div>
```

### 2. Bei Auto-Assigned Tags (mit "War falsch" Option)

```html
<!-- Auto-assigned Tag mit Korrektur-Option -->
{% for assignment in email.tag_assignments %}
<div class="assigned-tag flex items-center gap-1">
    <span class="tag-badge" style="background: {{ assignment.tag.color }}">
        {{ assignment.tag.name }}
    </span>
    
    <!-- Normales Entfernen -->
    <button onclick="removeTag({{ assignment.tag.id }}, {{ email.id }})" 
            class="btn-xs btn-ghost" title="Tag entfernen">
        <i class="fas fa-times"></i>
    </button>
    
    <!-- "War falsch" NUR bei auto_assigned Tags -->
    {% if assignment.auto_assigned %}
    <button onclick="removeAndRejectTag({{ assignment.tag.id }}, {{ email.id }})" 
            class="btn-xs btn-ghost text-orange-500" 
            title="War falsch - entfernen und nicht mehr vorschlagen">
        <i class="fas fa-thumbs-down"></i>
    </button>
    {% endif %}
</div>
{% endfor %}
```

### JavaScript

```javascript
async function rejectTagSuggestion(tagId, emailId) {
    try {
        const response = await fetch(`/api/tags/${tagId}/reject/${emailId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ source: 'suggestion' })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('Feedback gespeichert', 'success');
            // Suggestion aus UI entfernen
            document.querySelector(`[data-suggestion-tag="${tagId}"]`)?.remove();
        } else {
            showToast(data.error || 'Fehler', 'error');
        }
    } catch (error) {
        console.error('Reject error:', error);
        showToast('Netzwerkfehler', 'error');
    }
}

async function removeAndRejectTag(tagId, emailId) {
    if (!confirm('Tag entfernen UND für ähnliche Emails nicht mehr vorschlagen?')) {
        return;
    }
    
    try {
        // 1. Tag entfernen
        await fetch(`/api/emails/${emailId}/tags/${tagId}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': getCsrfToken() }
        });
        
        // 2. Als Negativ markieren
        await fetch(`/api/tags/${tagId}/reject/${emailId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ source: 'auto_assign' })
        });
        
        showToast('Tag entfernt und Feedback gespeichert', 'success');
        location.reload();
    } catch (error) {
        console.error('Error:', error);
        showToast('Fehler', 'error');
    }
}
```

---

## ❌ Was NICHT implementiert wird (bewusste Entscheidung)

### 1. "Passt nicht" bei manuellem Tagging

**Grund:** Kontraintuitiv. User, die manuell taggen, wollen Tags **zuweisen**, nicht ablehnen. Ablehnung macht nur Sinn bei KI-Vorschlägen.

### 2. Automatische Rejection bei Tag-Removal

**Grund:** User entfernt Tags aus vielen Gründen (aufräumen, erledigt, etc.) - das ist KEINE Ablehnung. Nur **explizite** User-Aktionen (Buttons) als Negativ-Feedback.

### 3. Counter-basierte Alternative

**Grund:** Funktioniert nicht - berücksichtigt nicht die Ähnlichkeit zwischen Emails.

---

## 📊 Beispiel-Workflow

```
1. Tag "Rechnung" hat 50 positive Emails (echte Rechnungen)
   → learned_embedding = avg(50 Rechnungs-Embeddings)

2. KI schlägt "Rechnung" für Newsletter vor (wegen "PayPal" im Text)
   → User klickt ✗ "Passt nicht"
   → System: add_negative_example(tag="Rechnung", email=newsletter)
   → negative_embedding wird berechnet

3. Nächster PayPal Newsletter kommt
   → Positive Similarity zu "Rechnung": 72%
   → Negative Similarity: 85% (sehr ähnlich zum abgelehnten Newsletter)
   → 85% >= 80% SKIP-Threshold → Tag wird KOMPLETT übersprungen ✅

4. Echte PayPal Rechnung kommt
   → Positive Similarity zu "Rechnung": 88%
   → Negative Similarity: 45% (unähnlich zum Newsletter)
   → Keine Penalty
   → 88% → AUTO-ASSIGN ✅
```

---

## 📋 Implementierungs-Checkliste

### Phase 0: Vorbereitung
- [ ] **PATCH_PHASE_F2_QUEUE_FLAG_BUG.md** zuerst implementieren!

### Phase 1: Datenbank (30 Min)
- [ ] `02_models.py`: `EmailTag` um Felder erweitern
- [ ] `02_models.py`: `TagNegativeExample` Klasse hinzufügen
- [ ] Migration erstellen: `alembic revision --autogenerate -m "Add negative feedback"`
- [ ] Migration ausführen: `alembic upgrade head`

### Phase 2: Backend Core (2h)
- [ ] `tag_manager.py`: Konstanten hinzufügen
- [ ] `tag_manager.py`: `add_negative_example()` implementieren
- [ ] `tag_manager.py`: `remove_negative_example()` implementieren
- [ ] `tag_manager.py`: `update_negative_embedding()` implementieren
- [ ] `tag_manager.py`: `get_negative_similarity()` implementieren
- [ ] `tag_manager.py`: `calculate_negative_penalty()` implementieren

### Phase 3: Integration (1h)
- [ ] `tag_manager.py`: `suggest_tags_by_email_embedding()` erweitern
- [ ] SKIP-Threshold + Penalty-Logik einbauen
- [ ] Logging hinzufügen

### Phase 4: API (30 Min)
- [ ] `01_web_app.py`: POST `/api/tags/<id>/reject/<email_id>`
- [ ] `01_web_app.py`: DELETE `/api/tags/<id>/reject/<email_id>`

### Phase 5: UI (1h)
- [ ] `email_detail.html`: ✗ Button bei Suggestions
- [ ] `email_detail.html`: 👎 Button bei Auto-Assigned Tags
- [ ] JavaScript-Funktionen
- [ ] Toast-Notifications

### Phase 6: Testing (1h)
- [ ] Unit-Tests für Penalty-Berechnung
- [ ] Integration-Test: Newsletter vs. Rechnung
- [ ] UI-Test

**Gesamt: ~6 Stunden**

---

## 🔮 Zukünftige Erweiterungen (Phase 2+)

### 1. Ratio-basierte Gewichtung (bei vielen Negativen)

```python
# Wenn positive_count vs. negative_count unausgewogen:
if negative_count > positive_count * 2:
    # User ist wahrscheinlich verwirrt → Penalty reduzieren
    penalty = penalty * 0.5
    logger.warning(f"⚠️ Tag '{tag.name}': Viele Negative ({negative_count}) vs Positive ({positive_count})")
```

### 2. Confidence-Decay (ältere Beispiele weniger gewichten)

```python
# Ältere Negative verlieren an Gewicht
age_days = (datetime.now() - neg.created_at).days
decay_factor = max(0.5, 1.0 - (age_days / 365))  # Nach 1 Jahr: 50%
```

### 3. Bulk-Feedback ("Alle ähnlichen ablehnen")

```python
# Wenn User Newsletter ablehnt → alle ähnlichen auch ablehnen
@app.route("/api/tags/<tag_id>/reject/<email_id>/similar", methods=["POST"])
def reject_similar(tag_id, email_id):
    similar = find_similar_emails(email_id, threshold=0.80)
    for sim_id in similar:
        add_negative_example(tag_id, sim_id, user_id)
```

---

## 🎯 Erwartete Verbesserung

| Metrik | Vorher | Nachher (realistisch) |
|--------|--------|----------------------|
| False Positives bei Suggestions | ~20% | ~8-10% |
| User-Korrektur-Aufwand | Hoch (immer wieder gleiche Fehler) | Niedrig (einmal ablehnen) |
| Learning-Geschwindigkeit | Nur durch Positive | Doppelt (Positive + Negative) |

**Hinweis:** Voller Effekt erst nach 2-3 Wochen Nutzung, wenn User Feedback gegeben haben.
