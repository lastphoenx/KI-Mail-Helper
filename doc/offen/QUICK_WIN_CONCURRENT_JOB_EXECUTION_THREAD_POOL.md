# ⚡ Quick-Win: Thread-Pool für Job-Parallelisierung

**Scope:** 3-4 simultane Fetch-Jobs ermöglichen  
**Aufwand:** ~10 Stunden (statt 60-80h für Pipeline Broker)  
**Nutzen:** 3-4 User können gleichzeitig fetchen, **nicht blockiert**

---

## 🎯 Was ist das Problem?

**Aktuell (14_background_jobs.py, Line 93):**
```python
self._worker = threading.Thread(...)  # EIN Thread!
```

**Szenario: 4 User, jeder fetcht 1 Account gleichzeitig**
```
User 1 Fetch Start  (0s)   ────────────── (15s)  Done
User 2 Fetch Start  (15s)  ────────────── (30s)  Done  ❌ Muss warten!
User 3 Fetch Start  (30s)  ────────────── (45s)  Done  ❌ Muss warten!
User 4 Fetch Start  (45s)  ────────────── (60s)  Done  ❌ Muss warten!

Total: 60s (sequenziell) → User schlechte UX ("Fetching..." Spinnrad)
```

**Mit Thread-Pool (4 Worker):**
```
User 1 Fetch Start  (0s)  ────────── (15s)  Done
User 2 Fetch Start  (0s)  ────────── (15s)  Done  ✅ Parallel!
User 3 Fetch Start  (0s)  ────────── (15s)  Done  ✅ Parallel!
User 4 Fetch Start  (0s)  ────────── (15s)  Done  ✅ Parallel!

Total: 15s (parallel) → 4× schneller!
```

---

## 🏗️ Design

### Architektur

```
┌──────────────────────────────────────────┐
│  BackgroundJobQueue (MODIFIED)           │
├──────────────────────────────────────────┤
│ self.executor = ThreadPoolExecutor(4)    │  ← 4 parallel Worker-Threads
│ self.queue = Queue()                     │  ← Job Queue (wenn Executor voll)
│ self.status = {}                         │  ← Job-Status Tracking
└──────────────────────────────────────────┘
         │
         ├─→ Worker 1 ─→ Fetch Job 1
         ├─→ Worker 2 ─→ Fetch Job 2
         ├─→ Worker 3 ─→ Fetch Job 3
         └─→ Worker 4 ─→ Fetch Job 4
```

### Implementation Plan

#### Phase 1: ThreadPoolExecutor Integration (4h)

**File:** `src/14_background_jobs.py` (modifizieren)

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

class BackgroundJobQueue:
    MAX_QUEUE_SIZE = 50
    MAX_WORKERS = 4  # NEW: 3-4 parallel Threads
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.queue = Queue(maxsize=self.MAX_QUEUE_SIZE)
        
        # OLD (entfernen):
        # self._worker = threading.Thread(...)
        
        # NEW (hinzufügen):
        self.executor = ThreadPoolExecutor(
            max_workers=self.MAX_WORKERS,
            thread_name_prefix="mail-fetch-worker"
        )
        self._status: Dict[str, Dict[str, Any]] = {}
        self._status_lock = threading.Lock()
        self._active_futures: List[Any] = []  # Tracking
```

#### Phase 2: Job-Submission (3h)

```python
def enqueue_fetch_job(self, *, user_id, account_id, master_key, ...):
    """Submitte Fetch-Job zum ThreadPool"""
    job = FetchJob(...)
    job_id = str(uuid.uuid4())
    
    # Registriere Job-Status
    with self._status_lock:
        self._status[job_id] = {
            "status": "queued",
            "user_id": user_id,
            "account_id": account_id,
            "created_at": datetime.now(),
            "started_at": None,
            "completed_at": None,
        }
    
    # Submit zu ThreadPool
    future = self.executor.submit(self._execute_fetch_job, job, job_id)
    
    # Tracking
    with self._status_lock:
        self._active_futures.append(future)
    
    return job_id
```

#### Phase 3: Status-Polling UI (2h)

**File:** `src/01_web_app.py` (neue Route)

```python
@app.route("/api/job-status/<job_id>", methods=["GET"])
@login_required
def get_job_status(job_id):
    """Prüfe Job-Status (für UI Progress-Bar)"""
    status = background_jobs.get_job_status(job_id)
    
    if not status:
        return jsonify({"error": "Job nicht gefunden"}), 404
    
    # Validierung: User kann nur eigene Jobs sehen
    if status["user_id"] != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify(status)
