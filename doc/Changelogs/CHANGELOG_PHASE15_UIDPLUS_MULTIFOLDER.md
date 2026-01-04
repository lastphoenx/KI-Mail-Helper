# CHANGELOG - Phase 15: UIDPLUS COPYUID & Multi-Folder DB Sync

**Date:** 02. Januar 2026  
**Duration:** ~4 hours  
**Status:** ✅ COMPLETE + Phase 16 Bugfixes  

---

## 🎯 Overview

Phase 15 implements two critical improvements:

1. **UIDPLUS COPYUID Support for Trash**: `move_to_trash()` now returns `MoveResult` with new UID/UIDVALIDITY, ensuring DB stays synchronized with IMAP server after move operations.

2. **Multi-Folder DB Sync Check (Test 12)**: IMAP Diagnostics can now verify synchronization across all folders or specific folders, with expandable detail views showing IMAP vs DB comparison.

---

## 📦 Changes

### A) 🗑️ move_to_trash: UIDPLUS COPYUID Support

**Files:** `src/01_web_app.py` (Route `/email/<int:email_id>/move-trash`)

**Problem:**
- `move_to_trash()` returned `(bool, str)` tuple (old API)
- DB was not updated with new UID/UIDVALIDITY after COPY+DELETE operation
- IMAP standard: "Move to trash" is a **MOVE operation** (COPY + DELETE), not just a flag

**Solution:**
```python
# Old (Phase 14):
success, message = synchronizer.move_to_trash(uid, folder)
if success:
    email.deleted_at = datetime.now(UTC)
    db.commit()

# New (Phase 15):
result = synchronizer.move_to_trash(uid, folder)  # Returns MoveResult
if result.success:
    raw_email.imap_folder = result.target_folder      # Update folder
    raw_email.imap_uid = result.target_uid            # Update UID (from COPYUID)
    raw_email.imap_uidvalidity = result.target_uidvalidity  # Update UIDVALIDITY
    email.deleted_at = datetime.now(UTC)
    db.commit()
```

**UIDPLUS Response Example:**
```
COPYUID: [b'1352540700 451 5']
        │    │          │   └─ New UID in Trash folder
        │    │          └───── Old UID in source folder  
        │    └──────────────── UIDVALIDITY of Trash folder
        └───────────────────── Format: UIDVALIDITY old-uid new-uid
```

**Validation (from logs):**
```
Email 22: UID 451 → 5 (INBOX → Gelöscht)     COPYUID: [b'1352540700 451 5']
Email 2:  UID 11  → 6 (Entwürfe → Gelöscht)  COPYUID: [b'1352540700 11 6']
```

**Benefits:**
- ✅ DB always has correct UID after move operations
- ✅ No sync issues when fetching emails from Trash folder
- ✅ Consistent with `move_to_folder()` implementation
- ✅ RFC 4315 UIDPLUS compliant

---

### B) 📁 Test 12: Multi-Folder DB Sync Check

**Files:** `src/imap_diagnostics.py`, `src/01_web_app.py`, `templates/imap_diagnostics.html`

**Problem:**
- Test 12 only checked `Archiv` folder (hard-coded)
- No way to verify sync status for all folders at once
- No visual comparison between IMAP and DB values

**Solution:**

#### Backend Changes (`src/imap_diagnostics.py`):

**New Signature:**
```python
def verify_db_sync(
    self, 
    client=None, 
    account_id: int = None, 
    session=None, 
    folder_name: str = None  # NEW: Optional folder filter
) -> Dict[str, Any]:
```

**Logic:**
- `folder_name` given → Single-folder mode (detailed mail list)
- `folder_name = None` → Multi-folder mode (all folders overview)

**Multi-Folder Result Structure:**
```python
{
  'success': True,
  'multi_folder_mode': True,
  'folders': {
    'Archiv': { 
        'imap_count': 1, 
        'db_count': 1, 
        'sync_ok': True,
        'all_mails': [...]  # With IMAP/DB comparison data
    },
    'INBOX': { ... },
    'Gelöscht': { ... }
  },
  'summary': 'Gecheckt: 7 Ordner, ✅ Alle synchronisiert',
  'total_folders': 7,
  'folders_with_issues': 0
}
```

