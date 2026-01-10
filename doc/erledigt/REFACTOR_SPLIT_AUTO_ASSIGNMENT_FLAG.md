# 🔧 REFACTOR: Auto-Assignment Flag von Queue-Flag trennen

**Datum:** 2026-01-06  
**Priorität:** 🔥 HIGH - Blockiert Phase F.3 Testing  
**Status:** 📋 Planung

## Problem

Aktuell steuert **ein einziges Flag** zwei völlig unterschiedliche Features:

```python
if similarity >= AUTO_ASSIGN_THRESHOLD:
    if user.enable_tag_suggestion_queue:  # ← FALSCHES FLAG!
        TagManager.assign_tag(...)
```

### Feature-Confusion:

| Feature | Was es macht | Aktuelles Flag |
|---------|-------------|----------------|
| **Tag Suggestion Queue** | KI schlägt NEUE (nicht-existierende) Tags vor → Queue → User bestätigt | `enable_tag_suggestion_queue` ✅ |
| **Auto-Assignment** | KI weist BESTEHENDE Tags automatisch zu bei ≥80% Similarity | `enable_tag_suggestion_queue` ❌ |

### Warum ist das falsch?

**Diese Features sind semantisch unabhängig!**

Ein User könnte wollen:

1. **Queue AUS + Auto-Assignment AN**  
   → "Keine neuen Tags vorschlagen, aber bestehende automatisch zuweisen"  
   → Szenario: User hat perfekte Tag-Struktur, will nur Auto-Tagging

2. **Queue AN + Auto-Assignment AUS**  
   → "Neue Tags vorschlagen, aber ich weise immer manuell zu"  
   → Szenario: User will volle Kontrolle über Zuweisungen

3. **Beide AN**  
   → Volle KI-Automation

4. **Beide AUS**  
   → Nur manuelle Tag-Vorschläge in Email-Detail

**Aktuell sind nur Szenario 3 und 4 möglich!**

## Architektur-Ziel

```
┌─────────────────────────────────────────┐
│ User Settings                           │
├─────────────────────────────────────────┤
│ ☐ enable_tag_suggestion_queue           │ ← Queue für NEUE Tags
│ ☐ enable_auto_assignment                │ ← Auto-Zuweisung BESTEHENDER Tags
└─────────────────────────────────────────┘

Flow 1: Neue Tags (Queue)
━━━━━━━━━━━━━━━━━━━━━━━━
KI findet "Projekt X" (Tag existiert NICHT)
↓
if enable_tag_suggestion_queue == True:
    → TagSuggestionQueue speichern
else:
    → Ignorieren (kein Vorschlag)

Flow 2: Bestehende Tags (Auto-Assignment)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KI findet "Arbeit" (Tag existiert, 85% Match)
↓
if enable_auto_assignment == True:
    if similarity >= AUTO_ASSIGN_THRESHOLD (80%):
        → Automatisch zuweisen
    else:
        → In Vorschlag-Box zeigen
else:
    → Immer nur in Vorschlag-Box zeigen
```

## Implementation Plan

### Phase 1: Database Schema ✅ (Ready to implement)

**Migration:** `add_enable_auto_assignment_flag.py`

```python
def upgrade():
    op.add_column('users', 
        sa.Column('enable_auto_assignment', sa.Boolean(), 
                  nullable=False, server_default='0'))

def downgrade():
    op.drop_column('users', 'enable_auto_assignment')
```

**Default:** `False` (Safety first - keine automatischen Zuweisungen ohne Opt-in)

### Phase 2: Model Update

**File:** `src/02_models.py`

```python
class User(Base):
    # ... existing fields ...
    enable_tag_suggestion_queue = Column(Boolean, nullable=False, default=False)  # Existing
    enable_auto_assignment = Column(Boolean, nullable=False, default=False)       # NEW
```

### Phase 3: Backend Logic Update

**File:** `src/12_processing.py` ⚠️ **WICHTIG: NICHT tag_manager.py!**

Die Assignment-Logik ist in der Processing-Pipeline, NICHT in tag_manager.py!

**Location:** Zeile ~600 in `process_email()`

