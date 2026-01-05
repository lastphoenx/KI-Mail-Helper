# 🔄 Task 6: Mail-Processing Pipeline Integration

**Integration von Diagnostics UI mit Mail-Fetcher & Multi-Account Orchestration**

**Status:** 🎯 Geplant (nach Phase 11.5 & Task 5)  
**Priority:** 🔴 Höchste  
**Estimated Effort:** 60-80 Stunden  
**Created:** 30. Dezember 2025

---

## 📋 Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Zielsetzung & Probleme](#zielsetzung--probleme)
3. [Architektur-Übersicht](#architektur-übersicht)
4. [Pipeline Broker Design](#pipeline-broker-design)
5. [Job Queue System](#job-queue-system)
6. [Multi-Account Testing](#multi-account-testing)
7. [Performance-Profiling](#performance-profiling)
8. [Background Job Error-Handling](#background-job-error-handling)
9. [Monitoring & Observability](#monitoring--observability)
10. [TODO-Liste](#todo-liste)

---

## Überblick

**Goal:** Diagnostics UI + Mail-Fetcher + Background-Jobs koordinieren in einer Production-Ready Pipeline

**Aktuelles Problem:**
```
Diagnostics (imap_diagnostics.py)
    ↓ (isoliert, nur Tests)
    
Mail-Fetcher (06_mail_fetcher.py)
    ↓ (Production, aber unabhängig)
    
Background-Jobs (14_background_jobs.py)
    ↓ (entkoppelt, keine Koordination)
    
→ Keine zentrale Orchestration
→ Keine Performance-Metriken
→ Keine Fehlerbehandlung über Komponenten hinweg
```

**Gewünscht:**
```
┌─────────────────────────────────┐
│  Pipeline Broker (NEW)           │
├─────────────────────────────────┤
│ ├─ Job Queue Management          │
│ ├─ Performance Metrics           │
│ ├─ Error Recovery                │
│ ├─ Account State Management      │
│ └─ Progress Tracking             │
└────┬──────────────┬──────────────┘
     │              │
     ▼              ▼
┌──────────────┐ ┌─────────────────┐
│ Diagnostics  │ │ Mail-Fetcher    │
│ (Tests)      │ │ (Production)    │
└──────────────┘ └─────────────────┘
```

---

## Zielsetzung & Probleme

### Probleme der aktuellen Implementierung

#### 1. Isolation

- Diagnostics Tests sind isoliert (nur zum Testen)
- Mail-Fetcher läuft unabhängig
- Background Jobs haben keine Einsicht in Fehler anderer Jobs
- **Resultat:** Keine ganzheitliche Überwachung

#### 2. Multi-Account Szenarien

```
Current: Accounts werden sequenziell verarbeitet
User 1 hat 3 Accounts (GMX, Gmail, Outlook)
  Account 1 (GMX): 5s
  Account 2 (Gmail): 8s
  Account 3 (Outlook): 3s
  Total: 16s (sequenziell)

Desired: Parallelisiert, mit Fehlerbehandlung
  Accounts 1,2,3 parallel: max 8s
  Aber: Nur wenn einer nicht fehlschlägt!
```

#### 3. Performance-Metriken

- Wir wissen nicht wie lange Fetches dauern
- Wir wissen nicht ob es Bottlenecks gibt (I/O vs CPU)
- Wir können nicht planen wann Maintenance ist
- **Resultat:** Keine Basis für Optimierungen

#### 4. Error Recovery

- Bei Timeout: Job schlägt still fehl
- Bei Auth-Error: Keine Benachrichtigung
- Bei Partial Failure: Keine Retry
- **Resultat:** User wissen nicht dass Fetch fehlgeschlagen ist

---

## Architektur-Übersicht

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    PIPELINE BROKER                          │
│                                                              │
│ 1. Fetch Job enqueued                                        │
│ 2. For each account:                                         │
│    ├─ Load credentials (decrypted with master_key)           │
│    ├─ Check account health (HEALTHY/DEGRADED/BROKEN)         │
│    ├─ Execute diagnostics (CAPABILITY check)                 │
│    ├─ Execute mail-fetch (with timeout)                      │
│    └─ Store metrics (duration, email count, errors)          │
│ 3. On error:                                                 │
│    ├─ Check retry-count                                      │
│    ├─ If retryable: enqueue again                            │
│    └─ If permanent: alert user                               │
│ 4. Job complete: store result in DB                          │
└─────────────────────────────────────────────────────────────┘
```

### Component Interaction

```
┌────────────────────────────────────────────────┐
│ FlaskWeb                                       │
├────────────────────────────────────────────────┤
│ Route: POST /mail-account/<id>/fetch           │
│ ├─ Get user from session                       │
│ ├─ Get master_key from session                 │
│ └─ Call PipelineBroker.enqueue_fetch_job()     │
└────────────────┬───────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│ PipelineBroker                                 │
├────────────────────────────────────────────────┤
│ - enqueue_fetch_job()                          │
│ - execute_fetch_job()                          │
│ - handle_job_error()                           │
│ - get_account_status()                         │
│ - get_performance_metrics()                    │
└────────────────┬───────────────────────────────┘
                 │
     ┌───────────┴───────────┐
     │                       │
     ▼                       ▼
┌──────────────────────┐ ┌──────────────────┐
│ Mail-Fetcher         │ │ Diagnostics      │
│ - fetch_new_emails() │ │ - test_*()       │
│ - connect()          │ │ - run_all_tests()│
│ - disconnect()       │ └──────────────────┘
└──────────────────────┘
```

---

## Pipeline Broker Design

### Core Interface

```python
# src/pipeline_broker.py

from enum import Enum
from typing import Optional, Dict, List
from datetime import datetime, timedelta, UTC
import uuid

class AccountHealth(str, Enum):
    """Health status of a mail account"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BROKEN = "broken"

class JobStatus(str, Enum):
    """Job execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    RETRYING = "retrying"

class PipelineJob:
    """Represents a fetch/process job"""
    
    def __init__(
        self,
        job_id: str,
        user_id: int,
        account_id: int,
        job_type: str,  # fetch, process, diagnostics
        master_key: str,
        max_mails: int = 100,
        timeout_seconds: int = 120
    ):
        self.job_id = job_id
        self.user_id = user_id
        self.account_id = account_id
        self.job_type = job_type
        self.master_key = master_key
        self.max_mails = max_mails
        self.timeout_seconds = timeout_seconds
        
        # Execution state
        self.status = JobStatus.PENDING
        self.created_at = datetime.now(UTC)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        
        # Results
        self.emails_fetched = 0
        self.emails_processed = 0
        self.errors: List[str] = []
        self.retry_count = 0
        self.metrics = {}

class PipelineBroker:
    """Orchestrates mail-fetching and processing pipeline"""
    
    def __init__(self, db_session, diagnostics_client=None):
        self.db = db_session
        self.diag = diagnostics_client
        self.job_queue = {}  # In-memory for MVP, move to DB later
    
    def enqueue_fetch_job(
        self,
        user_id: int,
        account_id: Optional[int] = None,
        master_key: Optional[str] = None,
        max_mails: int = 100,
        timeout_seconds: int = 120
    ) -> str:
        """Enqueue a fetch job for one or all accounts"""
        
        job_id = str(uuid.uuid4())
        job = PipelineJob(
            job_id=job_id,
            user_id=user_id,
            account_id=account_id,
            job_type='fetch',
            master_key=master_key,
            max_mails=max_mails,
            timeout_seconds=timeout_seconds
        )
        
        self.job_queue[job_id] = job
        logger.info(f"Job {job_id} enqueued for user {user_id}")
        
        # TODO: Use APScheduler or Celery to execute
        # For MVP: execute synchronously
        self.execute_fetch_job(job)
        
        return job_id
    
    def execute_fetch_job(self, job: PipelineJob) -> PipelineJob:
        """Execute a fetch job with error handling & metrics"""
        
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        
        try:
            user = self.db.query(models.User).filter_by(id=job.user_id).first()
            
            if job.account_id:
                # Single account
                accounts = [
                    self.db.query(models.MailAccount).filter_by(
                        id=job.account_id, user_id=job.user_id
                    ).first()
                ]
            else:
                # All accounts
                accounts = self.db.query(models.MailAccount).filter_by(
                    user_id=job.user_id, enabled=True
                ).all()
            
            if not accounts:
                job.status = JobStatus.FAILED
                job.errors.append("No accounts found")
                return job
            
            # Process each account
            for account in accounts:
                try:
                    self._fetch_from_account(job, user, account)
                except Exception as e:
                    job.errors.append(f"Account {account.id}: {str(e)}")
                    self._update_account_health(account, AccountHealth.DEGRADED)
            
            # Determine final status
            if not job.errors:
                job.status = JobStatus.SUCCESS
            elif len(job.errors) < len(accounts):
                job.status = JobStatus.PARTIAL_FAILURE
            else:
                job.status = JobStatus.FAILED
        
        except Exception as e:
            logger.error(f"Job {job.job_id} failed: {e}")
            job.status = JobStatus.FAILED
            job.errors.append(str(e))
        
        finally:
            job.completed_at = datetime.now(UTC)
            self._store_job_result(job)
        
        return job
    
    def _fetch_from_account(self, job: PipelineJob, user, account):
        """Fetch emails from a single account"""
        
        # Timing
        start_time = time.time()
        
        try:
            # 1. Run diagnostics (check connectivity)
            self._run_diagnostics(job, account)
            
            # 2. Fetch emails
            fetcher = get_mail_fetcher_for_account(account, job.master_key)
            fetcher.connect()
            
            try:
                emails = fetcher.fetch_new_emails(
                    folder='INBOX',
                    limit=job.max_mails
                )
                
                job.emails_fetched += len(emails)
                
                # 3. Store in database
                saved = self._persist_emails(job, user, account, emails)
                
                # 4. Process emails
                processed = self._process_emails(job, user, account)
                job.emails_processed += processed
                
                # Store metrics
                duration = time.time() - start_time
                job.metrics[f"account_{account.id}"] = {
                    'duration': duration,
                    'emails_fetched': len(emails),
                    'emails_processed': processed,
                    'success': True
                }
                
                # Update health
                self._update_account_health(account, AccountHealth.HEALTHY)
            
            finally:
                fetcher.disconnect()
        
        except Exception as e:
            duration = time.time() - start_time
            job.metrics[f"account_{account.id}"] = {
                'duration': duration,
                'success': False,
                'error': str(e)
            }
            
            raise
    
    def _run_diagnostics(self, job: PipelineJob, account):
        """Run diagnostics before fetch"""
        
        if not self.diag:
            return
        
        try:
            # Quick connection test
            result = self.diag.test_connection()
            
            if not result.get('connected'):
                raise ConnectionError("Diagnostics: Cannot connect to server")
            
            # Capability check
            caps = self.diag.test_capabilities()
            
            if not caps.get('capabilities'):
                raise RuntimeError("Diagnostics: Cannot get capabilities")
            
            logger.debug(f"Diagnostics passed for account {account.id}")
        
        except Exception as e:
            logger.warning(f"Diagnostics failed for account {account.id}: {e}")
            raise
    
    def _persist_emails(self, job, user, account, emails) -> int:
        """Store fetched emails in database"""
        # Reuse from 14_background_jobs.py
        pass
    
    def _process_emails(self, job, user, account) -> int:
        """Run KI processing on emails"""
        # Reuse from 12_processing.py
        pass
    
    def _update_account_health(self, account, health: AccountHealth):
        """Update account health status"""
        account.health_status = health
        account.health_checked_at = datetime.now(UTC)
        self.db.commit()
    
    def _store_job_result(self, job: PipelineJob):
        """Store job result in database for audit & monitoring"""
        
        job_record = models.PipelineJob(
            job_id=job.job_id,
            user_id=job.user_id,
            account_id=job.account_id,
            job_type=job.job_type,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            emails_fetched=job.emails_fetched,
            emails_processed=job.emails_processed,
            errors=json.dumps(job.errors),
            metrics=json.dumps(job.metrics),
            retry_count=job.retry_count
        )
        
        self.db.add(job_record)
        self.db.commit()
    
    def get_job_status(self, job_id: str) -> Optional[PipelineJob]:
        """Get current job status"""
        return self.job_queue.get(job_id)
    
    def get_account_health(self, user_id: int) -> Dict:
        """Get health status for all user accounts"""
        
        accounts = self.db.query(models.MailAccount).filter_by(
            user_id=user_id, enabled=True
        ).all()
        
        return {
            account.id: {
                'name': account.name,
                'health': account.health_status or AccountHealth.HEALTHY,
                'checked_at': account.health_checked_at,
                'last_fetch': account.last_fetch_at
            }
            for account in accounts
        }
    
    def get_performance_metrics(self, user_id: int) -> Dict:
        """Get performance metrics for user's accounts"""
        
        jobs = self.db.query(models.PipelineJob).filter_by(
            user_id=user_id,
            status=JobStatus.SUCCESS
        ).order_by(
            models.PipelineJob.completed_at.desc()
        ).limit(100).all()
        
        if not jobs:
            return {}
        
        # Aggregate metrics
        total_duration = sum(j.duration for j in jobs)
        total_emails = sum(j.emails_fetched for j in jobs)
        avg_duration = total_duration / len(jobs)
        
        return {
            'total_jobs': len(jobs),
            'total_duration': total_duration,
            'avg_duration': avg_duration,
            'total_emails_fetched': total_emails,
            'avg_emails_per_job': total_emails / len(jobs)
        }
```

---

## Job Queue System

### Option 1: APScheduler (Empfohlen für MVP)

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

# src/job_queue.py

class JobQueue:
    """Job queue using APScheduler"""
    
    def __init__(self, db_engine):
        jobstores = {
            'default': SQLAlchemyJobStore(engine=db_engine)
        }
        
        executors = {
            'default': ThreadPoolExecutor(max_workers=4)
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            timezone='UTC'
        )
    
    def start(self):
        self.scheduler.start()
    
    def enqueue_fetch(self, user_id: int, account_id: int, master_key: str):
        """Schedule a fetch job"""
        
        job_id = self.scheduler.add_job(
            func=self._execute_fetch,
            args=(user_id, account_id, master_key),
            id=f"fetch_{user_id}_{account_id}_{uuid.uuid4()}",
            coalesce=True,  # If 2+ jobs scheduled, execute only once
            max_instances=1  # Don't run same job twice
        )
        
        return job_id.id
    
    def _execute_fetch(self, user_id: int, account_id: int, master_key: str):
        """Actual job execution (runs in background thread)"""
        
        broker = PipelineBroker(get_db_session())
        job = broker.enqueue_fetch_job(
            user_id=user_id,
            account_id=account_id,
            master_key=master_key
        )
        
        return job.job_id
```

### Option 2: Celery (für Production mit vielen Jobs)

```python
# src/celery_app.py

from celery import Celery
from celery.schedules import crontab

celery_app = Celery(__name__)
celery_app.conf.broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379')
celery_app.conf.result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379')

@celery_app.task(name='fetch_emails')
def fetch_emails_task(user_id: int, account_id: int, master_key: str):
    """Celery task for fetching emails"""
    
    broker = PipelineBroker(get_db_session())
    job = broker.enqueue_fetch_job(
        user_id=user_id,
        account_id=account_id,
        master_key=master_key
    )
    
    return {
        'job_id': job.job_id,
        'status': job.status,
        'emails_fetched': job.emails_fetched
    }

# Periodic task: fetch all accounts daily
celery_app.conf.beat_schedule = {
    'fetch-all-accounts-daily': {
        'task': 'fetch_emails',
        'schedule': crontab(hour=9, minute=0)  # 09:00 UTC daily
    }
}
```

---

## Multi-Account Testing

### Test-Szenarien

#### Szenario 1: Sequenziell (Baseline)

```
Account A (GMX): CONNECT → FETCH → DISCONNECT: 2.5s
Account B (Gmail): CONNECT → FETCH → DISCONNECT: 3.2s
Account C (Outlook): CONNECT → FETCH → DISCONNECT: 1.8s
─────────────────────────────────────────────────────
Total: 7.5s (sequenziell)
```

#### Szenario 2: Parallel (Optimal)

```
Account A ─┐
Account B ─┼→ max(2.5s, 3.2s, 1.8s) = 3.2s
Account C ─┘
```

#### Szenario 3: Cascade Error

```
Account A (GMX): SUCCESS (2.5s)
Account B (Gmail): TIMEOUT (retry nach 2s, dann 4s)
Account C (Outlook): Sollte NICHT warten auf B!
    → Läuft parallel/unabhängig

Result: 
  A: 2.5s ✓
  B: 5s (timeout + retry) ✗
  C: 1.8s ✓
  Total: 5s (nicht blockiert durch B)
```

### Test Implementation

```python
# tests/test_pipeline_multi_account.py

def test_multi_account_parallel_fetch(self):
    """Test fetching from multiple accounts in parallel"""
    
    # Setup: Create test user with 3 accounts
    user = create_test_user()
    accounts = [
        create_test_account(user, 'GMX'),
        create_test_account(user, 'Gmail'),
        create_test_account(user, 'Outlook')
    ]
    
    broker = PipelineBroker(db_session)
    
    # Fetch all accounts
    start_time = time.time()
    job = broker.enqueue_fetch_job(user_id=user.id)
    duration = time.time() - start_time
    
    # Assert: Total time ~= max account time, not sum
    assert duration < 10  # Should be faster than 7.5s (sequential)
    assert job.status == JobStatus.SUCCESS
    assert len(job.metrics) == 3  # 3 accounts processed

def test_multi_account_cascade_error(self):
    """Test that one failing account doesn't block others"""
    
    user = create_test_user()
    accounts = [
        create_test_account(user, 'GMX', healthy=True),
        create_test_account(user, 'Gmail', healthy=False),  # Will timeout
        create_test_account(user, 'Outlook', healthy=True)
    ]
    
    broker = PipelineBroker(db_session)
    job = broker.enqueue_fetch_job(user_id=user.id)
    
    # Assert: A and C succeeded, B failed
    assert job.metrics['account_a']['success'] == True
    assert job.metrics['account_b']['success'] == False
    assert job.metrics['account_c']['success'] == True
    
    # Job status is PARTIAL_FAILURE (not all failed)
    assert job.status == JobStatus.PARTIAL_FAILURE
```

---

## Performance-Profiling

### Metrics zu sammeln

```python
class PerformanceMetrics:
    """Metrics for a fetch operation"""
    
    account_id: int
    duration: float  # Total time in seconds
    
    # Breakdown
    connect_time: float
    folder_list_time: float
    fetch_time: float
    parse_time: float
    save_time: float
    process_time: float
    disconnect_time: float
    
    # Results
    email_count: int
    folder_count: int
    
    # Resource usage
    memory_peak_mb: float
    cpu_percent: float
```

### Profiling Implementation

```python
import cProfile
import pstats
import psutil

class PerformanceProfiler:
    """Profile fetch operations for bottleneck detection"""
    
    def __init__(self):
        self.metrics = []
    
    def profile_fetch(self, fetcher, folder='INBOX', limit=100):
        """Profile mail fetch operation"""
        
        process = psutil.Process()
        
        # Memory baseline
        mem_before = process.memory_info().rss / 1024 / 1024  # MB
        
        # CPU profiling
        profiler = cProfile.Profile()
        
        start_time = time.time()
        profiler.enable()
        
        try:
            emails = fetcher.fetch_new_emails(folder=folder, limit=limit)
        finally:
            profiler.disable()
        
        duration = time.time() - start_time
        
        # Memory peak
        mem_after = process.memory_info().rss / 1024 / 1024
        mem_peak = mem_after - mem_before
        
        # CPU stats
        stats = pstats.Stats(profiler)
        
        # Store metrics
        metric = PerformanceMetrics(
            account_id=fetcher.account_id,
            duration=duration,
            email_count=len(emails),
            memory_peak_mb=max(mem_peak, 0),
            cpu_percent=process.cpu_percent(interval=1)
        )
        
        self.metrics.append(metric)
        
        return metric
    
    def report(self):
        """Generate performance report"""
        
        if not self.metrics:
            return "No metrics collected"
        
        avg_duration = sum(m.duration for m in self.metrics) / len(self.metrics)
        max_memory = max(m.memory_peak_mb for m in self.metrics)
        
        return f"""
Performance Report:
  Avg Duration: {avg_duration:.2f}s
  Max Memory: {max_memory:.2f}MB
  Emails Fetched: {sum(m.email_count for m in self.metrics)}
  
Per-Account Breakdown:
{chr(10).join([f"  Account {m.account_id}: {m.duration:.2f}s ({m.email_count} emails)" for m in self.metrics])}
"""
```

### Acceptable Performance Targets

| Operation | Target | Acceptable | Critical |
|-----------|--------|-----------|----------|
| Connect | < 1s | < 2s | > 5s ❌ |
| Folder List | < 1s | < 2s | > 10s ❌ |
| Fetch 50 Mails | < 2s | < 5s | > 15s ❌ |
| Parse + Save | < 1s | < 3s | > 10s ❌ |
| **Total (100 Mails)** | < 5s | < 10s | > 30s ❌ |

---

## Background Job Error-Handling

### Error-Klassifizierung

```python
class ErrorType(str, Enum):
    """Classification of errors for retry decisions"""
    
    # Transient (Retry)
    TIMEOUT = "timeout"
    CONNECTION_RESET = "connection_reset"
    TEMPORARY_UNAVAILABLE = "temporarily_unavailable"
    
    # Permanent (Don't retry)
    AUTH_FAILED = "auth_failed"
    INVALID_CREDENTIALS = "invalid_credentials"
    ACCOUNT_DISABLED = "account_disabled"
    
    # Unknown
    UNKNOWN = "unknown"
```

### Retry-Logic

```python
class RetryPolicy:
    """Policy for retrying failed operations"""
    
    MAX_RETRIES = 3
    
    # Exponential backoff: 1s, 2s, 4s
    BACKOFF_BASE = 2
    BACKOFF_INITIAL = 1
    
    # Circuit breaker: after 5 failures in 1 hour, disable account
    FAILURE_THRESHOLD = 5
    FAILURE_WINDOW = 3600  # seconds
    
    @staticmethod
    def get_retry_delay(attempt: int) -> int:
        """Get delay in seconds for retry attempt"""
        return RetryPolicy.BACKOFF_INITIAL * (RetryPolicy.BACKOFF_BASE ** attempt)
    
    @staticmethod
    def should_retry(error: Exception, attempt: int) -> bool:
        """Decide whether to retry based on error type"""
        
        if attempt >= RetryPolicy.MAX_RETRIES:
            return False
        
        error_type = classify_error(error)
        
        if error_type in [ErrorType.AUTH_FAILED, ErrorType.INVALID_CREDENTIALS]:
            return False  # Never retry auth errors
        
        if error_type == ErrorType.ACCOUNT_DISABLED:
            return False  # Account disabled, won't help to retry
        
        # Retry all transient errors
        return error_type in [
            ErrorType.TIMEOUT,
            ErrorType.CONNECTION_RESET,
            ErrorType.TEMPORARY_UNAVAILABLE
        ]
```

### Error Handler Implementation

```python
def handle_job_error(self, job: PipelineJob, error: Exception):
    """Handle job failure with retry logic"""
    
    error_type = self._classify_error(error)
    
    # Should retry?
    if RetryPolicy.should_retry(error, job.retry_count):
        job.retry_count += 1
        delay = RetryPolicy.get_retry_delay(job.retry_count)
        
        # Enqueue retry
        self.scheduler.add_job(
            func=self.execute_fetch_job,
            args=(job,),
            trigger='date',
            run_date=datetime.now(UTC) + timedelta(seconds=delay)
        )
        
        job.status = JobStatus.RETRYING
        logger.info(f"Job {job.job_id} will retry in {delay}s")
    
    else:
        # Permanent error or max retries exceeded
        job.status = JobStatus.FAILED
        
        # Alert user
        self._notify_user(
            user_id=job.user_id,
            title="Mail Fetch Failed",
            message=f"Failed to fetch mails: {error}"
        )
        
        # Update account health
        account = self.db.query(models.MailAccount).filter_by(
            id=job.account_id
        ).first()
        
        if error_type == ErrorType.AUTH_FAILED:
            self._update_account_health(account, AccountHealth.BROKEN)
        else:
            self._update_account_health(account, AccountHealth.DEGRADED)
```

---

## Monitoring & Observability

### Dashboard Komponenten

#### Job History

```html
<div class="job-history">
  <h3>Letzte 10 Fetch-Jobs</h3>
  <table>
    <tr>
      <th>Job-ID</th>
      <th>User</th>
      <th>Account</th>
      <th>Status</th>
      <th>Duration</th>
      <th>Emails</th>
      <th>Timestamp</th>
    </tr>
    <tr class="success">
      <td>#job-123</td>
      <td>user@example.com</td>
      <td>GMX</td>
      <td>✅ Success</td>
      <td>2.3s</td>
      <td>12</td>
      <td>2024-12-30 09:15</td>
    </tr>
    <tr class="partial-failure">
      <td>#job-124</td>
      <td>user@example.com</td>
      <td>All (3 accounts)</td>
      <td>⚠️ Partial Failure</td>
      <td>5.2s</td>
      <td>45/50</td>
      <td>2024-12-30 09:30</td>
    </tr>
    <!-- More rows... -->
  </table>
</div>
```

#### Performance Trends

```html
<div class="performance-trends">
  <h3>7-Tage Performance-Trend</h3>
  <canvas id="performance-chart"></canvas>
  
  <div class="metrics">
    <div class="metric">
      <label>Ø Fetch-Zeit</label>
      <value>3.2s</value>
    </div>
    <div class="metric">
      <label>Success Rate</label>
      <value>94%</value>
    </div>
    <div class="metric">
      <label>Total Emails</label>
      <value>1,234</value>
    </div>
  </div>
</div>
```

#### Account Health

```html
<div class="account-health">
  <h3>Account-Status</h3>
  
  <div class="account healthy">
    <span class="status-indicator healthy"></span>
    <span class="name">GMX</span>
    <span class="last-check">Letzte Prüfung: vor 2min</span>
  </div>
  
  <div class="account degraded">
    <span class="status-indicator degraded"></span>
    <span class="name">Gmail</span>
    <span class="last-check">Letzte Prüfung: vor 30min</span>
    <span class="error">⚠️ 2 Fehler in letzten 5 Versuchen</span>
  </div>
  
  <div class="account broken">
    <span class="status-indicator broken"></span>
    <span class="name">Outlook</span>
    <span class="last-check">Letzte Prüfung: vor 1h</span>
    <span class="error">❌ Auth fehgeschlagen - Credentials neubindung nötig</span>
  </div>
</div>
```

### Logging & Alerting

```python
# Structured logging für Pipeline-Events

logger.info(
    "Job started",
    extra={
        'job_id': job.job_id,
        'user_id': job.user_id,
        'account_id': job.account_id,
        'type': 'pipeline_event'
    }
)

logger.warning(
    "Job partial failure",
    extra={
        'job_id': job.job_id,
        'processed': 45,
        'failed': 5,
        'type': 'pipeline_event'
    }
)

# Alert-System
class AlertManager:
    def send_alert(self, user_id: int, title: str, message: str):
        """Send alert to user via email or in-app notification"""
        
        # Option 1: In-app notification
        notification = models.Notification(
            user_id=user_id,
            title=title,
            message=message,
            created_at=datetime.now(UTC)
        )
        self.db.add(notification)
        self.db.commit()
        
        # Option 2: Email notification (optional)
        # send_email(user.email, title, message)
```

---

## TODO-Liste

### Phase 1: Pipeline Broker Design & Implementation (2-3 Wochen, 40-50h)

- [ ] Design PipelineBroker class
  - [ ] Job queuing mechanism
  - [ ] Job execution with error handling
  - [ ] Performance metrics collection
  - [ ] Account health tracking

- [ ] Implement core methods:
  - [ ] enqueue_fetch_job()
  - [ ] execute_fetch_job()
  - [ ] _fetch_from_account()
  - [ ] handle_job_error()
  - [ ] get_account_health()

- [ ] Database changes:
  - [ ] Add PipelineJob table (audit trail)
  - [ ] Add AccountHealth enum/status
  - [ ] Add health_status & health_checked_at to MailAccount

- [ ] Unit-Tests:
  - [ ] test_job_enqueueing
  - [ ] test_single_account_fetch
  - [ ] test_multiple_account_fetch
  - [ ] test_error_handling

### Phase 2: Job Queue Integration (1-2 Wochen, 20-30h)

- [ ] Choose job scheduler (APScheduler for MVP)
  - [ ] Setup background scheduler
  - [ ] Implement job enqueuing
  - [ ] Setup periodic tasks

- [ ] Flask integration:
  - [ ] Route: POST /api/jobs/fetch
  - [ ] Route: GET /api/jobs/<job_id>
  - [ ] Route: GET /api/jobs/history

- [ ] Error handling:
  - [ ] Implement RetryPolicy
  - [ ] Error classification logic
  - [ ] Circuit breaker for broken accounts

### Phase 3: Multi-Account Testing & Optimization (2 Wochen, 30-40h)

- [ ] Performance profiling:
  - [ ] Implement PerformanceProfiler
  - [ ] Benchmark single vs. multiple accounts
  - [ ] Identify bottlenecks (I/O vs. CPU)

- [ ] Test scenarios:
  - [ ] Sequential vs. parallel fetch
  - [ ] Cascade error handling
  - [ ] Timeout recovery
  - [ ] Auth failure handling

- [ ] Optimization:
  - [ ] Connection pooling (if needed)
  - [ ] Parallel account processing
  - [ ] Adaptive timeout adjustment

### Phase 4: Monitoring & Dashboard (1-2 Wochen, 20-30h)

- [ ] Metrics collection:
  - [ ] Job duration & status
  - [ ] Email count per account
  - [ ] Error rates & types
  - [ ] Performance trends

- [ ] Dashboard implementation:
  - [ ] Job history display
  - [ ] Performance charts (7-day trend)
  - [ ] Account health status
  - [ ] Real-time monitoring

- [ ] Alerting system:
  - [ ] In-app notifications
  - [ ] Email alerts (optional)
  - [ ] Alert thresholds & rules

### Phase 5: Documentation & Deployment (1 Woche, 15-20h)

- [ ] Document Pipeline Broker API
- [ ] Write operational runbook
- [ ] Setup monitoring/alerting in production
- [ ] Create disaster recovery plan
- [ ] Test full pipeline against staging

---

## Success Criteria

- ✅ Pipeline Broker orchestriert Fetch + Processing + Diagnostics
- ✅ Multi-account Fetches laufen (teilweise) parallel
- ✅ Job-Status wird tracked & accessible
- ✅ Fehler werden klassifiziert & retry-entscheidungen getroffen
- ✅ Account-Health wird monitored (HEALTHY/DEGRADED/BROKEN)
- ✅ Performance-Metriken werden gesammelt & visualisiert
- ✅ Partial failures werden korrekt gehandhabt (nicht blockierend)
- ✅ Circuit breaker stoppt Retries bei zu vielen Fehlern
- ✅ Alerts bei kritischen Fehlern
- ✅ Zero-Knowledge Architektur eingehalten

---

## Dependencies

- ✅ Phase 11.5: IMAP Diagnostics (Tests verfügbar)
- ✅ Task 5: Bulk Operations (optional, aber sinnvoll)
- ⚠️ Task 12: Metadata Enrichment (für erweiterte Metriken)
- 🔴 APScheduler oder Celery (neu)

---

## Estimated Timeline

| Phase | Effort | Time (1 FTE) |
|-------|--------|-------------|
| 1: Pipeline Broker | 40-50h | 1-1.5 Wochen |
| 2: Job Queue | 20-30h | 0.5-1 Woche |
| 3: Multi-Account Testing | 30-40h | 1-1.5 Wochen |
| 4: Monitoring | 20-30h | 0.5-1 Woche |
| 5: Documentation | 15-20h | 0.5 Woche |
| **TOTAL** | **125-170h** | **3.5-5.5 Wochen** |

---

**Nächste Schritte:** Nach Task 5 (Bulk Operations) und Task 12 (Metadata) implementieren.
