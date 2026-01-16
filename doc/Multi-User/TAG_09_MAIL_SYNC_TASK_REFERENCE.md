# Tag 9 - Mail-Sync Task Implementation - Quick Reference

## ✅ Was erreicht wurde

### 1. Task Implementation
- **File:** [src/tasks/mail_sync_tasks.py](../src/tasks/mail_sync_tasks.py)
- `sync_user_emails(user_id, account_id, master_key, max_emails=50)`
  - Nutzt `MailSyncServiceV2` (3-Schritt-Workflow)
  - Retry-Mechanismus: 3x mit 60s, 120s, 240s Delays
  - Security: User & Account Ownership Validation
- `sync_all_accounts(user_id, master_key)`
  - Iteriert über alle Accounts eines Users
  - Partial Failure Handling

### 2. Blueprint Updates
- **File:** [src/blueprints/accounts.py](../src/blueprints/accounts.py)
- `fetch_mails()` - Dual-Mode: Celery (neu) oder Legacy (alt)
- `task_status(task_id)` - Neuer Endpoint für Task-Status
- Environment-Variable: `USE_LEGACY_JOBS=false` → aktiviert Celery

### 3. Tests
- **Unit-Tests:** [tests/test_mail_sync_tasks.py](../tests/test_mail_sync_tasks.py)
- **Integration-Test:** [scripts/celery-integration-test.py](../scripts/celery-integration-test.py)

---

## 🚀 Benutzung

### Option 1: Via UI (Empfohlen)

```bash
# 1. Flask App starten
cd /home/thomas/projects/KI-Mail-Helper-Dev
source venv/bin/activate
USE_BLUEPRINTS=1 python3 -m src.00_main --serve --https --port 5003

# 2. Browser öffnen: https://localhost:5003
# 3. Einloggen als 'thomas'
# 4. Settings → Mail-Accounts
# 5. "Sync" Button klicken

# 6. Task-Status in Flower: http://localhost:5555
```

### Option 2: Via Python (Manuell)

```python
from src.tasks.mail_sync_tasks import sync_user_emails

# Task queuen
task = sync_user_emails.delay(
    user_id=1,
    account_id=1,
    master_key="your_master_key_from_session",
    max_emails=50
)

print(f"Task ID: {task.id}")

# Status abfragen
import time
time.sleep(5)

from src.celery_app import celery_app
result = celery_app.AsyncResult(task.id)
print(f"State: {result.state}")
print(f"Result: {result.result if result.ready() else 'Still running...'}")
```

### Option 3: Via REST API

```bash
# 1. Sync triggern
curl -X POST https://localhost:5003/mail-account/1/fetch \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -H "Content-Type: application/json"

# Response:
# {
#   "status": "queued",
#   "task_id": "abc-123-xyz",
#   "task_type": "celery",
#   ...
# }

# 2. Task-Status abfragen
curl https://localhost:5003/tasks/abc-123-xyz \
  -H "Cookie: session=YOUR_SESSION_COOKIE"

# Response:
# {
#   "task_id": "abc-123-xyz",
#   "state": "SUCCESS",
#   "status": "completed",
#   "result": {
#     "status": "success",
#     "email_count": 42,
#     ...
#   }
# }
```

---

## 🔍 Monitoring & Debugging

### Celery Worker Logs
```bash
# Realtime
sudo journalctl -u mail-helper-celery-worker -f

# Last 50 lines
tail -50 /var/log/mail-helper/celery-worker.log

# Errors only
grep ERROR /var/log/mail-helper/celery-worker.log
```

### Flower Web UI
```bash
# Öffnen
xdg-open http://localhost:5555

# Features:
# - Task History
# - Active Tasks
# - Worker Status
# - Task Details mit Traceback bei Fehler
```

### Health-Check
```bash
bash scripts/celery-health-check.sh
```

### Integration-Test
```bash
python3 scripts/celery-integration-test.py
```

---

## 🔧 Troubleshooting

### Problem: Task bleibt in PENDING
```bash
# Check: Worker läuft?
systemctl status mail-helper-celery-worker

# Check: Redis erreichbar?
redis-cli ping  # Sollte: PONG

# Check: Task registriert?
python3 scripts/celery-integration-test.py
```

### Problem: Task schlägt sofort fehl
```bash
# Check Logs
tail -100 /var/log/mail-helper/celery-worker.log | grep ERROR

# Häufige Ursachen:
# 1. Master-Key fehlt/falsch → Session-Problem
# 2. Account nicht gefunden → user_id/account_id falsch
# 3. IMAP-Credentials → Entschlüsselung fehlgeschlagen
```

### Problem: Worker crashed
```bash
# Restart
sudo systemctl restart mail-helper-celery-worker

# Check Status
systemctl status mail-helper-celery-worker

# Check Logs für Crash-Ursache
sudo journalctl -u mail-helper-celery-worker --since "10 minutes ago"
```

---

## 📊 Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│                    Flask App (Port 5003)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Blueprint: accounts.py                                  │ │
│  │ Route: POST /mail-account/<id>/fetch                   │ │
│  │ ├─ USE_LEGACY_JOBS=false → Celery Path                │ │
│  │ └─ USE_LEGACY_JOBS=true  → Legacy Path                │ │
│  └────────────────────────────────────────────────────────┘ │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    │ task.delay()
                    ↓
         ┌──────────────────────┐
         │   Redis (Port 6379)   │  ← Message Broker
         │   Database 1: Celery  │
         └──────────────────────┘
                    │
                    │ consume
                    ↓
    ┌───────────────────────────────────┐
    │ Celery Worker (systemd service)   │
    │ - 4 Prozesse (prefork pool)       │
    │ - Task: sync_user_emails          │
    │   └─> MailSyncServiceV2           │
    │       └─> IMAPClient → IMAP Server│
    │       └─> PostgreSQL (write)      │
    └───────────────────────────────────┘
                    │
                    │ result
                    ↓
         ┌──────────────────────┐
         │   Redis (Port 6379)   │  ← Result Backend
         │   Database 2: Results │
         └──────────────────────┘
                    │
                    │ query
                    ↓
         ┌──────────────────────┐
         │ Flower (Port 5555)    │  ← Monitoring
         │ Web UI                │
         └──────────────────────┘
```

---

## 🎯 Nächste Schritte (Tag 10)

1. **End-to-End Test** mit echtem Mail-Account
   - Flask App starten
   - Einloggen
   - Sync Button klicken
   - Result in Flower prüfen

2. **Load-Test**
   - 10 parallele Sync-Tasks
   - Performance messen

3. **Error-Handling Test**
   - IMAP-Fehler simulieren
   - Retry-Mechanismus verifizieren

4. **Monitoring Setup**
   - Alerting konfigurieren
   - Grafana/Prometheus (optional)

---

**Status:** ✅ Tag 9 ABGESCHLOSSEN  
**Nächster Schritt:** Tag 10 - Testing & Verification  
**Bereit für:** Production Go-Live (nach Tag 10)
