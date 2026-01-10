# Phase 13C: Fetch-Filter & Konfiguration

**Zeitraum:** 2026-01-03 bis 2026-01-04  
**Commits:** bec3526, e945315, 2c7089b  
**Status:** ✅ Abgeschlossen

## Übersicht

Implementierung von konfigurierbaren Fetch-Filtern für intelligentes Mail-Synchronisieren. User können jetzt präzise steuern **welche** Mails **wie** abgerufen werden.

## Features

### Part 4: Basis-Konfiguration (User-global)
- **Mails pro Ordner:** 10-1000, Standard 100
- **Max. Gesamt:** 0-10000 (0 = unbegrenzt)
- **Delta-Sync:** Toggle für "nur neue Mails seit letztem Sync"

### Part 5: Erweiterte Filter (Initial: User-global)
- **SINCE-Datum:** Nur Mails ab bestimmtem Datum (z.B. "2025-12-01")
- **UNSEEN-Only:** Nur ungelesene Mails (IMAP UNSEEN Flag)
- **Include-Ordner:** Nur bestimmte Ordner synchronisieren
- **Exclude-Ordner:** Bestimmte Ordner ausschließen
- **Live-Vorschau:** Zeigt geschätzte Mail-Anzahl + Remote/Lokal/Delta

### Part 6: Account-spezifische Filter (Refactoring)
**Problem:** Filter waren User-global → Unflexibel bei mehreren Accounts

**Lösung:** Filter pro Account speichern
- Migration: `users.fetch_*` → `mail_accounts.fetch_*`
- Automatische Datenmigration (User-Filter auf alle Accounts kopiert)
- Neue API: `/account/<id>/fetch-filters`
- UI: Account-Select lädt Filter automatisch
- localStorage: Behält Account-Auswahl nach Speichern
- Badge: ⚙️ zeigt welche Accounts Filter haben

## Wichtiger Fix (2c7089b)

### Problem
Filter wurden nur beim **allerersten Sync** angewendet:
```python
if not account.initial_sync_done:
    # Filter NUR beim ersten Mal
```

**Konsequenz:**
- User fetched ohne Filter → 5000 Mails
- Setzt nachträglich Filter → werden ignoriert!
- Musste Account löschen und neu anlegen 😤

### Lösung
Filter gelten jetzt **bei jedem Fetch**:
```python
# UNSEEN: Immer aktiv
fetch_unseen = account_unseen_only

# SINCE: Aktiv außer bei Delta-Sync (uid_range effizienter)
if not uid_range and account_since_date:
    fetch_since = datetime.combine(account_since_date, datetime.min.time())
```

**Vorteile:**
- ✅ Account ohne Filter anlegen und testen
- ✅ Filter nachträglich setzen und erneut fetchen
- ✅ Filter flexibel anpassen ohne Account-Neuanlegen

## Filter-Logik im Detail

### Ordner-Filter
**Gelten:** Immer (bei Initial und Delta)
```python
if include_folders and folder_name not in include_folders:
    continue  # Ordner überspringen
if exclude_folders and folder_name in exclude_folders:
    continue  # Ordner überspringen
```

### UNSEEN-Filter
**Gelten:** Immer wenn gesetzt
```python
fetch_unseen = account_unseen_only  # True/False
fetcher.fetch_new_emails(..., unseen_only=fetch_unseen)
```

### SINCE-Filter
**Gelten:** Immer, **außer bei Delta-Sync**
```python
if not uid_range and account_since_date:
    fetch_since = datetime.combine(account_since_date, datetime.min.time())
```

**Warum Ausnahme bei Delta?**
- Delta-Sync nutzt UID-Range: `(last_uid+1):*` = "nur neue"
- SINCE wäre redundant und langsamer
- UID-basiert ist die effizienteste Methode

## Datenbank-Änderungen

### Migration: ph13c_p5_fetch_filters
```sql
ALTER TABLE users ADD COLUMN fetch_since_date DATE;
ALTER TABLE users ADD COLUMN fetch_unseen_only BOOLEAN DEFAULT 0;
ALTER TABLE users ADD COLUMN fetch_include_folders TEXT;
ALTER TABLE users ADD COLUMN fetch_exclude_folders TEXT;
```

