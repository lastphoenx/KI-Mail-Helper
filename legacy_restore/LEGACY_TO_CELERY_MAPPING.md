# Legacy Code → Celery Tasks Mapping
## KI-Mail-Helper Multi-User Migration

**Datum**: Januar 2026  
**Zweck**: Zeigt GENAU welcher Legacy-Code in welche neuen Celery-Tasks überführt werden muss  

---

## 📊 EXECUTIVE SUMMARY

Der Legacy-Code verteilt sich auf **4 Hauptbereiche**:

| Legacy-Modul | Zeilen | Status | Ziel (Celery Task) | Priorität |
|--------------|--------|--------|-------------------|-----------|
| `14_background_jobs.py` | 1.140 | ⚠️ DEPRECATED | 3 neue Tasks | 🔴 HOCH |
| `12_processing.py` | ~500 | ⚠️ UMBAUEN | 1 Task | 🔴 HOCH |
| `semantic_search.py` | ~300 | 🟡 OPTIONAL | 1 Task | 🟡 MITTEL |
| `auto_rules_engine.py` | ~200 | 🟡 OPTIONAL | 1 Task | 🟡 NIEDRIG |
| **TOTAL** | **~2.140** | | **6 Tasks** | |

---

## 🗺️ MAPPING-TABELLE

### 1. Mail-Sync (KRITISCH) 🔴

**Legacy-Quelle:**
```
Datei: src/14_background_jobs.py
Funktion: _process_fetch_job(job: FetchJob)
Zeilen: ~50-150 (geschätzt, da die genaue Struktur im Dokument nicht vollständig ist)
Klasse: FetchJob

Abhängigkeiten:
- src/16_mail_sync.py (IMAP-Verbindung)
- src/02_models.py (RawEmail, MailAccount)
- src/helpers/database.py (Session)
```

**Ziel (Celery):**
```
Datei: src/tasks/mail_sync_tasks.py ✅ BEREITS ERSTELLT (210 Zeilen)
Funktion: sync_user_emails(user_id, account_id, max_emails)
```

**Service (zu erstellen):**
```
Datei: src/services/mail_sync_service.py ❌ FEHLT NOCH
Klasse: MailSyncService
Methode: sync_emails(user, account, max_mails)

Zu extrahieren aus:
- 14_background_jobs.py:_process_fetch_job()
  └─ IMAP-Verbindung aufbauen
  └─ Emails fetchen (Schleife über UIDs)
  └─ Raw-Email speichern (DB)
  └─ Duplikate checken (message_id)
  └─ Folder-Sync (INBOX, Archiv, etc.)
  └─ Error-Handling
```

**Blueprint-Integration:**
```
Alt (Legacy):
  src/blueprints/accounts.py Zeile 1249
  → job_queue.enqueue_fetch(user_id, account_id)

Neu (Celery):
  src/blueprints/accounts.py
  → from src.tasks.mail_sync_tasks import sync_user_emails
  → task = sync_user_emails.delay(user_id, account_id)
```

**Funktionalität zu übernehmen:**
- ✅ IMAP-Verbindung (über 16_mail_sync.py)
- ✅ UID-basiertes Fetching
- ✅ Raw-Email Persistierung
- ✅ Duplikate-Check (message_id + content_hash)
- ✅ Folder-Handling (INBOX, Sent, Trash, etc.)
- ✅ Progress-Callback (für UI)
- ✅ Error-Retry-Logik
- ✅ Timeout-Handling (IMAP kann hängen)

**Status:** Template existiert ✅, Service-Implementierung fehlt ❌

---

### 2. Email-Processing (KRITISCH) 🔴

**Legacy-Quelle:**
```
Datei: src/12_processing.py
Funktion: process_email(email_id, user_id, model, provider)
Zeilen: ~500 (geschätzt)

Abhängigkeiten:
- src/ai_client.py (AI-Modelle)
- src/services/hybrid_pipeline.py (Scoring)
- src/services/ensemble_combiner.py (Multi-Modell)
- src/02_models.py (ProcessedEmail)
```

