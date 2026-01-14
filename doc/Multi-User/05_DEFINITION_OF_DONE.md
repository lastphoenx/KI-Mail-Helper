# Definition of Done (DoD) Checklist
## KI-Mail-Helper Multi-User Migration

**Status**: Klare Akzeptanzkriterien für Completion  
**Geschätzter Aufwand**: 2-3 Stunden Dokumentation  
**Datum**: Januar 2026  
**Sprache**: Deutsch  

---

## 🎯 ZIEL

Definiere exakte, messbare Kriterien für "fertig" auf mehreren Ebenen:
- ✅ Task-Level (einzelne Celery Task)
- ✅ Feature-Level (z.B. Mail-Sync komplett)
- ✅ Release-Level (Multi-User Migration fertig)

---

## 📋 LEVEL 1: Celery Task DoD

Jeder Task (z.B. `sync_user_emails`) ist fertig, wenn:

### Code-Qualität
- [ ] ✅ Code geschrieben (Business-Logic aus 14_background_jobs.py extrahiert)
- [ ] ✅ Code reviewed (min. 1 andere Person)
- [ ] ✅ No hardcoded secrets (DB-Passwörter, API-Keys in Code)
- [ ] ✅ Error-Handling: Alle Exceptions caught & logged
- [ ] ✅ Logging: Jeder kritische Schritt geloggt (Task-Start, -Ende, -Fehler)

### Sicherheit
- [ ] ✅ User-Ownership-Check: Task validiert Zugehörigkeit (user_id ↔ account_id)
- [ ] ✅ Permission-Errors: PermissionError geworfen bei Zugriffsversuch anderer User
- [ ] ✅ Session-Cleanup: DB-Session wird immer geschlossen (finally-Block!)
- [ ] ✅ Retry-Logik: exponential backoff implementiert (nicht sofort retry)

### Datenbank
- [ ] ✅ Transaktionen: Atomic operations (commit oder rollback, nie partial)
- [ ] ✅ Concurrency: Keine Race-Conditions bei parallel Tasks (Lock wenn nötig)
- [ ] ✅ Indices: Queries nutzen Performance-Indizes (EXPLAIN ANALYZE)
- [ ] ✅ Cleanup: Alte/soft-deleted Daten nicht doppelt verarbeitet

### Testing
- [ ] ✅ Unit Tests: `test_<task_name>_basic.py` erfolgreich
- [ ] ✅ Error Tests: `test_<task_name>_errors.py` erfolgreich
- [ ] ✅ Integration Tests: Mit echtem Service getestet
- [ ] ✅ Coverage: Min. 80% Line-Coverage für Task-Logik
- [ ] ✅ Performance: Task completes in < expected_time (z.B. < 30 Sekunden)

### Monitoring & Logging
- [ ] ✅ Logs geschrieben: `logger.info("Task started"), logger.error(...)`
- [ ] ✅ Task-ID in Logs: `logger.info(f"[Task {self.request.id}] ...")`
- [ ] ✅ Fehler alertbar: ERROR-Level Logs für Monitoring-Tool (New Relic, etc.)
- [ ] ✅ Metriken: Task-Latenz tracking (via Celery Signals)

### Dokumentation
- [ ] ✅ Docstring: Task erklärt (Input, Output, Exceptions)
- [ ] ✅ Usage-Beispiel: Blueprint zeigt wie Task aufgerufen wird
- [ ] ✅ CHANGELOG.md: Task neu dokumentiert
- [ ] ✅ TROUBLESHOOTING: Häufige Fehler + Lösungen

---

## 📦 LEVEL 2: Feature DoD (z.B. Mail-Sync)

Mail-Sync ist "fertig", wenn **ALLE folgenden Tasks** Level-1-DoD erfüllen:

### Mail-Sync Tasks
1. `sync_user_emails` (Haupttask)
   - [ ] ✅ Level-1 DoD erfüllt
   - [ ] ✅ IMAP-Verbindung & Fetch funktioniert
   - [ ] ✅ Duplikate-Handling (message_id, content_hash)
   - [ ] ✅ Folder-Sync (INBOX, Archiv, Deleted)

2. `process_fetched_emails` (AI-Verarbeitung)
   - [ ] ✅ Level-1 DoD erfüllt
   - [ ] ✅ AI-Scoring funktioniert
   - [ ] ✅ Embedding-Generierung (falls nutzen)
   - [ ] ✅ Rule-Engine Anwendung

