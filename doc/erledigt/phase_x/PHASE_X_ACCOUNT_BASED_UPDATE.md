# ✅ Phase X - Account-Based Whitelist Umbauten

## 1. **Migration ph19 erstellt & deployed** ✅

**Datei:** `migrations/versions/ph19_trusted_senders_account_id.py`

**Änderungen:**
- Neue Spalte: `account_id` (Foreign Key zu `mail_accounts`)
- Neuer Index: `ix_trusted_senders_account_pattern` auf (account_id, sender_pattern)
- Bestehende Spalten: user_id bleibt für globale Whitelists

**Schema-Logik:**
```
account_id = NULL  →  Global für alle Accounts des Users
account_id != NULL →  Nur für dieses spezifische Account
```

**Status:** Deployed ✅ (verified with sqlite3)

---

## 2. **Model TrustedSender aktualisiert** ✅

**Datei:** `src/02_models.py` (Lines 1186-1234)

**Neue Felder:**
```python
account_id = Column(Integer, ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=True)
mail_account = relationship("MailAccount", foreign_keys=[account_id])
```

**Relationship:** Kann jetzt auf das MailAccount zugreifen

**Status:** Updated ✅

---

## 3. **Service-Methoden account-aware gemacht** ✅

### **A) `is_trusted_sender()`**

**Neue Signatur:**
```python
@staticmethod
def is_trusted_sender(db, user_id: int, sender_email: str, account_id: Optional[int] = None) -> Optional[Dict]
```

**Verhalten:**
- Wenn `account_id=None`: Nur globale Whitelists (account_id=NULL)
- Wenn `account_id` gegeben: 
  1. Erst account-spezifische (account_id=X) prüfen
  2. Dann globale (account_id=NULL) prüfen
  3. Account-spezifische haben Priorität

**Return:** Zusätzlich jetzt `'account_id'` im Dict

**Status:** Implemented ✅

---

### **B) `add_trusted_sender()`**

**Neue Signatur:**
```python
@staticmethod
def add_trusted_sender(
    db,
    user_id: int,
    sender_pattern: str,
    pattern_type: str,
    label: Optional[str] = None,
    account_id: Optional[int] = None  # NEU
) -> Dict
```

**Features:**
- Limit-Check ist jetzt account-aware (pro Account max 500 Sender)
- Uniqueness-Check prüft (user_id, sender_pattern, account_id) Kombination
- Speichert `account_id` mit in die DB

**Status:** Implemented ✅

---

## 4. **DB Schema Verification** ✅

```
╔════════════════════════════════════════════════════════════════╗
║  trusted_senders Table (aktualisiertes Schema)                ║
╠════════════════════════════════════════════════════════════════╣
║ id                INTEGER PRIMARY KEY                         ║
║ user_id           INTEGER NOT NULL  (FK → users.id)           ║
║ account_id        INTEGER NULL      (FK → mail_accounts.id)   ║
║ sender_pattern    VARCHAR(255) NOT NULL                       ║
║ pattern_type      VARCHAR(20) NOT NULL                        ║
║ label             VARCHAR(100)                                ║
║ use_urgency_booster BOOLEAN DEFAULT 1                         ║
║ added_at          DATETIME NOT NULL                           ║
║ last_seen_at      DATETIME                                    ║
║ email_count       INTEGER DEFAULT 0                           ║
║                                                                ║
║ Constraints:                                                   ║
║ - PRIMARY KEY (id)                                            ║
║ - UNIQUE (user_id, sender_pattern)  [bestehend]              ║
║ - FK (user_id) REFERENCES users(id) ON DELETE CASCADE         ║
║ - FK (account_id) REFERENCES mail_accounts(id) ON DELETE CASCADE
║                                                                ║
║ Indexes:                                                       ║
║ - ix_trusted_senders_user_pattern (user_id, sender_pattern)   ║
║ - ix_trusted_senders_account_pattern (account_id, sender_pattern)
╚════════════════════════════════════════════════════════════════╝
```

---

## 5. **Nächste Schritte (für dich):**

### **TODO 1: API Endpoints aktualisieren**
**Datei:** `src/01_web_app.py` (Lines ~7270-7520)

Die 7 Endpoints müssen `account_id` akzeptieren:
```python
# BEISPIEL
def api_get_trusted_senders():
    user_id = current_user.id
    account_id = request.args.get('account_id', type=int)  # NEU
    
    senders = db.query(TrustedSender).filter(
        TrustedSender.user_id == user_id,
        (TrustedSender.account_id == account_id) | (TrustedSender.account_id.is_(None))
    ).all()
```

