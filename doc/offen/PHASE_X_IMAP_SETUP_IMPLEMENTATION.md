# 🚀 Phase X.3: IMAP Schnell-Setup für Whitelist

**Projekt:** KI-Mail-Helper  
**Feature:** Separate `/whitelist-imap-setup` Seite für Pre-Fetch Absender-Scan  
**Datum:** 2026-01-07  
**Status:** 📋 IMPLEMENTATIONSPLAN  
**Aufwand:** ~4-6 Stunden  

---

## 📋 Übersicht

### Problem
- Whitelist zeigt nur Absender von bereits importierten Mails
- UrgencyBooster kann nicht beim ersten Fetch greifen
- User muss erst importieren, dann whitelisten → ineffizient

### Lösung: Separate IMAP-Setup-Seite
**Route:** `/whitelist-imap-setup`

**Workflow:**
1. User wählt Mail-Account aus
2. System holt **nur IMAP-Header** (ENVELOPE) ohne Bodies
3. Dedupliziert Absender automatisch
4. Zeigt Bulk-UI: "Alle auswählen", einzeln abwählbar, "Hinzufügen"
5. Bulk-Insert in `trusted_senders` Tabelle
6. User kann dann Fetch starten → UrgencyBooster greift sofort

### Vorteile
- ✅ Saubere Trennung (Setup vs. Verwaltung)
- ✅ Funktioniert auch ohne DB-Daten
- ✅ Schnell (nur IMAP-Header, kein Full-Fetch)
- ✅ Bulk-fähig mit Vorauswahl
- ✅ Separate Navigation

---

## 🎯 Ziel-Features

| Feature | Beschreibung |
|---------|--------------|
| **Account-Auswahl** | Dropdown mit allen Mail-Accounts |
| **IMAP-Scan** | Nur ENVELOPE-Header holen (sehr schnell) |
| **Deduplizierung** | Automatisch Duplikate entfernen |
| **Bulk-UI** | "Alle auswählen" / "Abwählen" / "Hinzufügen" |
| **Preview** | Zeigt Name, Email, Mail-Count |
| **Progress** | Loading-Indicator während Scan |
| **Account-Binding** | Optional: Absender nur für diesen Account whitelisten |

---

## 📁 Dateistruktur

### Neue Dateien
```
templates/
└── whitelist_imap_setup.html    # Neue Template (ca. 400 Zeilen)

src/
└── 01_web_app.py                # +2 neue Routes
```

### Zu ändernde Dateien
```
templates/base.html               # Navigation: Link zu /whitelist-imap-setup
```

---

## 🔧 Implementation

### PHASE 1: Backend-Funktion (1-2h)

#### Schritt 1.1: IMAP Sender Scanner Service

**Datei:** `src/services/imap_sender_scanner.py` (NEU)