3. `sync_email_flags` (Flag-Sync mit Server)
   - [ ] ✅ Level-1 DoD erfüllt
   - [ ] ✅ Seen/Unseen synchronisiert
   - [ ] ✅ Custom Flags unterstützt
   - [ ] ✅ Conflict-Resolution (local vs. server)

### Integration
- [ ] ✅ Blueprint ruft Tasks korrekt auf (mit user_id, error-handling)
- [ ] ✅ Task-Status abfragbar: `GET /api/sync/status/<task_id>`
- [ ] ✅ Fehler-Notification: User wird über fehlgeschlagene Sync informiert
- [ ] ✅ Rate-Limiting: Mehrfaches Click auf "Sync" wird gehandelt

### Database
- [ ] ✅ Alle Emails sind in `raw_emails` + `processed_emails`
- [ ] ✅ Daten-Konsistenz: `raw_emails.count ≥ processed_emails.count`
- [ ] ✅ Keine Duplikate: Über message_id oder content_hash prüfen
- [ ] ✅ Keine orphaned Einträge: Alle Emails haben valid user_id + account_id

### Performance
- [ ] ✅ Latenz: Task startet in < 500ms nach `.delay()`
- [ ] ✅ Durchsatz: 50+ Emails synchronisieren in < 30 Sekunden
- [ ] ✅ Memory: Celery Worker Memory < 200 MB während Task
- [ ] ✅ DB Connections: Keine connection leaks (max_connections nicht überschritten)

### Testing
- [ ] ✅ Integration Test mit 50 Test-Emails
- [ ] ✅ End-to-End Test: User startet Sync → Emails in DB
- [ ] ✅ Error-Path Test: Netzwerk-Fehler → Retry → Success
- [ ] ✅ Parallel-Test: 3 parallel Users synchronisieren → keine conflicts

### Monitoring
- [ ] ✅ Dashboard: Sync success rate ≥ 95%
- [ ] ✅ Alerts: Bei Task-Fehler wird Alert gesendet
- [ ] ✅ Logs: `grep "sync_user_emails" logs/ | wc -l` → Anzahl Läufe trackbar
- [ ] ✅ Metrics: Latenz-Histogramm (p50, p95, p99) trackbar

### Documentation
- [ ] ✅ Implementierungs-Anleitung: doc/Multi-User/MULTI_USER_CELERY_LEITFADEN.md
- [ ] ✅ API-Docs: Blueprint Route `/api/sync` dokumentiert
- [ ] ✅ Troubleshooting: doc/Multi-User/TROUBLESHOOTING.md hat Mail-Sync Sektion
- [ ] ✅ Release Notes: CHANGELOG.md hat Mail-Sync Feature

---

## 🚀 LEVEL 3: Release DoD (Multi-User Migration v1.0)

Migration ist produktionsreif, wenn:

### Infrastruktur
- [ ] ✅ PostgreSQL: Lokal + Staging erfolgreich getestet (30+ Tage)
- [ ] ✅ Redis: Lokal + Staging erfolgreich getestet (30+ Tage)
- [ ] ✅ Celery Worker: Lokal + Staging erfolgreich getestet (30+ Tage)
- [ ] ✅ Docker Compose (optional): Für schnelles Local Setup

### Features
- [ ] ✅ Feature 1: Mail-Sync via Celery (Level-2 DoD)
- [ ] ✅ Feature 2: Email-Processing via Celery (Level-2 DoD)
- [ ] ✅ Feature 3: Batch-Reprocessing via Celery (Level-2 DoD)
- [ ] ✅ Feature 4: Multi-User Session-Management (neue)

### Testing
- [ ] ✅ Unit Tests: coverage ≥ 85% in src/tasks/, src/celery_app.py
- [ ] ✅ Integration Tests: PostgreSQL + Redis + Celery zusammen getestet
- [ ] ✅ Load Tests: 5 concurrent Users → 0 data loss, < 2% error rate
- [ ] ✅ Chaos Tests: Worker crashed → Recovery ohne data loss

### Performance (SLA)
- [ ] ✅ Task Latency: < 5 Sekunden median (p50)
- [ ] ✅ Task Throughput: ≥ 100 Tasks/Minute (single worker)
- [ ] ✅ Database: < 100ms query für 100.000 Emails
- [ ] ✅ Memory: Celery Worker stable < 300 MB (no memory leaks)
- [ ] ✅ Connection Pool: Max 20 open connections (Redis + PostgreSQL)