**VORHER:**
```python
for tag, similarity in tag_suggestions:
    if similarity >= AUTO_ASSIGN_THRESHOLD:
        # PATCH 2026-01-06: Respektiere enable_tag_suggestion_queue Flag
        # Siehe: doc/offen/PATCH_PHASE_F2_QUEUE_FLAG_BUG.md
        if user.enable_tag_suggestion_queue:  # ← FALSCHES FLAG!
            # Auto-Assign für sehr sichere Matches (>= 80%)
            try:
                tag_manager_mod.TagManager.assign_tag(
                    db=session,
                    email_id=processed_email.id,
                    tag_id=tag.id,
                    user_id=user.id
                )
```

**NACHHER:**
```python
for tag, similarity in tag_suggestions:
    if similarity >= AUTO_ASSIGN_THRESHOLD:
        if user.enable_auto_assignment:  # ← RICHTIGES FLAG!
            # Auto-Assign für sehr sichere Matches (>= 80%)
            try:
                tag_manager_mod.TagManager.assign_tag(
                    db=session,
                    email_id=processed_email.id,
                    tag_id=tag.id,
                    user_id=user.id
                )
                auto_assigned_count += 1
                logger.info(
                    f"⚡ AUTO-ASSIGNED Tag '{tag.name}' ({similarity:.0%} similarity) "
                    f"to email {processed_email.id}"
                )
```

**Zusätzlich:** Patch-Kommentar entfernen (Zeile 598-599), da Problem jetzt gelöst ist.

### Phase 4: API Endpoints

**File:** `src/01_web_app.py`

#### 4.1 Settings GET Endpoint

```python
@app.route("/api/tag-suggestions/settings", methods=["GET"])
def api_get_tag_suggestion_settings():
    # ... existing code ...
    return jsonify({
        "enable_tag_suggestion_queue": user.enable_tag_suggestion_queue,  # Existing
        "enable_auto_assignment": user.enable_auto_assignment              # NEW
    })
```

#### 4.2 Settings POST Endpoint

```python
@app.route("/api/tag-suggestions/settings", methods=["POST"])
def api_update_tag_suggestion_settings():
    data = request.json
    
    # Update queue flag (existing)
    if "enable_tag_suggestion_queue" in data:
        user.enable_tag_suggestion_queue = data["enable_tag_suggestion_queue"]
    
    # Update auto-assignment flag (NEW)
    if "enable_auto_assignment" in data:
        user.enable_auto_assignment = data["enable_auto_assignment"]
    
    db.commit()
```

### Phase 5: UI Updates

#### 5.1 Settings Modal - Tag Suggestions Page

**File:** `templates/tag_suggestions.html`

```html
<div class="modal-body">
    <!-- Existing: Queue Toggle -->
    <div class="form-check form-switch mb-3">
        <input class="form-check-input" type="checkbox" id="enableQueueToggle" 
               {% if queue_enabled %}checked{% endif %}>
        <label class="form-check-label" for="enableQueueToggle">
            💡 Tag-Vorschläge für neue Tags aktivieren (Queue)
        </label>
        <small class="text-muted d-block mt-1">
            KI kann neue Tag-Namen vorschlagen, die Sie bestätigen müssen.
        </small>
    </div>
    
    <!-- NEW: Auto-Assignment Toggle -->
    <div class="form-check form-switch">
        <input class="form-check-input" type="checkbox" id="enableAutoAssignToggle"
               {% if auto_assignment_enabled %}checked{% endif %}>
        <label class="form-check-label" for="enableAutoAssignToggle">
            ⚡ Automatische Tag-Zuweisung aktivieren
        </label>
        <small class="text-muted d-block mt-1">
            Bestehende Tags werden bei ≥80% Ähnlichkeit automatisch zugewiesen.
        </small>
    </div>
    
    <div class="alert alert-warning mt-3 mb-0">
        ⚠️ <strong>Empfehlung:</strong> Teste Auto-Assignment erst mit wenigen Emails, 
        bevor du es permanent aktivierst!
    </div>
</div>
```

#### 5.2 JavaScript Update

