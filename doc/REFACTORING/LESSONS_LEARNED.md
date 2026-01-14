# LESSONS LEARNED - Blueprint Refactoring

**Erstellt:** 13. Januar 2026  
**Zweck:** Dokumentation von Fehlern und deren Lösungen während des Refactorings

---

## 🚨 KRITISCHE FEHLER

### 1. `fetch_mails` Route - Falsche Methodensignatur (13.01.2026)

**Problem:**
```python
# FALSCH (vereinfacht, aber kaputt):
job_id = job_queue.enqueue_fetch(current_user.id, account_id)
```

**Symptom:**
```
AttributeError: 'BackgroundJobQueue' object has no attribute 'enqueue_fetch'
TypeError: BackgroundJobQueue.enqueue_fetch_job() takes 1 positional argument but 3 were given
```

**Ursache:**
- Methodenname falsch: `enqueue_fetch` statt `enqueue_fetch_job`
- Methode hat keyword-only Arguments (`*`), nicht positional
- 8 erforderliche Parameter wurden auf 2 reduziert

**Lösung aus `01_web_app.py` (Zeile 7406):**
```python
# KORREKT (vollständige Signatur):
job_id = job_queue.enqueue_fetch_job(
    user_id=user.id,
    account_id=account.id,
    master_key=master_key,           # ← Aus session.get("master_key")
    provider=provider,               # ← Aus user.preferred_ai_provider
    model=resolved_model,            # ← Aus ai_client.resolve_model()
    max_mails=fetch_limit,           # ← 500 initial, 50 danach
    sanitize_level=sanitize_level,   # ← Aus sanitizer.get_sanitization_level()
    meta={"trigger": "settings", "is_initial": is_initial},
)
```

**Lektion:**
> ⚠️ **NIEMALS** komplexe Funktionsaufrufe "vereinfachen" ohne die Signatur zu prüfen!  
> Die Lösung steht IMMER in `01_web_app.py` - einfach 1:1 kopieren!

---

### 2. `sync_mail_flags` Route - Verschlüsseltes Feld (13.01.2026)

**Problem:**
```python
# FALSCH (Feld existiert nicht):
imap_server = account.imap_server
```

**Symptom:**
```
AttributeError: 'MailAccount' object has no attribute 'imap_server'
```

**Ursache:**
- Zero-Knowledge Architektur: Server-Name ist verschlüsselt
- Das Feld heißt `encrypted_imap_server`, nicht `imap_server`

**Lösung:**
```python
# KORREKT (Entschlüsselung):
imap_server = encryption.CredentialManager.decrypt_email_address(
    account.encrypted_imap_server, master_key
)
```

**Lektion:**
> ⚠️ Bei `MailAccount` sind ALLE sensiblen Felder verschlüsselt!  
> Immer `encrypted_*` Felder mit `CredentialManager.decrypt_*()` entschlüsseln.

---

### 3. `_get_job_queue()` - Falscher Import (13.01.2026)

**Problem:**
```python
# FALSCH (job_queue existiert nicht als Modul-Variable):
job_mod = importlib.import_module(".14_background_jobs", "src")
_job_queue = job_mod.job_queue  # ← AttributeError!
```

**Symptom:**
```
AttributeError: module 'src.14_background_jobs' has no attribute 'job_queue'
```

**Ursache:**
- `14_background_jobs.py` definiert nur die Klasse `BackgroundJobQueue`
- Die Instanz wird in `app_factory.py` erstellt

**Lösung:**
```python
# KORREKT (Import aus app_factory):
from src.app_factory import job_queue as jq
_job_queue = jq
```

**Lektion:**
> ⚠️ Globale Singletons wie `job_queue` werden in `app_factory.py` instanziiert!  
> Nicht aus dem Modul importieren, sondern aus der Factory.

---

### 4. Cache-Key ohne Filter-Parameter (13.01.2026)

**Problem:**
```python
# FALSCH (Cache ignoriert Filter):
cache_key = account_id
```

**Symptom:**
- Toggle "Nur ungelesene" ändert die Anzeige nicht
- Cache gibt alte Daten zurück

