# DESIGN: Tag Suggestion Queue

**Feature:** KI-Tag-Vorschläge in Warteschlange mit User-Approval  
**Phase:** Nach Sofort-Fix (PATCH_DISABLE_TAG_AUTO_CREATION.md)  
**Aufwand:** ~4-6 Stunden  
**Priorität:** Medium (Nice-to-have, verbessert UX)

---

## 🎯 Ziel

Statt Tags automatisch zu erstellen, sammelt das System KI-Vorschläge in einer Queue. Der User entscheidet selbst, welche Tags er annehmen, ablehnen oder zu existierenden Tags mergen möchte.

**Kernprinzip:** Nur der User darf Tags erstellen. Das System darf nur vorschlagen.

---

## 📐 Architektur

### Datenmodell

**Neue Tabelle:** `tag_suggestion_queue`

```python
# src/02_models.py

class TagSuggestionQueue(Base):
    """Warteschlange für KI-vorgeschlagene Tags"""
    __tablename__ = "tag_suggestion_queue"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Was wurde vorgeschlagen
    suggested_name = Column(String(50), nullable=False)
    
    # Woher kam der Vorschlag
    source_email_id = Column(Integer, ForeignKey("processed_emails.id", ondelete="SET NULL"), nullable=True)
    
    # Wann
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    
    # Status
    status = Column(String(20), default="pending")  # pending, approved, rejected, merged
    
    # Falls zu existierendem Tag gemappt
    merged_into_tag_id = Column(Integer, ForeignKey("email_tags.id", ondelete="SET NULL"), nullable=True)
    
    # Wie oft wurde dieser Name vorgeschlagen (für Priorisierung)
    suggestion_count = Column(Integer, default=1)
    
    # Relationships
    user = relationship("User", backref="tag_suggestions")
    source_email = relationship("ProcessedEmail", backref="tag_suggestions")
    merged_into_tag = relationship("EmailTag", backref="merged_suggestions")
    
    # Unique constraint: Nur ein pending Vorschlag pro Name pro User
    __table_args__ = (
        UniqueConstraint('user_id', 'suggested_name', 'status', 
                        name='uq_user_suggestion_status'),
    )
```

### User-Setting

**Erweiterung:** `users` Tabelle oder separate Settings-Tabelle

```python
# Option A: In User-Model
class User(Base):
    # ... existing fields ...
    
    # Tag-Queue Feature (Default: AUS)
    enable_tag_suggestion_queue = Column(Boolean, default=False)
```

```sql
-- Migration
ALTER TABLE users ADD COLUMN enable_tag_suggestion_queue BOOLEAN DEFAULT FALSE;
```

---

## 🔄 Workflow

### 1. Email-Processing (Backend)

```
┌─────────────────────────────────────────────────────────────┐
│  process_pending_raw_emails()                               │
│                                                             │
│  AI analysiert Email → suggested_tags: ["Rechnung", "Bank"] │
│                                                             │
│  FOR EACH tag_name:                                         │
│    │                                                        │
│    ├─ Tag existiert?                                        │
│    │   └─ JA → assign_tag() ✅                              │
│    │                                                        │
│    └─ Tag existiert NICHT?                                  │
│        │                                                    │
│        ├─ User hat Queue aktiviert?                         │
│        │   └─ JA → add_to_suggestion_queue() 📥            │
│        │                                                    │
│        └─ Queue deaktiviert?                                │
│            └─ Ignorieren (nur loggen) 💡                    │
└─────────────────────────────────────────────────────────────┘
```

### 2. Queue-Management (Backend)

