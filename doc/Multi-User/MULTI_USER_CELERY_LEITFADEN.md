# Multi-User Celery Leitfaden: Architektur & Job-Orchestration

**Status**: Schritt-für-Schritt Implementierungs-Anleitung  
**Ziel**: PostgreSQL + Redis + Celery in 3 Wochen  
**Templates**: Siehe `/src/celery_app.py`, `/src/tasks/`  
**Analyse**: Siehe `MULTI_USER_MIGRATION_REPORT.md` (gleiches Verzeichnis)  

---

## 🚀 QUICK START (2-3 Stunden zum Ausprobieren)

### 1. Docker Services starten
```bash
# PostgreSQL (5432)
docker run -d --name mail-pg \
  -e POSTGRES_PASSWORD=dev123 \
  -e POSTGRES_DB=mail_helper \
  -p 5432:5432 \
  postgres:15

# Redis (6379)
docker run -d --name mail-redis \
  -p 6379:6379 \
  redis:7

# Verifikation
psql postgresql://postgres:dev123@localhost:5432/mail_helper -c "SELECT 1"
redis-cli ping  # → PONG
```

### 2. Python Dependencies
```bash
# Celery + PostgreSQL adapter
pip install "celery[redis]==5.3.4" psycopg2-binary
```

### 3. Umgebungsvariablen
```bash
# .env
DATABASE_URL=postgresql://postgres:dev123@localhost:5432/mail_helper
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

### 4. Templates aus `/src/` verwenden
- ✅ `src/celery_app.py` (70 Zeilen) - Production-ready
- ✅ `src/tasks/__init__.py` - Task-Discovery
- ✅ `src/tasks/mail_sync_tasks.py` (205 Zeilen) - Beispiel-Implementierung
- ✅ `src/helpers/database.py` - Celery-kompatible Helper-Funktionen

**Hinweis**: Dies sind **Templates** für die Multi-User Migration. Sie zeigen das empfohlene Pattern (Business-Logic Separation) und können direkt in Ihr Projekt integriert werden.

### ⚠️ VORAUSSETZUNG: MailSyncService

Die Tasks importieren `src/services/mail_sync_service.py`, der noch erstellt werden muss:

```python
# src/services/mail_sync_service.py (zu erstellen)
# Extrahiere Business-Logic aus 14_background_jobs.py:_process_fetch_job()

class MailSyncService:
    def __init__(self, session):
        self.session = session
    
    def sync_emails(self, user, account, max_mails=50) -> dict:
        """Synchronisiere Emails für einen Account.
        
        Returns:
            {"email_count": 42, "status": "success", ...}
        """
        # TODO: Implementierung aus 14_background_jobs.py extrahieren
        pass
```

### 5. Celery Worker starten (neues Terminal)
```bash
cd /path/to/KI-Mail-Helper-Dev
celery -A src.celery_app worker --loglevel=info
```

### 6. Test
```python
from src.celery_app import celery_app
from src.tasks.mail_sync_tasks import sync_user_emails

# Starte Task async
task = sync_user_emails.delay(user_id=1, account_id=1)

# Warte auf Ergebnis (mit Timeout)
result = task.get(timeout=30)
print(result)
```

---

## 📋 DETAILLIERTE ROADMAP (3 Wochen)

### WOCHE 1: Infrastruktur-Setup

#### Tag 1-2: PostgreSQL Migration
```bash
# Schritt 1: Alte SQLite-DB sichern
cp emails.db emails.db.backup

# Schritt 2: PostgreSQL starten
docker run -d --name mail-pg \
  -e POSTGRES_PASSWORD=secure \
  -e POSTGRES_DB=mail_helper \
  -p 5432:5432 \
  postgres:15

# Schritt 3: .env aktualisieren
echo 'DATABASE_URL=postgresql://postgres:secure@localhost:5432/mail_helper' >> .env

# Schritt 4: Alembic Migration
pip install alembic
alembic revision --autogenerate -m "PostgreSQL init"
alembic upgrade head

# Schritt 5: Test
python scripts/check_db.py
```

**Checkpoint**: Schema ist in PostgreSQL initialisiert ✅

#### Tag 3: Redis Setup
```bash
# Schritt 1: Redis starten
docker run -d --name mail-redis -p 6379:6379 redis:7

