# Legacy Code Deprecation Plan
## KI-Mail-Helper Multi-User Migration

**Status**: Produktionsreifen Decommissioning-Plan  
**Geschätzter Aufwand**: 2-3 Stunden  
**Datum**: Januar 2026  
**Sprache**: Deutsch  

---

## 🎯 ZIEL

Strukturierter Plan zur Ablösung von `src/14_background_jobs.py` durch Celery-basierte Task-Architecture mit:
- ✅ Strikte Deprecation-Timeline
- ✅ Feature-Flag für Deaktivierung
- ✅ Katalogisierung aller Abhängigkeiten
- ✅ Parallel-Phase für Sicherheit (kein Datenkonflikt)
- ✅ Monitoring für Fehler in alter/neuer API

---

## 📊 SCHRITT 1: Dependency-Analyse

### 1.1 Katalogisiere alle Importe von 14_background_jobs.py

```bash
cd /home/thomas/projects/KI-Mail-Helper-Dev

# Alle Imports finden
grep -r "import.*14_background_jobs\|from.*14_background_jobs\|from.*BackgroundJobQueue" src/ --include="*.py" | tee legacy_imports.log

# Zähle
wc -l legacy_imports.log
```

**Erwartete Outputs:**
```
src/01_web_app.py:from src.14_background_jobs import BackgroundJobQueue
src/blueprints/accounts.py:from src.14_background_jobs import FetchJob
src/blueprints/api.py:job_queue = ...  # Impliziter Job-Queue Zugriff
```

### 1.2 Script: Dependency-Katalog

```python
# scripts/analyze_legacy_imports.py
"""Analysiere alle Abhängigkeiten von 14_background_jobs.py"""

import os
import re
import json
from pathlib import Path
from collections import defaultdict

def find_legacy_imports():
    """Finde alle direkten + impliziten Imports."""
    
    project_root = Path("/home/thomas/projects/KI-Mail-Helper-Dev")
    legacy_patterns = [
        r"from\s+src\.14_background_jobs\s+import",
        r"import\s+src\.14_background_jobs",
        r"BackgroundJobQueue",
        r"FetchJob",
        r"BatchReprocessJob",
        r"job_queue\.",  # Implizite Nutzung
    ]
    
    results = defaultdict(list)
    
    for py_file in project_root.glob("src/**/*.py"):
        if "14_background_jobs" in py_file.name:
            continue  # Skip die Datei selbst
        
        with open(py_file, 'r', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            for pattern in legacy_patterns:
                if re.search(pattern, line):
                    results[str(py_file.relative_to(project_root))].append({
                        "line": i,
                        "pattern": pattern,
                        "code": line.strip()
                    })
    
    return dict(results)

def main():
    imports = find_legacy_imports()
    
    print("\n" + "="*70)
    print("LEGACY CODE DEPENDENCY ANALYSIS")
    print("="*70)
    
    total_files = len(imports)
    total_lines = sum(len(v) for v in imports.values())
    
    print(f"\n📊 Statistik:")
    print(f"   Files mit Legacy-Imports: {total_files}")
    print(f"   Gesamte Legacy-References: {total_lines}")
    
    print(f"\n📁 Detailüberblick:\n")
    
    for file, refs in sorted(imports.items()):
        print(f"{file}:")
        for ref in refs:
            print(f"  Line {ref['line']:4d}: {ref['code'][:60]}...")
        print()
    
    # Exportiere als JSON für weitere Verarbeitung
    with open("legacy_imports.json", "w") as f:
        json.dump(imports, f, indent=2)
    
    print(f"✅ Katalog exportiert: legacy_imports.json")
    
    return imports

if __name__ == "__main__":
    main()
```

**Ausführen:**
```bash
python scripts/analyze_legacy_imports.py
```

---

## 🗺️ SCHRITT 2: Migration Roadmap

### 2.1 Timeline: Phasen

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: PARALLEL-BETRIEB (2 Wochen)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ✅ Celery ist produktiv im Einsatz                            │
│ ✅ Alle Mail-Sync-Tasks laufen über Celery                    │
│ ⚠️  14_background_jobs.py läuft STILL (keine neuen Jobs)      │
│ ✅ Monitoring: Kein Fehler bei Fallback                       │
│                                                                 │
│ Startdatum: 28.01.2026 (nach Celery Production-Deploy)        │
│ Enddatum:   11.02.2026                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                          ↓ (2 Wochen ohne Issues)
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 2: DEAKTIVIERUNG VORBEREITEN (1 Woche)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ✅ Deprecation-Warnung in Code                                │
│ ✅ Feature-Flag: USE_LEGACY_JOBS=false Testphase             │
│ ✅ Alerts für alte Job-Queue aufräumen                        │
│ ✅ Finale Cleanup-Dokumentation                               │
│                                                                 │
│ Startdatum: 12.02.2026                                         │
│ Enddatum:   18.02.2026                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                          ↓ (1 Woche ohne Issues)
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 3: HARD CUTOFF (Tag X)                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ❌ 14_background_jobs.py WIRD GELÖSCHT                        │
│ ❌ Alle Imports entfernt                                       │
│ ❌ Feature-Flag USE_LEGACY_JOBS gelöscht                      │
│ ✅ Test-Äquivalente in pytest-Suite                           │
│                                                                 │
│ Datum: 28.02.2026 (oder wenn 30 Tage ohne Issues)           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Entscheidungsbaum