### **TODO 2: UI Account-Selector hinzufügen**
**Datei:** `templates/settings.html` (Phase X Section)

```html
<!-- Neuer Selector oben in der Phase X Section -->
<select id="accountSelect" onchange="loadWhitelistForAccount()">
  <option value="">📌 Global (alle Accounts)</option>
  <option value="1">📧 Account 1: martina</option>
  <option value="2">📧 Account 2: thomas-beispiel-firma</option>
</select>

<div id="trustedSendersList" class="suggestions-list">
  <!-- Hier werden die Sender gefiltert nach ausgewähltem Account angezeigt -->
</div>
```

### **TODO 3: JavaScript für Account-Filter**
```javascript
function loadWhitelistForAccount() {
  const accountId = document.getElementById('accountSelect').value;
  
  fetch(`/api/trusted-senders?account_id=${accountId}`)
    .then(res => res.json())
    .then(data => {
      // Render trusted senders for this account
      renderTrustedSenders(data);
    });
}
```

---

## 6. **Verwendungsbeispiele**

### **Szenario A: Global whitelist (für alle Accounts)**
```python
TrustedSenderManager.add_trusted_sender(
    db=db,
    user_id=1,
    sender_pattern="chef@firma.de",
    pattern_type="exact",
    label="CEO",
    account_id=None  # Global!
)

# Ergebnis in DB:
# user_id=1, account_id=NULL, sender_pattern=chef@firma.de
```

### **Szenario B: Account-spezifische whitelist**
```python
TrustedSenderManager.add_trusted_sender(
    db=db,
    user_id=1,
    sender_pattern="admin@example.com",
    pattern_type="email_domain",
    label="Beispiel-Firma Admin",
    account_id=2  # Nur für "thomas-beispiel-firma" Account!
)

# Ergebnis in DB:
# user_id=1, account_id=2, sender_pattern=@example.com
```

### **Szenario C: Matching mit is_trusted_sender()**
```python
# User 1 hat diese Whitelists:
# 1. user_id=1, account_id=NULL, pattern=chef@firma.de (global)
# 2. user_id=1, account_id=2, pattern=@example.com (nur account 2)

# Abfrage für Account 2:
result = TrustedSenderManager.is_trusted_sender(
    db=db,
    user_id=1,
    sender_email="admin@example.com",
    account_id=2
)
# Result: Matched! (account-spezifisch gefunden)

# Abfrage für Account 1 mit gleicher Email:
result = TrustedSenderManager.is_trusted_sender(
    db=db,
    user_id=1,
    sender_email="admin@example.com",
    account_id=1
)
# Result: None (nicht matched - account 1 hat keine @example.com)

# Aber global whitelisted chef@firma.de funktioniert auf allen Accounts:
result = TrustedSenderManager.is_trusted_sender(
    db=db,
    user_id=1,
    sender_email="chef@firma.de",
    account_id=2  # Egal welcher Account
)
# Result: Matched! (global gefunden)
```

---

## 7. **Priority-Logik (wichtig!)**

Wenn sowohl account-spezifische AND globale Whitelists existieren:

```
1. Account-spezifische Whitelists werden ZUERST gepräft
2. Globale Whitelists sind Fallback
3. Account-spezifische haben **PRIORITÄT**

Beispiel:
  User hat:
  - Global: pattern=@firma.de (akzeptiert ALLE @firma.de)
  - Account 2 nur: pattern=boss@firma.de (nur dieser)
  
  Email: boss@firma.de auf Account 2
  → Matched account-spezifische zuerst → Verwendet die spezifischeren Einstellungen!
```

---

## ✅ **Zusammenfassung: Was ist DONE**

| Komponente | Status | Details |
|-----------|--------|---------|
| Migration ph19 | ✅ Deployed | account_id Spalte + Indexes |
| TrustedSender Model | ✅ Updated | account_id Column + Relationship |
| is_trusted_sender() | ✅ Implemented | Account-aware matching |
| add_trusted_sender() | ✅ Implemented | Account-aware storage |
| API Endpoints | ⏳ TODO | Braucht account_id Parameter |
| UI Account-Selector | ⏳ TODO | Dropdown für Account-Auswahl |
| JS Event Listener | ⏳ TODO | Nachladen beim Account-Wechsel |

---

## 🎯 **NÄCHSTES ZIEL:**

Die API-Endpoints in `src/01_web_app.py` anpassen um:
1. `account_id` von Query-Parametern akzeptieren
2. Alle Queries mit Account-Filter versehen
3. Die 7 Endpoints neu testen

**Brauchst du dass ich das mache?**