# Schritt 2: .env aktualisieren
echo 'REDIS_URL=redis://localhost:6379/0' >> .env

# Schritt 3: Test
python -c "import redis; r=redis.Redis(); r.ping(); print('✅ Redis OK')"

# Schritt 4: Session-Config in app_factory.py updaten
# (Code-Snippet siehe unten)
```

**Checkpoint**: Redis läuft, Session-Storage funktioniert ✅

#### Tag 4-5: Celery Setup
```bash
# Schritt 1: Dependencies
pip install "celery[redis]==5.3.4"

# Schritt 2: celery_app.py verwenden (siehe src/celery_app.py)

# Schritt 3: .env aktualisieren
echo 'CELERY_BROKER_URL=redis://localhost:6379/1' >> .env
echo 'CELERY_RESULT_BACKEND=redis://localhost:6379/2' >> .env

# Schritt 4: Worker in neuem Terminal starten
celery -A src.celery_app worker --loglevel=info

# Schritt 5: Task testen
python -c "from src.celery_app import debug_task; \
           task = debug_task.delay(); \
           print(task.id)"
```

**Checkpoint**: Celery Worker läuft, Test-Task funktioniert ✅

---

### WOCHE 2: Task-Refactoring

#### Tag 6-7: Mail Sync Task
```bash
# Schritt 1: Task-Modul verwenden
# src/tasks/mail_sync_tasks.py (siehe Template)

# Schritt 2: In Blueprint integrieren
# Update src/blueprints/email_actions.py (siehe Code-Snippet unten)

# Schritt 3: Test
pytest tests/test_tasks/test_mail_sync_task.py -v

# Checkpoint: Mail Sync funktioniert async ✅
```

#### Tag 8-9: Email Processing Task
```bash
# Schritt 1: Neue Task-Datei
# src/tasks/email_processing_tasks.py

# Schritt 2: Blueprint Update
# src/blueprints/api.py - /emails/<id>/reprocess endpoint

# Schritt 3: Test
pytest tests/test_tasks/test_processing_task.py -v
```

#### Tag 10: Integration-Testing
```bash
# Alle Tasks zusammen testen
pytest tests/test_tasks/ -v

# Load-Test mit 5 concurrent tasks
python tests/load_test_tasks.py
```

**Checkpoint**: Alle 2 Tasks funktionieren ✅

---

### WOCHE 3: Embedding + Rules + Production

#### Tag 11: Embedding Task (Optional)
```bash
# Datei erstellen: src/tasks/embedding_tasks.py
# Funktion: Semantic Search Embedding-Generierung

# Integration: Blueprint /api/batch-reprocess-embeddings

# Test ausführen:
pytest tests/test_tasks/test_embedding_task.py
```

#### Tag 12: Rule Execution Task (Optional)
```bash
# Datei erstellen: src/tasks/rule_execution_tasks.py
# Funktion: Auto-Rules Ausführung

# Integration: Blueprint /api/rules/apply

# Test ausführen:
pytest tests/test_tasks/test_rule_task.py
```

#### Tag 13-15: Testing + Production
```bash
# Full Integration Test
pytest tests/ -v --cov=src

# Load Test (20 concurrent users)
locust -f tests/load_test.py --host=http://localhost:5000

# Docker Compose aufsetzen
docker-compose up -d  # PostgreSQL + Redis + Web + Celery

# Production-Deployment testen
gunicorn --workers 4 src.00_main:app
```

**Checkpoint**: Alles funktioniert in Produktion ✅

---

## 💻 CODE-SNIPPETS: Integration in Blueprints

### A. Update Session-Config (`app_factory.py`, Zeilen ~96-105)

**VORHER:**
```python
app.config["SESSION_TYPE"] = "filesystem"
session_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".flask_sessions")
os.makedirs(session_dir, mode=0o700, exist_ok=True)
app.config["SESSION_FILE_DIR"] = session_dir
Session(app)
```

**NACHHER:**
```python
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
try:
    import redis
    redis_client = redis.from_url(REDIS_URL)
    redis_client.ping()
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = redis_client
    logger.info("✅ Redis Session Store aktiviert")