```

#### Phase 4: Error-Handling & Cleanup (1h)

```python
def _execute_fetch_job(self, job: FetchJob, job_id: str):
    """Führe Fetch aus mit Fehlerbehandlung"""
    try:
        with self._status_lock:
            self._status[job_id]["status"] = "running"
            self._status[job_id]["started_at"] = datetime.now()
        
        # Aktueller Code: raw_emails = self._fetch_raw_emails(...)
        result = self._fetch_raw_emails(...)
        
        with self._status_lock:
            self._status[job_id]["status"] = "completed"
            self._status[job_id]["completed_at"] = datetime.now()
            self._status[job_id]["result"] = result
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        with self._status_lock:
            self._status[job_id]["status"] = "failed"
            self._status[job_id]["error"] = str(e)
```

---

## 📝 Detaillierter Implementierungs-Plan

### Schritt 1: Änderungen in `src/14_background_jobs.py`

**Zeilen zu ersetzen:**

```python
# ALT (Line 88-95):
def ensure_worker(self) -> None:
    if self._worker and self._worker.is_alive():
        return
    self._stop_event.clear()
    self._worker = threading.Thread(
        target=self._run, name="mail-helper-worker", daemon=True
    )
    self._worker.start()
    logger.info("🧵 Hintergrund-Worker gestartet")

# NEU:
def ensure_worker(self) -> None:
    """ThreadPoolExecutor ist bereits in __init__ initialisiert"""
    logger.info(f"✓ ThreadPool mit {self.MAX_WORKERS} Worker-Threads aktiv")
```

**Neuer Code nach `__init__`:**

```python
def __init__(self, db_path: str):
    self.db_path = db_path
    self.queue = Queue(maxsize=self.MAX_QUEUE_SIZE)  # Fallback Queue
    self._stop_event = threading.Event()
    self._status: Dict[str, Dict[str, Any]] = {}
    self._status_lock = threading.Lock()
    self._SessionFactory = self._init_session_factory()
    
    # NEW: ThreadPool mit 4 Worker-Threads
    self.executor = ThreadPoolExecutor(
        max_workers=self.MAX_WORKERS,
        thread_name_prefix="mail-fetch-worker"
    )
    self._active_futures: List[Any] = []
    self._future_to_job_id: Dict[Any, str] = {}
```

### Schritt 2: Job-Submission ändern

**In `enqueue_fetch_job()` (Line 103+):**

```python
def enqueue_fetch_job(self, *, user_id, account_id, master_key, ...):
    job = FetchJob(...)
    job_id = str(uuid.uuid4())
    
    # Status initialisieren
    with self._status_lock:
        self._status[job_id] = {
            "id": job_id,
            "status": "queued",
            "user_id": user_id,
            "account_id": account_id,
            "created_at": datetime.now(UTC),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "email_count": 0,
        }
    
    # Submit zu ThreadPool (nicht zu Queue!)
    future = self.executor.submit(self._execute_fetch_job, job, job_id)
    
    with self._status_lock:
        self._active_futures.append(future)
        self._future_to_job_id[future] = job_id
    
    logger.info(f"📤 Fetch-Job {job_id} submitted (user={user_id})")
    return job_id
```

### Schritt 3: _execute_fetch_job anpassen

```python
def _execute_fetch_job(self, job: FetchJob, job_id: str) -> None:
    """Execute mit Status-Tracking"""
    session = self._SessionFactory()
    
    try:
        # Update Status: running
        with self._status_lock:
            self._status[job_id]["status"] = "running"
            self._status[job_id]["started_at"] = datetime.now(UTC)
        
        # ... Aktueller Fetch-Code ...
        raw_emails = self._fetch_raw_emails(account, master_key, job.max_mails)
        saved = self._persist_raw_emails(raw_emails, account, job.user_id)
        
        # Update Status: completed
        with self._status_lock:
            self._status[job_id]["status"] = "completed"
            self._status[job_id]["completed_at"] = datetime.now(UTC)
            self._status[job_id]["email_count"] = saved
        
        logger.info(f"✅ Job {job_id} completed: {saved} emails saved")
        
    except Exception as e:
        logger.error(f"❌ Job {job_id} failed: {e}")
        with self._status_lock:
            self._status[job_id]["status"] = "failed"
            self._status[job_id]["error"] = str(e)
            self._status[job_id]["completed_at"] = datetime.now(UTC)
    
    finally:
        session.close()