```python
"""
IMAP Sender Scanner - Holt nur Absender-Header ohne Full-Fetch
"""

import logging
from collections import Counter
from typing import Dict, List, Tuple
from imapclient import IMAPClient
from email.utils import parseaddr

logger = logging.getLogger(__name__)


def scan_account_senders(
    imap_server: str,
    imap_username: str,
    imap_password: str,
    folder: str = 'INBOX',
    batch_size: int = 500
) -> Dict:
    """
    Scannt einen Mail-Account nach allen Absendern ohne Full-Fetch.
    
    Args:
        imap_server: IMAP Server-Adresse
        imap_username: Login-Username
        imap_password: Login-Passwort
        folder: IMAP-Ordner (default: INBOX)
        batch_size: Anzahl Mails pro Batch (default: 500)
    
    Returns:
        {
            'success': bool,
            'senders': [
                {
                    'email': 'boss@firma.de',
                    'name': 'CEO Name',
                    'count': 47
                },
                ...
            ],
            'total_senders': int,
            'total_emails': int,
            'error': str (nur bei Fehler)
        }
    """
    try:
        # IMAP Connect
        logger.info(f"Connecting to {imap_server} as {imap_username}")
        
        client = IMAPClient(imap_server, use_uid=True)
        client.login(imap_username, imap_password)
        
        # Ordner auswählen (read-only!)
        client.select_folder(folder, readonly=True)
        
        # Alle UIDs holen
        messages = client.search(['ALL'])
        total_emails = len(messages)
        
        logger.info(f"Found {total_emails} emails in {folder}")
        
        if total_emails == 0:
            return {
                'success': True,
                'senders': [],
                'total_senders': 0,
                'total_emails': 0
            }
        
        # Sender-Counter und Namen
        sender_counter = Counter()
        sender_names = {}
        
        # Batch-Fetch für Performance (nur ENVELOPE!)
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i+batch_size]
            logger.info(f"Fetching batch {i//batch_size + 1}/{(len(messages)-1)//batch_size + 1}")
            
            # WICHTIG: Nur ENVELOPE holen (sehr schnell!)
            response = client.fetch(batch, ['ENVELOPE'])
            
            for uid, data in response.items():
                envelope = data.get(b'ENVELOPE')
                if envelope and envelope.from_:
                    # From-Field parsen
                    from_field = envelope.from_[0]
                    
                    # Email-Adresse zusammenbauen
                    mailbox = from_field.mailbox.decode('utf-8', errors='ignore') if from_field.mailbox else 'unknown'
                    host = from_field.host.decode('utf-8', errors='ignore') if from_field.host else 'unknown'
                    email = f"{mailbox}@{host}".lower()
                    
                    # Name extrahieren (falls vorhanden)
                    name = from_field.name.decode('utf-8', errors='ignore') if from_field.name else ''
                    
                    # Counter aktualisieren
                    sender_counter[email] += 1
                    
                    # Namen speichern (nur beim ersten Vorkommen)
                    if email not in sender_names and name:
                        sender_names[email] = name
        
        # IMAP Verbindung schließen
        client.logout()
        
        # Ergebnis formatieren (sortiert nach Häufigkeit)
        senders = [
            {
                'email': email,
                'name': sender_names.get(email, ''),
                'count': count
            }
            for email, count in sender_counter.most_common()
        ]
        
        logger.info(f"Scan complete: {len(senders)} unique senders from {total_emails} emails")
        
        return {
            'success': True,
            'senders': senders,
            'total_senders': len(senders),
            'total_emails': total_emails
        }
        
    except Exception as e:
        logger.error(f"IMAP Scan Error: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'senders': [],
            'total_senders': 0,
            'total_emails': 0
        }
```

---

### PHASE 2: API Endpoints (30min)

#### Schritt 2.1: Route in `src/01_web_app.py`

**Position:** Nach den anderen `/api/trusted-senders` Routes (ca. Zeile 2800)