except (ImportError, ConnectionError) as e:
    logger.warning(f"⚠️  Redis nicht verfügbar: {e}")
    app.config["SESSION_TYPE"] = "filesystem"
    session_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".flask_sessions")
    os.makedirs(session_dir, mode=0o700, exist_ok=True)
    app.config["SESSION_FILE_DIR"] = session_dir

Session(app)
```

### B. Blueprint: Mail Sync async aufrufen

**VORHER** (`src/blueprints/email_actions.py`):
```python
@email_actions_bp.route("/sync-emails/<account_id>", methods=["POST"])
def sync_emails_endpoint(account_id):
    user = get_user_from_session()
    # BLOCKING: Diese Zeile wartet bis Sync fertig ist!
    result = job_queue.enqueue_fetch_job(user.id, account_id)
    return jsonify({"status": "done", "result": result})
```

**NACHHER**:
```python
from src.tasks.mail_sync_tasks import sync_user_emails

@email_actions_bp.route("/sync-emails/<account_id>", methods=["POST"])
def sync_emails_endpoint(account_id):
    user = get_user_from_session()
    
    # ✅ NON-BLOCKING: Task wird in Redis gequeued
    task = sync_user_emails.delay(user.id, int(account_id))
    
    return jsonify({
        "status": "queued",
        "task_id": task.id,
        "message": "Email sync started in background"
    })

# Neuer Endpoint: Task-Status abfragen
@email_actions_bp.route("/sync-status/<task_id>", methods=["GET"])
def sync_status(task_id):
    from src.celery_app import celery_app
    
    result = celery_app.AsyncResult(task_id)
    
    return jsonify({
        "task_id": task_id,
        "status": result.state,  # PENDING, STARTED, SUCCESS, FAILURE
        "result": result.result if result.ready() else None,
        "progress": result.info.get("progress") if result.info else None,
    })
```

### C. Requirements.txt Update

**NEUE ZEILEN hinzufügen:**
```
# requirements.txt

# Database - PostgreSQL Support
psycopg2-binary==2.9.9      # PostgreSQL adapter

# Celery - Async Task Queue
celery[redis]==5.3.4        # Celery + Redis backend
python-dateutil==2.8.2      # Dependencies
```

---

## 🧪 TESTING: Unit + Integration

### Unit Test (Service, nicht Task)
```python
# tests/test_services/test_mail_sync_service.py
def test_sync_emails_user_isolation(session):
    """Services: Data bleibt pro User getrennt."""
    from src.services.mail_sync_service import MailSyncService
    
    user1 = create_test_user(session, "user1@test.com")
    user2 = create_test_user(session, "user2@test.com")
    
    service = MailSyncService(session)
    
    # User1 sync
    result1 = service.sync_emails(user1, account_id=1)
    user1_count = len(session.query(Email).filter_by(user_id=user1.id).all())
    
    # User2 sync (sollte ANDERE Emails haben)
    result2 = service.sync_emails(user2, account_id=1)
    user2_count = len(session.query(Email).filter_by(user_id=user2.id).all())
    
    assert user1_count > 0
    assert user2_count > 0
    assert session.query(Email).filter_by(user_id=user1.id) != \
           session.query(Email).filter_by(user_id=user2.id)
```

### Integration Test (Task + Database + Redis)
```python
# tests/test_tasks/test_mail_sync_task.py
import pytest
from celery import current_task

@pytest.mark.celery
def test_sync_task_user_isolation():
    """Tasks: User-Isolation wird durchgesetzt."""
    from src.tasks.mail_sync_tasks import sync_user_emails
    
    user1_id = create_test_user("user1@test.com").id
    user2_id = create_test_user("user2@test.com").id
    
    # Task für User1
    task1 = sync_user_emails.delay(user1_id, account_id=1)
    result1 = task1.get(timeout=30)
    
    # Task für User2
    task2 = sync_user_emails.delay(user2_id, account_id=1)
    result2 = task2.get(timeout=30)
    
    # Verifiziere: Unterschiedliche Daten
    assert result1["status"] == "success"
    assert result2["status"] == "success"
    assert result1["user_id"] == user1_id
    assert result2["user_id"] == user2_id
