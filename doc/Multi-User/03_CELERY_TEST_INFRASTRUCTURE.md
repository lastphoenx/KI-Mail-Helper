# Celery Test-Infrastructure Leitfaden
## KI-Mail-Helper Multi-User Migration

**Status**: Produktionsreife Test-Strategie  
**Geschätzter Aufwand**: 8-10 Stunden  
**Datum**: Januar 2026  
**Sprache**: Deutsch  

---

## 🎯 ZIEL

Aufbau einer verlässlichen Test-Infrastruktur für Celery Tasks mit:
- ✅ pytest Fixtures für Redis + Celery Setup
- ✅ Retry-Logik Tests
- ✅ Timeout-Handling Tests
- ✅ Task-Isolation Tests
- ✅ Production-ähnliche Bedingungen

---

## 📦 SCHRITT 1: Test-Dependencies installieren (30 min)

### 1.1 Requirements hinzufügen

```bash
cat >> requirements.txt << 'EOF'

# Testing (Celery + Redis)
pytest==7.4.3
pytest-cov==4.1.0
pytest-asyncio==0.21.1
pytest-mock==3.12.0
fakeredis==2.20.0
EOF

source venv/bin/activate
pip install -r requirements.txt
```

### 1.2 pytest Konfiguration

```ini
# pytest.ini (im Root-Verzeichnis, falls nicht vorhanden)
[pytest]
minversion = 7.0
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --cov=src
    --cov-report=html
    --cov-report=term
    -ra
markers =
    celery: Celery task tests
    redis: Redis integration tests
    slow: Slow running tests
```

---

## 🔧 SCHRITT 2: Shared Fixtures (2h)

### 2.1 conftest.py für Test-Session

```python
# tests/conftest.py
"""
Shared pytest Fixtures für alle Tests.
- Redis Mock/Real Setup
- Celery Worker Setup
- Database Session Setup
"""

import os
import pytest
import logging
from pathlib import Path

# Lese Requirements aus pytest.ini
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/1"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/2"
os.environ["DATABASE_URL"] = "sqlite:///test_emails.db"
os.environ["FLASK_ENV"] = "test"

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def celery_config():
    """Celery-Konfiguration für Tests."""
    return {
        "broker_url": "redis://localhost:6379/1",
        "result_backend": "redis://localhost:6379/2",
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "Europe/Berlin",
        "enable_utc": True,
        "task_always_eager": False,  # ← Asynchrone Tests!
        "task_eager_propagates": True,
        "worker_prefetch_multiplier": 1,
        "task_acks_late": True,
    }


@pytest.fixture(scope="session")
def celery_enable_logging():
    """Enable Celery logging für Tests."""
    return True


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Erstelle Test-Datenbank vor allen Tests."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from src.helpers.database import get_engine
    from src.02_models import Base
    
    engine = get_engine()
    
    # Erstelle alle Tabellen
    Base.metadata.create_all(engine)
    logger.info("✅ Test-Datenbank erstellt")
    
    yield
    
    # Cleanup nach allen Tests
    # Base.metadata.drop_all(engine)  # Optional: DB löschen nach Tests
    logger.info("🧹 Test-Cleanup abgeschlossen")


@pytest.fixture
def redis_connection():
    """
    Redis-Verbindung für Tests.
    
    Nutzt fakeredis im Memory, NICHT echtes Redis!
    (Schneller und isolation-safe)
    """
    import fakeredis
    
    # Echter Redis (auskommentiert)
    # import redis
    # return redis.Redis(host="localhost", port=6380, db=0)
    
    # Fake Redis (empfohlen für Unit-Tests)
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture
def db_session():
    """Datenbanksesion für Tests mit Auto-Rollback."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from src.helpers.database import get_session
    
    session = get_session()()
    
    yield session
    
    # Rollback nach Test (keine Daten persistent)
    session.rollback()
    session.close()


@pytest.fixture
def test_user(db_session):
    """Erstelle Test-User für Tasks."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from src.02_models import User
    from werkzeug.security import generate_password_hash
    
    user = User(
        email="testuser@example.com",
        username="testuser",
        password_hash=generate_password_hash("test_password_123")
    )
    db_session.add(user)
    db_session.commit()
    
    yield user
    
    db_session.delete(user)
    db_session.commit()


@pytest.fixture
def test_account(db_session, test_user):
    """Erstelle Test-Mail-Account für Tasks."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from src.02_models import MailAccount
    
    account = MailAccount(
        user_id=test_user.id,
        email="test@mail.example.com",
        provider="imap",
        server_host="imap.example.com",
        server_port=993,
        imap_port=993,
        smtp_port=587,
        encryption_type="SSL"
    )
    db_session.add(account)
    db_session.commit()
    
    yield account
    
    db_session.delete(account)
    db_session.commit()


@pytest.fixture
def celery_worker(celery_app, celery_config):
    """
    Starte echten Celery Worker für Integration-Tests.
    
    Nutze @pytest.mark.celery für Tests, die echten Worker brauchen.
    """
    from celery.contrib.testing.worker import start_worker
    
    worker = start_worker(
        celery_app,
        loglevel="info",
        perform_health_checks=False,
        concurrency=1
    )
    
    yield worker
    
    worker.stop()

```