```python
# ============================================================================
# IMAP SENDER SCANNER
# ============================================================================

from src.services.imap_sender_scanner import scan_account_senders


@app.route('/whitelist-imap-setup')
@login_required
def whitelist_imap_setup_page():
    """
    Separate Seite für IMAP-Setup (Pre-Fetch Absender-Scan).
    """
    master_key = session.get('master_key')
    if not master_key:
        flash('Bitte erst einloggen', 'warning')
        return redirect(url_for('login'))
    
    # Alle Mail-Accounts des Users laden
    mail_accounts = models.MailAccount.query.filter_by(
        user_id=current_user.id
    ).all()
    
    return render_template(
        'whitelist_imap_setup.html',
        mail_accounts=mail_accounts
    )


@app.route('/api/scan-account-senders/<int:account_id>', methods=['POST'])
@login_required
def api_scan_account_senders(account_id):
    """
    Scannt einen Mail-Account nach Absendern (nur IMAP-Header).
    
    POST Body (optional):
    {
        "folder": "INBOX"  // default: INBOX
    }
    
    Returns:
        {
            "success": true,
            "senders": [
                {"email": "boss@firma.de", "name": "CEO", "count": 47},
                ...
            ],
            "total_senders": 150,
            "total_emails": 2340
        }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            'success': False,
            'error': 'Nicht authentifiziert'
        }), 401
    
    # Account laden und Berechtigung prüfen
    account = models.MailAccount.query.filter_by(
        id=account_id,
        user_id=current_user.id
    ).first()
    
    if not account:
        return jsonify({
            'success': False,
            'error': 'Account nicht gefunden'
        }), 404
    
    # Optional: Ordner aus Request-Body
    data = request.get_json() or {}
    folder = data.get('folder', 'INBOX')
    
    # Credentials entschlüsseln
    try:
        imap_server = account.decrypted_imap_server
        imap_username = account.decrypted_imap_username
        imap_password = account.decrypted_imap_password
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        return jsonify({
            'success': False,
            'error': 'Fehler beim Entschlüsseln der Credentials'
        }), 500
    
    # IMAP-Scan durchführen
    result = scan_account_senders(
        imap_server=imap_server,
        imap_username=imap_username,
        imap_password=imap_password,
        folder=folder
    )
    
    return jsonify(result)


@app.route('/api/trusted-senders/bulk-add', methods=['POST'])
@login_required
def api_bulk_add_trusted_senders():
    """
    Fügt mehrere Absender auf einmal zur Whitelist hinzu.
    
    POST Body:
    {
        "senders": [
            {"pattern": "boss@firma.de", "type": "exact", "label": "Chef"},
            {"pattern": "@marketing.de", "type": "email_domain", "label": "Marketing"},
            ...
        ],
        "account_id": 1  // optional: null = global
    }
    
    Returns:
        {
            "success": true,
            "added": 15,
            "skipped": 2,
            "details": {
                "added": ["boss@firma.de", ...],
                "skipped": [
                    {"pattern": "duplicate@test.de", "reason": "Bereits vorhanden"},
                    ...
                ]
            }
        }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            'success': False,
            'error': 'Nicht authentifiziert'
        }), 401
    
    data = request.get_json()
    if not data or 'senders' not in data:
        return jsonify({
            'success': False,
            'error': 'Keine Absender angegeben'
        }), 400
    
    senders = data.get('senders', [])
    account_id = data.get('account_id')  # kann None sein (global)
    
    # Account validieren (falls angegeben)
    if account_id is not None:
        account = models.MailAccount.query.filter_by(
            id=account_id,
            user_id=current_user.id
        ).first()
        
        if not account:
            return jsonify({
                'success': False,
                'error': 'Account nicht gefunden'
            }), 404
    
    added = []
    skipped = []
    
    # Import-Funktion aus trusted_senders Service
    from src.services.trusted_senders import add_trusted_sender
    
    for sender_data in senders:
        try:
            pattern = sender_data.get('pattern', '').strip()
            pattern_type = sender_data.get('type', 'exact')
            label = sender_data.get('label', '').strip() or None
            
            if not pattern:
                skipped.append({
                    'pattern': pattern,
                    'reason': 'Leeres Pattern'
                })
                continue
            
            # Hinzufügen
            result = add_trusted_sender(
                user_id=current_user.id,
                sender_pattern=pattern,
                pattern_type=pattern_type,
                label=label,
                account_id=account_id,
                use_urgency_booster=True  # Default: Booster aktiviert
            )
            
            if result['success']:
                added.append(pattern)
            else:
                skipped.append({
                    'pattern': pattern,
                    'reason': result.get('error', 'Unbekannter Fehler')
                })
                
        except Exception as e:
            logger.error(f"Bulk-Add Error for {sender_data}: {e}")
            skipped.append({
                'pattern': sender_data.get('pattern', 'unknown'),
                'reason': str(e)
            })
    
    return jsonify({
        'success': True,
        'added': len(added),
        'skipped': len(skipped),
        'details': {
            'added': added,
            'skipped': skipped
        }
    })
```

---

### PHASE 3: Frontend Template (2-3h)

#### Schritt 3.1: Template `templates/whitelist_imap_setup.html`