**Lösung:**
```python
# KORREKT (Cache-Key enthält alle Filter):
cache_key = f"{account_id}:{since_date_str or ''}:{unseen_only}:{include_folders_param or ''}"
```

**Lektion:**
> ⚠️ Cache-Keys müssen ALLE Parameter enthalten, die das Ergebnis beeinflussen!

---

## ✅ BEST PRACTICES

### 1. Vor dem Refactoring einer Route:
1. **Suche in `01_web_app.py`** nach der originalen Implementation
2. **Kopiere 1:1** - keine "Vereinfachungen"!
3. **Prüfe alle Imports** - sind sie im Blueprint verfügbar?
4. **Prüfe Methodensignaturen** - `help(methode)` oder Quellcode lesen

### 2. Bei Fehlern:
1. **Lese die VOLLSTÄNDIGE Fehlermeldung** - sie sagt genau was fehlt
2. **Vergleiche mit Legacy-Code** - die Lösung steht dort
3. **Dokumentiere den Fix** in diesem Dokument

### 3. Zero-Knowledge beachten:
- `MailAccount`: `encrypted_imap_server`, `encrypted_imap_username`, `encrypted_imap_password`
- `RawEmail`: `encrypted_sender`, `encrypted_subject`, `encrypted_body`
- Immer `CredentialManager.decrypt_*()` oder `EmailDataManager.decrypt_*()` verwenden

---

---

### 5. Falscher Modul-Import für Sanitizer (13.01.2026)

**Problem:**
```python
# FALSCH (Modul existiert nicht):
sanitizer = importlib.import_module(".services.content_sanitizer", "src")
```

**Symptom:**
```
AttributeError: module 'src.services.content_sanitizer' has no attribute 'get_sanitization_level'
```

**Ursache:**
- Copy-Paste aus einem anderen Blueprint, der ein anderes Modul nutzt
- NICHT geprüft, was `01_web_app.py` tatsächlich importiert

**Lösung aus `01_web_app.py` (Zeile 55):**
```python
# KORREKT:
sanitizer = importlib.import_module(".04_sanitizer", "src")
```

**Lektion:**
> ⚠️ **IMMER die Imports aus `01_web_app.py` prüfen!**  
> Zeile 1-100 enthält alle globalen Imports - dort nachschlagen!

---

## ✅ SYSTEMATISCHE PRÜFUNG VOR REFACTORING

### Schritt 1: Legacy-Code vollständig lesen
```bash
# 1. Finde die Route in Legacy:
grep -n "def route_name" src/01_web_app.py

# 2. Lese den VOLLSTÄNDIGEN Code:
sed -n '7372,7440p' src/01_web_app.py

# 3. Finde alle verwendeten Module:
grep -n "sanitizer\|ai_client\|job_queue" src/01_web_app.py | head -20
```

### Schritt 2: Imports prüfen (Zeile 1-100 von 01_web_app.py)
```python
# Legacy-Imports (src/01_web_app.py Zeilen 50-60):
ai_client = importlib.import_module(".03_ai_client", "src")    # ← NICHT services.ai!
sanitizer = importlib.import_module(".04_sanitizer", "src")    # ← NICHT services.content_sanitizer!
job_queue = background_jobs.BackgroundJobQueue(DATABASE_PATH)  # ← Instanz, nicht Modul!
```

### Schritt 3: Vollständige Signatur kopieren
```python
# NICHT:
job_queue.enqueue_fetch(user_id, account_id)  # ← FALSCH

# SONDERN (komplett aus 01_web_app.py Zeile 7406):
job_id = job_queue.enqueue_fetch_job(
    user_id=user.id,
    account_id=account.id,
    master_key=master_key,
    provider=provider,
    model=resolved_model,
    max_mails=fetch_limit,
    sanitize_level=sanitize_level,
    meta={"trigger": "settings", "is_initial": is_initial},
)
```

---

## 📋 CHECKLISTE für neue Blueprint-Routes