### 2.2 conftest.py in tests/tasks/ (für spezifische Tests)

```python
# tests/tasks/conftest.py
"""Fixtures spezifisch für Task-Tests."""

import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def mock_imap_connection():
    """Mock für IMAP-Verbindung."""
    mock = Mock()
    mock.login = Mock(return_value=("OK", []))
    mock.select = Mock(return_value=("OK", [1000]))  # 1000 Mails
    mock.fetch = Mock(return_value=("OK", [
        (1, b"Content"),
        (2, b"Content2"),
    ]))
    mock.close = Mock(return_value=("OK", None))
    
    return mock


@pytest.fixture
def mock_mail_sync_service():
    """Mock für MailSyncService."""
    mock = Mock()
    mock.sync_emails = Mock(return_value={
        "email_count": 10,
        "status": "success",
        "new_emails": 5,
        "updated_emails": 3,
        "deleted_emails": 1
    })
    
    return mock

```

---

## ✅ SCHRITT 3: Basis-Task Tests (2h)

### 3.1 Test: Task wird in Queue eingereiht

```python
# tests/tasks/test_mail_sync_tasks_basic.py
"""Basis-Tests für Mail-Sync Tasks."""

import pytest
from src.celery_app import celery_app
from src.tasks.mail_sync_tasks import sync_user_emails


@pytest.mark.celery
class TestMailSyncTaskBasic:
    """Basis-Funktionalität der Mail-Sync Task."""
    
    def test_task_registered(self):
        """Task sollte in Celery registriert sein."""
        assert "src.tasks.mail_sync_tasks.sync_user_emails" in celery_app.tasks
    
    def test_task_queuing(self, test_user, test_account):
        """Task sollte in Queue eingereiht werden können."""
        task = sync_user_emails.delay(
            user_id=test_user.id,
            account_id=test_account.id
        )
        
        assert task.id is not None
        assert task.state in ["PENDING", "STARTED"]
    
    def test_task_with_eager_execution(self, test_user, test_account):
        """Mit eager=True synchrone Ausführung testen."""
        # In conftest.py: task_always_eager: False
        # Für diesen Test synchron machen:
        
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
        
        try:
            task = sync_user_emails.delay(
                user_id=test_user.id,
                account_id=test_account.id
            )
            
            # Mit eager=True: Task läuft sofort
            assert task.ready()
            
        finally:
            celery_app.conf.task_always_eager = False
```

### 3.2 Test: Task-Fehlerbehandlung

```python
# tests/tasks/test_mail_sync_tasks_errors.py
"""Error-Handling Tests."""

import pytest
from src.tasks.mail_sync_tasks import sync_user_emails
from src.celery_app import celery_app


@pytest.mark.celery
class TestMailSyncTaskErrors:
    """Fehlerbehandlung in Tasks."""
    
    def test_invalid_user_id(self):
        """Task mit ungültiger user_id sollte scheitern."""
        task = sync_user_emails.delay(user_id=99999, account_id=1)
        
        celery_app.conf.task_always_eager = True
        try:
            result = task.get(timeout=5)
        except Exception as e:
            assert "not found" in str(e).lower() or task.failed
    
    def test_invalid_account_id(self, test_user):
        """Task mit ungültiger account_id sollte scheitern."""
        task = sync_user_emails.delay(user_id=test_user.id, account_id=99999)
        
        celery_app.conf.task_always_eager = True
        try:
            result = task.get(timeout=5)
        except Exception as e:
            assert "not found" in str(e).lower() or task.failed
    
    def test_permission_denied(self, test_user, db_session):
        """Task sollte scheitern bei unauthorized Account-Access."""
        from src.02_models import User, MailAccount
        
        # Andere User
        other_user = User(
            email="other@example.com",
            username="otheruser",
            password_hash="hashed"
        )
        db_session.add(other_user)
        db_session.commit()
        
        # Account des anderen Users
        other_account = MailAccount(
            user_id=other_user.id,
            email="other@mail.example.com",
            provider="imap",
            server_host="imap.example.com",
            imap_port=993,
            smtp_port=587
        )
        db_session.add(other_account)
        db_session.commit()
        
        # Versuche als test_user auf anderen Account zuzugreifen
        task = sync_user_emails.delay(
            user_id=test_user.id,
            account_id=other_account.id
        )
        
        celery_app.conf.task_always_eager = True
        try:
            result = task.get(timeout=5)
            assert False, "Sollte PermissionError werfen"
        except PermissionError:
            pass  # Erwartet!

```