```html
{% extends "base.html" %}

{% block title %}IMAP Schnell-Setup - Whitelist{% endblock %}

{% block content %}
<div class="container-fluid mt-4">
    <!-- Header -->
    <div class="row mb-4">
        <div class="col">
            <h2>🔍 IMAP Schnell-Setup</h2>
            <p class="text-muted">
                Scanne einen Mail-Account und füge Absender zur Whitelist hinzu 
                <strong>ohne</strong> Mails zu importieren.
            </p>
        </div>
        <div class="col-auto">
            <a href="/whitelist" class="btn btn-outline-secondary">
                ← Zurück zur Whitelist
            </a>
        </div>
    </div>

    <!-- Step 1: Account-Auswahl -->
    <div class="card border-0 shadow-sm bg-dark text-light mb-4">
        <div class="card-header" style="background: linear-gradient(135deg, #7c3aed, #5b21b6);">
            <h5 class="mb-0 text-light">📧 Schritt 1: Account wählen</h5>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-8">
                    <label class="form-label small text-light mb-2">
                        Mail-Account für Scan:
                    </label>
                    <select class="form-select bg-dark text-light border-secondary" id="scanAccountSelector">
                        <option value="">-- Bitte wählen --</option>
                        {% for account in mail_accounts %}
                        <option value="{{ account.id }}" 
                                data-server="{{ account.imap_server }}"
                                data-username="{{ account.decrypted_imap_username or account.name }}">
                            📧 {{ account.decrypted_imap_username or account.name }}
                            ({{ account.imap_server }})
                        </option>
                        {% endfor %}
                    </select>
                    
                    {% if mail_accounts|length == 0 %}
                    <div class="alert alert-warning mt-3">
                        ⚠️ Keine Mail-Accounts konfiguriert. 
                        <a href="/settings" class="alert-link">Account hinzufügen</a>
                    </div>
                    {% endif %}
                </div>
                
                <div class="col-md-4">
                    <label class="form-label small text-light mb-2">
                        IMAP-Ordner (optional):
                    </label>
                    <input type="text" class="form-control bg-dark text-light border-secondary" 
                           id="folderInput" value="INBOX" placeholder="INBOX">
                    <small class="text-light opacity-75">
                        Standard: INBOX
                    </small>
                </div>
            </div>
            
            <div class="mt-3">
                <button type="button" class="btn btn-primary btn-lg w-100" 
                        id="startScanBtn" disabled>
                    🔍 Absender scannen
                </button>
            </div>
        </div>
    </div>

    <!-- Step 2: Scan-Ergebnisse -->
    <div id="scanResultsContainer" style="display: none;">
        <div class="card border-0 shadow-sm bg-dark text-light">
            <div class="card-header d-flex justify-content-between align-items-center" 
                 style="background: linear-gradient(135deg, #0c4a6e, #082f49);">
                <div>
                    <h5 class="mb-0 text-light">📋 Schritt 2: Absender auswählen</h5>
                    <small class="text-light opacity-75">
                        <span id="totalSendersText">0</span> eindeutige Absender gefunden
                        aus <span id="totalEmailsText">0</span> Emails
                    </small>
                </div>
                <div>
                    <span class="badge bg-info" id="selectedCountBadge">0 ausgewählt</span>
                </div>
            </div>
            
            <div class="card-body">
                <!-- Bulk-Aktionen -->
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <div>
                        <button class="btn btn-sm btn-outline-light" id="selectAllBtn">
                            ✅ Alle auswählen
                        </button>
                        <button class="btn btn-sm btn-outline-light" id="deselectAllBtn">
                            ❌ Alle abwählen
                        </button>
                        <button class="btn btn-sm btn-outline-info" id="selectTop50Btn">
                            🔝 Top 50 auswählen
                        </button>
                    </div>
                    
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" 
                               id="accountSpecificToggle" checked>
                        <label class="form-check-label text-light" for="accountSpecificToggle">
                            Nur für diesen Account whitelisten
                        </label>
                    </div>
                </div>
                
                <!-- Sender-Liste -->
                <div id="scannedSendersList" class="border border-secondary rounded p-3" 
                     style="max-height: 500px; overflow-y: auto;">
                    <!-- Dynamic content -->
                </div>
                
                <!-- Hinzufügen-Button -->
                <div class="mt-3">
                    <button type="button" class="btn btn-success btn-lg w-100" 
                            id="bulkAddBtn" disabled>
                        ➕ <span id="selectedCountText">0</span> Absender zur Whitelist hinzufügen
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Toast Container für Notifications -->
<div class="position-fixed bottom-0 end-0 p-3" style="z-index: 11">
    <div id="toastContainer"></div>
</div>

<script nonce="{{ csp_nonce() }}">
// ========================================
// IMAP SETUP PAGE JavaScript
// ========================================

let selectedSenders = new Set();
let scannedData = [];
let currentAccountId = null;

// Helper: CSRF Token
function getCsrfToken() {
    const token = document.querySelector('meta[name="csrf-token"]');
    return token ? token.getAttribute('content') : '';
}

// Helper: Safe Fetch mit Error Handling
async function safeFetch(url, options = {}) {
    const csrfToken = getCsrfToken();
    if (csrfToken && !options.headers) {
        options.headers = {};
    }
    if (csrfToken && options.headers) {
        options.headers['X-CSRFToken'] = csrfToken;
    }
    
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            let errorMsg = `HTTP ${response.status}: ${response.statusText}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.error || errorMsg;
            } catch {}
            throw new Error(errorMsg);
        }
        return await response.json();
    } catch (error) {
        if (error instanceof TypeError && error.message.includes('fetch')) {
            throw new Error('Netzwerkfehler: Server nicht erreichbar');
        }
        throw error;
    }
}