```python
# src/services/tag_suggestion_service.py

class TagSuggestionService:
    
    @staticmethod
    def add_to_queue(
        db: Session, 
        user_id: int, 
        suggested_name: str, 
        source_email_id: int
    ) -> TagSuggestionQueue:
        """Fügt Vorschlag zur Queue hinzu oder erhöht Counter"""
        
        # Prüfe ob bereits pending
        existing = db.query(TagSuggestionQueue).filter(
            TagSuggestionQueue.user_id == user_id,
            TagSuggestionQueue.suggested_name == suggested_name,
            TagSuggestionQueue.status == "pending"
        ).first()
        
        if existing:
            # Nur Counter erhöhen
            existing.suggestion_count += 1
            db.commit()
            return existing
        
        # Neuen Vorschlag erstellen
        suggestion = TagSuggestionQueue(
            user_id=user_id,
            suggested_name=suggested_name,
            source_email_id=source_email_id,
            status="pending",
            suggestion_count=1
        )
        db.add(suggestion)
        db.commit()
        return suggestion
    
    @staticmethod
    def get_pending_suggestions(db: Session, user_id: int) -> List[TagSuggestionQueue]:
        """Holt alle pending Vorschläge, sortiert nach Häufigkeit"""
        return (
            db.query(TagSuggestionQueue)
            .filter(
                TagSuggestionQueue.user_id == user_id,
                TagSuggestionQueue.status == "pending"
            )
            .order_by(TagSuggestionQueue.suggestion_count.desc())
            .all()
        )
    
    @staticmethod
    def approve_suggestion(
        db: Session, 
        suggestion_id: int, 
        user_id: int,
        color: str = "#3B82F6"
    ) -> EmailTag:
        """Genehmigt Vorschlag → Erstellt Tag"""
        suggestion = db.query(TagSuggestionQueue).filter(
            TagSuggestionQueue.id == suggestion_id,
            TagSuggestionQueue.user_id == user_id
        ).first()
        
        if not suggestion:
            raise ValueError("Suggestion not found")
        
        # Tag erstellen
        tag = TagManager.create_tag(
            db=db,
            user_id=user_id,
            name=suggestion.suggested_name,
            color=color
        )
        
        # Status aktualisieren
        suggestion.status = "approved"
        suggestion.merged_into_tag_id = tag.id
        db.commit()
        
        return tag
    
    @staticmethod
    def reject_suggestion(db: Session, suggestion_id: int, user_id: int) -> bool:
        """Lehnt Vorschlag ab"""
        suggestion = db.query(TagSuggestionQueue).filter(
            TagSuggestionQueue.id == suggestion_id,
            TagSuggestionQueue.user_id == user_id
        ).first()
        
        if not suggestion:
            return False
        
        suggestion.status = "rejected"
        db.commit()
        return True
    
    @staticmethod
    def merge_suggestion(
        db: Session, 
        suggestion_id: int, 
        target_tag_id: int,
        user_id: int
    ) -> bool:
        """Merged Vorschlag zu existierendem Tag"""
        suggestion = db.query(TagSuggestionQueue).filter(
            TagSuggestionQueue.id == suggestion_id,
            TagSuggestionQueue.user_id == user_id
        ).first()
        
        if not suggestion:
            return False
        
        # Alle Emails mit diesem Vorschlag zum Ziel-Tag zuweisen
        # (Optional: Könnte auch nur die source_email taggen)
        
        suggestion.status = "merged"
        suggestion.merged_into_tag_id = target_tag_id
        db.commit()
        return True
```

---

## 🖥️ UI Design

### Navigation

```
┌─────────────────────────────────────────────────────────────┐
│  📧 Emails  │  🏷️ Tags  │  ⚡ Auto-Rules  │  💡 Vorschläge (5) │
│                                              ↑               │
│                                          Badge mit Count     │
└─────────────────────────────────────────────────────────────┘
```

### Seite: `/tag-suggestions`

```
┌─────────────────────────────────────────────────────────────┐
│  💡 Tag-Vorschläge                           [⚙️ Einstellungen]│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ☐  "Rechnung"              12x vorgeschlagen        │   │
│  │     📧 Letzte Email: "RE: Ihre Rechnung #4521"      │   │
│  │     [✅ Annehmen] [🔀 Zu "Finanzen" mergen ▼] [❌]   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ☐  "Newsletter"            8x vorgeschlagen         │   │
│  │     📧 Letzte Email: "Weekly Digest - Tech News"    │   │
│  │     [✅ Annehmen] [🔀 Zu "News" mergen ▼] [❌]       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ☐  "Tracking"              3x vorgeschlagen         │   │
│  │     📧 Letzte Email: "Ihre Sendung ist unterwegs"   │   │
│  │     [✅ Annehmen] [🔀 Zu "..." mergen ▼] [❌]        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ────────────────────────────────────────────────────────  │
│  Ausgewählt: 0  │  [Alle annehmen] [Alle ablehnen]         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Settings-Modal (⚙️)

```
┌─────────────────────────────────────────────────────────────┐
│  ⚙️ Tag-Vorschläge Einstellungen                      [X]   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [ ] KI-Tag-Vorschläge aktivieren                          │
│      Wenn aktiviert, sammelt das System KI-vorgeschlagene  │
│      Tags zur manuellen Überprüfung.                       │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  ⚠️ Hinweis: Tags werden NIE automatisch erstellt.          │
│     Nur Sie können neue Tags anlegen.                       │
│                                                             │
│                                        [💾 Speichern]       │
└─────────────────────────────────────────────────────────────┘
```

---

## 📡 API Endpoints

```python
# src/01_web_app.py

