# Phase 1: Bulk Email Operations

**Status:** 🔲 Offen  
**Priorität:** 🟡 Mittel  
**Aufwand:** 15-20h  
**Erstellt:** 05.01.2026  

---

## 🎯 Ziel

Ermöglicht Batch-Aktionen für mehrere Emails gleichzeitig (Archive, Delete, Move, Flag, Read).

---

## 📋 Anforderungen

### 1. Multi-Select UI

- [ ] Checkboxen für jede Email in `/liste`
- [ ] "Select All" / "Deselect All" Toggle im Header
- [ ] Visuelle Hervorhebung ausgewählter Rows
- [ ] Counter: "X Emails ausgewählt"

### 2. Bulk-Action Toolbar

- [ ] Erscheint wenn mind. 1 Email ausgewählt
- [ ] Sticky-Position (bleibt sichtbar beim Scrollen)
- [ ] Aktionen-Dropdown:
  - Archive → Move zu Archive-Folder
  - Spam → Move zu Junk-Folder  
  - Löschen → Move zu Trash
  - Als gelesen markieren → +\Seen Flag
  - Als ungelesen markieren → -\Seen Flag
  - Flaggen → +\Flagged

### 3. Confirmation Dialogs

| Aktion | Bestätigung | Grund |
|--------|-------------|-------|
| Archive | Optional | Nicht destruktiv |
| Spam | Empfohlen | User kann Fehler machen |
| Löschen | **Pflicht** | Destruktiv |
| Read/Flag | Keine | Reversibel |

### 4. Progress & Feedback

- [ ] Progress-Bar während Ausführung
- [ ] Live-Counter: "3/10 verarbeitet..."
- [ ] Erfolgs-/Fehler-Feedback: "9/10 erfolgreich, 1 Fehler"
- [ ] Detail-Ansicht bei Fehlern (welche Email, warum)

### 5. Error Handling

- [ ] Partial Failure: Weitermachen bei einzelnen Fehlern
- [ ] Retry-Logic: 3 Versuche mit Exponential Backoff
- [ ] Circuit Breaker: Abbruch bei >50% Fehlerrate

---

## 🏗️ Architektur

### Frontend (JavaScript)

```javascript
// static/js/bulk_actions.js

class SelectionManager {
    selectedIds = new Set();
    
    toggle(emailId) { ... }
    selectAll() { ... }
    deselectAll() { ... }
    getSelected() { return Array.from(this.selectedIds); }
}

class BulkToolbar {
    show() { ... }
    hide() { ... }
    updateCounter(count) { ... }
}

async function executeBulkAction(action, emailIds) {
    const response = await fetch(`/api/bulk/${action}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ email_ids: emailIds })
    });
    return response.json();
}
```

### Backend (Python)

```python
# src/bulk_operations_handler.py

class BulkOperationsHandler:
    def __init__(self, db_session, user_id, master_key):
        self.db = db_session
        self.user_id = user_id
        self.master_key = master_key
    
    def execute(self, action: str, email_ids: List[int]) -> BulkResult:
        results = []
        for email_id in email_ids:
            try:
                result = self._execute_single(action, email_id)
                results.append(result)
            except Exception as e:
                results.append({"id": email_id, "success": False, "error": str(e)})
        
        return BulkResult(results)
    
    def _execute_single(self, action: str, email_id: int) -> dict:
        # IMAP-Operation durchführen
        # DB aktualisieren
        pass
```

### API Endpoints

```python
# src/01_web_app.py

@app.route("/api/bulk/<action>", methods=["POST"])
@login_required
def bulk_action(action: str):
    """Bulk-Aktion für mehrere Emails."""
    data = request.get_json()
    email_ids = data.get("email_ids", [])
    
    # Validierung
    if len(email_ids) > 1000:
        return jsonify({"error": "Max 1000 Emails pro Request"}), 400
    
    handler = BulkOperationsHandler(db, current_user.id, session["master_key"])
    result = handler.execute(action, email_ids)
    
    return jsonify(result.to_dict())
```

---

## 📁 Dateien

| Datei | Änderungen |
|-------|------------|
| `templates/list_view.html` | Checkboxen, Toolbar-HTML |
| `static/js/bulk_actions.js` | NEU: SelectionManager, BulkToolbar |
| `src/bulk_operations_handler.py` | NEU: BulkOperationsHandler |
| `src/01_web_app.py` | API Endpoints |

---

## ⏱️ Aufwand-Schätzung

| Task | Aufwand |
|------|---------|
| Multi-Select UI | 3-4h |
| Bulk-Toolbar | 2-3h |
| Backend Handler | 4-5h |
| API Endpoints | 2h |
| Confirmation Dialogs | 2h |
| Progress/Feedback | 2-3h |
| Testing | 2h |
| **Gesamt** | **15-20h** |

---

## 🧪 Testing

### Unit Tests
- `test_bulk_archive_success`
- `test_bulk_delete_confirmation`
- `test_circuit_breaker`
- `test_retry_logic`

### Integration Tests (gegen IMAP)
- `test_bulk_archive_real`
- `test_bulk_spam_real`
- `test_partial_failure`

---

## ✅ Definition of Done

- [ ] Checkboxen in Listen-Ansicht funktional
- [ ] Select-All Toggle funktional
- [ ] Bulk-Toolbar erscheint bei Auswahl
- [ ] Alle 6 Aktionen implementiert
- [ ] Confirmation für Delete
- [ ] Progress-Anzeige funktional
- [ ] Fehler werden angezeigt
- [ ] Partial Failure wird korrekt behandelt
- [ ] Tests geschrieben und bestanden