// Helper: Toast Notification
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" 
                    data-bs-dismiss="toast"></button>
        </div>
    `;
    
    document.getElementById('toastContainer').appendChild(toast);
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
    
    // Auto-remove nach 5 Sekunden
    setTimeout(() => toast.remove(), 5000);
}

// Helper: HTML Escape
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Event: Account-Auswahl aktiviert Scan-Button
document.getElementById('scanAccountSelector').addEventListener('change', function() {
    const accountId = this.value;
    document.getElementById('startScanBtn').disabled = !accountId;
    currentAccountId = accountId ? parseInt(accountId) : null;
});

// Event: Scan starten
document.getElementById('startScanBtn').addEventListener('click', async function() {
    const accountId = document.getElementById('scanAccountSelector').value;
    const folder = document.getElementById('folderInput').value.trim() || 'INBOX';
    
    if (!accountId) {
        showToast('Bitte Account auswählen', 'warning');
        return;
    }
    
    const btn = this;
    btn.disabled = true;
    btn.innerHTML = '⏳ Scanne IMAP-Server...';
    
    try {
        const response = await safeFetch(`/api/scan-account-senders/${accountId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ folder: folder })
        });
        
        if (!response.success) {
            showToast(`❌ Fehler: ${response.error}`, 'danger');
            return;
        }
        
        // Ergebnisse speichern und anzeigen
        scannedData = response.senders;
        displayScannedSenders(response);
        
        showToast(`✅ ${response.total_senders} Absender gefunden!`, 'success');
        
    } catch (error) {
        showToast(`❌ Fehler: ${error.message}`, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🔍 Absender scannen';
    }
});

// Funktion: Gescannte Absender anzeigen
function displayScannedSenders(data) {
    const container = document.getElementById('scanResultsContainer');
    const list = document.getElementById('scannedSendersList');
    
    // Header-Texte aktualisieren
    document.getElementById('totalSendersText').textContent = data.total_senders;
    document.getElementById('totalEmailsText').textContent = data.total_emails;
    
    // Sender-Liste erstellen
    list.innerHTML = data.senders.map((sender, idx) => {
        const email = sender.email || '';
        const name = sender.name || '';
        const count = sender.count || 0;
        
        return `
            <div class="form-check mb-2 p-2 border-bottom border-secondary sender-item"
                 data-index="${idx}">
                <input class="form-check-input sender-checkbox" type="checkbox" 
                       id="sender_${idx}" 
                       data-email="${escapeHtml(email)}" 
                       data-name="${escapeHtml(name)}">
                <label class="form-check-label w-100" for="sender_${idx}">
                    <div class="d-flex justify-content-between align-items-center">
                        <div style="flex-grow: 1;">
                            <strong class="text-light">${escapeHtml(email)}</strong>
                            ${name ? `<div class="small text-light opacity-75">${escapeHtml(name)}</div>` : ''}
                        </div>
                        <span class="badge bg-secondary">${count} Mails</span>
                    </div>
                </label>
            </div>
        `;
    }).join('');
    
    // Container anzeigen
    container.style.display = 'block';
    container.scrollIntoView({ behavior: 'smooth' });
    
    // Event Listeners für Checkboxen
    document.querySelectorAll('.sender-checkbox').forEach(cb => {
        cb.addEventListener('change', updateBulkAddButton);
    });
    
    // Initial: Alle abgewählt
    selectedSenders.clear();
    updateBulkAddButton();
}

// Funktion: Bulk-Add Button aktualisieren
function updateBulkAddButton() {
    const checkboxes = document.querySelectorAll('.sender-checkbox:checked');
    const count = checkboxes.length;
    
    selectedSenders.clear();
    checkboxes.forEach(cb => {
        selectedSenders.add({
            email: cb.getAttribute('data-email'),
            name: cb.getAttribute('data-name')
        });
    });
    
    const btn = document.getElementById('bulkAddBtn');
    const countText = document.getElementById('selectedCountText');
    const countBadge = document.getElementById('selectedCountBadge');
    
    countText.textContent = count;
    countBadge.textContent = `${count} ausgewählt`;
    btn.disabled = count === 0;
}

// Event: Alle auswählen
document.getElementById('selectAllBtn').addEventListener('click', function() {
    document.querySelectorAll('.sender-checkbox').forEach(cb => cb.checked = true);
    updateBulkAddButton();
});

// Event: Alle abwählen
document.getElementById('deselectAllBtn').addEventListener('click', function() {
    document.querySelectorAll('.sender-checkbox').forEach(cb => cb.checked = false);
    updateBulkAddButton();
});

