# 🖥️ KI-Mail-Helper v2.0 – CLI-Befehlsreferenz

**Alle wichtigen Kommandozeilen-Befehle für Entwicklung, Wartung und Betrieb**

> **v2.0 Multi-User Edition** – PostgreSQL + Celery + Flask Blueprints

---

## 📋 Inhaltsverzeichnis

1. [Schnellstart](#1-schnellstart)
2. [Server & Services starten](#2-server--services-starten)
3. [Celery Worker & Monitoring](#3-celery-worker--monitoring)
4. [Datenbank-Verwaltung (PostgreSQL)](#4-datenbank-verwaltung-postgresql)
5. [Email-Verwaltung](#5-email-verwaltung)
6. [Wartungs-Skripte](#6-wartungs-skripte)
7. [Alembic Migrationen](#7-alembic-migrationen)
8. [Tests ausführen](#8-tests-ausführen)
9. [Ollama (KI-Backend)](#9-ollama-ki-backend)
10. [Systemd Services](#10-systemd-services)
11. [Git Workflow](#11-git-workflow)
12. [Backup & Restore](#12-backup--restore)
13. [PostgreSQL Direktzugriff](#13-postgresql-direktzugriff)
14. [Debugging & Logs](#14-debugging--logs)
15. [Schnellreferenz](#15-schnellreferenz)
16. [Hybrid Classifier / Machine Learning Administration](#16-hybrid-classifier--machine-learning-administration)

---

## 1. Schnellstart

### Komplettes Setup in 5 Befehlen

```bash
# 1. Ins Projektverzeichnis wechseln
cd /home/thomas/projects/KI-Mail-Helper-Dev

# 2. Virtual Environment aktivieren
source venv/bin/activate

# 3. Services starten (Flask + Celery Worker + Beat)
bash scripts/start-multi-user.sh
# → Flask auf Port 5003
# → Celery Worker + Beat automatisch gestartet

# 4. Im Browser öffnen
xdg-open https://localhost:5003
```

### Production-Check vor Start

```bash
# Prüft: PostgreSQL, Redis, Celery, Ollama
bash scripts/production-readiness-check.sh
```

---

## 2. Server & Services starten

### Development (Einzeln)

```bash
# Flask starten (Port 5003)
source venv/bin/activate
python3 -m src.00_main --serve --https --port 5003

# Alternativer Start via Flask CLI
flask --app "src.app_factory:create_app()" run --host 127.0.0.1 --port 5000
```

### Production (Gunicorn)

```bash
# Mit Gunicorn (empfohlen für Production)
gunicorn -c config/gunicorn.conf.py "src.app_factory:create_app()"

# Manuell mit Parametern
gunicorn --bind 127.0.0.1:5000 --workers 4 "src.app_factory:create_app()"
```

### Komplettstart (Flask + Celery)

```bash
# Alles in einem Befehl
bash scripts/start-multi-user.sh

# Was passiert:
# 1. Celery Worker startet
# 2. Celery Beat startet (Scheduled Tasks)
# 3. Flask startet auf Port 5003
```

---

## 3. Celery Worker & Monitoring

### Worker manuell starten

```bash
# Worker starten (Vordergrund)
celery -A src.celery_app worker --loglevel=info

# Mit mehr Concurrency
celery -A src.celery_app worker --loglevel=info --concurrency=4

# Beat Scheduler (für periodische Tasks)
celery -A src.celery_app beat --loglevel=info
```

### Worker Status prüfen

```bash
# Ping alle Worker
celery -A src.celery_app inspect ping

# Aktive Tasks anzeigen
celery -A src.celery_app inspect active

# Registrierte Tasks auflisten
celery -A src.celery_app inspect registered

# Queue-Status
celery -A src.celery_app inspect stats
```

### Flower Web-UI (Monitoring)

```bash
# Flower starten (Web-Dashboard für Celery)
celery -A src.celery_app flower --port=5555

# Im Browser öffnen
xdg-open http://localhost:5555
```

### Celery Tests

```bash
# Smoke Test (schneller Funktionstest)
python3 scripts/celery-smoke-test.py

# Health Check
bash scripts/celery-health-check.sh

# E2E Integration Test
python3 scripts/celery-e2e-test.py
```

### Live-Logs

```bash
# Worker-Logs verfolgen
tail -f /var/log/mail-helper/celery-worker.log

# Mit Filtern
tail -f /var/log/mail-helper/celery-worker.log | grep -E "ERROR|SUCCESS|Starting email sync"

# Systemd Journal
sudo journalctl -u mail-helper-celery-worker -f
```

---

## 4. Datenbank-Verwaltung (PostgreSQL)

### Verbindung prüfen

```bash
# PostgreSQL Status
sudo systemctl status postgresql

# Verbindung testen
psql -U mail_helper -h localhost -d mail_helper -c "SELECT version();"

# Tabellen anzeigen
psql -U mail_helper -h localhost -d mail_helper -c "\dt"
```

### Datenbank erstellen (einmalig)

```bash
# Als postgres User
sudo -u postgres psql << EOF
CREATE USER mail_helper WITH PASSWORD 'dein_sicheres_passwort';
CREATE DATABASE mail_helper OWNER mail_helper;
GRANT ALL PRIVILEGES ON DATABASE mail_helper TO mail_helper;
EOF
```

### Schema-Status

```bash
# Aktuelle Alembic-Version
source venv/bin/activate
alembic current

# Tabellen zählen (~23 erwartet)
psql -U mail_helper -h localhost -d mail_helper -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"

# Zeilen pro Tabelle
psql -U mail_helper -h localhost -d mail_helper << EOF
SELECT 
    schemaname,
    relname as table_name,
    n_live_tup as row_count
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
EOF
```

### Datenbank zurücksetzen (⚠️ Alle Daten weg!)

```bash
# Kompletter Reset
sudo -u postgres psql -c "DROP DATABASE IF EXISTS mail_helper;"
sudo -u postgres psql -c "CREATE DATABASE mail_helper OWNER mail_helper;"

# Schema neu erstellen
source venv/bin/activate
alembic upgrade head
```

---

## 5. Email-Verwaltung

### Übersicht anzeigen

```bash
# User, Accounts und Email-Anzahl anzeigen
python3 scripts/reset_all_emails.py --list
```

**Beispielausgabe:**
```
🐘 PostgreSQL Mode: localhost:5432/mail_helper
📋 Übersicht: User und Mail-Accounts
==========================================================================================
User ID    Username             Account ID   Account Name              Emails    
------------------------------------------------------------------------------------------
1          thomas               1            martina                   30        
                                2            thomas-unibas             61        
------------------------------------------------------------------------------------------
Gesamt:    1 User               2 Accounts                 91 Emails
```

### Emails löschen

```bash
# Alle Emails löschen (Soft-Delete)
python3 scripts/reset_all_emails.py

# Alle Emails löschen (Hard-Delete, empfohlen für sauberen Re-Fetch)
python3 scripts/reset_all_emails.py --hard-delete

# Nur für Account 1
python3 scripts/reset_all_emails.py --account=1 --hard-delete

# Nur für User 1
python3 scripts/reset_all_emails.py --user=1 --hard-delete

# Nur bestimmte Email IDs
python3 scripts/reset_all_emails.py --email=4
python3 scripts/reset_all_emails.py --email=4,5,6

# Ohne Bestätigung
python3 scripts/reset_all_emails.py --email=4 --force --hard-delete
```

### Sanitization-Daten bereinigen

Löscht nur die anonymisierten Versionen (für Re-Anonymisierung):

```bash
# Alle Emails
python3 scripts/reset_all_emails.py --clean-sanitization

# Nur bestimmte Emails
python3 scripts/reset_all_emails.py --email=4 --clean-sanitization

# Ohne Bestätigung
python3 scripts/reset_all_emails.py --email=4 --clean-sanitization --force
```

### Parameter-Übersicht reset_all_emails.py

| Parameter | Beschreibung |
|-----------|--------------|
| `--list` | Zeigt Übersicht aller User/Accounts/Emails |
| `--account=ID` | Nur für diese Mail-Account ID |
| `--user=ID` | Nur für diese User ID |
| `--email=ID[,ID,...]` | Komma-getrennte Liste von Email IDs |
| `--force` | Ohne Bestätigung löschen |
| `--hard-delete` | HARD DELETE (komplett löschen). Default: SOFT DELETE |
| `--clean-sanitization` | Nur Sanitization-Daten löschen |

### KI-Analyse zurücksetzen

```bash
# Alle ProcessedEmails löschen (ohne RawEmails)
python3 scripts/reset_base_pass.py

# Ohne Bestätigung
python3 scripts/reset_base_pass.py --force

# Nur für Account 1
python3 scripts/reset_base_pass.py --account=1 --force
```

### Tag-Learning zurücksetzen

Das Learning-System ist **pro User** (nicht pro Account). Jeder User hat eigene Tags mit:
- `learned_embedding` – aggregiert aus zugewiesenen Emails
- `negative_embedding` – aggregiert aus abgelehnten Vorschlägen

```bash
# Status aller User anzeigen
python scripts/manage_learning.py --list

# Status für User 1
python scripts/manage_learning.py --user=1

# Komplettes Tag-Learning für User 1 resetten
python scripts/manage_learning.py --user=1 --reset

# Nur Negative-Learning resetten (behält positive Beispiele)
python scripts/manage_learning.py --user=1 --reset-negative

# Einzelnen Tag resetten
python scripts/manage_learning.py --tag=5 --reset

# Ohne Bestätigung
python scripts/manage_learning.py --user=1 --reset --force
```

> **Hinweis:** Nach dem Reset muss der User Tags neu zuweisen, damit das Learning wieder aufgebaut wird.

### Sanitization per SQL bereinigen (Alternative)

```bash
# Direkt in PostgreSQL (für einzelne Email ID 4)
psql -U mail_helper -h localhost -d mail_helper << EOF
UPDATE raw_emails
SET encrypted_subject_sanitized = NULL,
    encrypted_body_sanitized = NULL,
    sanitization_entities_count = NULL,
    sanitization_level = NULL,
    sanitization_time_ms = NULL
WHERE id = 4;
EOF
```

---

## 4.5. Schnelle DB-Wartung (SQL)

### Häufig genutzte SQL-Befehle für Debugging & Wartung

#### Email-Status zurücksetzen

```bash
# Status für einzelne Email zurücksetzen (wird neu verarbeitet)
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
UPDATE raw_emails SET
    processing_status = 0,
    processing_error = NULL,
    processing_warnings = NULL,
    processing_retry_count = 0,
    processing_last_attempt_at = NULL
WHERE id = 1276;
EOF

# Mehrere Emails gleichzeitig
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
UPDATE raw_emails SET
    processing_status = 0,
    processing_error = NULL,
    processing_warnings = NULL
WHERE id IN (1276, 1277, 1278);
EOF

# Alle fehlgeschlagenen Emails neu verarbeiten
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
UPDATE raw_emails SET
    processing_status = 0,
    processing_error = NULL,
    processing_warnings = NULL
WHERE processing_error IS NOT NULL;
EOF
```

#### Übersetzung zurücksetzen (für Re-Translation)

```bash
# Übersetzung für einzelne Email löschen
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
UPDATE raw_emails SET
    processing_status = 0,
    encrypted_translation_de = NULL,
    translation_engine = NULL,
    detected_language = NULL,
    processing_error = NULL,
    processing_warnings = NULL
WHERE id = 1276;
EOF

# Alle Opus-MT-Übersetzungen neu generieren (z.B. nach Fix)
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
UPDATE raw_emails SET
    processing_status = 0,
    encrypted_translation_de = NULL,
    translation_engine = NULL
WHERE translation_engine = 'opus-mt-it-de';
EOF
```

#### Email-Status abfragen

```bash
# Status-Übersicht für alle Emails
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
SELECT 
    processing_status,
    COUNT(*) as count,
    CASE processing_status
        WHEN 0 THEN 'Unbearbeitet'
        WHEN 10 THEN 'Embedding'
        WHEN 20 THEN 'Translation'
        WHEN 40 THEN 'AI-Classified'
        WHEN 50 THEN 'Auto-Rules'
        WHEN 100 THEN 'Complete'
        ELSE 'Unknown'
    END as status_name
FROM raw_emails
GROUP BY processing_status
ORDER BY processing_status;
EOF

# Fehlerhafte Emails anzeigen
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
SELECT 
    id,
    subject,
    processing_status,
    processing_error,
    processing_retry_count,
    processing_last_attempt_at
FROM raw_emails
WHERE processing_error IS NOT NULL
ORDER BY id DESC
LIMIT 10;
EOF

# Emails mit Übersetzung anzeigen
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
SELECT 
    id,
    detected_language,
    translation_engine,
    length(encrypted_translation_de) as translation_length
FROM raw_emails
WHERE encrypted_translation_de IS NOT NULL
ORDER BY id DESC
LIMIT 10;
EOF
```

#### Batch-Operationen

```bash
# Alle unvollständigen Emails neu starten (Status < 100)
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
UPDATE raw_emails SET
    processing_status = 0,
    processing_error = NULL
WHERE processing_status > 0 AND processing_status < 100;
EOF

# Alle Emails eines Accounts neu verarbeiten
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
UPDATE raw_emails SET
    processing_status = 0,
    processing_error = NULL,
    processing_warnings = NULL
WHERE mail_account_id = 3;
EOF
```

#### ProcessedEmails löschen (für vollständige Neu-Verarbeitung)

```bash
# ProcessedEmails für einzelne RawEmail löschen
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
DELETE FROM processed_emails
WHERE raw_email_id = 1276;

UPDATE raw_emails SET processing_status = 0 WHERE id = 1276;
EOF

# Alle ProcessedEmails löschen (kompletter Reset)
psql postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper << 'EOF'
DELETE FROM processed_emails;
UPDATE raw_emails SET processing_status = 0;
EOF
```

> **💡 Tipp:** Nach Status- oder Übersetzungs-Reset immer Celery Worker neustarten:
> ```bash
> sudo systemctl restart mail-helper-celery-worker
> ```

> **⚠️ Warnung:** `DELETE FROM processed_emails` ist eine harte Operation. Besser: Nur Status zurücksetzen mit `UPDATE raw_emails SET processing_status = 0`.
EOF
```

---

## 6. Wartungs-Skripte

### User-Verwaltung

```bash
# Email zur Whitelist hinzufügen (erlaubt Registration)
python3 scripts/manage_users.py add-whitelist user@example.com

# Von Whitelist entfernen
python3 scripts/manage_users.py remove-whitelist user@example.com

# Alle Whitelist-Einträge anzeigen
python3 scripts/manage_users.py list-whitelist

# IMAP-Diagnostics für User aktivieren
python3 scripts/manage_users.py enable-diagnostics admin@example.com

# IMAP-Diagnostics deaktivieren
python3 scripts/manage_users.py disable-diagnostics admin@example.com
```

### Skript-Übersicht

| Skript | Zweck |
|--------|-------|
| `start-multi-user.sh` | Startet Flask + Celery Worker + Beat |
| `production-readiness-check.sh` | Prüft alle Services |
| `celery-smoke-test.py` | Schneller Celery-Funktionstest |
| `celery-health-check.sh` | Celery Status prüfen |
| `reset_all_emails.py` | Emails löschen (PostgreSQL) |
| `reset_base_pass.py` | KI-Analyse zurücksetzen |
| `manage_users.py` | User-Whitelist & Diagnostics |
| `manage_learning.py` | Learning-Status & Reset |
| `clear_tag_embedding_cache.py` | Tag-Cache leeren |

### Learning-Verwaltung

Das System hat **zwei Learning-Mechanismen**:

| System | Scope | Speicherung | Beschreibung |
|--------|-------|-------------|--------------|
| **Tag-Learning** | Pro User | DB (`email_tags`) | Embedding-Aggregation aus Tag-Zuweisungen |
| **Score-Learning** | **Global** | `src/classifiers/*.pkl` | SGD-Classifier für Dringlichkeit/Wichtigkeit |

> ⚠️ **Wichtig:** Score-Learning ist aktuell **global** – Korrekturen eines Users beeinflussen alle anderen User. Dies wird in v2.1 auf Pro-User umgestellt.

#### Tag-Learning (Pro User)

```bash
# Status aller User anzeigen
python scripts/manage_learning.py --list

# Status für User 1
python scripts/manage_learning.py --user=1

# Komplettes Tag-Learning für User 1 resetten
python scripts/manage_learning.py --user=1 --reset

# Nur Negative-Learning resetten (behält positive Beispiele)
python scripts/manage_learning.py --user=1 --reset-negative

# Einzelnen Tag resetten
python scripts/manage_learning.py --tag=5 --reset

# Ohne Bestätigung
python scripts/manage_learning.py --user=1 --reset --force
```

#### Tag-Learning direkt via SQL (Praxis-Beispiele)

Wenn `manage_learning.py` nicht ausreicht, können Tag-Zuweisungen und Embeddings 
direkt in der Datenbank korrigiert werden:

```bash
# 1. Tag suchen (z.B. alle Tags mit "IT" im Namen)
sudo -u postgres psql -d mail_helper -c \
  "SELECT id, name, user_id FROM email_tags WHERE name ILIKE '%IT%';"

# 2. Tag-Zuweisungen für bestimmten Account löschen
#    Nützlich wenn Auto-Rules falsche Tags gesetzt haben
sudo -u postgres psql -d mail_helper -c "
DELETE FROM email_tag_assignments 
WHERE tag_id = 41  -- ← Tag-ID anpassen
AND email_id IN (
    SELECT pe.id FROM processed_emails pe
    JOIN raw_emails re ON pe.raw_email_id = re.id
    WHERE re.mail_account_id = 2  -- ← Account-ID anpassen
);
"

# 3. Learned Embedding zurücksetzen ("falsches Wissen" löschen)
#    Das Tag vergisst alle gelernten Muster und startet von Null
sudo -u postgres psql -d mail_helper -c "
UPDATE email_tags 
SET learned_embedding = NULL, 
    embedding_updated_at = NULL,
    negative_embedding = NULL,
    negative_updated_at = NULL,
    negative_count = 0
WHERE id = 41;  -- ← Tag-ID anpassen
"

# 4. Alle Tag-Zuweisungen für einen Tag anzeigen (mit Account-Info)
sudo -u postgres psql -d mail_helper -c "
SELECT eta.id, re.mail_account_id, eta.auto_assigned, eta.assigned_at
FROM email_tag_assignments eta
JOIN processed_emails pe ON eta.email_id = pe.id
JOIN raw_emails re ON pe.raw_email_id = re.id
WHERE eta.tag_id = 41
ORDER BY eta.assigned_at DESC
LIMIT 20;
"
```

> **Tipp:** `auto_assigned = true` bedeutet, dass die Zuweisung von einer Auto-Rule 
> oder dem Similarity-Matching stammt, nicht vom User manuell.

#### Score-Learning (Global)

```bash
# Score-Classifier Status anzeigen
python scripts/manage_learning.py --classifiers

# Score-Classifier resetten (alle .pkl Dateien löschen)
python scripts/manage_learning.py --reset-classifiers

# Neu trainieren (nach Reset)
curl -X POST http://localhost:5000/retrain
# Oder via UI: Einstellungen → "Modelle trainieren"
```

> **Nach Reset:** User-Korrekturen bleiben in der DB erhalten. Beim nächsten Training werden die Classifier neu aufgebaut.

---

## 7. Alembic Migrationen

### Status prüfen

```bash
source venv/bin/activate

# Aktuelle Version
alembic current

# Alle Migrationen
alembic history

# Pending Migrationen
alembic history --indicate-current
```

### Migrationen ausführen

```bash
# Auf neueste Version
alembic upgrade head

# Eine Version vorwärts
alembic upgrade +1

# Zu spezifischer Revision
alembic upgrade 0490296358e5
```

### Migrationen rückgängig

```bash
# Eine Version zurück
alembic downgrade -1

# Zu spezifischer Revision
alembic downgrade 55a17d1115b6

# Komplett zurücksetzen (⚠️ Datenverlust!)
alembic downgrade base
```

### Neue Migration erstellen

```bash
# Autogenerate (vergleicht Models mit DB)
alembic revision --autogenerate -m "add_new_column"

# Leere Migration (manuell)
alembic revision -m "custom_migration"
```

---

## 8. Tests ausführen

### Alle Tests

```bash
# Komplett
python3 -m pytest tests/ -v

# Mit Coverage
python3 -m pytest tests/ --cov=src --cov-report=html

# Parallel
python3 -m pytest tests/ -n auto
```

### Celery-spezifische Tests

```bash
# Smoke Test
python3 scripts/celery-smoke-test.py

# Integration Test
python3 scripts/celery-integration-test.py

# E2E Complete Test
python3 scripts/celery-e2e-complete-test.py

# Load Test
python3 scripts/celery-load-test.py
```

### Einzelne Tests

```bash
# Spezifische Datei
python3 -m pytest tests/test_sanitizer.py -v

# Mit Pattern
python3 -m pytest tests/ -k "encryption" -v

# Spezifischer Test
python3 -m pytest tests/test_ai_client.py::test_ollama_connection -v
```

---

## 9. Ollama (KI-Backend)

### Service-Verwaltung

```bash
# Status
systemctl status ollama

# Starten
sudo systemctl start ollama

# Automatisch starten
sudo systemctl enable ollama
```

### Modelle verwalten

```bash
# Installierte Modelle
ollama list

# Modell herunterladen
ollama pull llama3.2:3b          # Analyse-Modell (2 GB)
ollama pull all-minilm:22m       # Embedding-Modell (46 MB)

# Modell testen
ollama run llama3.2:3b "Hallo, teste die Verbindung"

# Modell löschen
ollama rm llama3.2:1b
```

### API testen

```bash
# Verfügbare Modelle
curl http://localhost:11434/api/tags | jq '.models[].name'

# Embedding testen
curl http://localhost:11434/api/embeddings \
  -d '{"model": "all-minilm:22m", "prompt": "Test"}'

# Chat testen
curl http://localhost:11434/api/generate \
  -d '{"model": "llama3.2:3b", "prompt": "Hi", "stream": false}'
```

---

## 10. Systemd Services

### Service-Übersicht

| Service | Beschreibung |
|---------|--------------|
| `mail-helper.service` | Flask/Gunicorn Web-App |
| `mail-helper-celery-worker.service` | Celery Worker |
| `mail-helper-celery-beat.service` | Celery Beat Scheduler |
| `mail-helper-celery-flower.service` | Flower Monitoring (optional) |

### Befehle

```bash
# Status aller Services
sudo systemctl status mail-helper
sudo systemctl status mail-helper-celery-worker

# Starten
sudo systemctl start mail-helper mail-helper-celery-worker

# Stoppen
sudo systemctl stop mail-helper mail-helper-celery-worker

# Neustarten
sudo systemctl restart mail-helper-celery-worker

# Logs anzeigen
sudo journalctl -u mail-helper -f
sudo journalctl -u mail-helper-celery-worker -f

# Aktivieren (Autostart)
sudo systemctl enable mail-helper mail-helper-celery-worker

# Services neu laden nach Config-Änderung
sudo systemctl daemon-reload
```

---

## 11. Git Workflow

### Branches verwalten

```bash
# Alle Branches anzeigen
git branch -a

# Feature-Branch erstellen
git checkout -b feature/neue-funktion

# Zurück zu main
git checkout main

# Remote-Branches aktualisieren
git fetch --all --prune
```

### Commits & Push

```bash
# Änderungen stagen
git add -A

# Commit
git commit -m "feat: Neue Funktion hinzugefügt"

# Push
git push origin main
```

### Tags für Releases

```bash
# Tag erstellen
git tag -a v2.0.0 -m "Multi-User Edition Release"

# Tag pushen
git push origin v2.0.0

# Alle Tags anzeigen
git tag -l
```

### Parallelbetrieb (alte vs. neue Version)

```bash
# Terminal 1: Alte Version (main, Port 5003)
git checkout main
python3 -m src.00_main --serve --https --port 5003

# Terminal 2: Feature-Branch (Port 5004)
git checkout feature/xyz
python3 -m src.00_main --serve --https --port 5004
```

---

## 12. Backup & Restore

### Schnelles Projekt-Backup (rsync)

```bash
# Backup mit Timestamp
rsync -avh --progress \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='*.pyc' \
  --exclude='.cache/' \
  --exclude='*.egg-info/' \
  --exclude='.eggs/' \
  --exclude='legacy_restore/' \
  --exclude='.zencoder/' \
  --exclude='.zenflow/' \
  --exclude='flask_session/' \
  --exclude='.flask_sessions/' \
  --exclude='migration_log*.txt' \
  --exclude='node_modules/' \
  --exclude='.git/' \
  /home/thomas/projects/KI-Mail-Helper-Dev/ \
  "/home/thomas/projects/backups/KI-Mail-Helper-Dev_$(date +%Y%m%d_%H%M%S)/"
```

### PostgreSQL Backup

```bash
# Komplettes Backup
pg_dump -U mail_helper -h localhost mail_helper > backup_$(date +%Y%m%d).sql

# Komprimiert
pg_dump -U mail_helper -h localhost mail_helper | gzip > backup_$(date +%Y%m%d).sql.gz

# Nur Schema (ohne Daten)
pg_dump -U mail_helper -h localhost --schema-only mail_helper > schema.sql
```

### PostgreSQL Restore

```bash
# Aus SQL-Dump
psql -U mail_helper -h localhost -d mail_helper < backup.sql

# Aus komprimiertem Dump
gunzip -c backup.sql.gz | psql -U mail_helper -h localhost -d mail_helper
```

---

## 13. PostgreSQL Direktzugriff

### Interaktive Shell

```bash
# PostgreSQL Shell öffnen
psql -U mail_helper -h localhost -d mail_helper

# Mit formatierter Ausgabe
psql -U mail_helper -h localhost -d mail_helper --pset=border=2
```

### Nützliche Queries

```bash
# User-Anzahl
psql -U mail_helper -h localhost -d mail_helper -c "SELECT COUNT(*) as users FROM users;"

# Email-Anzahl pro Account
psql -U mail_helper -h localhost -d mail_helper << EOF
SELECT 
    ma.name as account,
    COUNT(re.id) as emails
FROM mail_accounts ma
LEFT JOIN raw_emails re ON re.mail_account_id = ma.id AND re.deleted_at IS NULL
GROUP BY ma.id
ORDER BY emails DESC;
EOF

# Unverarbeitete Emails
psql -U mail_helper -h localhost -d mail_helper << EOF
SELECT COUNT(*) as pending
FROM raw_emails re
LEFT JOIN processed_emails pe ON pe.raw_email_id = re.id
WHERE pe.id IS NULL AND re.deleted_at IS NULL;
EOF

# Tags mit Email-Count
psql -U mail_helper -h localhost -d mail_helper << EOF
SELECT 
    t.name,
    t.color,
    COUNT(a.id) as email_count
FROM email_tags t
LEFT JOIN email_tag_assignments a ON a.tag_id = t.id
GROUP BY t.id
ORDER BY email_count DESC;
EOF

# Alembic-Version
psql -U mail_helper -h localhost -d mail_helper -c "SELECT version_num FROM alembic_version;"
```

### Daten exportieren

```bash
# Als CSV
psql -U mail_helper -h localhost -d mail_helper -c "COPY (SELECT id, imap_folder FROM raw_emails LIMIT 100) TO STDOUT WITH CSV HEADER;" > emails.csv

# Schema dumpen
pg_dump -U mail_helper -h localhost --schema-only mail_helper > schema.sql
```

---

## 14. Debugging & Logs

### Log-Dateien

```bash
# Celery Worker
tail -f /var/log/mail-helper/celery-worker.log

# Gunicorn Access
tail -f logs/gunicorn_access.log

# Gunicorn Error
tail -f logs/gunicorn_error.log

# Systemd Logs
sudo journalctl -u mail-helper -f
sudo journalctl -u mail-helper-celery-worker -f
```

### Flask Debug-Mode

```bash
# Debug-Mode aktivieren
FLASK_DEBUG=1 python3 -m src.00_main --serve

# Mit Reload bei Code-Änderungen
FLASK_DEBUG=1 FLASK_ENV=development flask --app "src.app_factory:create_app()" run --reload
```

### Syntax prüfen

```bash
# Alle Source-Files kompilieren
python3 -m py_compile src/*.py src/blueprints/*.py src/tasks/*.py

# Mit flake8
flake8 src/ --max-line-length 120
```

### Imports testen

```bash
# Module laden
python3 -c "from src.app_factory import create_app; print('✅ app_factory OK')"
python3 -c "from src.celery_app import celery_app; print('✅ celery_app OK')"
python3 -c "from src.blueprints import register_blueprints; print('✅ blueprints OK')"
```

---

## 15. Schnellreferenz

### Die 10 wichtigsten Befehle

```bash
# 1. App starten
bash scripts/start-multi-user.sh

# 2. Celery Status prüfen
celery -A src.celery_app inspect ping

# 3. Logs verfolgen
tail -f /var/log/mail-helper/celery-worker.log

# 4. DB migrieren
alembic upgrade head

# 5. Emails löschen (für Re-Fetch)
python3 scripts/reset_all_emails.py --hard-delete --force

# 6. Tests laufen lassen
python3 -m pytest tests/ -v

# 7. Flower öffnen (Celery Monitoring)
xdg-open http://localhost:5555

# 8. PostgreSQL Shell
psql -U mail_helper -h localhost -d mail_helper

# 9. Service neustarten
sudo systemctl restart mail-helper-celery-worker

# 10. Backup erstellen
pg_dump -U mail_helper -h localhost mail_helper > backup_$(date +%Y%m%d).sql
```

### Troubleshooting Quick-Fixes

```bash
# "Connection refused" (PostgreSQL)
sudo systemctl start postgresql

# "Connection refused" (Redis)
sudo systemctl start redis-server

# Celery Worker antwortet nicht
sudo systemctl restart mail-helper-celery-worker

# "No module named 'src'"
export PYTHONPATH=/home/thomas/projects/KI-Mail-Helper-Dev

# Session-Probleme
rm -rf .flask_sessions/*

# Alembic "Target database is not up to date"
alembic upgrade head
```

---

## 16. Hybrid Classifier / Machine Learning Administration

Das Hybrid Score-Learning System trainiert persönliche Classifier basierend auf 
Benutzerkorrekturen. Hier die wichtigsten Verwaltungsbefehle:

### Circuit Breaker zurücksetzen

Wenn das Training durch zu viele Fehler blockiert ist (`circuit_breaker_open`), muss der error_count zurückgesetzt werden.

**💡 Tipp:** Statt den vollen Connection-String zu tippen, nutze die Umgebungsvariable:

```bash
export DATABASE_URL="postgresql://mail_helper:dev_mail_helper_2026@localhost:5432/mail_helper"
```

Dann kannst du einfach `psql $DATABASE_URL -c "..."` verwenden.

---

#### 1. Fehlerhafte Klassifikatoren abfragen

Zeigt alle Einträge, bei denen der Circuit-Breaker (error_count >= 3) zugeschlagen hat:

```bash
psql $DATABASE_URL -c "SELECT user_id, classifier_type, error_count, is_active, last_trained_at FROM classifier_metadata WHERE error_count >= 3;"

# Oder alle anzeigen (inklusive funktionierende):
psql $DATABASE_URL -c "SELECT user_id, classifier_type, error_count, is_active, last_trained_at FROM classifier_metadata ORDER BY user_id, classifier_type;"
```

#### 2. Error-Count für spezifischen Klassifikator zurücksetzen

Falls du das Training für einen bestimmten User (z.B. ID 1) und Typ (z.B. 'dringlichkeit') wieder freischalten willst:

```bash
psql $DATABASE_URL -c "UPDATE classifier_metadata SET error_count = 0, is_active = true WHERE user_id = 1 AND classifier_type = 'dringlichkeit';"
```

#### 3. Alle Fehler auf einmal zurücksetzen

Um den Circuit-Breaker für alle User/Modelle global auf 0 zu setzen:

```bash
# Alle mit error_count > 0 zurücksetzen
psql $DATABASE_URL -c "UPDATE classifier_metadata SET error_count = 0, is_active = true WHERE error_count > 0;"

# ODER: Komplett alle zurücksetzen (auch wenn error_count schon 0 ist)
psql $DATABASE_URL -c "UPDATE classifier_metadata SET error_count = 0, is_active = true;"
```

#### 4. Bestätigung anzeigen

Nach dem Reset prüfen, ob alles zurückgesetzt wurde:

```bash
psql $DATABASE_URL -c "SELECT user_id, classifier_type, error_count, is_active FROM classifier_metadata ORDER BY user_id, classifier_type;"
```

---

#### Alternative: Python-Script (falls psql nicht verfügbar)

```bash
cd /home/thomas/projects/KI-Mail-Helper-Dev

# Alle error_counts zurücksetzen
python3 -c "
import sys; sys.path.insert(0, '.')
from src.helpers.database import get_db_session
from sqlalchemy import text
with get_db_session() as db:
    result = db.execute(text('UPDATE classifier_metadata SET error_count = 0, is_active = true WHERE error_count > 0'))
    db.commit()
    print(f'✅ {result.rowcount} Einträge zurückgesetzt')
"
```

---

### Classifier-Metadaten anzeigen

```bash
# Alle Classifier-Metadaten
psql $DATABASE_URL -c "SELECT user_id, classifier_type, model_version, training_samples, accuracy_score, last_trained_at FROM classifier_metadata ORDER BY user_id, classifier_type;"

# Nur trainierte Modelle (mit Accuracy)
psql $DATABASE_URL -c "SELECT user_id, classifier_type, model_version, training_samples, accuracy_score, last_trained_at FROM classifier_metadata WHERE last_trained_at IS NOT NULL ORDER BY user_id, classifier_type;"
```

### Training manuell triggern

```bash
cd /home/thomas/projects/KI-Mail-Helper-Dev
source venv/bin/activate

# Force-Training für einen User (z.B. user_id=1), alle Classifier-Typen
python3 -c "
from src.tasks.training_tasks import train_personal_classifier
for ctype in ['dringlichkeit', 'wichtigkeit', 'spam', 'kategorie']:
    result = train_personal_classifier.delay(user_id=1, classifier_type=ctype, force=True)
    print(f'{ctype}: Task {result.id} submitted')
"
```

### Celery Worker Administration

```bash
# Worker Status prüfen
sudo systemctl status mail-helper-celery-worker

# Worker neustarten (nach Code-Änderungen!)
sudo systemctl restart mail-helper-celery-worker

# Worker stoppen
sudo systemctl stop mail-helper-celery-worker

# Worker starten
sudo systemctl start mail-helper-celery-worker

# Live-Logs während Training beobachten
tail -f /var/log/mail-helper/celery-worker.log

# Nur Training-relevante Logs
tail -f /var/log/mail-helper/celery-worker.log | grep -E "Training|Throttle|Circuit|error_count"
```

### Gespeicherte Modelle verwalten

```bash
# Modell-Verzeichnis anzeigen
ls -la /home/thomas/projects/KI-Mail-Helper-Dev/ml_models/

# Modelle für User 1
ls -la /home/thomas/projects/KI-Mail-Helper-Dev/ml_models/user_1/

# Modell löschen (erzwingt Neutraining)
rm /home/thomas/projects/KI-Mail-Helper-Dev/ml_models/user_1/dringlichkeit_v*.pkl

# Alle Modelle löschen (Vorsicht!)
rm -rf /home/thomas/projects/KI-Mail-Helper-Dev/ml_models/user_*/
```

### Korrekturen prüfen

```bash
# Anzahl Korrekturen pro User anzeigen
sudo -u postgres psql -d mail_helper -c "
  SELECT re.user_id, 
         COUNT(CASE WHEN pe.user_override_dringlichkeit IS NOT NULL THEN 1 END) as dringlichkeit,
         COUNT(CASE WHEN pe.user_override_wichtigkeit IS NOT NULL THEN 1 END) as wichtigkeit,
         COUNT(CASE WHEN pe.user_override_spam IS NOT NULL THEN 1 END) as spam,
         COUNT(CASE WHEN pe.user_override_kategorie IS NOT NULL THEN 1 END) as kategorie
  FROM processed_emails pe
  JOIN raw_emails re ON pe.raw_email_id = re.id
  GROUP BY re.user_id
  ORDER BY re.user_id;
"
```

### Häufige Training-Probleme

| Problem | Ursache | Lösung |
|---------|---------|--------|
| `circuit_breaker_open (errors=3)` | 3+ Trainingsfehler | **Python-Script verwenden** (siehe oben), dann Worker restart |
| `throttle_samples (only X new corrections)` | Weniger als 5 Korrekturen | Normal - Training startet ab 5 Korrekturen |
| `insufficient_samples` | Zu wenig Samples pro Klasse | Mehr Korrekturen machen (min. 2 pro Klasse) |
| `throttle_time` | Zu oft trainiert | Warten (min. 5 Min zwischen Trainings) |
| Worker reagiert nicht | Alter Code im Cache | `sudo systemctl restart mail-helper-celery-worker` |
| `'RawEmail' object has no attribute 'embedding'` | Bug in Code | Gefixt - Worker neustarten |

---

*Stand: Januar 2026 | KI-Mail-Helper v2.0 (Multi-User Edition)*
