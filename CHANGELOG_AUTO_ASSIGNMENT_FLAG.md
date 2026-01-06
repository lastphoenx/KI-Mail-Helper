# 🔧 Refactoring: Auto-Assignment Flag von Queue-Flag getrennt

**Datum:** 2026-01-06  
**Status:** ✅ Implementiert

## Problem

Ein einzelnes Flag (`enable_tag_suggestion_queue`) steuerte fälschlicherweise **zwei verschiedene Features**:

1. **Tag Suggestion Queue** - KI schlägt NEUE (nicht-existierende) Tags vor
2. **Auto-Assignment** - KI weist BESTEHENDE Tags automatisch zu (≥80%)

Dies verhinderte sinnvolle Kombinationen wie:
- Queue AUS + Auto-Assignment AN
- Queue AN + Auto-Assignment AUS

## Lösung

**Zwei separate Flags:**
```python
enable_tag_suggestion_queue  # Queue für NEUE Tags
enable_auto_assignment       # Auto-Zuweisung BESTEHENDER Tags
```

## Changes

### Database Schema

**Migration:** `13710d93ee9c_add_enable_auto_assignment_flag_to_users.py`

1. **users.enable_auto_assignment** (Boolean, default=False)
2. **email_tag_assignments.auto_assigned** (Boolean, default=False)

### Backend

**src/02_models.py:**
- User: `enable_auto_assignment` Column hinzugefügt
- EmailTagAssignment: `auto_assigned` Column hinzugefügt

**src/12_processing.py (Zeile ~600):**
```python
# VORHER:
if user.enable_tag_suggestion_queue:  # ← FALSCH!
    TagManager.assign_tag(...)

# NACHHER:
if user.enable_auto_assignment:  # ← RICHTIG!
    TagManager.assign_tag(..., auto_assigned=True)
```

**src/services/tag_manager.py:**
- `assign_tag()` Parameter erweitert: `auto_assigned: bool = False`
- Assignment-Objekt speichert Flag

### API

**src/01_web_app.py:**

`GET/POST /api/tag-suggestions/settings`:
```json
{
  "enable_tag_suggestion_queue": true,
  "enable_auto_assignment": false
}
```

### UI

**templates/tag_suggestions.html:**
- Settings-Modal: Zwei separate Toggles
- JavaScript: Beide Flags beim Speichern senden

**templates/tag_suggestions.html (Zeile ~35-55):**
```html
<!-- Queue Toggle -->
💡 Tag-Vorschläge für neue Tags aktivieren (Queue)

<!-- Auto-Assignment Toggle (NEW) -->
⚡ Automatische Tag-Zuweisung aktivieren
```

## Feature Matrix

| Queue | Auto | Verhalten |
|-------|------|-----------|
| OFF | OFF | Nur manuelle Vorschläge in Email-Detail |
| OFF | ON | Bestehende Tags mit ≥80% automatisch zugewiesen |
| ON | OFF | Queue für neue Tags, bestehende nur Vorschlag |
| ON | ON | Queue für neue + Auto-Assignment für bestehende |

## Migration

```bash
alembic upgrade head
```

**Backward Compatible:** Beide Flags defaulten auf `False` (wie bisher).

## Testing

```sql
-- Check User Flags
SELECT id, email, enable_tag_suggestion_queue, enable_auto_assignment 
FROM users;

-- Check Auto-Assigned Tags
SELECT e.subject, t.name, eta.auto_assigned
FROM email_tag_assignments eta
JOIN processed_emails e ON e.id = eta.email_id
JOIN email_tags t ON t.id = eta.tag_id
WHERE eta.auto_assigned = 1;
```

## Logging

**Neue Log-Messages:**
```
⚡ AUTO-ASSIGNED Tag 'Arbeit' (85% similarity) to email 123
💡 SUGGEST: Tag 'Projekt' (82%) - Auto-Assignment disabled
```

## Files Changed

- ✅ migrations/versions/13710d93ee9c_*.py
- ✅ src/02_models.py
- ✅ src/12_processing.py
- ✅ src/services/tag_manager.py
- ✅ src/01_web_app.py
- ✅ templates/tag_suggestions.html

**LOC:** ~150 (Migration + Backend + UI)

## Benefits

✅ Saubere Architektur - Ein Flag = Ein Feature  
✅ Alle 4 Kombinationen möglich  
✅ Basis für Negative Feedback (Auto-Assignment Tracking)  
✅ Zero Breaking Changes  
✅ User hat volle Kontrolle

---

**Implementiert gemäß:** `doc/offen/REFACTOR_SPLIT_AUTO_ASSIGNMENT_FLAG.md`