```
NEUE FEATURE GEPLANT?
    │
    ├─ Async Job (Mail-Fetch, Batch-Processing)
    │  └─ CELERY TASK verwenden ✅
    │
    ├─ Synchrone Operation (Login, Daten-Abfrage)
    │  └─ Service + Blueprint ✅
    │
    └─ Legacy-Code braucht Job?
       └─ Feature-Flag USE_LEGACY_JOBS?
          ├─ true  → Zu 14_background_jobs.py
          └─ false → ERROR + Log-Warning
```

---

## 🚩 SCHRITT 3: Feature-Flag Implementation

### 3.1 Umgebungsvariable definieren

```bash
# .env
USE_LEGACY_JOBS=true

# Production (nach 28.02.2026)
USE_LEGACY_JOBS=false
```

### 3.2 Code: Feature-Flag-Guard

```python
# In allen Dateien, die 14_background_jobs.py nutzen:

import os
import logging

USE_LEGACY_JOBS = os.getenv("USE_LEGACY_JOBS", "true").lower() == "true"
logger = logging.getLogger(__name__)

# OPTION 1: Bei Import-Zeit prüfen
if not USE_LEGACY_JOBS:
    raise RuntimeError(
        "❌ DEPRECATION: Legacy Background Jobs sind deaktiviert (USE_LEGACY_JOBS=false).\n"
        "   Bitte verwende Celery Tasks stattdessen (siehe doc/Multi-User/MULTI_USER_CELERY_LEITFADEN.md)"
    )

# OPTION 2: Zur Laufzeit (für schrittweise Migration)
def get_job_queue():
    if not USE_LEGACY_JOBS:
        logger.warning(
            "⚠️  DEPRECATION: Legacy job_queue.add_job() ist deaktiviert.\n"
            "   Diese Methode wird am 28.02.2026 gelöscht.\n"
            "   Migration: Verwende stattdessen sync_user_emails.delay()"
        )
        return None
    
    return job_queue
```

### 3.3 Beispiel: Blueprint-Migration

**BEFORE (mit 14_background_jobs):**
```python
# src/blueprints/accounts.py (alt)
from src.14_background_jobs import job_queue, FetchJob

@accounts.route("/sync", methods=["POST"])
def start_sync():
    job = FetchJob(
        job_id=str(uuid.uuid4()),
        user_id=current_user.id,
        account_id=request.json['account_id'],
        ...
    )
    job_queue.add_job(job)
    return {"status": "queued"}
```

**AFTER (mit Celery):**
```python
# src/blueprints/accounts.py (neu)
from src.tasks.mail_sync_tasks import sync_user_emails
from src.celery_app import celery_app

@accounts.route("/sync", methods=["POST"])
def start_sync():
    task = sync_user_emails.delay(
        user_id=current_user.id,
        account_id=request.json['account_id']
    )
    return {"status": "queued", "task_id": task.id}
```

**WÄHREND MIGRATION (mit Feature-Flag):**
```python
# src/blueprints/accounts.py (temporär)
import os

USE_LEGACY_JOBS = os.getenv("USE_LEGACY_JOBS", "true").lower() == "true"

if USE_LEGACY_JOBS:
    from src.14_background_jobs import job_queue, FetchJob
else:
    from src.tasks.mail_sync_tasks import sync_user_emails

@accounts.route("/sync", methods=["POST"])
def start_sync():
    if USE_LEGACY_JOBS:
        # Alt
        job = FetchJob(...)
        job_queue.add_job(job)
    else:
        # Neu
        task = sync_user_emails.delay(...)
    
    return {"status": "queued"}
```

---

## 🔍 SCHRITT 4: Monitoring & Alerts

### 4.1 Legacy Job Queue Monitoring