```markdown
[ ] Route existiert in 01_web_app.py? → Code 1:1 kopieren
[ ] Legacy-Imports geprüft? (Zeile 1-100 von 01_web_app.py)
[ ] Alle Imports vorhanden? (models, encryption, session, etc.)
[ ] Methodensignaturen korrekt? (keyword-only args beachten!)
[ ] Verschlüsselte Felder? → decrypt_* verwenden
[ ] Cache-Keys vollständig? → Alle Filter-Parameter einbeziehen
[ ] Error-Handling? → Spezifische Fehler loggen
[ ] Getestet mit USE_BLUEPRINTS=1?
```

---

## 🔍 SCHNELL-REFERENZ: Module in 01_web_app.py

| Blueprint-Import | RICHTIG (01_web_app.py) | FALSCH |
|------------------|-------------------------|--------|
| AI Client | `.03_ai_client` | `.services.ai` |
| Sanitizer | `.04_sanitizer` | `.services.content_sanitizer` |
| job_queue | `from src.app_factory import job_queue` | `from src.14_background_jobs import job_queue` |
| Encryption | `.08_encryption` | `.services.encryption` |

---

### 6. `encrypted_entity_map` fehlte in `12_processing.py` (13.01.2026)

**Problem:**
Während des Fetch-Prozesses wurde die Anonymisierung durchgeführt, aber die Entity-Map (für De-Anonymisierung) wurde NICHT in der DB gespeichert.

**Symptom:**
- Reply-Entwurf enthält Platzhalter: `[PERSON_5]`, `[EMPFÄNGER_VORNAME]`
- Frontend-Console: `⚠️ deAnonymizeText: reverseMap is empty`
- Nach `--clean-sanitization` + On-the-fly funktioniert's (weil dort entity_map gespeichert wird)

**Ursache:**
In `src/12_processing.py` wurden gespeichert:
```python
raw_email.encrypted_subject_sanitized = ...  ✅
raw_email.encrypted_body_sanitized = ...     ✅
raw_email.sanitization_entities_count = ...  ✅
raw_email.sanitization_level = ...           ✅
raw_email.sanitization_time_ms = ...         ✅
# raw_email.encrypted_entity_map = ...       ❌ FEHLTE!
```

**Lösung:**
```python
# 🆕 EntityMap für De-Anonymisierung speichern
import json
entity_map_dict = sanitization_result.entity_map.to_dict()
raw_email.encrypted_entity_map = encryption_mod.EncryptionManager.encrypt_data(
    json.dumps(entity_map_dict), master_key
)
```

**Lektion:**
> ⚠️ Bei neuen DB-Feldern: ALLE Stellen prüfen wo Daten gespeichert werden!  
> Hier gab es 3 Stellen: `12_processing.py` (2x), `api.py` (1x), `01_web_app.py` (1x)

---

### 7. Delta-Sync bei Filter-Fetch falsch implementiert (13.01.2026)

**Problem:**
Delta-Sync nutzte `UID > max_uid_in_db`, aber bei Filter-Fetch (SINCE/UNSEEN) können ältere Mails dem Filter entsprechen.

**Symptom:**
- Mail gelöscht mit `--hard-delete`
- Fetch zeigt "0 neue Mails, 1 aktualisiert"
- Mail fehlt trotzdem in der DB

**Ursache:**
```python
# FALSCH: Delta-Sync ignoriert Filter!
uid_range = f"{last_uid + 1}:*"  # Sucht nur neue UIDs
# Aber Filter-Mails können ältere UIDs haben!
```

**Lösung:**
```python
# KORREKT: Filter-basiertes Delta
if fetch_since or fetch_unseen:
    # 1. Hole alle UIDs vom Server die dem Filter entsprechen
    server_uids = fetcher.search_uids(folder, since=fetch_since, unseen_only=fetch_unseen)
    
    # 2. Hole existierende UIDs aus DB
    db_uids = set(...)
    
    # 3. Delta = Server UIDs - DB UIDs
    missing_uids = [uid for uid in server_uids if uid not in db_uids]
    
    # 4. Nur fehlende laden
    folder_emails = fetcher.fetch_new_emails(..., specific_uids=missing_uids)
```

**Lektion:**
> ⚠️ Delta-Sync mit `UID > X` funktioniert NUR bei sequentiellen Full-Fetches!  
> Bei Filter-Fetch: Server-UIDs gegen DB-UIDs vergleichen!