```

---

## 🚨 HÄUFIGE PROBLEME & LÖSUNGEN

### Problem 1: "redis.exceptions.ConnectionError"
```
❌ Error: ConnectionError: Error 111 connecting to localhost:6379
```
**Lösung:**
```bash
# Redis ist nicht am Laufen
docker ps | grep redis  # Nicht vorhanden?

# Neu starten
docker stop mail-redis 2>/dev/null
docker run -d --name mail-redis -p 6379:6379 redis:7
redis-cli ping  # → PONG
```

### Problem 2: "psycopg2.OperationalError"
```
❌ Error: could not connect to server: Connection refused
```
**Lösung:**
```bash
# PostgreSQL läuft nicht
docker ps | grep postgres  # Nicht vorhanden?

# Neu starten
docker stop mail-pg 2>/dev/null
docker run -d --name mail-pg \
  -e POSTGRES_PASSWORD=dev123 \
  -e POSTGRES_DB=mail_helper \
  -p 5432:5432 \
  postgres:15

# Kurz warten, dann testen
sleep 5
psql postgresql://postgres:dev123@localhost:5432/mail_helper -c "SELECT 1"
```

### Problem 3: "Celery worker findet Tasks nicht"
```
❌ Error: Received unregistered task 'tasks.sync_user_emails'
```
**Lösung:**
```python
# Überprüfe: celery_app.py hat autodiscover?
# celery_app.py Zeile ~27:
celery_app.autodiscover_tasks(["src.tasks"])

# Starte Worker neu
pkill -f "celery -A src.celery_app"
celery -A src.celery_app worker --loglevel=info
```

### Problem 4: "Task hängt fest (STARTED state)"
```
❌ Status: STARTED (für lange Zeit)
```
**Lösung:**
```bash
# Task dauert zu lange oder Worker crash
# Logs überprüfen:
tail -f celery_worker.log

# Worker mit Timeout starten
celery -A src.celery_app worker \
  --time-limit=1800 \
  --soft-time-limit=1500 \
  --loglevel=info

# Im Code: Implementiere Timeout
from celery.exceptions import SoftTimeLimitExceeded

@celery_app.task
def long_task():
    try:
        # ... work ...
    except SoftTimeLimitExceeded:
        logger.warning("Task timeout!")
        raise
```

---

## 📊 MONITORING & DEBUGGING

### Celery Status überprüfen
```bash
# Worker-Status
celery -A src.celery_app inspect active

# Task-Stats
celery -A src.celery_app inspect stats

# Registered Tasks
celery -A src.celery_app inspect registered
```

### Redis Debugging
```bash
# Redis CLI
redis-cli

# Alle Keys anschauen
KEYS *

# Task Queue länge
LLEN celery

# Cache-Größe
DBSIZE

# Alles löschen (NUR IM DEV!)
FLUSHDB
```

### PostgreSQL Connection-Pool
```python
# app_factory.py - Connection-Pool Monitoring
from sqlalchemy import event

@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    logger.info(f"Pool size: {engine.pool.size()}")
```

---

## 🚢 PRODUCTION CHECKLIST

- [ ] PostgreSQL mit Backups konfiguriert
- [ ] Redis mit Persistence (RDB/AOF) konfiguriert
- [ ] Celery Worker mit Supervisor/systemd gemanagt
- [ ] Celery Beat für periodische Tasks konfiguriert
- [ ] Monitoring (Prometheus/Grafana) aufgesetzt
- [ ] Logging centralisiert (ELK Stack optional)
- [ ] Load-Test erfolgreich (20+ concurrent users)
- [ ] Rollback-Plan dokumentiert
- [ ] Team trainiert auf neue Architektur

---

## 📚 WEITERE RESSOURCEN

- [Celery Dokumentation](https://docs.celeryproject.org/)
- [Flask + Celery Pattern](https://docs.celeryproject.org/en/stable/frameworks/flask.html)
- [PostgreSQL Performance](https://www.postgresql.org/docs/current/performance.html)
- [Redis Best Practices](https://redis.io/topics/client-side-caching)
- **Analyse-Report**: Siehe `MULTI_USER_MIGRATION_REPORT.md` für vollständige technische Analyse

---

**Viel Erfolg beim Refactoring! 🚀**