**Helper Method:**
```python
def _verify_db_sync_multi_folder(self, client, folders: list, account_id, session):
    """Iterates over all folders and collects sync status"""
    for folder in folders:
        folder_result = self.verify_db_sync(client, account_id, session, folder)
        results[folder] = folder_result
    return multi_folder_summary
```

#### API Endpoint (`src/01_web_app.py`):

```python
# POST /api/imap-diagnostics/<account_id>
# Body: { "folder_name": "Archiv" } or { "folder_name": null }

target_folder = None
if request.is_json:
    json_data = request.get_json(silent=True) or {}
    target_folder = json_data.get("folder_name", None)

result = diagnostics.run_diagnostics(
    subscribed_only=subscribed_only,
    account_id=account_id,
    session=db,
    folder_name=target_folder  # NEW
)
```

#### Frontend Changes (`templates/imap_diagnostics.html`):

**1. Folder Selection Dropdown:**
```html
<select id="folderSelect" class="form-select">
    <option value="">-- Alle Ordner überprüfen --</option>
    <!-- Gefüllt nach Diagnostics mit list_folders() -->
</select>
```

**2. Multi-Folder Overview Table:**
```
┌─────────┬──────┬────┬──────┬──────────────────────────┬─────────┐
│ Ordner  │ IMAP │ DB │ Sync │ Details                  │ Aktion  │
├─────────┼──────┼────┼──────┼──────────────────────────┼─────────┤
│ Archiv  │  1   │  1 │  ✅  │ ✅ Perfekt synchronisiert│📋 Details│ ← Expandable!
│ INBOX   │ 28   │ 28 │  ✅  │ ✅ Perfekt synchronisiert│📋 Details│
│ Gelöscht│  4   │  4 │  ✅  │ ✅ Perfekt synchronisiert│📋 Details│
└─────────┴──────┴────┴──────┴──────────────────────────┴─────────┘
```

**3. Expandable Detail View (per folder):**
```
📧 Mails in Ordner "Gelöscht" (4):
┌────────┬─────────────────┬─────────────────┬─────────────┬───┬───┬───┬─────────┐
│ Status │  📡 IMAP        │  💾 DB          │ Betreff     │👁️ │🚩│↩️│ Datum   │
│        ├─────────┬───────┼─────────┬───────┤             │   │   │   │         │
│        │   UID   │UIDVAL │   UID   │UIDVAL │             │   │   │   │         │
├────────┼─────────┼───────┼─────────┼───────┼─────────────┼───┼───┼───┼─────────┤
│   ✅   │    2    │ 13525 │    2    │ 13525 │ Papierkorb  │ ✅│ —│ —│2025-12-│
│   ✅   │    5    │ 13525 │    5    │ 13525 │ Test Email  │ — │🚩│ —│2025-12-│
└────────┴─────────┴───────┴─────────┴───────┴─────────────┴───┴───┴───┴─────────┘
```

**Key Features:**
- **Visual Comparison**: IMAP vs DB side-by-side
- **Automatic Mismatch Detection**: Red background if UID or UIDVALIDITY differ
- **Toggle Details**: Click "📋 Details" button to expand/collapse mail list
- **Event-Delegation**: CSP-compliant (no inline `onclick=""`)

**JavaScript Functions:**
```javascript
populateFolderSelect(foldersArray)           // Fill dropdown after diagnostics
displayMultiFolderDbSync(data, ...)          // Show overview table
renderFolderMailDetails(folderName, data)    // Render expandable mail list
attachFolderDetailsToggleListeners()         // CSP-compliant event binding
```

#### Data Structure Enhancement:

**Separate IMAP/DB Values:**
```python
# Each mail now has:
{
    'imap_uid': 123,           # UID from IMAP server
    'imap_uidvalidity': 17023, # UIDVALIDITY from IMAP
    'db_uid': 123,             # UID from database
    'db_uidvalidity': 17023,   # UIDVALIDITY from database
    'in_imap': True,
    'in_db': True,
    'subject': '...',
    # ... other fields
}
```