// Event: Top 50 auswählen
document.getElementById('selectTop50Btn').addEventListener('click', function() {
    const checkboxes = document.querySelectorAll('.sender-checkbox');
    checkboxes.forEach((cb, idx) => {
        cb.checked = idx < 50;
    });
    updateBulkAddButton();
});

// Event: Bulk hinzufügen
document.getElementById('bulkAddBtn').addEventListener('click', async function() {
    const checkboxes = document.querySelectorAll('.sender-checkbox:checked');
    const accountSpecific = document.getElementById('accountSpecificToggle').checked;
    
    if (checkboxes.length === 0) {
        showToast('Keine Absender ausgewählt', 'warning');
        return;
    }
    
    // Senders-Array erstellen
    const senders = Array.from(checkboxes).map(cb => ({
        pattern: cb.getAttribute('data-email'),
        type: 'exact',  // Default: Exakte Email-Adresse
        label: cb.getAttribute('data-name') || null
    }));
    
    // Account-ID bestimmen
    const accountId = accountSpecific ? currentAccountId : null;
    
    // Bestätigung
    const accountText = accountSpecific ? 'für diesen Account' : 'global (alle Accounts)';
    if (!confirm(`${senders.length} Absender ${accountText} zur Whitelist hinzufügen?`)) {
        return;
    }
    
    const btn = this;
    btn.disabled = true;
    btn.innerHTML = '⏳ Füge hinzu...';
    
    try {
        const response = await safeFetch('/api/trusted-senders/bulk-add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                senders: senders,
                account_id: accountId
            })
        });
        
        if (response.success) {
            const skippedText = response.skipped > 0 
                ? ` (${response.skipped} bereits vorhanden)` 
                : '';
            showToast(
                `✅ ${response.added} Absender hinzugefügt!${skippedText}`, 
                'success'
            );
            
            // Scan-Ergebnisse zurücksetzen
            document.getElementById('scanResultsContainer').style.display = 'none';
            document.getElementById('scanAccountSelector').value = '';
            document.getElementById('startScanBtn').disabled = true;
            selectedSenders.clear();
            
            // Optional: Zur Whitelist-Seite weiterleiten
            setTimeout(() => {
                if (confirm('Zur Whitelist-Verwaltung wechseln?')) {
                    window.location.href = '/whitelist';
                }
            }, 1500);
        } else {
            showToast(`❌ Fehler: ${response.error}`, 'danger');
        }
        
    } catch (error) {
        showToast(`❌ Fehler: ${error.message}`, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '➕ <span id="selectedCountText">0</span> Absender zur Whitelist hinzufügen';
        updateBulkAddButton();
    }
});
</script>
{% endblock %}
```

---

### PHASE 4: Navigation (15min)

#### Schritt 4.1: Link in `templates/base.html`

**Position:** Nach dem `/whitelist` Link (ca. Zeile 48)

```html
<a class="nav-link" href="/whitelist">🛡️ Whitelist</a>
<a class="nav-link" href="/whitelist-imap-setup">⚡ IMAP Setup</a>  <!-- NEU -->
<a class="nav-link" href="/settings">⚙️ Einstellungen</a>
```

---

## 🧪 Testing & Verification

### Test 1: Backend-Service testen

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate

# Python-Syntax prüfen
python -m py_compile src/services/imap_sender_scanner.py

# Manuell testen (angepasst mit echten Credentials)
python3 << 'EOF'
from src.services.imap_sender_scanner import scan_account_senders

result = scan_account_senders(
    imap_server='mail.gmx.net',
    imap_username='your@email.com',
    imap_password='your_password',
    folder='INBOX'
)

print(f"Success: {result['success']}")
print(f"Total Senders: {result.get('total_senders', 0)}")
print(f"Total Emails: {result.get('total_emails', 0)}")

# Ersten 5 Sender anzeigen
for sender in result.get('senders', [])[:5]:
    print(f"  {sender['email']} ({sender['count']} Mails) - {sender['name']}")
EOF
```

**Expected Output:**
```
Success: True
Total Senders: 150
Total Emails: 2340
  boss@firma.de (47 Mails) - CEO Name
  hr@firma.de (23 Mails) - HR Department
  ...
```

### Test 2: API Endpoint testen

```bash
# Server starten
flask run

# In neuem Terminal: API testen
curl -X POST http://localhost:5000/api/scan-account-senders/1 \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: YOUR_TOKEN" \
  -b "session=YOUR_SESSION_COOKIE" \
  -d '{"folder": "INBOX"}'
```