**Ziel (Celery):**
```
Datei: src/tasks/email_processing_tasks.py ❌ ZU ERSTELLEN
Funktion: process_email_with_ai(email_id, user_id, model, provider)
```

**Zu extrahieren aus `12_processing.py`:**
```python
# DIESE Logik kopieren:
def process_email(email_id, user_id, model, provider):
    # 1. Email aus DB laden
    raw_email = session.query(RawEmail).get(email_id)
    
    # 2. AI-Client initialisieren
    client = get_ai_client(model, provider)
    
    # 3. Scoring durchführen
    from src.services.hybrid_pipeline import HybridPipeline
    pipeline = HybridPipeline(client)
    scores = pipeline.score_email(raw_email)
    
    # 4. Ensemble-Combiner (falls multi-model)
    from src.services.ensemble_combiner import EnsembleCombiner
    combiner = EnsembleCombiner()
    final_score = combiner.combine(scores)
    
    # 5. ProcessedEmail erstellen/updaten
    processed = ProcessedEmail(
        raw_email_id=email_id,
        user_id=user_id,
        ai_score=final_score,
        model_used=model,
        ...
    )
    session.add(processed)
    session.commit()
    
    return {"email_id": email_id, "score": final_score}
```

**Blueprint-Integration:**
```
Alt (Legacy):
  src/blueprints/api.py (vermutlich direkter Aufruf)
  → result = process_email(email_id, user_id, model, provider)

Neu (Celery):
  src/blueprints/api.py
  → from src.tasks.email_processing_tasks import process_email_with_ai
  → task = process_email_with_ai.delay(email_id, user_id, model, provider)
```

**Funktionalität zu übernehmen:**
- ✅ AI-Client Initialisierung
- ✅ Hybrid-Pipeline Integration
- ✅ Ensemble-Combiner (falls multi-model)
- ✅ Scoring-Logik
- ✅ ProcessedEmail Persistierung
- ✅ Error-Handling (AI API failures)
- ✅ Retry-Logik (API Rate-Limits)
- ✅ Timeout-Handling (AI kann langsam sein)

**Status:** ❌ Noch nicht erstellt

---

### 3. Batch-Reprocessing (MITTEL) 🟡

**Legacy-Quelle:**
```
Datei: src/14_background_jobs.py
Funktion: _process_batch_reprocess_job(job: BatchReprocessJob)
Zeilen: ~100-200

Abhängigkeiten:
- src/12_processing.py (process_email)
- src/02_models.py (RawEmail, ProcessedEmail)
```

**Ziel (Celery):**
```
Datei: src/tasks/batch_reprocess_tasks.py ❌ ZU ERSTELLEN
Funktion: batch_reprocess_emails(user_id, email_ids, model, provider)
```

**Zu extrahieren:**
```python
# DIESE Logik kopieren:
def _process_batch_reprocess_job(job: BatchReprocessJob):
    for email_id in job.email_ids:
        # Nutze process_email() aus 12_processing.py
        result = process_email(email_id, job.user_id, job.model, job.provider)
        
        # Progress-Update (optional)
        job.progress = (index + 1) / len(job.email_ids)
```

**Blueprint-Integration:**
```
Alt (Legacy):
  src/blueprints/api.py Zeile 2094
  → job_queue.enqueue_batch_reprocess_job(user_id, email_ids, ...)

Neu (Celery):
  src/blueprints/api.py
  → from src.tasks.batch_reprocess_tasks import batch_reprocess_emails
  → task = batch_reprocess_emails.delay(user_id, email_ids, model, provider)
```

**Funktionalität zu übernehmen:**
- ✅ Batch-Iteration über email_ids
- ✅ Aufruf von process_email() für jede Email
- ✅ Progress-Tracking (wie viele % fertig?)
- ✅ Error-Handling (einzelne Email fehlgeschlagen ≠ ganzer Batch)
- ✅ Partial Success (50/100 emails processed)

**Status:** ❌ Noch nicht erstellt

---

### 4. Embedding-Generation (OPTIONAL) 🟡