**Benefits:**
- ✅ Visual debugging: See immediately if IMAP and DB differ
- ✅ All folders overview: No need to manually check each folder
- ✅ Detailed inspection: Click to see full mail list with flags
- ✅ Mismatch highlighting: Red background for sync issues

---

## 🐛 Bugs Fixed

### 1. **folder.count does not exist**
**Problem:** `list_all_folders()` does not return `count` field  
**Location:** `templates/imap_diagnostics.html:402`  
**Fix:** Removed `(${folder.count || 0} Mails)` from dropdown, show only folder name

### 2. **CSP violation: inline onclick**
**Problem:** `onclick="toggleFolderDetails(...)"` blocked by Content-Security-Policy  
**Location:** `templates/imap_diagnostics.html`  
**Fix:** Changed to `data-folder-id` attribute + event delegation with `addEventListener()`

### 3. **Template string syntax error**
**Problem:** `<br>` tag outside template string, causing "expected expression, got '<'"  
**Location:** `templates/imap_diagnostics.html:602-604`  
**Fix:** Moved HTML content inside template string, before closing backtick

---

## 📊 Testing & Validation

### Test Case 1: move_to_trash with UIDPLUS

**Test:**
1. Open email in INBOX
2. Click "In Papierkorb verschieben"
3. Check logs for COPYUID
4. Verify DB update

**Result:**
```
✅ COPYUID: [b'1352540700 451 5']
✅ Email 22: UID 451 → 5 (INBOX → Gelöscht)
✅ DB updated: imap_uid=5, imap_folder='Gelöscht', imap_uidvalidity=1352540700
```

### Test Case 2: Multi-Folder DB Sync

**Test:**
1. Open IMAP Diagnostics
2. Select account
3. Run diagnostics (folder_name=null)
4. Verify all 7 folders checked

**Result:**
```
✅ Gecheckt: 7 Ordner, ✅ Alle synchronisiert
✅ Archiv:    1 IMAP,  1 DB, sync_ok=True
✅ Entwürfe:  2 IMAP,  2 DB, sync_ok=True
✅ Gelöscht:  4 IMAP,  4 DB, sync_ok=True
✅ Gesendet: 16 IMAP, 16 DB, sync_ok=True
✅ INBOX:    26 IMAP, 26 DB, sync_ok=True
✅ OUTBOX:    0 IMAP,  0 DB, sync_ok=True
✅ Spamverdacht: 0 IMAP, 0 DB, sync_ok=True
```

### Test Case 3: Single-Folder Detail View

**Test:**
1. Select "Gelöscht" folder in dropdown
2. Run diagnostics again
3. Click "📋 Details" button
4. Verify IMAP vs DB columns

**Result:**
```
✅ Expandable detail row shown
✅ IMAP UID: 2, 3, 5, 6 (column 1)
✅ DB UID:   2, 3, 5, 6 (column 2)
✅ IMAP UIDVAL: 1352540700 (all rows)
✅ DB UIDVAL:   1352540700 (all rows)
✅ No red highlighting (all values match)
```

---

## 📝 Code Quality

### Type Safety
- ✅ All function signatures have type hints
- ✅ `folder_name: str = None` parameter added consistently
- ✅ `MoveResult` dataclass used (not tuple unpacking)

### Error Handling
- ✅ Try-catch blocks around folder iteration
- ✅ Graceful degradation if folder check fails
- ✅ DB rollback on update failure

### Performance
- ✅ Single IMAP connection for multi-folder check
- ✅ No N+1 queries (uses single query with `.in_()` filter)
- ✅ Early context limiting (4500 chars)

### Security
- ✅ CSP-compliant (no inline event handlers)
- ✅ SQL injection safe (SQLAlchemy ORM)
- ✅ CSRF token validation in POST requests

---

## 🎯 Impact

### move_to_trash UIDPLUS Support:
- **Before:** DB had stale UIDs after trash operations → sync errors
- **After:** DB always has current UID/UIDVALIDITY → perfect sync

### Multi-Folder DB Sync:
- **Before:** Manual checking of each folder (tedious)
- **After:** One-click overview of all 7 folders + expandable details