### Security
- [ ] ✅ Secrets: DB-Password + Redis-Password NICHT in .env / Code
- [ ] ✅ Encryption: Sensitive Data verschlüsselt in DB
- [ ] ✅ Authentication: Multi-User Isolation per Task validiert
- [ ] ✅ Authorization: Feature-Flag für Legacy Code deaktivierbar
- [ ] ✅ Audit: Alle Task-Starts + -Errors geloggt für Audit-Trail

### Monitoring & Alerting
- [ ] ✅ Dashboards: Celery Task Success Rate, Latency, Queue Size
- [ ] ✅ Alerts: Bei Error-Rate > 5% wird Alert gesendet
- [ ] ✅ Health-Check: `/api/health` zeigt Celery + Redis + DB Status
- [ ] ✅ Logs: Centralized Logging (ELK oder ähnlich) konfiguriert

### Deployment
- [ ] ✅ Migration Script: SQLite → PostgreSQL ohne Datenverlust
- [ ] ✅ Rollback Plan: Datensicherung vor Migration, Fallback dokumentiert
- [ ] ✅ Feature Flags: USE_LEGACY_JOBS=false kann aktiviert werden
- [ ] ✅ Deployment Docs: Wie man Celery Worker startet in Prod

### Legacy Code
- [ ] ✅ 14_background_jobs.py: Markiert als @deprecated
- [ ] ✅ Legacy Monitoring: `LegacyJobMonitor` aktiv, Warnungen in Logs
- [ ] ✅ Deprecation Date: 28.02.2026 in Code / Docs dokumentiert
- [ ] ✅ Migration Path: Alle Blueprints können auf Celery umschalten

### Documentation
- [ ] ✅ Implementierungs-Leitfaden: doc/Multi-User/MULTI_USER_*
- [ ] ✅ API-Docs: /docs/API.md oder ähnlich
- [ ] ✅ Troubleshooting: doc/Multi-User/TROUBLESHOOTING.md vollständig
- [ ] ✅ README: Root README.md nennt Multi-User als verfügbar
- [ ] ✅ Changelog: CHANGELOG.md dokumentiert alle Features + Breaking Changes

---

## 📊 METRIKEN & ACCEPTANCE CRITERIA

### Performance Metrics

| Metrik | Target | Messung |
|--------|--------|---------|
| Task Latency (p50) | < 3s | `celery_app.AsyncResult(task_id).get()` benchmark |
| Task Latency (p95) | < 10s | Celery Flower Dashboard oder Prometheus |
| Task Throughput | ≥ 100/min | `redis-cli INFO stats` RPS |
| Error Rate | < 2% | (failed_tasks / total_tasks) * 100 |
| Success Rate | ≥ 98% | (successful_tasks / total_tasks) * 100 |
| Worker Memory | < 300 MB | `docker stats` oder `ps aux` |
| DB Connection Pool | < 20 | `SELECT count(*) FROM pg_stat_activity` |
| Redis Memory | < 500 MB | `redis-cli INFO memory \| grep used_memory_human` |
| Retry Rate | < 5% | (retried_tasks / total_tasks) * 100 |

### Quality Metrics

| Metrik | Target | Tool |
|--------|--------|------|
| Unit Test Coverage | ≥ 85% | `pytest --cov=src.tasks` |
| Integration Test Coverage | ≥ 75% | `pytest tests/integration` |
| Code Duplication | < 5% | `radon cc src/tasks/` |
| Cyclomatic Complexity | < 10 pro Task | `radon cc -n C src/tasks/` |
| Security Scan | 0 Critical | `bandit -r src/tasks/` |
| Lint Issues | 0 | `pylint src/tasks/` |

### Business Metrics

| Metrik | Target | Definition |
|--------|--------|------------|
| Data Loss | 0 | Keine Email sollte verloren gehen |
| Duplicate Emails | 0 | Keine Duplikate in raw_emails |
| User Isolation | 100% | Kein User sieht Emails anderer Users |
| Concurrent Users | ≥ 5 | Gleichzeitig 5 User können synchen |
| RTO (Recovery Time) | < 1h | Nach Fehler wieder available |
| RPO (Recovery Point) | < 15min | Max. 15 Min alte Daten verloren |

---

## ✅ VERWENDUNG: Task-Completion Checklist

### Beispiel: Task "sync_user_emails" ist fertig