**Legacy-Quelle:**
```
Datei: src/semantic_search.py
Funktion: generate_embedding_for_email(email_id)
Zeilen: ~300 (geschätzt)

Abhängigkeiten:
- src/ai_client.py (Embedding-Modelle)
- src/02_models.py (RawEmail, EmailEmbedding)
```

**Ziel (Celery):**
```
Datei: src/tasks/embedding_tasks.py ❌ ZU ERSTELLEN
Funktion: generate_email_embedding(email_id, user_id)
```

**Zu extrahieren:**
```python
# DIESE Logik kopieren:
def generate_embedding_for_email(email_id):
    # 1. Email laden
    raw_email = session.query(RawEmail).get(email_id)
    
    # 2. Embedding-Modell nutzen (z.B. OpenAI, Cohere, local)
    from src.ai_client import get_embedding_client
    client = get_embedding_client()
    
    # 3. Text vorbereiten (Subject + Body)
    text = f"{raw_email.subject}\n{raw_email.body}"
    
    # 4. Embedding generieren
    embedding_vector = client.create_embedding(text)
    
    # 5. In DB speichern
    email_embedding = EmailEmbedding(
        email_id=email_id,
        embedding=embedding_vector,
        model="text-embedding-ada-002"  # oder ähnlich
    )
    session.add(email_embedding)
    session.commit()
```

**Blueprint-Integration:**
```
Alt (Legacy):
  src/blueprints/api.py (vermutlich direkter Aufruf)
  → result = generate_embedding_for_email(email_id)

Neu (Celery):
  src/blueprints/api.py
  → from src.tasks.embedding_tasks import generate_email_embedding
  → task = generate_email_embedding.delay(email_id, user_id)
```

**Funktionalität zu übernehmen:**
- ✅ Embedding-Client Initialisierung
- ✅ Text-Preparation (Subject + Body)
- ✅ Embedding-Generation
- ✅ Vector-Persistierung
- ✅ Error-Handling (API failures)
- ✅ Batch-Embedding (optional, für Effizienz)

**Status:** ❌ Noch nicht erstellt

---

### 5. Rule-Execution (OPTIONAL) 🟡

**Legacy-Quelle:**
```
Datei: src/auto_rules_engine.py
Funktion: execute_rules(email_id, user_id)
Zeilen: ~200 (geschätzt)

Abhängigkeiten:
- src/02_models.py (AutoRule, RawEmail)
- src/services/tag_manager.py (Tag-Anwendung)
```

**Ziel (Celery):**
```
Datei: src/tasks/rule_execution_tasks.py ❌ ZU ERSTELLEN
Funktion: apply_rules_to_email(email_id, user_id)
```

**Zu extrahieren:**
```python
# DIESE Logik kopieren:
def execute_rules(email_id, user_id):
    # 1. Email laden
    raw_email = session.query(RawEmail).get(email_id)
    
    # 2. User's Rules laden
    rules = session.query(AutoRule).filter_by(
        user_id=user_id,
        is_active=True
    ).all()
    
    # 3. Jede Rule evaluieren
    for rule in rules:
        if rule.matches(raw_email):
            # 4. Action ausführen (z.B. Tag hinzufügen)
            if rule.action == "add_tag":
                from src.services.tag_manager import TagManager
                tag_manager = TagManager(session)
                tag_manager.add_tag_to_email(email_id, rule.tag_id)
            
            # 5. Weitere Actions (move_to_folder, mark_as_read, etc.)
```

**Blueprint-Integration:**
```
Alt (Legacy):
  src/blueprints/rules.py (vermutlich direkter Aufruf)
  → result = execute_rules(email_id, user_id)

Neu (Celery):
  src/blueprints/rules.py
  → from src.tasks.rule_execution_tasks import apply_rules_to_email
  → task = apply_rules_to_email.delay(email_id, user_id)
```

**Funktionalität zu übernehmen:**
- ✅ Rules laden (user-spezifisch)
- ✅ Rule-Evaluation (matches email?)
- ✅ Action-Execution (add_tag, move_folder, etc.)
- ✅ Error-Handling (Rule fehlgeschlagen)
- ✅ Logging (welche Rules angewendet?)