### Migration: ph13c_p6_move_filters_to_accounts
```sql
-- Von users → mail_accounts verschieben
ALTER TABLE mail_accounts ADD COLUMN fetch_since_date DATE;
ALTER TABLE mail_accounts ADD COLUMN fetch_unseen_only BOOLEAN DEFAULT 0;
ALTER TABLE mail_accounts ADD COLUMN fetch_include_folders TEXT;
ALTER TABLE mail_accounts ADD COLUMN fetch_exclude_folders TEXT;

-- User-Filter auf alle Accounts kopieren (Datenmigration)
UPDATE mail_accounts SET fetch_* = (SELECT fetch_* FROM users WHERE ...)

-- Alte Spalten entfernen
ALTER TABLE users DROP COLUMN fetch_since_date;
ALTER TABLE users DROP COLUMN fetch_unseen_only;
ALTER TABLE users DROP COLUMN fetch_include_folders;
ALTER TABLE users DROP COLUMN fetch_exclude_folders;
```

## API-Erweiterungen

### Quick Count API
**Endpoint:** `GET /account/<id>/mail-count`

**Neu in Response:**
```json
{
  "folders": {
    "INBOX": {"total": 28, "unseen": 11},
    "Archiv": {"total": 2, "unseen": 2}
  },
  "summary": {
    "total_remote": 49,
    "total_unseen": 13,
    "total_local": 47,
    "delta": 2
  }
}
```

### Filter-Laden API
**Endpoint:** `GET /account/<id>/fetch-filters`

**Response:**
```json
{
  "account_id": 1,
  "account_name": "martina",
  "since_date": "2025-12-01",
  "unseen_only": false,
  "include_folders": ["INBOX", "Work"],
  "exclude_folders": ["Spam", "Trash"],
  "has_filters": true
}
```

### Save Config
**Endpoint:** `POST /settings/fetch-config`

**Neu:** Benötigt `account_id` (Hidden Field)
```python
account_id = request.form.get('account_id')  # Required!
account.fetch_since_date = since_date
account.fetch_unseen_only = unseen_only
account.fetch_include_folders = json.dumps(include_folders)
```

## UI/UX-Verbesserungen

### Alert-Boxen statt Cards
**Vorher:** Dunkle Card-Container → Ordnernamen unsichtbar  
**Nachher:** `alert-success` (grün) + `alert-warning` (gelb)

### Mail-Count Format
**Vorher:** `28` + separater Badge `11 ungelesen`  
**Nachher:** `28/11` (Total/Ungelesen) - konsistent mit Quick Count

### State-Management
**Problem:** Nach Speichern alles weg (Account-Auswahl, Filter, Vorschau)

**Lösung:**
```javascript
// Speichere Account-ID
localStorage.setItem('lastSelectedAccountId', accountId);

// Nach Page-Load: Restore
window.addEventListener('load', () => {
    const lastAccountId = localStorage.getItem('lastSelectedAccountId');
    if (lastAccountId) {
        folderAccountSelect.value = lastAccountId;
        folderAccountSelect.dispatchEvent(new Event('change'));
        setTimeout(() => loadFoldersBtn.click(), 500);
    }
});
```

### Klarere Texte
**Vorher:** "Erweiterte Filter (Initial-Sync)" → irreführend  
**Nachher:** 
```
📋 Erweiterte Filter
Diese Filter gelten bei jedem Fetch (außer SINCE bei Delta-Sync).
Perfekt um große Accounts schrittweise zu synchronisieren.
```

### Include/Exclude Hints
```html
<!-- Include -->
<small class="text-muted">
    💡 Keine Auswahl = Alle Ordner werden synchronisiert
</small>

<!-- Exclude -->
<small class="text-muted">
    Standard: Keine Ordner ausgeschlossen. Wähle gezielt aus.
</small>
```

## Typische Use Cases

### 1. Großer alter Account (10.000+ Mails)
**Problem:** Zu viele Mails auf einmal

**Lösung:**
1. SINCE auf "2025-12-01" setzen → nur letzte 2 Monate
2. Exclude: Spam, Trash, Sent
3. Nach erstem Fetch: SINCE entfernen für Delta-Sync
4. Schrittweise ältere Mails nachholen

### 2. Newsletter-Account
**Problem:** 95% Newsletter, 5% wichtige Mails

**Lösung:**
1. UNSEEN-Only aktivieren
2. Exclude: Newsletter-Ordner
3. Nur neue wichtige Mails landen in DB

### 3. Multi-Account Setup
**Problem:** Privat + Firma brauchen unterschiedliche Filter

**Lösung:**
- Privat-Account: SINCE 2025-01-01, Include [INBOX, Family]
- Firma-Account: UNSEEN-Only, Exclude [Marketing, HR]
- Jeder Account hat eigene Filter, unabhängig konfigurierbar

### 4. Schrittweises Onboarding
**Workflow:**
1. Account anlegen, "Quick Count" klicken
2. Sieht: 5000 Mails, 200 ungelesen
3. Entscheidet: "Erstmal nur ungelesene"
4. Setzt UNSEEN-Only, klickt "Abrufen" → 200 Mails
5. Später: UNSEEN-Only ausschalten für vollständigen Sync