```bash
# 1. Code geschrieben (src/tasks/mail_sync_tasks.py)
✅ Code-Qualität DoD erfüllt
✅ Security DoD erfüllt
✅ Database DoD erfüllt

# 2. Tests geschrieben
pytest tests/tasks/test_mail_sync_tasks*.py -v
# → Alle Tests PASS
✅ Testing DoD erfüllt

# 3. Monitoring konfiguriert
# → Logging + Alerts aktiv
✅ Monitoring DoD erfüllt

# 4. Dokumentation aktualisiert
✅ Docstring
✅ CHANGELOG.md
✅ TROUBLESHOOTING.md
✅ Documentation DoD erfüllt

# RESULT: Task ist COMPLETE!
```

---

## 📋 SCHRITT-FÜR-SCHRITT: DoD anwenden

### Phase 1: Task-Development (Developer)

1. **Schreibe Code** basierend auf Template aus `MULTI_USER_CELERY_LEITFADEN.md`
2. **Self-Review**: Prüfe gegen Task-Level DoD
3. **Schreibe Tests**: Unit + Integration
4. **Prüfe Metriken**: Performance + Coverage akzeptabel?
5. **Dokumentiere**: Docstring, CHANGELOG, API-Docs

### Phase 2: Code-Review (Reviewer)

1. **Code Review**: Alle Level-1 DoD Punkte
2. **Test Review**: Sind Tests sinnvoll + ausreichend?
3. **Approval**: ✅ LGTM oder 🔴 Änderungen nötig

### Phase 3: QA/Testing (QA)

1. **Feature Tests**: Gegen Feature-Level DoD
2. **Regression Tests**: Alte Features still funktionieren?
3. **Performance Tests**: SLA eingehalten?
4. **Approval**: ✅ Ready for Staging oder 🔴 Bugs

### Phase 4: Staging (DevOps)

1. **Deploy**: Auf Staging-Umgebung
2. **Smoke Tests**: Basic functionality works?
3. **Load Tests**: Performance unter Last?
4. **Approval**: ✅ Ready for Production oder 🔴 Issues

### Phase 5: Production (DevOps + PM)

1. **Deploy**: Auf Production
2. **Monitoring**: KPIs within SLA?
3. **User Feedback**: Zufrieden?
4. **Approval**: ✅ Release erfolgreich oder 🔴 Rollback

---

## 🚨 Definition of FAIL (❌ Blockers)

Eine Task ist **NICHT fertig** wenn:

- ❌ Coverage < 80% (nur in Ausnahmefällen)
- ❌ Unbehandelte Exceptions im Code
- ❌ Hardcoded Secrets (DB-Passwort, API-Key)
- ❌ User A kann Emails von User B sehen
- ❌ Task läuft länger als 2x vom geschätzten Aufwand
- ❌ Keine Unit Tests geschrieben
- ❌ Dokumentation fehlt
- ❌ Breaking Change nicht dokumentiert
- ❌ Error Rate in Staging > 5%
- ❌ Performance > 2x vom SLA

---

## 🔄 Definition of REVIEW (👀 Approval Workflow)

```
Developer              Code Review              QA
    │                      │                      │
    ├─→ Commits Code        │                      │
    │                       │                      │
    │   (Self-Review DoD)   │                      │
    ├─→ PR created          │                      │
    │                       │                      │
    │                      ← PR Review required   │
    │                       │ (all DoD points)    │
    │                       │                      │
    │                      ✅ Approved             │
    │                       ├─→ Merge              │
    │                       │                      │
    │                       │                     ← Feature Test
    │                       │                      │ (Level-2 DoD)
    │                       │                      │
    │                       │                     ✅ Approved
    │                       │                      ├─→ Staging Deploy
    │                       │                      │
    │                       │                      ├─→ Load Test
    │                       │                      │
    │                       │                     ✅ Ready for Prod
    │                       │                      │
    └───────────────────────────────────────────────→ RELEASE
```

---

## 📚 Verwandte Dokumente

- [MULTI_USER_CELERY_LEITFADEN.md](MULTI_USER_CELERY_LEITFADEN.md) - Wie Tasks geschrieben werden
- [03_CELERY_TEST_INFRASTRUCTURE.md](03_CELERY_TEST_INFRASTRUCTURE.md) - Testing Details
- [02_POSTGRESQL_COMPATIBILITY_TEST.md](02_POSTGRESQL_COMPATIBILITY_TEST.md) - DB Testing
- [04_LEGACY_CODE_DEPRECATION_PLAN.md](04_LEGACY_CODE_DEPRECATION_PLAN.md) - Cleanup Timeline