```

### Schritt 4: Status-API Routes

**In `src/01_web_app.py`:**

```python
@app.route("/api/job-status/<job_id>", methods=["GET"])
@login_required
def get_job_status(job_id):
    """Polling-Endpunkt für Job-Status"""
    status = background_jobs._status.get(job_id)
    
    if not status:
        return jsonify({"error": "Job nicht gefunden"}), 404
    
    # Sicherheit: User kann nur seine eigenen Jobs sehen
    if status["user_id"] != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify({
        "id": status["id"],
        "status": status["status"],  # queued, running, completed, failed
        "created_at": status["created_at"].isoformat(),
        "started_at": status["started_at"].isoformat() if status["started_at"] else None,
        "completed_at": status["completed_at"].isoformat() if status["completed_at"] else None,
        "email_count": status["email_count"],
        "error": status["error"],
    })

@app.route("/api/jobs/active", methods=["GET"])
@login_required
def get_active_jobs():
    """Liste aller aktiven Jobs des Users"""
    user_jobs = [
        job for job in background_jobs._status.values()
        if job["user_id"] == current_user.id
    ]
    return jsonify(user_jobs)
```

### Schritt 5: UI Integration

**In `templates/email_detail.html` oder Dashboard:**

```javascript
// Polling für Job-Status
async function pollJobStatus(jobId) {
    const response = await fetch(`/api/job-status/${jobId}`);
    const status = await response.json();
    
    if (status.status === "running") {
        document.getElementById("fetch-status").textContent = 
            `Fetching... (${status.email_count} emails so far)`;
        setTimeout(() => pollJobStatus(jobId), 1000);
    } else if (status.status === "completed") {
        document.getElementById("fetch-status").textContent = 
            `✓ Completed: ${status.email_count} emails`;
    } else if (status.status === "failed") {
        document.getElementById("fetch-status").textContent = 
            `✗ Error: ${status.error}`;
    }
}

// Nach Fetch-Button Click:
const jobId = await startFetch();  // Gibt job_id zurück
pollJobStatus(jobId);
```

---

## ⚠️ Wichtige Punkte

### User-Isolation
```python
# KRITISCH: Alle Status-Queries filtern nach user_id!
if status["user_id"] != current_user.id:
    return jsonify({"error": "Unauthorized"}), 403
```

### DB-Concurrency
```python
# Mehrere Threads können gleichzeitig writes machen
# SQLAlchemy Connection Pool verwaltet das automatisch
# ABER: Per-Account Locks beachten (falls implementiert)
```

### Memory
```python
# self._status wird nicht geleert!
# Problem: Alte Jobs bleiben im Dict
# Lösung: Cleanup nach 24h oder MAX_HISTORY=1000
```

### Graceful Shutdown
```python
def stop(self):
    logger.info("Shuttingdown ThreadPool...")
    self.executor.shutdown(wait=True)  # Warte bis alle Jobs done
```

---

## ✅ Ergebnis nach 10h

**Vorher (1 Worker):**
```
4 Fetches = 60 Sekunden (sequenziell)
UX: "Bitte warten..." spinner
```

**Nachher (4 Worker):**
```
4 Fetches = 15 Sekunden (parallel)
UX: "Fetching in Hintergrund..." (non-blocking)
```

**Was funktioniert:**
- ✅ 3-4 User können gleichzeitig fetchen
- ✅ Jeder sieht nur seine Jobs (user_id isolation)
- ✅ UI polling zeigt Fortschritt
- ✅ Fehlerbehandlung per Job
- ✅ Graceful shutdown

**Was NICHT funktioniert:**
- ❌ Persistent Job Queue (nur in-memory)
- ❌ Monitoring Dashboard (nur API Polling)
- ❌ Distributed (nur 1 Server)

---

## 📊 Vergleich

| Feature | Thread-Pool (10h) | Full Pipeline (60h) |
|---------|---|---|
| 3-4 parallel Fetches | ✅ | ✅ |
| Job-Status Polling | ✅ | ✅ |
| User-Isolation | ✅ | ✅ |
| Persistent Queue | ❌ | ✅ |
| Monitoring Dashboard | ❌ | ✅ |
| Multi-Server Support | ❌ | ✅ |
| Circuit Breaker | ❌ | ✅ |

---

## 🚀 Next Steps

1. **Implementation starten** (10h)
2. **Testen mit 3-4 User parallel**
3. **UI Polling hinzufügen** (2h Extra)
4. **Bei Bedarf auf Pipeline Broker upgraden** (50h später)