**Expected Response:**
```json
{
  "success": true,
  "senders": [
    {
      "email": "boss@firma.de",
      "name": "CEO Name",
      "count": 47
    },
    ...
  ],
  "total_senders": 150,
  "total_emails": 2340
}
```

### Test 3: Frontend-UI testen

```bash
# Browser öffnen
http://localhost:5000/whitelist-imap-setup

# Schritte:
1. Account auswählen → ✅ Scan-Button aktiviert
2. "Absender scannen" → ✅ Loading-Indicator
3. Ergebnisse angezeigt → ✅ Liste mit Checkboxen
4. "Alle auswählen" → ✅ Alle Checkboxen aktiviert
5. "Hinzufügen" → ✅ Bulk-Insert in DB
6. Toast-Notification → ✅ "X Absender hinzugefügt"
```

### Test 4: Bulk-Add validieren

```bash
# DB prüfen
sqlite3 emails.db << 'EOF'
SELECT 
    sender_pattern, 
    pattern_type, 
    label, 
    account_id,
    use_urgency_booster
FROM trusted_senders
WHERE user_id = 1
ORDER BY created_at DESC
LIMIT 10;
EOF
```

**Expected Output:**
```
boss@firma.de|exact|CEO Name|1|1
hr@firma.de|exact|HR Department|1|1
...
```

---

## 📊 Performance-Erwartungen

| Operation | Zeit | Details |
|-----------|------|---------|
| **IMAP Connect** | 1-3s | Je nach Server |
| **ENVELOPE Fetch** | 0.5-2s / 500 Mails | Sehr schnell (keine Bodies) |
| **1000 Mails scannen** | ~5-10s | 2x Batch à 500 |
| **5000 Mails scannen** | ~30-60s | 10x Batch à 500 |
| **Deduplizierung** | <1s | Python Counter ist sehr effizient |
| **Bulk-Insert 50 Sender** | 1-2s | SQLAlchemy Batch-Insert |

**Vergleich:**
- Full-Fetch 1000 Mails: **~15-30 Minuten** (mit Body + AI)
- Header-Scan 1000 Mails: **~5-10 Sekunden** (nur ENVELOPE)

→ **90-98% schneller!** 🚀

---

## 🔒 Security-Überlegungen

### ✅ Was gut ist:
- IMAP-Credentials werden nur aus der DB geladen (verschlüsselt)
- Master-Key aus Session (Zero-Knowledge)
- Readonly IMAP-Verbindung
- Keine Credentials in Logs/Responses

### ⚠️ Potenzielle Risiken:
- **IMAP-Timeout**: Bei sehr großen Mailboxen (>50k Mails) könnte Timeout auftreten
  - **Lösung:** Batch-Size reduzieren oder Pagination einführen
- **Rate Limiting**: Manche IMAP-Server limitieren schnelle Requests
  - **Lösung:** Sleep-Delays zwischen Batches (z.B. 0.5s)

---

## 📝 Changelog-Eintrag

**Für:** `docs/CHANGELOG.md`

```markdown
### Added - Phase X.3: IMAP Schnell-Setup (2026-01-07)

#### Neue `/whitelist-imap-setup` Seite

**Features:**
- ✅ **Separate Setup-Seite**: Pre-Fetch Absender-Scan ohne Full-Import
- ✅ **IMAP-Header-Scan**: Nur ENVELOPE-Daten (sehr schnell)
- ✅ **Deduplizierung**: Automatisch Duplikate entfernen
- ✅ **Bulk-UI**: "Alle auswählen" / "Top 50" / einzeln abwählbar
- ✅ **Account-Binding**: Optional nur für gewählten Account whitelisten
- ✅ **Performance**: ~90-98% schneller als Full-Fetch (z.B. 1000 Mails in 5-10s)

**Use Case:**
1. Vor erstem Email-Import: Wichtige Absender whitelisten
2. UrgencyBooster greift sofort beim Fetch
3. Keine unnötigen AI-Klassifikationen für bereits vertraute Sender

**Technische Details:**
- Route: `/whitelist-imap-setup` in `src/01_web_app.py`
- Service: `src/services/imap_sender_scanner.py` (NEU)
- Template: `templates/whitelist_imap_setup.html` (NEU)
- API: `POST /api/scan-account-senders/<id>` + `POST /api/trusted-senders/bulk-add`
- Navigation: Link in `templates/base.html`

**Performance:**
- 1000 Mails scannen: 5-10 Sekunden (nur Header)
- 50 Sender bulk-hinzufügen: 1-2 Sekunden
- Vergleich: Full-Fetch würde 15-30 Minuten dauern
```