```javascript
async function saveSettings() {
    const queueEnabled = document.getElementById('enableQueueToggle').checked;
    const autoAssignEnabled = document.getElementById('enableAutoAssignToggle').checked;  // NEW
    
    const response = await fetch('/api/tag-suggestions/settings', {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ 
            enable_tag_suggestion_queue: queueEnabled,
            enable_auto_assignment: autoAssignEnabled  // NEW
        })
    });
    
    if (response.ok) {
        alert('✅ Einstellungen gespeichert!');
        location.reload();
    }
}
```

#### 5.3 Einstellungen-Seite (Settings Page)

**File:** `templates/settings.html`

Falls es eine zentrale Settings-Seite gibt, dort ebenfalls beide Toggles anbieten.

### Phase 6: Auto-Assigned Tags Handling

**Zwei Varianten zur Auswahl:**

#### Variante A: Checkbox im Remove-Dialog (Empfehlung)

```python
# In 02_models.py
class EmailTagAssignment(Base):
    # ... existing fields ...
    auto_assigned = Column(Boolean, nullable=False, default=False)  # NEW
    assigned_at = Column(DateTime, default=datetime.utcnow)
```

**UI bei Tag-Entfernung:**
```html
<div class="modal-body">
    Tag "<strong>Arbeit</strong>" entfernen?
    
    <!-- NEW: Nur bei auto_assigned=True zeigen -->
    <div class="form-check mt-3">
        <input class="form-check-input" type="checkbox" id="addNegativeExample">
        <label class="form-check-label" for="addNegativeExample">
            🚫 Als negatives Beispiel speichern (nicht mehr automatisch zuweisen)
        </label>
    </div>
</div>
```

**JavaScript:**
```javascript
async function removeTag(emailId, tagId, isAutoAssigned) {
    if (isAutoAssigned) {
        // Show modal with checkbox
        const addNegative = document.getElementById('addNegativeExample').checked;
        
        await fetch(`/api/emails/${emailId}/tags/${tagId}`, { method: 'DELETE' });
        
        if (addNegative) {
            await fetch(`/api/emails/${emailId}/tags/${tagId}/reject`, { method: 'POST' });
        }
    } else {
        // Normal remove
        if (confirm('Tag entfernen?')) {
            await fetch(`/api/emails/${emailId}/tags/${tagId}`, { method: 'DELETE' });
        }
    }
}
```

#### Variante B: Spezielle Box für Auto-Assignments

```html
<!-- Separate Box über den zugewiesenen Tags -->
<div id="autoAssignedTagsBox" class="alert alert-warning py-2 px-3">
    <small class="fw-bold">⚡ Automatisch zugewiesen:</small>
    <div class="mt-1">
        <span class="badge bg-warning text-dark">
            Arbeit (85%)
            <button class="btn-close btn-close-dark" data-add-negative="true"></button>
        </span>
    </div>
    <small class="text-muted d-block mt-1">
        Klick auf × entfernt Tag und speichert als negatives Beispiel.
    </small>
</div>
```

**Empfehlung:** **Variante A** - Weniger UI-Clutter, mehr Flexibilität

### Phase 7: Testing

#### 7.1 Unit Tests (Optional)

```python
# tests/test_auto_assignment_flag.py

def test_auto_assignment_disabled_by_default():
    user = create_test_user()
    assert user.enable_auto_assignment == False

def test_high_similarity_without_auto_assignment():
    user.enable_auto_assignment = False
    suggestions = suggest_tags_by_email_embedding(...)
    # Tags sollten in Vorschlag-Box sein, NICHT zugewiesen
    
def test_high_similarity_with_auto_assignment():
    user.enable_auto_assignment = True
    assign_tags_for_email(...)  # Simuliert Processing
    # Tags mit ≥80% sollten automatisch zugewiesen sein
```

#### 7.2 Manual Testing Checklist

**Setup:**
```sql
-- User-Flags prüfen
SELECT id, email, enable_tag_suggestion_queue, enable_auto_assignment FROM users;

-- Test-Tags erstellen
INSERT INTO email_tags (name, color, user_id, description) 
VALUES ('TestAuto', '#FF0000', 1, 'Test für Auto-Assignment');
```

**Test-Szenarien:**

| Queue | Auto | Erwartetes Verhalten |
|-------|------|---------------------|
| OFF | OFF | Nur manuelle Vorschläge in Email-Detail |
| OFF | ON | Bestehende Tags mit ≥80% werden automatisch zugewiesen, keine Queue |
| ON | OFF | Queue für neue Tags, bestehende nur als Vorschlag |
| ON | ON | Queue für neue Tags + Auto-Assignment für bestehende |