## Technische Details

### JSON-Serialisierung
```python
# Speichern
user.fetch_include_folders = json.dumps(["INBOX", "Work"])

# Laden
include_folders = json.loads(user.fetch_include_folders)
```

### Error Handling
```javascript
// API-Fehler (500) abfangen
if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Server-Fehler (${response.status}): ${errorText}`);
}
```

### DOM-Manipulation
**Problem:** Template-Strings mit `innerHTML` → Text unsichtbar

**Lösung:** Native DOM-Methoden
```javascript
const label = document.createElement('label');
label.textContent = folderName + ' ';  // Nicht template string!
const badge = document.createElement('span');
badge.textContent = mailCount + '/' + unseenCount;
label.appendChild(badge);
```

## Lessons Learned

### ❌ Was nicht funktionierte
1. **User-globale Filter** → Bei mehreren Accounts unpraktisch
2. **Filter nur beim Initial-Sync** → User konnte nicht nachträglich anpassen
3. **Template-Strings für Text-Rendering** → Silently fails in innerHTML
4. **Auto-Selected Excludes** → User verwirrt warum Ordner gecheckt sind

### ✅ Was gut funktionierte
1. **Account-spezifische Filter** → Flexible per-Account Konfiguration
2. **Filter bei jedem Fetch** → User kann jederzeit anpassen
3. **createElement + textContent** → Zuverlässiges Text-Rendering
4. **localStorage für State** → Nahtloses UX nach Reload
5. **Live-Vorschau mit Summary** → User sieht was passiert

## Metriken

- **Migrations:** 2 (ph13c_p5, ph13c_p6)
- **Neue Spalten:** 4 pro MailAccount
- **Neue Routes:** 2 (save_fetch_config, get_account_fetch_filters)
- **Commits:** 3 (Part 5, Part 6, Fix)
- **Lines Changed:** ~900 (Backend + Frontend + Migration)
- **Test Cases:** Manuell getestet mit GMX Account

## Testing

### Test-Szenario 1: Filter setzen
1. Account "martina" auswählen ✅
2. SINCE auf 2025-12-01 setzen ✅
3. UNSEEN-Only aktivieren ✅
4. Nur INBOX + Archiv includen ✅
5. Spam + Trash excluden ✅
6. "Speichern" → Page reload → Filter noch da ✅

### Test-Szenario 2: Filter ändern
1. Account bereits konfiguriert
2. Filter von "SINCE 2025-12-01" auf "SINCE 2025-11-01" ändern
3. "Abrufen" klicken
4. **Erwartung:** Neue Mails ab 2025-11-01 werden gefetched ✅
5. **Vorher (Bug):** Filter wurden ignoriert ❌

### Test-Szenario 3: Multi-Account
1. Account A: SINCE 2025-01-01, Include [INBOX]
2. Account B: UNSEEN-Only, Exclude [Spam]
3. Wechsel zwischen A und B
4. **Erwartung:** Jeder Account lädt eigene Filter ✅

## Next Steps (Optional)

### Mögliche Erweiterungen
- **Filter-Presets:** "Newsletter-Mode", "Wichtige-Mails-Only"
- **Reset-Button:** "Alle Filter zurücksetzen"
- **Filter-Export/Import:** JSON-Backup
- **Statistik:** "X Mails durch Filter reduziert"
- **Ordner-Tags:** Farben/Icons für schnelle Erkennung

### Performance-Optimierung
- **Ordner-Cache:** list_folders() nur 1x pro Session
- **Batch-Update:** Mehrere Accounts parallel fetchen
- **Incremental UI:** Ordner einzeln rendern statt alles auf einmal

## Referenzen

- **Migrations:** 
  - `migrations/versions/ph13c_p5_fetch_filters.py`
  - `migrations/versions/ph13c_p6_move_filters_to_accounts.py`
- **Models:** `src/02_models.py` (User, MailAccount)
- **Backend:** `src/01_web_app.py` (Routes)
- **Jobs:** `src/14_background_jobs.py` (_fetch_raw_emails)
- **Frontend:** `templates/settings.html`

## Commits

1. **bec3526** - Phase 13C Part 5: Fetch-Filter für Initial-Sync
2. **e945315** - Phase 13C Part 6: Account-spezifische Fetch-Filter
3. **2c7089b** - fix: Filter gelten jetzt bei jedem Fetch

---

**Fazit:** Phase 13C ermöglicht präzise, flexible Mail-Synchronisation. User haben volle Kontrolle über **welche** Mails **wann** und **wie** abgerufen werden. Die account-spezifische Lösung skaliert gut für Multi-Account-Setups.