---

## ✅ Implementation Checklist

### Backend (2-3h)
- [ ] `src/services/imap_sender_scanner.py` erstellen
- [ ] Funktion `scan_account_senders()` implementieren
- [ ] Python-Syntax validieren (`python -m py_compile`)
- [ ] Manueller Test mit echten Credentials

### API Endpoints (1h)
- [ ] Route `/whitelist-imap-setup` in `src/01_web_app.py`
- [ ] API `/api/scan-account-senders/<id>` implementieren
- [ ] API `/api/trusted-senders/bulk-add` implementieren
- [ ] Error Handling + Logging
- [ ] Curl-Test durchführen

### Frontend (2h)
- [ ] Template `templates/whitelist_imap_setup.html` erstellen
- [ ] Account-Selector mit Validierung
- [ ] Scan-Button mit Loading-State
- [ ] Sender-Liste mit Checkboxen
- [ ] Bulk-Actions ("Alle", "Top 50", "Abwählen")
- [ ] Bulk-Add mit Account-Toggle
- [ ] Toast-Notifications

### Navigation (15min)
- [ ] Link in `templates/base.html` hinzufügen
- [ ] Browser-Test

### Testing (1h)
- [ ] Backend-Service testen
- [ ] API-Endpoints testen
- [ ] UI-Flow End-to-End testen
- [ ] DB-Validierung (Bulk-Insert prüfen)
- [ ] Performance-Messung (Zeit für 1000 Mails)

### Documentation (30min)
- [ ] Changelog-Eintrag in `docs/CHANGELOG.md`
- [ ] README-Update (falls nötig)
- [ ] Git-Commit mit aussagekräftiger Message

---

## 🚀 Deployment-Anleitung

### Schritt 1: Code deployen

```bash
cd /home/thomas/projects/KI-Mail-Helper
git pull  # oder git commit + push

# Dependencies prüfen (keine neuen nötig)
source venv/bin/activate
pip list | grep imapclient  # sollte vorhanden sein
```

### Schritt 2: Server neu starten

```bash
# Wenn systemd service
sudo systemctl restart mail-helper.service

# Oder manuell
flask run
```

### Schritt 3: Smoke Test

```bash
# Browser öffnen
curl -I http://localhost:5000/whitelist-imap-setup

# Expected: HTTP/1.1 200 OK
```

---

## 📈 Success Metrics

| Metric | Ziel | Messung |
|--------|------|---------|
| **Scan-Zeit (1000 Mails)** | <15s | Mit Timer im Frontend |
| **Bulk-Add (50 Sender)** | <3s | Mit Timer im Frontend |
| **User Adoption** | 80%+ nutzen Setup vor Fetch | Analytics |
| **Fehlerrate** | <2% | Server-Logs |
| **Page Load** | <500ms | Browser DevTools |

---

## 🎯 Zusammenfassung

### Was wird implementiert?
- Neue Seite `/whitelist-imap-setup` für Pre-Fetch Absender-Scan
- IMAP-Header-Scan ohne Full-Fetch (90-98% schneller)
- Bulk-UI mit "Alle auswählen" / "Top 50" / einzeln abwählbar
- Account-spezifisches oder globales Whitelisting

### Warum ist das wichtig?
- **Löst Schwanzbeißer-Problem:** User kann vor erstem Fetch whitelisten
- **UrgencyBooster-Effektivität:** Greift sofort beim initialen Import
- **Performance:** Spart massive Zeit (5-10s statt 15-30min für 1000 Mails)
- **User Experience:** Klar getrennte Setup- und Verwaltungs-Seiten

### Aufwand vs. Nutzen
- **Aufwand:** 4-6 Stunden Implementation + Testing
- **Nutzen:** Feature macht UrgencyBooster erst vollständig nutzbar
- **ROI:** Sehr hoch - kritischer Missing Link geschlossen

---

## 📞 Support & Feedback

Falls Probleme auftreten:
1. Logs prüfen: `tail -f logs/app.log`
2. Browser Console: F12 → Console → Errors?
3. IMAP-Verbindung testen: `/imap-diagnostics`

Bei Fragen oder Bugs: Issue im Projekt-Repo erstellen.

---

**Happy Coding! 🚀**