**Status:** ❌ Noch nicht erstellt

---

## 📋 BLUEPRINT-INTEGRATION MAPPING

Hier sind die KONKRETEN Zeilen in den Blueprints, die geändert werden müssen:

### accounts.py
```python
# VORHER (Zeile ~1249):
from src.14_background_jobs import job_queue
job_id = job_queue.enqueue_fetch(user_id=current_user.id, account_id=account_id)

# NACHHER:
from src.tasks.mail_sync_tasks import sync_user_emails
task = sync_user_emails.delay(user_id=current_user.id, account_id=account_id)
return jsonify({"task_id": task.id, "status": "queued"})
```

### api.py
```python
# VORHER (Zeile ~2094):
from src.14_background_jobs import job_queue
job_id = job_queue.enqueue_batch_reprocess_job(
    user_id=current_user.id,
    email_ids=email_ids,
    model=model,
    provider=provider
)

# NACHHER:
from src.tasks.batch_reprocess_tasks import batch_reprocess_emails
task = batch_reprocess_emails.delay(
    user_id=current_user.id,
    email_ids=email_ids,
    model=model,
    provider=provider
)
return jsonify({"task_id": task.id, "status": "queued"})
```

### email_actions.py (vermutlich)
```python
# VORHER (direkter Aufruf):
from src.12_processing import process_email
result = process_email(email_id, user_id, model, provider)

# NACHHER:
from src.tasks.email_processing_tasks import process_email_with_ai
task = process_email_with_ai.delay(email_id, user_id, model, provider)
return jsonify({"task_id": task.id, "status": "queued"})
```

### rules.py (vermutlich)
```python
# VORHER:
from src.auto_rules_engine import execute_rules
result = execute_rules(email_id, user_id)

# NACHHER:
from src.tasks.rule_execution_tasks import apply_rules_to_email
task = apply_rules_to_email.delay(email_id, user_id)
return jsonify({"task_id": task.id, "status": "queued"})
```

---

## 🔍 WIE FINDE ICH DEN LEGACY-CODE?

### Methode 1: Datei direkt öffnen
```bash
# Mail-Sync Logic
nano src/14_background_jobs.py
# Suche nach: "_process_fetch_job" (ca. Zeile 50-150)

# Email-Processing Logic
nano src/12_processing.py
# Suche nach: "def process_email" (ca. Zeile 1-500)

# Embedding Logic
nano src/semantic_search.py
# Suche nach: "generate_embedding_for_email"

# Rules Logic
nano src/auto_rules_engine.py
# Suche nach: "execute_rules"
```

### Methode 2: Grep durchsuchen
```bash
# Finde alle Funktionen die in Celery umgebaut werden sollen
cd /home/thomas/projects/KI-Mail-Helper-Dev

# Mail-Sync
grep -n "_process_fetch_job" src/14_background_jobs.py

# Processing
grep -n "def process_email" src/12_processing.py

# Embedding
grep -n "generate_embedding" src/semantic_search.py

# Rules
grep -n "execute_rules" src/auto_rules_engine.py

# Blueprints die job_queue nutzen
grep -rn "job_queue" src/blueprints/
```

### Methode 3: Dependency-Analyse (aus 04_LEGACY_CODE_DEPRECATION_PLAN.md)
```bash
# Script ausführen:
python scripts/analyze_legacy_imports.py

# Output: legacy_imports.json mit allen Abhängigkeiten
```

---

## 📊 PRIORITÄTS-MATRIX

| Task | Frequenz | CPU-Last | User-Impact | Prio | Aufwand |
|------|----------|----------|-------------|------|---------|
| **Mail-Sync** | Sehr hoch | Mittel | 🔴 Kritisch | 1 | 12h |
| **Email-Processing** | Hoch | Hoch | 🔴 Kritisch | 2 | 8h |
| **Batch-Reprocess** | Mittel | Hoch | 🟡 Mittel | 3 | 6h |
| **Embedding-Gen** | Niedrig | Hoch | 🟡 Nice-to-have | 4 | 4h |
| **Rule-Execution** | Mittel | Niedrig | 🟡 Nice-to-have | 5 | 4h |

