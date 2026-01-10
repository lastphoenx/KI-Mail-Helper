# 🖥️ KI-Mail-Helper – CLI-Befehlsreferenz

**Alle wichtigen Kommandozeilen-Befehle für Entwicklung, Wartung und Betrieb**

---

## 📋 Inhaltsverzeichnis

1. [Server & App starten](#1-server--app-starten)
2. [Datenbank-Verwaltung](#2-datenbank-verwaltung)
3. [Email-Verarbeitung](#3-email-verarbeitung)
4. [Wartungs-Skripte](#4-wartungs-skripte)
5. [Alembic Migrationen](#5-alembic-migrationen)
6. [Tests ausführen](#6-tests-ausführen)
7. [Ollama (KI-Backend)](#7-ollama-ki-backend)
8. [Systemd Services](#8-systemd-services)
9. [SQLite Direktzugriff](#9-sqlite-direktzugriff)
10. [Debugging & Logs](#10-debugging--logs)

---

## 1. Server & App starten

### Web-Dashboard starten

```bash
# Development (HTTP auf Port 5000)
python3 -m src.00_main --serve

# Development mit HTTPS (HTTP-Redirect auf 5000, HTTPS auf 5001)
python3 -m src.00_main --serve --https

# Mit Custom-Port
python3 -m src.00_main --serve --port 8080

# Mit spezifischer Host-Adresse (z.B. für LAN-Zugriff)
python3 -m src.00_main --serve --host 0.0.0.0
```

### Production (Gunicorn)

```bash
# Mit Gunicorn starten
gunicorn -c config/gunicorn.conf.py "src.01_web_app:create_app()"

# Oder direkt
gunicorn --bind 0.0.0.0:5000 --workers 4 "src.01_web_app:create_app()"
```

---

## 2. Datenbank-Verwaltung

### Datenbank initialisieren

```bash
# Neue Datenbank erstellen (erstellt emails.db)
python3 -m src.00_main --init-db

# Alternative via Python
python3 -c "import importlib; models = importlib.import_module('.02_models', 'src'); models.init_db()"
```

### Datenbank komplett zurücksetzen

```bash
# ⚠️ ACHTUNG: Löscht ALLE Daten!
rm emails.db emails.db-wal emails.db-shm 2>/dev/null
python3 -m src.00_main --init-db
alembic upgrade head
```

### Datenbank-Status prüfen

```bash
# Schneller Check (Tabellen, User-Count)
python3 scripts/check_db.py

# WAL-Modus verifizieren
python3 scripts/verify_wal_mode.py

# Encryption-Konsistenz prüfen
python3 scripts/encrypt_db_verification.py
```

### Backup erstellen

```bash
# Automatisches Backup mit Rotation (30/90 Tage)
bash scripts/backup_database.sh

# Manuelles Backup
sqlite3 emails.db ".backup emails_backup_$(date +%Y%m%d).db"

# Mit WAL-Checkpoint (empfohlen vor Backup)
sqlite3 emails.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 emails.db ".backup emails_backup.db"
```

---

## 3. Email-Verarbeitung

### Mails abrufen und verarbeiten

```bash
# Einmalig: Abrufen + KI-Analyse
python3 -m src.00_main --process-once

# Nur abrufen (ohne KI)
python3 -m src.00_main --fetch-only

# Mit Limit
python3 -m src.00_main --process-once --max-mails 100

# Background-Worker (läuft kontinuierlich)
python3 -m src.00_main --worker
```

### Email-Analyse zurücksetzen

```bash
# Alle ProcessedEmails löschen (KI-Analyse neu starten)
python3 scripts/reset_base_pass.py

# Ohne Bestätigung (für Automation)
python3 scripts/reset_base_pass.py --force

# Nur für einen Account
python3 scripts/reset_base_pass.py --account=1 --force

# Nur für einen User
python3 scripts/reset_base_pass.py --user=1 --force
```

### Alle Emails löschen

```bash
# Soft-Delete (behält Metadaten)
python3 scripts/reset_all_emails.py --user=1

# Hard-Delete (komplett entfernen)
python3 scripts/reset_all_emails.py --user=1 --hard

# Nur bestimmten Account
python3 scripts/reset_all_emails.py --user=1 --account=2

# Ohne Bestätigung
python3 scripts/reset_all_emails.py --user=1 --force
```

### Tag-Embedding-Cache leeren

```bash
# Nach Model-Wechsel: Tag-Embeddings neu generieren lassen
python3 scripts/clear_tag_embedding_cache.py
```

---

## 4. Wartungs-Skripte

### User-Verwaltung (Phase INV)

```bash
# === WHITELIST (Registration-Kontrolle) ===
# Email zur Whitelist hinzufügen (erlaubt Registration)
python3 scripts/manage_users.py add-whitelist user@example.com

# Email von Whitelist entfernen
python3 scripts/manage_users.py remove-whitelist user@example.com

# Alle Whitelist-Einträge anzeigen
python3 scripts/manage_users.py list-whitelist

# === IMAP-DIAGNOSTICS (Zugriffskontrolle) ===
# /imap-diagnostics für User aktivieren
python3 scripts/manage_users.py enable-diagnostics admin@example.com

# /imap-diagnostics für User deaktivieren
python3 scripts/manage_users.py disable-diagnostics admin@example.com

# Alle User mit Diagnostics-Zugriff anzeigen
python3 scripts/manage_users.py list-diagnostics
```

**Hinweis:** Erste Registration ist ohne Whitelist möglich. Alle weiteren User benötigen Whitelist-Eintrag.

### Übersicht aller Skripte

| Skript | Zweck |
|--------|-------|
| `manage_users.py` | User-Verwaltung (Whitelist, Diagnostics) |
| `check_db.py` | Datenbank-Status anzeigen |
| `verify_wal_mode.py` | WAL-Konfiguration prüfen |
| `encrypt_db_verification.py` | Encryption-Konsistenz testen |
| `reset_base_pass.py` | KI-Analyse zurücksetzen |
| `reset_all_emails.py` | Emails löschen |
| `clear_tag_embedding_cache.py` | Tag-Cache leeren |
| `backup_database.sh` | Automatisches Backup |
| `extract_commits.py` | Git-History exportieren |
| `automated_code_review.py` | KI-Code-Review |

### Ausführungsbeispiele

```bash
# DB-Status
python3 scripts/check_db.py

# WAL prüfen
python3 scripts/verify_wal_mode.py

# Encryption verifizieren
python3 scripts/encrypt_db_verification.py

# Git-History als Markdown
python3 scripts/extract_commits.py --structured -o GIT_HISTORY.md

# Code-Review mit KI (siehe CODE_REVIEW_TOOL.md)
python3 scripts/automated_code_review.py --files src/01_web_app.py
```

---

## 5. Alembic Migrationen

### Migration-Status

```bash
# Aktuelle Version anzeigen
alembic current

# Alle Migrationen auflisten
alembic history

# Verfügbare Heads zeigen
alembic heads
```

### Migrationen ausführen

```bash
# Auf neueste Version upgraden
alembic upgrade head

# Eine Version vorwärts
alembic upgrade +1

# Zu spezifischer Revision
alembic upgrade abc123def456
```

### Migrationen rückgängig

```bash
# Eine Version zurück
alembic downgrade -1

# Zu spezifischer Revision
alembic downgrade abc123def456

# Komplett zurücksetzen (⚠️ Datenverlust!)
alembic downgrade base
```

### Neue Migration erstellen

```bash
# Autogenerate (vergleicht Models mit DB)
alembic revision --autogenerate -m "add_new_column"

# Leere Migration (manuell schreiben)
alembic revision -m "custom_migration"
```

---

## 6. Tests ausführen

### Alle Tests

```bash
# Komplett
python3 -m pytest tests/ -v

# Mit Coverage
python3 -m pytest tests/ --cov=src --cov-report=html

# Parallel (schneller)
python3 -m pytest tests/ -n auto
```

### Einzelne Test-Dateien

```bash
# DB-Schema Tests
python3 -m pytest tests/test_db_schema.py -v

# AI-Client Tests
python3 -m pytest tests/test_ai_client.py -v

# Sanitizer Tests
python3 -m pytest tests/test_sanitizer.py -v

# Concurrent Access Tests
python3 -m pytest scripts/test_concurrent_access.py -v

# Race Condition Tests
python3 -m pytest scripts/test_race_condition_lockout.py -v

# ReDoS Protection Tests
python3 -m pytest scripts/test_redos_protection.py -v

# Audit Log Tests
python3 -m pytest scripts/test_audit_logs.py -v
```

### Einzelne Tests

```bash
# Spezifischer Test
python3 -m pytest tests/test_ai_client.py::test_ollama_connection -v

# Mit Pattern
python3 -m pytest tests/ -k "encryption" -v
```

---

## 7. Ollama (KI-Backend)

### Service-Verwaltung

```bash
# Status prüfen
systemctl status ollama

# Starten
sudo systemctl start ollama

# Stoppen
sudo systemctl stop ollama

# Automatisch starten
sudo systemctl enable ollama

# Manuell starten (Vordergrund)
ollama serve
```

### Modelle verwalten

```bash
# Installierte Modelle anzeigen
ollama list

# Modell herunterladen
ollama pull llama3.2
ollama pull llama3.2:1b
ollama pull llama3.2:3b
ollama pull all-minilm:22m
ollama pull mxbai-embed-large

# Modell löschen
ollama rm llama3.2

# Modell testen
ollama run llama3.2 "Hallo, teste die Verbindung"
```

### API testen

```bash
# Verfügbare Modelle via API
curl http://localhost:11434/api/tags | jq

# Embedding testen
curl http://localhost:11434/api/embeddings \
  -d '{"model": "all-minilm:22m", "prompt": "Test"}'

# Chat testen
curl http://localhost:11434/api/generate \
  -d '{"model": "llama3.2", "prompt": "Hi", "stream": false}'
```

### OpenAI-kompatible Modelle prüfen

```bash
# Liste aller verfügbaren OpenAI-Modelle
python3 scripts/list_openai_models.py
```

---

## 8. Systemd Services

### Mail-Helper Services

```bash
# Web-App Status
sudo systemctl status mail-helper

# Processor-Timer Status
sudo systemctl status mail-helper-processor.timer

# Services starten
sudo systemctl start mail-helper
sudo systemctl start mail-helper-processor.timer

# Services aktivieren (Autostart)
sudo systemctl enable mail-helper
sudo systemctl enable mail-helper-processor.timer

# Services neu laden
sudo systemctl daemon-reload
```

### Logs anzeigen

```bash
# Web-App Logs
sudo journalctl -u mail-helper -f

# Processor Logs
sudo journalctl -u mail-helper-processor -f

# Letzte 100 Zeilen
sudo journalctl -u mail-helper -n 100

# Logs seit heute
sudo journalctl -u mail-helper --since today
```

---

## 9. SQLite Direktzugriff

### Account-IDs anzeigen

**Alle Mail-Accounts über alle User auflisten:**

```bash
# Mit Python-Script (empfohlen - formatierte Ausgabe)
python3 scripts/list_accounts.py

# Mit Custom-DB-Pfad
python3 scripts/list_accounts.py --db /path/to/emails.db
```

**Ausgabe-Beispiel:**
```
+----+------------------+-----------+--------+------+
| ID | Account-Name     | User      | Aktiv  | Auth |
+====+==================+===========+========+======+
|  1 | gmx.ch           | thomas    | Ja     | imap |
|  3 | work-gmail       | thomas    | Ja     | oauth|
|  5 | personal         | admin     | Nein   | imap |
+----+------------------+-----------+--------+------+

📊 Gesamt: 3 Account(s)
```

**Direkt per SQL:**

```bash
# Schneller One-Liner (mit formatierter Ausgabe)
sqlite3 -header -column emails.db "SELECT ma.id AS account_id, ma.name AS account_name, u.username AS user_login, ma.enabled AS active FROM mail_accounts ma JOIN users u ON ma.user_id = u.id ORDER BY u.username, ma.name;"

# Alle Accounts mit User-Zuordnung (Multiline für Lesbarkeit)
sqlite3 emails.db <<EOF
SELECT 
    ma.id AS account_id,
    ma.name AS account_name,
    u.username AS user_login,
    CASE WHEN ma.enabled = 1 THEN 'Aktiv' ELSE 'Inaktiv' END AS status
FROM mail_accounts ma
JOIN users u ON ma.user_id = u.id
ORDER BY u.username, ma.name;
EOF

# Nur eigene Accounts (ersetze 'thomas' mit deinem Username)
sqlite3 emails.db <<EOF
SELECT ma.id, ma.name, ma.enabled
FROM mail_accounts ma
JOIN users u ON ma.user_id = u.id
WHERE u.username = 'thomas'
ORDER BY ma.name;
EOF
```

**💡 Wofür brauche ich die Account-ID?**
- Fetch-Filter konfigurieren (nur bestimmte Accounts fetchen)
- Bulk-Operations (später)
- API-Calls & Debugging

### Interaktive Shell

```bash
# SQLite Shell öffnen
sqlite3 emails.db

# Mit Header und Column-Mode
sqlite3 -header -column emails.db
```

### Nützliche Queries

```bash
# Tabellen anzeigen
sqlite3 emails.db "SELECT name FROM sqlite_master WHERE type='table';"

# User-Anzahl
sqlite3 emails.db "SELECT COUNT(*) as users FROM users;"

# Email-Anzahl pro Account
sqlite3 emails.db "
SELECT 
    ma.name as account,
    COUNT(re.id) as emails
FROM mail_accounts ma
LEFT JOIN raw_emails re ON re.mail_account_id = ma.id
GROUP BY ma.id;
"

# Unverarbeitete Emails
sqlite3 emails.db "
SELECT COUNT(*) as pending
FROM raw_emails re
LEFT JOIN processed_emails pe ON pe.email_id = re.id
WHERE pe.id IS NULL;
"

# Tags mit Email-Count
sqlite3 emails.db "
SELECT 
    t.name,
    t.color,
    COUNT(a.id) as email_count
FROM email_tags t
LEFT JOIN email_tag_assignments a ON a.tag_id = t.id
GROUP BY t.id
ORDER BY email_count DESC;
"

# WAL-Status
sqlite3 emails.db "PRAGMA journal_mode;"
sqlite3 emails.db "PRAGMA wal_checkpoint;"

# Alembic-Version
sqlite3 emails.db "SELECT version_num FROM alembic_version;"
```

### Daten exportieren

```bash
# Als CSV
sqlite3 -header -csv emails.db "SELECT id, imap_folder FROM raw_emails;" > emails.csv

# Schema dumpen
sqlite3 emails.db ".schema" > schema.sql

# Kompletter Dump
sqlite3 emails.db ".dump" > full_dump.sql
```

---

## 10. Debugging & Logs

### App-Logs

```bash
# Live-Logs (wenn als Daemon)
tail -f logs/app.log

# Gunicorn Access-Log
tail -f logs/gunicorn_access.log

# Gunicorn Error-Log
tail -f logs/gunicorn_error.log
```

### Flask Debug-Mode

```bash
# Debug-Mode aktivieren
FLASK_DEBUG=1 python3 -m src.00_main --serve

# Mit Reload
FLASK_DEBUG=1 FLASK_ENV=development python3 -m src.00_main --serve
```

### Python-Syntax prüfen

```bash
# Alle Source-Files kompilieren
python3 -m py_compile src/*.py

# Oder mit flake8
flake8 src/ --max-line-length 120
```

### Imports testen

```bash
# Module laden ohne Ausführung
python3 -c "import src.01_web_app; print('OK')"
python3 -c "import src.03_ai_client; print('OK')"
python3 -c "import src.semantic_search; print('OK')"
```

---

## 📎 Schnellreferenz

### Häufigste Befehle

```bash
# Server starten
python3 -m src.00_main --serve --https

# DB aktualisieren
alembic upgrade head

# Emails neu analysieren
python3 scripts/reset_base_pass.py --force
python3 -m src.00_main --process-once

# Tests laufen lassen
python3 -m pytest tests/test_db_schema.py -v

# Ollama prüfen
ollama list
curl http://localhost:11434/api/tags
```

### Troubleshooting Quick-Fixes

```bash
# "No such column" Fehler
alembic upgrade head

# "SQLITE_BUSY" Fehler
sqlite3 emails.db "PRAGMA wal_checkpoint(TRUNCATE);"

# Ollama nicht erreichbar
sudo systemctl start ollama

# Session-Probleme
rm -rf .flask_sessions/*

# Kompletter Neustart
rm emails.db*
python3 -m src.00_main --init-db
alembic upgrade head
```

---

*Stand: Januar 2026 | KI-Mail-Helper*