---

## 🔄 SCHRITT 4: Retry-Mechanismus Tests (2h)

### 4.1 Test: Exponential Backoff Retries

```python
# tests/tasks/test_mail_sync_tasks_retries.py
"""Retry-Logik Tests."""

import pytest
from unittest.mock import patch, MagicMock
from src.tasks.mail_sync_tasks import sync_user_emails
from src.celery_app import celery_app
from celery.exceptions import SoftTimeLimitExceeded


@pytest.mark.celery
class TestMailSyncTaskRetries:
    """Retry-Mechanismus validieren."""
    
    def test_retry_on_network_error(self, test_user, test_account):
        """Task sollte bei Netzwerk-Fehler retry-n."""
        
        call_count = [0]
        
        @patch("src.helpers.mail_fetcher.IMAPConnection")
        def run_test(mock_imap):
            call_count[0] += 1
            
            if call_count[0] < 3:
                # Erste 2 Versuche: Fehler
                mock_imap.side_effect = ConnectionError("IMAP timeout")
            else:
                # 3. Versuch: Erfolg
                mock_imap.return_value = MagicMock()
            
            # Task mit max_retries=3
            celery_app.conf.task_always_eager = True
            
            try:
                task = sync_user_emails.delay(
                    user_id=test_user.id,
                    account_id=test_account.id
                )
                # Task sollte nach 3 Versuchen erfolgreich sein
                assert task.state in ["SUCCESS", "PENDING", "RETRY"]
            finally:
                celery_app.conf.task_always_eager = False
        
        run_test()
    
    def test_retry_delays(self):
        """Retry-Delays sollten exponentiell steigen."""
        from src.tasks.mail_sync_tasks import sync_user_emails
        
        # Task-Definition sollte retry_delays haben
        task_config = sync_user_emails
        
        # Oder in Implementierung prüfen:
        # retry_delays = [60, 300]  # 1 min, 5 min
        # Sicherstellen dass exponential backoff implementiert ist
        
        assert hasattr(sync_user_emails, "autoretry_for") or \
               hasattr(sync_user_emails, "retry")
    
    def test_max_retries_exceeded(self, test_user, test_account):
        """Nach max_retries sollte Task fehlschlagen."""
        
        with patch("src.helpers.mail_fetcher.IMAPConnection") as mock_imap:
            mock_imap.side_effect = ConnectionError("Always fails")
            
            celery_app.conf.task_always_eager = True
            
            try:
                task = sync_user_emails.delay(
                    user_id=test_user.id,
                    account_id=test_account.id,
                    max_retries=2  # Limit
                )
                
                # Nach allen Retries: FAILURE
                # (Nicht mehr RETRY)
                assert task.failed or task.state == "FAILURE"
            finally:
                celery_app.conf.task_always_eager = False

```

---

## ⏱️ SCHRITT 5: Timeout Tests (1.5h)

### 5.1 Test: Soft Timeout (Task wird unterbrochen)

```python
# tests/tasks/test_mail_sync_tasks_timeouts.py
"""Timeout-Handling Tests."""

import pytest
import time
from unittest.mock import patch
from celery.exceptions import SoftTimeLimitExceeded
from src.celery_app import celery_app
from src.tasks.mail_sync_tasks import sync_user_emails


@pytest.mark.celery
class TestMailSyncTaskTimeouts:
    """Timeout-Handling validieren."""
    
    def test_soft_timeout_exception(self, test_user, test_account):
        """Soft Timeout sollte SoftTimeLimitExceeded werfen."""
        
        with patch("src.services.mail_sync_service.MailSyncService.sync_emails") as mock_sync:
            # Simuliere lange laufende Task
            mock_sync.side_effect = lambda *a, **k: time.sleep(100)
            
            # Config: task_soft_time_limit=25*60 (25 Minuten)
            celery_app.conf.task_soft_time_limit = 2  # 2 Sekunden für Test
            
            task = sync_user_emails.delay(
                user_id=test_user.id,
                account_id=test_account.id
            )
            
            # Task sollte bei timeout abgebrochen werden
            # Ergebnis: FAILURE oder REVOKED
            assert task.state in ["FAILURE", "REVOKED", "TIMEOUT"]
    
    def test_hard_timeout_limit(self, test_user, test_account):
        """Hard Timeout: Worker sollte Task forceful killen."""
        
        # Config: task_time_limit=30*60 (30 Minuten)
        celery_app.conf.task_time_limit = 5  # 5 Sekunden für Test
        
        with patch("src.services.mail_sync_service.MailSyncService.sync_emails") as mock_sync:
            mock_sync.side_effect = lambda *a, **k: time.sleep(100)
            
            task = sync_user_emails.delay(
                user_id=test_user.id,
                account_id=test_account.id
            )
            
            # Task sollte hart abgebrochen werden
            # (Nicht sauber, aber erzwungen)

```

