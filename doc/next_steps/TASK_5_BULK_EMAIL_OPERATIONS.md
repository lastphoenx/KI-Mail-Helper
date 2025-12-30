# 📋 Task 5: Bulk Email Operations

**Implementierung von Batch-Aktionen für Multiple Emails**

**Status:** 🎯 Geplant (nach Phase 11.5)  
**Priority:** 🔴 Höchste  
**Estimated Effort:** 40-60 Stunden  
**Created:** 30. Dezember 2025

---

## 📋 Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Anforderungsanalyse](#anforderungsanalyse)
3. [Architektur-Design](#architektur-design)
4. [Implementation Details](#implementation-details)
5. [API Endpoints](#api-endpoints)
6. [Frontend Components](#frontend-components)
7. [Error-Handling](#error-handling)
8. [Testing-Strategie](#testing-strategie)
9. [TODO-Liste](#todo-liste)

---

## Überblick

Ermöglicht Benutzer*innen, **mehrere E-Mails gleichzeitig zu verarbeiten** (archivieren, spammen, löschen, flaggen). Dies ist eine kritische Feature für produktives E-Mail-Management.

### Kernfunktionalität

```
User selekt mehrere Mails per Checkbox
   ↓
Toolbar zeigt "X Mails ausgewählt"
   ↓
User wählt Aktion (Archive, Spam, Delete, Mark Read)
   ↓
Bestätigungs-Dialog (besonders für destruktive Aktionen)
   ↓
Server führt Batch-Operation durch
   ↓
Progress-Indicator zeigt Fortschritt
   ↓
Feedback: "5/5 erfolgreich" oder "4/5 erfolgreich, 1 Fehler"
```

---

## Anforderungsanalyse

### Funktionale Anforderungen

#### 1. Multi-Select UI

- [ ] **Checkboxen** für jede E-Mail in der Liste
  - Individual-Checkbox pro Mail
  - "Select All" / "Deselect All" Toggle
  - Bulk-Action nur wenn mind. 1 Mail ausgewählt
  
- [ ] **Bulk-Action Toolbar**
  - Erscheint wenn Emails ausgewählt (über Liste)
  - Counter: "X Mails ausgewählt"
  - Dropdown mit Aktionen
  - Visual Feedback (Scroll zu sichtbarem Bereich)

#### 2. Verfügbare Aktionen

- [ ] **Archive** → Move zu Archive-Folder
- [ ] **Spam** → Move zu Junk/Spam-Folder
- [ ] **Löschen** → Move zu Trash oder EXPUNGE
- [ ] **Mark as Read** → STORE +\Seen
- [ ] **Mark as Unread** → STORE -\Seen
- [ ] **Flag** → STORE +\Flagged
- [ ] **Unflag** → STORE -\Flagged (optional)

#### 3. Bestätigungs-Dialoge

| Aktion | Bestätigung | Grund |
|--------|-------------|-------|
| Archive | Optional ("5 Mails archivieren?") | Nicht destruktiv |
| Spam | Recommended | User kann Fehler machen |
| Delete | **Mandatory** | Destruktiv! |
| Mark Read | Optional | Reversible |

#### 4. Fehler-Handling

- **Partial Failure:** Manche Mails erfolgreich, manche nicht
  - Weiterführen, nicht abbrechen
  - Zeige Fehler-Details am Ende
  
- **Network Errors:** Timeout, Connection Reset
  - Retry-Logic (3 versuche mit Backoff)
  - Zeige welche UIDs fehlgeschlagen

- **Permission Denied:** User hat keine Rechte auf Folder
  - Zeige Error mit User-Message
  - Angebot: Andere Aktionen versuchen

### Nicht-Funktionale Anforderungen

| Anforderung | Ziel | Grund |
|-------------|------|-------|
| **Performance** | 100+ Mails verarbeiten in < 5s | Gutes UX |
| **Timeout** | Pro Mail max 2s | Verhindert Stalls |
| **Progress** | Updates alle 100ms | Visuelles Feedback |
| **Memory** | < 50MB für 1000 UIDs | Efficient Batch-Processing |
| **Rollback** | Bei kritischen Fehlern (>50%) abbrechen | Datensicherheit |

---

## Architektur-Design

### 1. Frontend-Struktur

#### HTML/CSS

```html
<!-- Email-List mit Checkboxen -->
<table class="email-list">
  <thead>
    <tr>
      <th><input type="checkbox" id="select-all"></th>
      <th>Datum</th>
      <th>Von</th>
      <th>Betreff</th>
      <th>Größe</th>
    </tr>
  </thead>
  <tbody>
    <tr class="email-row">
      <td><input type="checkbox" class="email-checkbox" data-uid="123"></td>
      <td>2024-12-30</td>
      <td>sender@example.com</td>
      <td>Projektbesprechung Q1</td>
      <td>4.2 KB</td>
    </tr>
    <!-- More rows... -->
  </tbody>
</table>

<!-- Bulk-Action Toolbar (hidden by default) -->
<div id="bulk-toolbar" class="bulk-toolbar hidden">
  <span id="selected-count">5 Mails ausgewählt</span>
  
  <div class="bulk-actions">
    <button id="archive-btn" class="btn btn-secondary">Archivieren</button>
    <button id="spam-btn" class="btn btn-warning">Spam</button>
    <button id="delete-btn" class="btn btn-danger">Löschen</button>
    
    <div class="dropdown">
      <button class="btn btn-default dropdown-toggle">Mehr...</button>
      <ul class="dropdown-menu">
        <li><a href="#" data-action="mark-read">Als gelesen markieren</a></li>
        <li><a href="#" data-action="mark-unread">Als ungelesen markieren</a></li>
        <li><a href="#" data-action="flag">Flaggen</a></li>
      </ul>
    </div>
  </div>
  
  <button id="deselect-all-btn" class="btn btn-sm">Abwählen</button>
</div>

<!-- Progress Modal (shown during operation) -->
<div id="progress-modal" class="modal hidden">
  <div class="modal-content">
    <h3>Verarbeite Mails...</h3>
    <div class="progress-bar">
      <div class="progress-fill" style="width: 40%"></div>
    </div>
    <p id="progress-text">2/5 erfolgreich</p>
    <div id="error-list" class="error-list"></div>
  </div>
</div>

<!-- Confirmation Dialog -->
<div id="confirm-dialog" class="modal hidden">
  <div class="modal-content">
    <h3 id="confirm-title">Aktion bestätigen</h3>
    <p id="confirm-message">5 Mails werden gelöscht. Dies kann nicht rückgängig gemacht werden.</p>
    <div class="buttons">
      <button id="confirm-ok" class="btn btn-danger">Ja, fortfahren</button>
      <button id="confirm-cancel" class="btn btn-secondary">Abbrechen</button>
    </div>
  </div>
</div>
```

#### JavaScript Event-Handling

```javascript
// Select-All Toggle
document.getElementById('select-all').addEventListener('change', function(e) {
    const isChecked = e.target.checked;
    document.querySelectorAll('.email-checkbox').forEach(cb => {
        cb.checked = isChecked;
    });
    updateToolbar();
});

// Individual Checkbox
document.querySelectorAll('.email-checkbox').forEach(cb => {
    cb.addEventListener('change', updateToolbar);
});

// Toolbar Actions
document.getElementById('archive-btn').addEventListener('click', () => {
    bulkAction('archive', false);  // false = no confirmation
});

document.getElementById('delete-btn').addEventListener('click', () => {
    bulkAction('delete', true);  // true = confirm first
});

function updateToolbar() {
    const selected = document.querySelectorAll('.email-checkbox:checked').length;
    const toolbar = document.getElementById('bulk-toolbar');
    
    if (selected > 0) {
        document.getElementById('selected-count').textContent = `${selected} Mails ausgewählt`;
        toolbar.classList.remove('hidden');
    } else {
        toolbar.classList.add('hidden');
    }
}

function bulkAction(action, requireConfirm) {
    const uids = Array.from(document.querySelectorAll('.email-checkbox:checked'))
        .map(cb => cb.dataset.uid);
    
    if (requireConfirm) {
        showConfirmDialog(action, uids.length, () => {
            performAction(action, uids);
        });
    } else {
        performAction(action, uids);
    }
}

function performAction(action, uids) {
    showProgressModal();
    
    fetch('/api/bulk/' + action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            folder: getCurrentFolder(),
            uids: uids,
            account_id: getSelectedAccount()
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSuccess(`${data.processed} Mails erfolgreich verarbeitet`);
            if (data.failed > 0) {
                showErrors(data.errors);
            }
            reloadEmailList();
        } else {
            showError(data.error);
        }
    })
    .catch(err => showError('Netzwerkfehler: ' + err.message));
}
```

### 2. Backend API-Endpoints

#### POST /api/bulk/archive

```json
Request:
{
  "account_id": 1,
  "folder": "INBOX",
  "uids": [123, 124, 125]
}

Response (200):
{
  "success": true,
  "processed": 3,
  "failed": 0,
  "errors": [],
  "batch_id": "uuid-123"
}

Response (207 Partial):
{
  "success": true,
  "processed": 2,
  "failed": 1,
  "errors": [
    {
      "uid": 125,
      "error": "Permission denied on Archive folder",
      "code": "PERMISSION_DENIED"
    }
  ],
  "batch_id": "uuid-123"
}
```

#### POST /api/bulk/spam, /api/bulk/delete, /api/bulk/flag

Gleiche Format wie `/api/bulk/archive`

### 3. IMAP Command Mapping

| Aktion | IMAP Command | Folder |
|--------|--------------|--------|
| Archive | COPY uids_set archive_folder | (User-specific) |
| Spam | COPY uids_set [Gmail]/Spam | oder server-spezifisch |
| Delete | STORE uids_set +\Deleted; EXPUNGE | (permanent) |
| Mark Read | STORE uids_set +\Seen | (current folder) |
| Mark Unread | STORE uids_set -\Seen | (current folder) |
| Flag | STORE uids_set +\Flagged | (current folder) |

---

## Implementation Details

### Phase 1: Frontend-Komponenten (1-2 Wochen)

#### Schritt 1: List-View Modification

1. Bestehende `list_view.html` modifizieren:
   - Checkboxen-Spalte hinzufügen
   - CSS für Toolbar styling
   - Select-All Checkbox im Header

2. CSS schreiben (Bootstrap 5 compatible):
   - `.bulk-toolbar` styling (sticky auf Bottom oder Top)
   - `.email-row:hover` mit Checkbox-Highlight
   - `.email-row.selected` Highlight
   - Progress-Modal Styling

#### Schritt 2: JavaScript Event-Handling

1. Checkbox Event-Listener
2. Toolbar Show/Hide Logic
3. Confirmation Dialog Modal
4. Progress Modal mit Live-Updates
5. Error-Message Display

### Phase 2: Backend API (2-3 Wochen)

#### Schritt 1: Flask Routes schreiben

```python
@app.route('/api/bulk/<action>', methods=['POST'])
@login_required
def bulk_action(action):
    """Handle bulk email operations"""
    user = get_current_user_model(db)
    master_key = session.get('master_key')
    
    if not master_key:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    account_id = data.get('account_id')
    folder = data.get('folder')
    uids = data.get('uids', [])
    
    # Validate input
    if not uids or len(uids) == 0:
        return jsonify({'error': 'No UIDs provided'}), 400
    if len(uids) > 1000:
        return jsonify({'error': 'Max 1000 UIDs per request'}), 400
    
    account = db.query(MailAccount).filter_by(
        id=account_id, user_id=user.id
    ).first()
    
    if not account:
        return jsonify({'error': 'Account not found'}), 404
    
    # Perform bulk operation
    try:
        result = bulk_ops_handler.perform_action(
            action=action,
            account=account,
            master_key=master_key,
            folder=folder,
            uids=uids,
            user=user
        )
        
        status_code = 200 if result['failed'] == 0 else 207
        return jsonify(result), status_code
    
    except Exception as e:
        logger.error(f"Bulk action failed: {e}")
        return jsonify({'error': 'Operation failed'}), 500
```

#### Schritt 2: Bulk Operations Handler

```python
# src/bulk_operations_handler.py

class BulkOperationsHandler:
    
    def perform_action(self, action, account, master_key, folder, uids, user):
        """Execute bulk operation with error tracking"""
        
        results = {
            'processed': 0,
            'failed': 0,
            'errors': [],
            'batch_id': str(uuid.uuid4())
        }
        
        # Get IMAP connection
        fetcher = get_mail_fetcher_for_account(account, master_key)
        fetcher.connect()
        
        try:
            # Execute based on action type
            if action == 'archive':
                self._bulk_archive(fetcher, folder, uids, results)
            elif action == 'spam':
                self._bulk_spam(fetcher, folder, uids, results)
            elif action == 'delete':
                self._bulk_delete(fetcher, folder, uids, results)
            elif action in ['mark-read', 'mark-unread', 'flag']:
                self._bulk_flag(fetcher, folder, action, uids, results)
            else:
                return {'error': f'Unknown action: {action}'}, 400
            
            results['success'] = results['failed'] == 0
            return results
        
        finally:
            fetcher.disconnect()
    
    def _bulk_archive(self, fetcher, current_folder, uids, results):
        """Move emails to archive folder"""
        archive_folder = 'Archive'  # TODO: User-configurable
        
        for uid in uids:
            try:
                # COPY uid to archive, then mark for deletion
                fetcher.connection.copy(uid, archive_folder)
                fetcher.connection.store(uid, '+\Deleted')
                results['processed'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'uid': uid,
                    'error': str(e),
                    'code': 'COPY_FAILED'
                })
        
        # Expunge deleted messages
        try:
            fetcher.connection.expunge()
        except:
            pass
    
    def _bulk_spam(self, fetcher, current_folder, uids, results):
        """Move emails to spam folder"""
        spam_folder = '[Gmail]/Spam'  # TODO: Detect per provider
        
        for uid in uids:
            try:
                fetcher.connection.copy(uid, spam_folder)
                fetcher.connection.store(uid, '+\Deleted')
                results['processed'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'uid': uid,
                    'error': str(e),
                    'code': 'COPY_FAILED'
                })
        
        try:
            fetcher.connection.expunge()
        except:
            pass
    
    def _bulk_delete(self, fetcher, current_folder, uids, results):
        """Delete emails (move to trash or expunge)"""
        
        for uid in uids:
            try:
                # Mark as deleted
                fetcher.connection.store(uid, '+\Deleted')
                results['processed'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'uid': uid,
                    'error': str(e),
                    'code': 'STORE_FAILED'
                })
        
        # Expunge
        try:
            fetcher.connection.expunge()
        except:
            pass
    
    def _bulk_flag(self, fetcher, current_folder, action, uids, results):
        """Flag/unflag or mark read/unread"""
        
        flag_map = {
            'mark-read': '+\Seen',
            'mark-unread': '-\Seen',
            'flag': '+\Flagged',
            'unflag': '-\Flagged'
        }
        
        flag = flag_map[action]
        
        for uid in uids:
            try:
                fetcher.connection.store(uid, flag)
                results['processed'] += 1
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'uid': uid,
                    'error': str(e),
                    'code': 'STORE_FAILED'
                })
```

### Phase 3: Error Recovery & Rollback

#### Retry-Logic

```python
def _execute_with_retry(self, operation, uid, max_retries=3):
    """Execute IMAP operation with exponential backoff"""
    
    for attempt in range(max_retries):
        try:
            return operation(uid)
        except imaplib.IMAP4.timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait_time)
            else:
                raise
        except imaplib.IMAP4.abort:
            # Connection lost, need to reconnect
            self.connection.open()
            if attempt < max_retries - 1:
                continue
            else:
                raise
```

#### Circuit Breaker

```python
class BulkOperationCircuitBreaker:
    """Stop bulk operations if error rate exceeds threshold"""
    
    def __init__(self, error_threshold=0.5):
        self.error_threshold = error_threshold
    
    def should_continue(self, processed, failed):
        """Check if should continue operation"""
        if processed == 0:
            return True
        
        error_rate = failed / (processed + failed)
        
        if error_rate > self.error_threshold:
            return False  # Too many errors, stop
        
        return True
```

---

## API Endpoints

### POST /api/bulk/archive

Archiviere mehrere Mails

**Request:**
```json
{
  "account_id": 1,
  "folder": "INBOX",
  "uids": [123, 124, 125]
}
```

**Success Response (200):**
```json
{
  "success": true,
  "processed": 3,
  "failed": 0,
  "errors": [],
  "batch_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Partial Response (207):**
```json
{
  "success": true,
  "processed": 2,
  "failed": 1,
  "errors": [
    {
      "uid": 125,
      "error": "Permission denied",
      "code": "PERMISSION_DENIED"
    }
  ]
}
```

### POST /api/bulk/spam

Markiere als Spam

**Identisch wie /archive, aber mit Ziel-Folder = Spam**

### POST /api/bulk/delete

Lösche Mails permanent

**Identisch wie /archive, aber mit EXPUNGE statt MOVE**

### POST /api/bulk/flag

Flagge/Unflagge oder Mark Read/Unread

**Request:**
```json
{
  "account_id": 1,
  "folder": "INBOX",
  "uids": [123, 124],
  "action": "mark-read"  // oder "mark-unread", "flag", "unflag"
}
```

---

## Frontend Components

### Bulk-Toolbar Component

```javascript
class BulkToolbar {
    constructor(parentSelector) {
        this.toolbar = document.querySelector(parentSelector);
        this.selectedCount = this.toolbar.querySelector('#selected-count');
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        // Button click handlers
        document.getElementById('archive-btn').onclick = () => this.action('archive');
        document.getElementById('spam-btn').onclick = () => this.action('spam');
        document.getElementById('delete-btn').onclick = () => this.action('delete', true);
    }
    
    update(count) {
        if (count === 0) {
            this.hide();
        } else {
            this.selectedCount.textContent = `${count} Mails ausgewählt`;
            this.show();
        }
    }
    
    show() {
        this.toolbar.classList.remove('hidden');
    }
    
    hide() {
        this.toolbar.classList.add('hidden');
    }
    
    async action(actionName, requireConfirm = false) {
        const uids = this.getSelectedUIDs();
        
        if (uids.length === 0) {
            alert('Keine Mails ausgewählt');
            return;
        }
        
        if (requireConfirm) {
            if (!confirm(`${uids.length} Mails wirklich ${actionName}?`)) {
                return;
            }
        }
        
        const response = await fetch(`/api/bulk/${actionName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                account_id: this.getAccountID(),
                folder: this.getCurrentFolder(),
                uids: uids
            })
        });
        
        const result = await response.json();
        this.handleResult(result);
    }
    
    getSelectedUIDs() {
        return Array.from(document.querySelectorAll('.email-checkbox:checked'))
            .map(cb => parseInt(cb.dataset.uid));
    }
    
    handleResult(result) {
        if (result.success) {
            alert(`✅ ${result.processed} Mails erfolgreich verarbeitet`);
            if (result.failed > 0) {
                alert(`⚠️ ${result.failed} Fehler: ${result.errors.map(e => e.error).join(', ')}`);
            }
            location.reload();  // Reload list
        } else {
            alert(`❌ Fehler: ${result.error}`);
        }
    }
}
```

### Progress Modal

```javascript
class ProgressModal {
    constructor(totalCount) {
        this.modal = document.getElementById('progress-modal');
        this.progressBar = this.modal.querySelector('.progress-fill');
        this.progressText = this.modal.querySelector('#progress-text');
        this.errorList = this.modal.querySelector('#error-list');
        this.totalCount = totalCount;
        this.currentCount = 0;
    }
    
    show() {
        this.modal.classList.remove('hidden');
    }
    
    hide() {
        this.modal.classList.add('hidden');
    }
    
    update(processed, failed) {
        this.currentCount = processed + failed;
        const percentage = (this.currentCount / this.totalCount) * 100;
        
        this.progressBar.style.width = percentage + '%';
        this.progressText.textContent = `${processed}/${this.totalCount} erfolgreich`;
        
        if (failed > 0) {
            this.progressText.textContent += ` (${failed} Fehler)`;
        }
    }
    
    addError(uid, message) {
        const li = document.createElement('li');
        li.textContent = `UID ${uid}: ${message}`;
        this.errorList.appendChild(li);
    }
}
```

---

## Error-Handling

### Szenario 1: Partial Failure

```
User archiviert 10 Mails
5 erfolgreich, 5 fehlgeschlagen
→ Result: HTTP 207, show Errors
→ UI zeigt "5/10 erfolgreich, 5 Fehler"
→ User kann manuell erneut versuchen oder ignorieren
```

### Szenario 2: Network Timeout

```
IMAP-Server antwortet nicht
→ Retry nach 1s, dann 2s, dann 4s
→ Nach 3 Versuchen: Fehler
→ User sieht "Netzwerkfehler, bitte später versuchen"
```

### Szenario 3: Permission Denied

```
User hat keine Rechte auf Archive-Folder
→ COPY operation schlägt fehl
→ Fehler gesammelt
→ Zeige: "Archive-Folder nicht erreichbar"
→ Angebot: "In Spam-Folder verschieben?"
```

### Szenario 4: Too Many Errors (Circuit Breaker)

```
User versucht 100 Mails zu archivieren
10 fehlgeschlagen = 10% Error Rate (unter Threshold)
20 fehlgeschlagen = 20% Error Rate (unter Threshold)
55 fehlgeschlagen = 55% Error Rate (ÜBER 50% Threshold!)
→ Operation stoppt
→ User sieht: "Zu viele Fehler (55%), Operation abgebrochen"
→ 45 Mails archiviert, 55 nicht
```

---

## Testing-Strategie

### Unit-Tests

```python
def test_bulk_archive_success(self):
    """Test successful archive operation"""
    handler = BulkOperationsHandler()
    result = handler.perform_action(
        action='archive',
        account=mock_account,
        master_key='test_key',
        folder='INBOX',
        uids=[123, 124, 125],
        user=mock_user
    )
    
    assert result['processed'] == 3
    assert result['failed'] == 0

def test_bulk_archive_partial_failure(self):
    """Test partial failure handling"""
    # Mock: 3/5 succeed
    result = handler.perform_action(...)
    assert result['processed'] == 3
    assert result['failed'] == 2
    assert len(result['errors']) == 2

def test_bulk_delete_requires_confirmation(self):
    """Test delete action shows confirmation"""
    # Frontend test
    # Click delete → confirmation modal appears
    # Click OK → operation executes

def test_circuit_breaker_stops_at_threshold(self):
    """Test circuit breaker stops operation"""
    # Simulate 50+ % failure rate
    # Operation should stop before processing all
```

### Integration-Tests

```python
def test_bulk_archive_real_imap(self):
    """Test against real IMAP server (staging)"""
    # Login with test account
    # Create 5 test mails
    # Bulk archive
    # Verify: mails in Archive folder
    # Verify: mails gone from INBOX
```

### UI-Tests (Selenium)

```python
def test_bulk_select_all(self):
    """Test select-all functionality"""
    # Open list view
    # Click select-all
    # Assert: all checkboxes checked
    # Assert: toolbar shows "10 Mails ausgewählt"

def test_bulk_action_confirmation(self):
    """Test delete action requires confirmation"""
    # Select 2 mails
    # Click delete
    # Confirmation dialog appears
    # Click cancel → operation stops
    # Click OK → operation executes
```

---

## TODO-Liste

### Phase 1: Frontend (1-2 Wochen, 30-40h)

- [ ] Modify `templates/list_view.html`:
  - [ ] Add checkbox column
  - [ ] Add select-all header checkbox
  - [ ] Style selected rows

- [ ] Create `static/js/bulk_actions.js`:
  - [ ] SelectionManager class
  - [ ] BulkToolbar class
  - [ ] ConfirmationDialog class
  - [ ] ProgressModal class

- [ ] Add CSS styling:
  - [ ] `.bulk-toolbar` sticky positioning
  - [ ] `.email-row.selected` highlighting
  - [ ] Modal dialogs styling
  - [ ] Progress bar animation

- [ ] Test gegen verschiedene Browser:
  - [ ] Chrome/Chromium
  - [ ] Firefox
  - [ ] Safari

### Phase 2: Backend (2-3 Wochen, 40-50h)

- [ ] Create `src/bulk_operations_handler.py`:
  - [ ] BulkOperationsHandler class
  - [ ] Methods: _bulk_archive, _bulk_spam, _bulk_delete, _bulk_flag
  - [ ] Retry-logic mit exponential backoff
  - [ ] Error tracking & partial failure handling

- [ ] Add Flask routes in `src/01_web_app.py`:
  - [ ] POST /api/bulk/archive
  - [ ] POST /api/bulk/spam
  - [ ] POST /api/bulk/delete
  - [ ] POST /api/bulk/flag

- [ ] Input validation:
  - [ ] Max 1000 UIDs per request
  - [ ] Account ownership check
  - [ ] Folder accessibility check

- [ ] Error handling:
  - [ ] Circuit breaker (stop at 50% error rate)
  - [ ] Retry mechanism (3 attempts)
  - [ ] Detailed error messages

- [ ] Database integration:
  - [ ] Log bulk operations (audit trail)
  - [ ] Update email flags nach Operation

### Phase 3: Integration & Testing (1-2 Wochen, 30-40h)

- [ ] Unit-Tests:
  - [ ] test_bulk_archive_success
  - [ ] test_bulk_delete_requires_confirmation
  - [ ] test_circuit_breaker
  - [ ] test_retry_logic

- [ ] Integration-Tests (gegen real IMAP):
  - [ ] test_bulk_archive_real_gmx
  - [ ] test_bulk_spam_real_gmail
  - [ ] test_bulk_delete_real_outlook

- [ ] UI-Tests (Selenium):
  - [ ] test_select_all
  - [ ] test_select_multiple
  - [ ] test_bulk_action_with_confirmation
  - [ ] test_progress_modal

- [ ] Performance-Tests:
  - [ ] Bulk archive 100 mails
  - [ ] Bulk archive 1000 mails (split in batches)
  - [ ] Measure response time & memory usage

- [ ] Test gegen verschiedene Provider:
  - [ ] GMX (Dovecot)
  - [ ] Gmail (Custom IMAP)
  - [ ] Outlook (Exchange)

### Phase 4: Documentation & Deployment (1 Woche, 15-20h)

- [ ] Document API endpoints in swagger/openapi
- [ ] Write user guide for bulk operations
- [ ] Create runbook for ops team
- [ ] Test deployment gegen staging
- [ ] Create rollback plan
- [ ] Update CHANGELOG.md

---

## Success Criteria

- ✅ User kann mehrere Mails mit Checkboxen auswählen
- ✅ Bulk-Action Toolbar zeigt Anzahl ausgewählter Mails
- ✅ Benutzer kann archivieren, spammen, löschen, flaggen
- ✅ Destruktive Aktionen (delete) erfordern Bestätigung
- ✅ Partial failure wird korrekt gehandhabt (weitermachen, Fehler zeigen)
- ✅ Progress wird während Operation angezeigt
- ✅ Retry-Logic bei Netzwerk-Fehlern
- ✅ Circuit Breaker bei zu vielen Fehlern
- ✅ 100+ Mails in < 5 Sekunden verarbeitet
- ✅ Tests gegen 3+ IMAP-Provider bestanden
- ✅ Zero-Knowledge Architektur eingehalten (Master-Key Handling)

---

## Abhängigkeiten

- ✅ Phase 11.5: IMAP Diagnostics (Mail-Fetcher ist getestet)
- ✅ Master-Key Management (Session-basiert)
- ⚠️ Folder Detection (Archive, Spam, Trash provider-spezifisch)
- ⚠️ Email-Flag Management (boolean flags aus Phase 12)

---

## Risiken & Mitigation

| Risiko | Severity | Mitigation |
|--------|----------|-----------|
| User archiviert 1000 Mails, 500 fehlen | 🔴 | Batch-Processing (100er), Circuit Breaker |
| IMAP-Connection timeout | ⚠️ | Retry-Logic mit exponential backoff |
| Archive-Folder nicht erreichbar | ⚠️ | Detect special folders, show error |
| User machen Fehler bei delete | 🔴 | Mandatory confirmation dialog |
| Zero-Knowledge Verletzung | 🔴 | Master-Key Parameter, Session-basiert |

---

**Nächste Schritte:** Nach Phase 11.5 & Metadata-Enrichment (Phase 12), dieses Feature als Phase 13 implementieren.