**Total Aufwand: ~34 Stunden** (für alle 5 Tasks)

---

## ✅ IMPLEMENTIERUNGS-REIHENFOLGE

### Phase 1: Kritische Path (Woche 2)

**Tag 6-7: Mail-Sync**
1. Öffne `src/14_background_jobs.py`
2. Kopiere `_process_fetch_job()` Logik
3. Erstelle `src/services/mail_sync_service.py`
4. Nutze existierendes `src/tasks/mail_sync_tasks.py` (bereits vorhanden!)
5. Integriere in `src/blueprints/accounts.py`
6. Test

**Tag 8-9: Email-Processing**
1. Öffne `src/12_processing.py`
2. Kopiere `process_email()` Logik
3. Erstelle `src/tasks/email_processing_tasks.py`
4. Integriere in `src/blueprints/api.py` oder `email_actions.py`
5. Test

### Phase 2: Batch & Optional (Woche 3)

**Tag 11: Batch-Reprocess**
1. Öffne `src/14_background_jobs.py`
2. Kopiere `_process_batch_reprocess_job()` Logik
3. Erstelle `src/tasks/batch_reprocess_tasks.py`
4. Integriere in `src/blueprints/api.py`
5. Test

**Tag 12: Embedding (optional)**
1. Öffne `src/semantic_search.py`
2. Kopiere Embedding-Logik
3. Erstelle `src/tasks/embedding_tasks.py`
4. Integriere in relevante Blueprints
5. Test

**Tag 13: Rules (optional)**
1. Öffne `src/auto_rules_engine.py`
2. Kopiere Rule-Execution-Logik
3. Erstelle `src/tasks/rule_execution_tasks.py`
4. Integriere in `src/blueprints/rules.py`
5. Test

---

## 🚨 WICHTIGE HINWEISE

### Was NICHT übernommen werden soll

❌ **Job-Queue Infrastructure aus 14_background_jobs.py**
```python
# NICHT übernehmen:
class BackgroundJobQueue:  # ← Wird durch Celery ersetzt
    def __init__(self):
        self._jobs = {}
        self._worker_thread = threading.Thread(...)
```

❌ **Thread-basierte Execution**
```python
# NICHT übernehmen:
def _worker_loop(self):
    while True:
        job = self._queue.get()
        self._process_job(job)
```

❌ **In-Memory Status**
```python
# NICHT übernehmen:
self._status = {}  # ← Wird durch Redis ersetzt
```

### Was MUSS übernommen werden

✅ **Business-Logic**
```python
# MUSS übernommen werden:
def _process_fetch_job(job):
    # 1. IMAP-Verbindung
    # 2. Email-Fetch
    # 3. DB-Persistierung
    # 4. Duplikate-Check
    # ...
```

✅ **Error-Handling**
```python
# MUSS übernommen werden:
try:
    # ... business logic ...
except ConnectionError as e:
    logger.error(f"IMAP failed: {e}")
    # Retry logic
```

✅ **Ownership-Validation**
```python
# MUSS übernommen werden:
account = session.query(MailAccount).filter_by(
    id=account_id,
    user_id=user_id  # ← WICHTIG für Multi-User!
).first()

if not account:
    raise PermissionError("Unauthorized access")
```

---

## 📚 VERWANDTE DOKUMENTE

- **Implementierungs-Timeline**: [00_MASTER_IMPLEMENTIERUNGS_LEITFADEN.md](00_MASTER_IMPLEMENTIERUNGS_LEITFADEN.md)
- **Legacy Deprecation**: [04_LEGACY_CODE_DEPRECATION_PLAN.md](04_LEGACY_CODE_DEPRECATION_PLAN.md)
- **Testing**: [03_CELERY_TEST_INFRASTRUCTURE.md](03_CELERY_TEST_INFRASTRUCTURE.md)