```python
# src/helpers/legacy_monitoring.py
"""Überwache Legacy Job Queue auf Fehler."""

import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

USE_LEGACY_JOBS = os.getenv("USE_LEGACY_JOBS", "true").lower() == "true"

class LegacyJobMonitor:
    """Überwache alte Job Queue auf unerwartete Fehler."""
    
    DEPRECATION_DATE = datetime(2026, 2, 28)
    
    @classmethod
    def warn_if_legacy_used(cls):
        """Warne wenn Legacy Jobs noch genutzt werden."""
        if USE_LEGACY_JOBS:
            days_left = (cls.DEPRECATION_DATE - datetime.now()).days
            if days_left > 0:
                logger.warning(
                    f"⏰ Legacy Job Queue wird am {cls.DEPRECATION_DATE.strftime('%d.%m.%Y')} gelöscht "
                    f"({days_left} Tage verbleibend). "
                    f"Bitte auf Celery migrieren!"
                )
            else:
                logger.error(
                    f"❌ Deprecation-Deadline überschritten! Legacy Job Queue sollte gelöscht sein!"
                )
    
    @classmethod
    def monitor_queue_health(cls, job_queue):
        """Prüfe auf Fehler in Job Queue."""
        if not USE_LEGACY_JOBS:
            return  # Nichts zu monitoren
        
        # Prüfe auf alte Jobs (älter als 1 Tag)
        for job_id, job in job_queue._status.items():
            if isinstance(job.get('created_at'), str):
                created = datetime.fromisoformat(job['created_at'])
                age = datetime.now() - created
                
                if age > timedelta(days=1):
                    logger.warning(
                        f"⚠️  Old job in queue: {job_id} (age: {age}). "
                        f"Überprüfe auf stuck jobs!"
                    )
                
                if job.get('retry_count', 0) > 3:
                    logger.error(
                        f"❌ Job {job_id} failed 3x, give up. "
                        f"Wird manuell gelöscht."
                    )
                    del job_queue._status[job_id]
```

### 4.2 Integration in Logging

```python
# In app_factory.py beim Startup:

from src.helpers.legacy_monitoring import LegacyJobMonitor

def create_app():
    app = Flask(__name__)
    
    # ... andere Setup ...
    
    # Legacy Monitoring
    LegacyJobMonitor.warn_if_legacy_used()
    
    if os.getenv("USE_LEGACY_JOBS", "true").lower() == "true":
        logger.warning("⚠️  Legacy Background Jobs sind AKTIVIERT. "
                      "Siehe: doc/Multi-User/04_LEGACY_CODE_DEPRECATION_PLAN.md")
    
    return app
```

---

## 🗑️ SCHRITT 5: Cleanup (Am Cutoff-Datum)

### 5.1 Datei-Löschung

```bash
# 28.02.2026 (oder später, nach ausreichender Produktionsphase):

# 1. Backup erstellen
cp src/14_background_jobs.py backups/14_background_jobs.py.backup_$(date +%Y%m%d)

# 2. Alle Importe finden & löschen
grep -r "14_background_jobs\|BackgroundJobQueue\|FetchJob" src/ --include="*.py"

# 3. Datei löschen
rm src/14_background_jobs.py

# 4. Test ausführen
pytest tests/ -v

# 5. Commit
git add -A
git commit -m "chore: remove legacy background job queue (deprecated 28.02.2026)"
```

### 5.2 Feature-Flag-Cleanup

```python
# Lösche aus app_factory.py:
# - USE_LEGACY_JOBS = os.getenv(...)
# - LegacyJobMonitor.warn_if_legacy_used()

# Lösche aus requirements.txt:
# - (keine Dependencies nur für Legacy Code)
```

### 5.3 Dokumentation-Cleanup

```bash
# Optional: Archiviere dieses Dokument
cp doc/Multi-User/04_LEGACY_CODE_DEPRECATION_PLAN.md \
   doc/Multi-User/ARCHIVE_04_LEGACY_CODE_DEPRECATION_PLAN.md

# Aktualisiere CHANGELOG.md
cat >> CHANGELOG.md << 'EOF'

## [vX.X.X] - 2026-02-28

### Removed
- **BREAKING**: Legacy background job queue (`src/14_background_jobs.py`) removed
  - Replaced by Celery-based task architecture
  - All async operations now via `src/tasks/` + `src/celery_app.py`
  - Migration guide: [Deprecated since January 2026]

EOF
```

---

## 📋 TESTING: Legacy-Code wird nicht mehr genutzt

### Test Suite Update