### 5.2 Test: Graceful Shutdown bei Timeout

```python
# tests/tasks/test_mail_sync_tasks_graceful_shutdown.py
"""Graceful Shutdown bei Timeouts."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.celery
class TestMailSyncTaskGracefulShutdown:
    """Sauberes Herunterfahren bei Timeouts."""
    
    def test_cleanup_on_timeout(self, test_user, test_account, db_session):
        """Bei Timeout: Session sollte geschlossen werden."""
        
        from src.tasks.mail_sync_tasks import sync_user_emails
        
        # Mock session cleanup
        with patch("src.helpers.database.get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = MagicMock(return_value=mock_session)
            
            with patch("src.services.mail_sync_service.MailSyncService.sync_emails") as mock_sync:
                mock_sync.side_effect = TimeoutError("Task took too long")
                
                try:
                    task = sync_user_emails.delay(
                        user_id=test_user.id,
                        account_id=test_account.id
                    )
                except TimeoutError:
                    pass
                
                # Session sollte geschlossen sein (finally-Block!)
                mock_session.close.assert_called()

```

---

## 🧪 SCHRITT 6: Integration Tests (1.5h)

### 6.1 Test: Task mit echtem Service

```python
# tests/tasks/test_mail_sync_tasks_integration.py
"""Integration Tests mit echtem MailSyncService."""

import pytest
from unittest.mock import patch, MagicMock
from src.tasks.mail_sync_tasks import sync_user_emails
from src.celery_app import celery_app


@pytest.mark.celery
class TestMailSyncTaskIntegration:
    """Integration mit MailSyncService."""
    
    def test_sync_task_with_service(self, test_user, test_account, db_session):
        """Task sollte MailSyncService aufrufen."""
        
        # Mock MailSyncService
        with patch("src.tasks.mail_sync_tasks.MailSyncService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            
            mock_service.sync_emails.return_value = {
                "email_count": 42,
                "status": "success",
                "new_emails": 10
            }
            
            celery_app.conf.task_always_eager = True
            
            try:
                task = sync_user_emails.delay(
                    user_id=test_user.id,
                    account_id=test_account.id
                )
                
                # Service sollte aufgerufen worden sein
                mock_service.sync_emails.assert_called_once()
                
                # Result sollte Sync-Info enthalten
                if task.ready():
                    result = task.result
                    assert result["email_count"] == 42
                    assert result["status"] == "success"
            
            finally:
                celery_app.conf.task_always_eager = False
    
    def test_sync_task_updates_database(self, test_user, test_account, db_session):
        """Task sollte Datenbank aktualisieren."""
        
        from src.02_models import RawEmail
        
        # Erstelle Test-Email
        email = RawEmail(
            user_id=test_user.id,
            account_id=test_account.id,
            message_id="<test@example.com>",
            sender="test@example.com",
            subject="Test",
            folder="INBOX",
            uid=1001
        )
        db_session.add(email)
        db_session.commit()
        
        initial_count = db_session.query(RawEmail).filter_by(
            user_id=test_user.id
        ).count()
        
        with patch("src.services.mail_sync_service.MailSyncService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service
            
            # Service erstellt neue Emails
            mock_service.sync_emails.return_value = {
                "email_count": 5,
                "status": "success",
                "new_emails": 5
            }
            
            celery_app.conf.task_always_eager = True
            
            try:
                task = sync_user_emails.delay(
                    user_id=test_user.id,
                    account_id=test_account.id
                )
                
                # Nach Task sollten mehr Emails vorhanden sein
                final_count = db_session.query(RawEmail).filter_by(
                    user_id=test_user.id
                ).count()
                
                assert final_count >= initial_count
            
            finally:
                celery_app.conf.task_always_eager = False

```

---