### Visual IMAP/DB Comparison:
- **Before:** Guessing if values match (no visibility)
- **After:** Side-by-side comparison with automatic mismatch highlighting

---

## 🔄 Migration Notes

**No database migration required** - uses existing fields:
- `raw_email.imap_uid`
- `raw_email.imap_uidvalidity`
- `raw_email.imap_folder`
- `email.deleted_at`

**Backward compatibility:**
- `move_to_trash()` already returned `MoveResult` (Phase 14c)
- Only route handler needed update to use `.target_uid`

---

## 🚀 Future Enhancements

### Possible Improvements:
1. **Bulk Sync Fix**: Button to batch-update mismatched UIDs from IMAP
2. **Sync History**: Log when sync issues occur (timestamp + details)
3. **Auto-Refresh**: Periodic sync check in background
4. **Export Report**: Download sync status as CSV/JSON

### Technical Debt:
- None identified

---

## 📚 Documentation Updated

- ✅ This CHANGELOG created
- ✅ Code comments added (Phase 15, Phase 15b markers)
- ✅ Function docstrings updated with new parameters
- ✅ API endpoint documented in code

---

## ✅ Checklist

- [x] move_to_trash: UIDPLUS COPYUID support implemented
- [x] DB update with target_uid, target_uidvalidity, target_folder
- [x] verify_db_sync: folder_name parameter added
- [x] Multi-folder mode with _verify_db_sync_multi_folder() helper
- [x] API endpoint: folder_name from request body
- [x] HTML: Folder selection dropdown
- [x] HTML: Multi-folder overview table
- [x] HTML: Expandable detail rows per folder
- [x] HTML: IMAP vs DB side-by-side columns
- [x] Bug fix: folder.count removed
- [x] Bug fix: CSP-compliant event delegation
- [x] Bug fix: Template string syntax error
- [x] Testing: move_to_trash with real IMAP operations
- [x] Testing: Multi-folder sync check (7 folders)
- [x] Testing: Detail view toggle functionality
- [x] Code review: Type hints, error handling
- [x] Documentation: CHANGELOG created

---

**Phase 15 Complete!** 🎉

All changes tested and validated with real IMAP server operations.

---

## 🐛 Phase 16: Bugfixes & UI Improvements (02.01.2026)

**Issues Found During Testing:**

### Issue 1: Optimize-Pass überschreibt Initial-Analyse
**Problem:** Optimize-Pass überschrieb `email.dringlichkeit`, `email.wichtigkeit`, `email.score` etc. → Initial-Analyse-Daten gingen verloren

**Solution:** Separate Felder für Optimize-Ergebnisse
- Neue DB-Spalten: `optimize_dringlichkeit`, `optimize_wichtigkeit`, `optimize_kategorie_aktion`, `optimize_spam_flag`, `optimize_score`, `optimize_matrix_x`, `optimize_matrix_y`, `optimize_farbe`, `optimize_encrypted_summary_de`, `optimize_encrypted_text_de`, `optimize_encrypted_tags`
- Migration: `ph16_separate_optimize_results.py`

### Issue 2-8: Weitere Bugfixes
- UTC+1 Zeitkonvertierung (Log vs UI)
- Score-Sichtbarkeit (CSS-Klasse statt inline-style)
- Zeitbasierte Logik (neuerer Lauf gewinnt)
- Modal-Close + Timer für Reprocess/Optimize
- Logging + Navigation verbessert
- Kategorie bei Initial-Analyse angezeigt

**Files Changed:**
- `src/01_web_app.py`, `src/02_models.py`
- `templates/email_detail.html`, `templates/list_view.html`
- `migrations/versions/ph15_add_rebase_timestamp.py`
- `migrations/versions/ph16_separate_optimize_results.py`

✅ **Phase 15 + 16 Complete!** All tested with real IMAP operations.
---

## 🔧 Phase 17: Provider Configuration Fix (02.01.2026)

**Issues Found During Settings Testing:**

### Issue 1: API Route ignoriert kind-Parameter
**Problem:** JavaScript sendet `?kind=base` oder `?kind=optimize`, aber `/api/available-models/<provider>` ignorierte den Parameter
- Dropdown zeigte **alle** Modelle statt nur erlaubte für jeweiligen Pass
- Settings erlaubte z.B. `gpt-4-turbo` für Base-Pass (nicht in `models_base`)