**Validierung:**
```sql
-- Auto-assigned Tags prüfen
SELECT e.subject, t.name, eta.auto_assigned, eta.assigned_at
FROM email_tag_assignments eta
JOIN processed_emails e ON e.id = eta.email_id
JOIN email_tags t ON t.id = eta.tag_id
WHERE eta.auto_assigned = 1
ORDER BY eta.assigned_at DESC;
```

## Migration Strategy

### Rollout-Plan

1. **Deploy Migration** → Neue Spalte `enable_auto_assignment` mit `default=False`
2. **Deploy Code** → Backend logic verwendet neues Flag
3. **Deploy UI** → Settings-Modal zeigt beide Toggles
4. **User Communication:**
   ```
   ⚠️ Neues Feature: Auto-Assignment
   
   Ab sofort kannst du steuern, ob Tags automatisch zugewiesen werden sollen.
   Gehe zu ⚙️ Einstellungen → Tag-Vorschläge und aktiviere "⚡ Automatische Tag-Zuweisung".
   
   Standardmäßig ist es AUS (wie bisher).
   ```

### Backward Compatibility

✅ **Keine Breaking Changes:**
- Bestehende User: `enable_auto_assignment=False` (Default)
- Bestehende Logik funktioniert weiter
- UI zeigt neue Option, aber ändert nichts an Verhalten bis User aktiviert

### Rollback-Plan

Falls Probleme auftreten:
```sql
-- Auto-Assignment für alle User deaktivieren
UPDATE users SET enable_auto_assignment = 0;
```

Code-Rollback:
```bash
git revert <commit-hash>
alembic downgrade -1
```

## Dependencies

### Blocked by:
- Keine (kann sofort implementiert werden)

### Blocks:
- ✅ Phase F.3 Testing (Negative Feedback)
- ✅ Auto-Assignment User-Testing
- ✅ Queue-Only Scenarios

## Success Criteria

✅ Migration läuft ohne Fehler  
✅ Beide Flags sind in UI sichtbar und togglebar  
✅ Auto-Assignment funktioniert nur wenn Flag=True  
✅ Queue funktioniert unabhängig von Auto-Assignment  
✅ Alle 4 Kombinationen (OFF/OFF, OFF/ON, ON/OFF, ON/ON) funktionieren  
✅ Negative Feedback funktioniert für auto-assigned Tags  
✅ Logging zeigt deutlich "⚡ Auto-assigned" vs "💡 Suggested"  

## Files to Change

### Database
- [ ] Migration: `migrations/versions/add_enable_auto_assignment_flag.py`

### Backend
- [ ] `src/02_models.py` - User model + EmailTagAssignment.auto_assigned
- [ ] `src/12_processing.py` - Auto-Assignment Logic (Flag-Check)
- [ ] `src/services/tag_manager.py` - assign_tag() mit auto_assigned parameter

### API
- [ ] `src/01_web_app.py` - GET/POST /api/tag-suggestions/settings

### Frontend
- [ ] `templates/tag_suggestions.html` - Settings modal
- [ ] `templates/email_detail.html` - Remove-Tag logic für auto-assigned
- [ ] `templates/settings.html` (falls vorhanden)

### Documentation
- [ ] `CHANGELOG_AUTO_ASSIGNMENT_FLAG.md`
- [ ] Update `FEATURE_NEGATIVE_TAG_FEEDBACK_v2.md`

## Estimated Effort

- **Migration + Model:** 15 min
- **Backend Logic:** 30 min
- **API Endpoints:** 20 min
- **UI Changes:** 45 min
- **Testing:** 30 min
- **Documentation:** 20 min

**Total:** ~2.5 hours

## Recommendation

**Soll ich direkt implementieren?**

✅ Ja, weil:
- Blockiert aktuell Phase F.3 Testing
- Saubere Architektur ist wichtiger als schnelle Features
- Refactoring ist überschaubar (~160 LOC)
- Zero Breaking Changes

---

**Status:** Warte auf Freigabe zur Implementation