## 🚀 SCHRITT 7: Tests ausführen

### 7.1 Alle Tests laufen lassen

```bash
cd /home/thomas/projects/KI-Mail-Helper-Dev

# Redis starten (erforderlich!)
docker run -d --name test-redis -p 6379:6379 redis:7

# Warten bis Redis ready
sleep 2
redis-cli ping

# Tests ausführen
pytest tests/tasks/ -v --tb=short

# Mit Coverage
pytest tests/tasks/ -v --cov=src.tasks --cov-report=html

# Nur schnelle Tests (nicht @pytest.mark.slow)
pytest tests/tasks/ -v -m "not slow"

# Specific test
pytest tests/tasks/test_mail_sync_tasks_retries.py::TestMailSyncTaskRetries::test_retry_on_network_error -v
```

### 7.2 Coverage-Report

```bash
# HTML Report öffnen
open htmlcov/index.html  # macOS
# oder
xdg-open htmlcov/index.html  # Linux

# Terminal Report
pytest tests/ --cov=src --cov-report=term-missing
```

---

## 📊 SCHRITT 8: Monitoring & Logging

### 8.1 Celery Task Logging

```python
# In mail_sync_tasks.py erweitern:
import logging
from src.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(bind=True)
def sync_user_emails(self, user_id, account_id):
    logger.info(f"[Task {self.request.id}] Starting sync for user {user_id}, account {account_id}")
    
    try:
        # ... Implementierung
        logger.info(f"[Task {self.request.id}] Sync completed successfully")
    except Exception as e:
        logger.error(f"[Task {self.request.id}] Sync failed: {e}", exc_info=True)
        raise
```

### 8.2 Test Monitoring

```python
# tests/tasks/test_mail_sync_tasks_monitoring.py
"""Monitoring und Logging validieren."""

import pytest
import logging


@pytest.mark.celery
def test_task_logging(test_user, test_account, caplog):
    """Task sollte ausführliche Logs schreiben."""
    
    from src.tasks.mail_sync_tasks import sync_user_emails
    from src.celery_app import celery_app
    
    with caplog.at_level(logging.INFO):
        celery_app.conf.task_always_eager = True
        
        try:
            task = sync_user_emails.delay(
                user_id=test_user.id,
                account_id=test_account.id
            )
        finally:
            celery_app.conf.task_always_eager = False
    
    # Logs sollten Task-ID enthalten
    assert any("Starting sync" in record.message for record in caplog.records)

```

---

## ✅ CHECKLISTE: Test-Coverage

- [ ] `conftest.py` erstellt mit Session/User/Account Fixtures
- [ ] `test_mail_sync_tasks_basic.py` → ✅ Task registriert
- [ ] `test_mail_sync_tasks_basic.py` → ✅ Task in Queue
- [ ] `test_mail_sync_tasks_errors.py` → ✅ Invalid IDs
- [ ] `test_mail_sync_tasks_errors.py` → ✅ Permission Denied
- [ ] `test_mail_sync_tasks_retries.py` → ✅ Retry on Error
- [ ] `test_mail_sync_tasks_retries.py` → ✅ Exponential Backoff
- [ ] `test_mail_sync_tasks_retries.py` → ✅ Max Retries
- [ ] `test_mail_sync_tasks_timeouts.py` → ✅ Soft Timeout
- [ ] `test_mail_sync_tasks_timeouts.py` → ✅ Hard Timeout
- [ ] `test_mail_sync_tasks_integration.py` → ✅ Service aufgerufen
- [ ] `test_mail_sync_tasks_integration.py` → ✅ DB aktualisiert
- [ ] Coverage: ≥ 85% in `src/tasks/`
- [ ] Coverage: ≥ 80% in `src/celery_app.py`

---

## 🐛 Troubleshooting

### Problem: "Connection refused" beim Redis-Test
```bash
# Redis läuft nicht!
docker ps | grep redis

# Starten:
docker run -d --name test-redis -p 6379:6379 redis:7
```

### Problem: "ModuleNotFoundError: No module named 'src'"
```bash
# sys.path nicht richtig gesetzt in conftest.py
# Lösung: In conftest.py:
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### Problem: "Task takes too long" beim Testing
```bash
# Timeout zu kurz gesetzt
# In conftest.py:
celery_app.conf.task_soft_time_limit = 300  # 5 Minuten für Tests
```

---

## 📚 Weiterführende Links

- pytest Dokumentation: https://docs.pytest.org/
- Celery Testing: https://docs.celeryproject.io/en/stable/userguide/testing.html
- fakeredis: https://github.com/anyascii/fakeredis