**Solution:**
```python
# src/01_web_app.py
@app.route("/api/available-models/<provider>")
def get_available_models(provider):
    kind = request.args.get('kind', None)  # ← NEU
    models_list = provider_utils.get_available_models(provider, kind=kind)
    return jsonify({"models": models_list})
```

### Issue 2: Anthropic Model-IDs inkonsistent
**Problem:** `get_anthropic_models()` gab andere Modelle zurück als in `PROVIDER_REGISTRY` definiert
- Registry: `claude-3-5-sonnet-20240620`, `claude-3-haiku-20240307`
- Funktion: `claude-opus-4-1-20250805`, `claude-3-5-sonnet-20241022`, `claude-3-opus-20240229`
- **Alle Modelle wurden herausgefiltert** → Empty dropdown

**Solution:** Alle Provider-Funktionen jetzt konsistent aus `PROVIDER_REGISTRY`:
```python
def get_anthropic_models() -> List[str]:
    try:
        ai_client = importlib.import_module("src.03_ai_client")
        registry = getattr(ai_client, "PROVIDER_REGISTRY", {})
        cfg = registry.get("anthropic", {})
        return cfg.get("models", [])
    except:
        return [fallback_models]
```

### Issue 3: Deprecated Claude 3.x Modelle
**Problem:** Anthropic API gab 404-Fehler für `claude-3-5-sonnet-20240620`
- Claude 3.x Modelle wurden retired (30.06.2025 deprecated, 05.01.2026 retired)
- Fehlermeldung: `{"type":"not_found_error","message":"model: claude-3-5-sonnet-20240620"}`

**Solution:** Update auf aktuelle Claude 4/4.5 Modelle:
```python
"anthropic": {
    "default_model_base": "claude-haiku-4-5-20251001",      # $1/$5
    "default_model_optimize": "claude-sonnet-4-5-20250929",  # $3/$15
    "models_base": [
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-20250514",
    ],
    "models_optimize": [
        "claude-sonnet-4-5-20250929",  # Beste Balance
        "claude-sonnet-4-20250514",
        "claude-opus-4-5-20251101",    # Premium
        "claude-opus-4-1-20250805",
        "claude-haiku-4-5-20251001",
    ],
}
```

### Issue 4: UI-Inkonsistenz (Button-Labels)
**Problem:** Email Detail Buttons nicht konsistent mit Settings-Terminologie
- Button: "🔄 Neu verarbeiten" / "🔧 Präzisiere Kategorisierung"
- Settings: "⚡ Base-Pass" / "🔧 Optimize-Pass"

**Solution:** Buttons angepasst:
- ✅ "🔄 Base-Pass neu"
- ✅ "🔧 Optimize-Pass"

**Files Changed:**
- `src/01_web_app.py` (API-Route mit kind-Parameter)
- `src/03_ai_client.py` (PROVIDER_REGISTRY: Anthropic Claude 4/4.5)
- `src/15_provider_utils.py` (Provider-Funktionen konsistent aus Registry)
- `templates/email_detail.html` (Button-Labels)

**Testing:**
- ✅ Base-Pass Dropdown: Nur `models_base` Modelle
- ✅ Optimize-Pass Dropdown: Nur `models_optimize` Modelle
- ✅ Anthropic: Claude Haiku 4.5 funktioniert
- ✅ OpenAI: Kein `gpt-4` mehr in Base-Pass
- ✅ Mistral: Modelle korrekt gefiltert

**Rationale - Two-Pass System:**
- **Base-Pass:** Schnelle Triage mit günstigen Modellen (Haiku $1/$5, gpt-4o-mini)
- **Optimize-Pass:** Tiefe Analyse mit besseren Modellen nur bei wichtigen Mails (Sonnet $3/$15, gpt-4o)
- Kosten-Optimierung: 90% der Mails brauchen nur Base-Pass

✅ **Phase 17 Complete!** Provider-Konfiguration konsistent, deprecated Modelle entfernt.