# === Tag Suggestions Queue ===

@app.route("/tag-suggestions")
@login_required
def tag_suggestions_page():
    """UI: Tag-Vorschläge Seite"""
    suggestions = TagSuggestionService.get_pending_suggestions(db, current_user.id)
    user_tags = TagManager.get_user_tags(db, current_user.id)
    return render_template(
        "tag_suggestions.html",
        suggestions=suggestions,
        user_tags=user_tags
    )

@app.route("/api/tag-suggestions", methods=["GET"])
@login_required
def api_get_tag_suggestions():
    """API: Pending Vorschläge abrufen"""
    suggestions = TagSuggestionService.get_pending_suggestions(db, current_user.id)
    return jsonify([{
        "id": s.id,
        "name": s.suggested_name,
        "count": s.suggestion_count,
        "source_email_subject": s.source_email.encrypted_subject if s.source_email else None,
        "created_at": s.created_at.isoformat()
    } for s in suggestions])

@app.route("/api/tag-suggestions/<int:id>/approve", methods=["POST"])
@login_required
def api_approve_suggestion(id):
    """API: Vorschlag annehmen → Tag erstellen"""
    data = request.get_json() or {}
    color = data.get("color", "#3B82F6")
    
    try:
        tag = TagSuggestionService.approve_suggestion(db, id, current_user.id, color)
        return jsonify({"success": True, "tag_id": tag.id, "tag_name": tag.name})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

@app.route("/api/tag-suggestions/<int:id>/reject", methods=["POST"])
@login_required
def api_reject_suggestion(id):
    """API: Vorschlag ablehnen"""
    success = TagSuggestionService.reject_suggestion(db, id, current_user.id)
    return jsonify({"success": success})

@app.route("/api/tag-suggestions/<int:id>/merge", methods=["POST"])
@login_required
def api_merge_suggestion(id):
    """API: Vorschlag zu existierendem Tag mergen"""
    data = request.get_json()
    target_tag_id = data.get("target_tag_id")
    
    if not target_tag_id:
        return jsonify({"error": "target_tag_id required"}), 400
    
    success = TagSuggestionService.merge_suggestion(db, id, target_tag_id, current_user.id)
    return jsonify({"success": success})

@app.route("/api/tag-suggestions/settings", methods=["GET", "POST"])
@login_required
def api_tag_suggestion_settings():
    """API: Queue-Einstellungen lesen/setzen"""
    if request.method == "GET":
        return jsonify({
            "enabled": current_user.enable_tag_suggestion_queue
        })
    
    data = request.get_json()
    current_user.enable_tag_suggestion_queue = data.get("enabled", False)
    db.commit()
    return jsonify({"success": True})
```

---

## 📁 Neue Dateien

```
src/
├── services/
│   └── tag_suggestion_service.py    # NEU: Queue-Service
├── 02_models.py                     # EDIT: TagSuggestionQueue Model
├── 01_web_app.py                    # EDIT: API Endpoints
├── 12_processing.py                 # EDIT: Queue-Integration

templates/
└── tag_suggestions.html             # NEU: UI-Template

migrations/versions/
└── xxx_add_tag_suggestion_queue.py  # NEU: Alembic Migration
```

---

## 🚀 Implementierungs-Reihenfolge

| Phase | Task | Aufwand |
|-------|------|---------|
| 1 | Migration + Model | 30 min |
| 2 | TagSuggestionService | 1h |
| 3 | processing.py Integration | 30 min |
| 4 | API Endpoints | 1h |
| 5 | UI Template | 2h |
| 6 | Settings in User-Preferences | 30 min |
| 7 | Navigation Badge | 15 min |
| **Total** | | **~6h** |

---

## ✅ Akzeptanzkriterien

- [ ] Neue Tags werden NIEMALS automatisch erstellt
- [ ] User kann Queue in Settings aktivieren/deaktivieren
- [ ] KI-Vorschläge erscheinen in Queue mit Häufigkeits-Counter
- [ ] User kann Vorschläge: annehmen, ablehnen, mergen
- [ ] Navigation zeigt Badge mit Anzahl pending Vorschläge
- [ ] Batch-Aktionen funktionieren (alle annehmen/ablehnen)
- [ ] Merge-Dropdown zeigt nur existierende User-Tags