```python
# tests/test_legacy_deprecation.py
"""Stelle sicher, dass Legacy Code nicht mehr genutzt wird."""

import pytest
import os
import re
from pathlib import Path


def test_no_legacy_imports():
    """Kein direkter Import von 14_background_jobs.py."""
    
    project_root = Path("/home/thomas/projects/KI-Mail-Helper-Dev")
    
    # Ignoriere diese Datei selbst
    files_to_check = [
        f for f in project_root.glob("src/**/*.py")
        if "14_background_jobs" not in f.name
    ]
    
    legacy_patterns = [
        r"from\s+src\.14_background_jobs",
        r"import\s+src\.14_background_jobs",
        r"BackgroundJobQueue",
    ]
    
    violations = []
    
    for py_file in files_to_check:
        with open(py_file, 'r', errors='ignore') as f:
            content = f.read()
        
        for pattern in legacy_patterns:
            if re.search(pattern, content):
                violations.append(str(py_file.relative_to(project_root)))
    
    assert not violations, (
        f"❌ Found legacy imports in:\n" +
        "\n".join(f"  - {v}" for v in violations)
    )


def test_feature_flag_honored(monkeypatch):
    """USE_LEGACY_JOBS=false sollte Error werfen."""
    
    monkeypatch.setenv("USE_LEGACY_JOBS", "false")
    
    # Wenn Feature-Flag ist false:
    # Jeder Versuch, legacy Job zu erstellen → RuntimeError
    
    from src.helpers.legacy_monitoring import LegacyJobMonitor
    
    with pytest.raises(RuntimeError) as exc_info:
        LegacyJobMonitor.warn_if_legacy_used()
    
    assert "DEPRECATION" in str(exc_info.value).upper()


def test_legacy_file_not_present_after_cutoff(monkeypatch):
    """Nach 28.02.2026 sollte 14_background_jobs.py nicht mehr existieren."""
    
    from pathlib import Path
    from datetime import datetime
    
    legacy_file = Path("/home/thomas/projects/KI-Mail-Helper-Dev/src/14_background_jobs.py")
    
    # Nur nach Cutoff-Datum prüfen
    cutoff = datetime(2026, 2, 28)
    if datetime.now() > cutoff:
        assert not legacy_file.exists(), (
            f"❌ Legacy file {legacy_file} sollte nach {cutoff} gelöscht sein!"
        )

```

---

## 📊 SCHRITT 6: Rollback-Plan

Wenn nach Deprecation-Phase Fehler auftreten:

```bash
# Datei wiederherstellen aus Git-History
git checkout <commit_vor_deletion> -- src/14_background_jobs.py

# Feature-Flag back to true
echo "USE_LEGACY_JOBS=true" >> .env.local

# Redeploy
python3 -m src.00_main --serve

# Incident-Report schreiben
cat > doc/incidents/incident_legacy_revert_<datum>.md << 'EOF'
# Incident Report: Legacy Job Queue Re-enabled

**Datum**: [INSERT]
**Ursache**: [INSERT - welche Tasks sind fehlgeschlagen?]
**Lösung**: Feature-Flag temporär zurück auf true
**Dauer**: [INSERT - wie lange lief Legacy-Code?]

## Nächste Schritte
1. Celery-Tasks debuggen
2. Neue Tests schreiben
3. Nächste Cutoff-Versuche
EOF
```

---

## ✅ CHECKLISTE: Deprecation-Process

### PHASE 1: Parallel-Betrieb (2 Wochen)
- [ ] Celery läuft erfolgreich in Production
- [ ] Alle Mail-Sync-Tasks laufen über Celery
- [ ] `legacy_imports.json` erstellt
- [ ] Keine neuen Errors in Logs nach 3 Tagen
- [ ] Keine neuen Errors nach 1 Woche
- [ ] Keine neuen Errors nach 2 Wochen

### PHASE 2: Deaktivierung vorbereiten (1 Woche)
- [ ] Feature-Flag `USE_LEGACY_JOBS` in Code eingebaut
- [ ] Deprecation-Warnung in Logs
- [ ] `LegacyJobMonitor` implementiert
- [ ] Test in `test_legacy_deprecation.py` grün
- [ ] Dokumentation aktualisiert

### PHASE 3: Hard Cutoff (nach mind. 3 Wochen)
- [ ] Cutoff-Datum ist erreicht (mind. 28.02.2026)
- [ ] Kein einziger Legacy-Job in letzten 7 Tagen
- [ ] Backup erstellt: `14_background_jobs.py.backup`
- [ ] Datei gelöscht
- [ ] Alle Tests grün
- [ ] Git Commit & Push
- [ ] CHANGELOG.md aktualisiert

---

## 🔗 Verweise

- Celery Leitfaden: [doc/Multi-User/MULTI_USER_CELERY_LEITFADEN.md](MULTI_USER_CELERY_LEITFADEN.md)
- Migration Report: [doc/Multi-User/MULTI_USER_MIGRATION_REPORT.md](MULTI_USER_MIGRATION_REPORT.md)
- Definition of Done: [doc/Multi-User/05_DEFINITION_OF_DONE.md](05_DEFINITION_OF_DONE.md) ← nächstes Dokument
