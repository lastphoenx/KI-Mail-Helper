# Maintenance & Helper-Skripte

Dieses Dokument dokumentiert alle Wartungs- und Helper-Skripte zum Verwalten der KI-Mail-Helper Installation.

---

## 📋 Verfügbare Skripte

### 1. `scripts/reset_base_pass.py` – Base-Pass Analysis Reset

Löscht alle verarbeiteten E-Mails aus der Datenbank, sodass der Worker diese beim nächsten Durchlauf **neu analysiert**.

**Verwendung:**

```bash
# Alle Emails zurücksetzen (mit Bestätigung)
python3 scripts/reset_base_pass.py

# Ohne Bestätigung (automatisiert)
python3 scripts/reset_base_pass.py --force

# Nur für einen spezifischen Mail-Account
python3 scripts/reset_base_pass.py --account=1 --force

# Nur für einen spezifischen User
python3 scripts/reset_base_pass.py --user=1 --force
```

**Was passiert:**
1. Alle `ProcessedEmail`-Einträge werden aus der Datenbank gelöscht
2. `RawEmail`-Einträge bleiben erhalten
3. Beim nächsten Worker-Run werden alle RawEmails neu verarbeitet (Base-Pass)

**Warnung:**
- Worker sollte während der Ausführung **NICHT** laufen
- Nutzen Sie `--force` nur, wenn Sie wissen, was Sie tun

**Rücksetzen bei Bedarf:**
- Nach Änderung des AI-Providers für Base-Pass
- Nach Tuning der KI-Prompts
- Für kompletten Neu-Analyse aller Emails

---

## 🔧 Datenbankmigrationen

### Manuelle Migrationen (SQLite Limitations)

**ServiceToken master_key (2025-12-28):**

```bash
cd /home/thomas/projects/KI-Mail-Helper
sqlite3 emails.db "ALTER TABLE service_tokens ADD COLUMN master_key TEXT;"
```

Diese Spalte speichert den verschlüsselten DEK für Background-Jobs (Mail-Abruf ohne aktive User-Session).

**Hinweis:** SQLite unterstützt nicht alle ALTER TABLE Operationen. Bei komplexen Schema-Änderungen:
1. Backup der DB erstellen
2. Neue Tabelle mit korrektem Schema erstellen
3. Daten migrieren
4. Alte Tabelle löschen

---

## 🔧 Alembic – Datenbankmigrationen (Legacy)

Die Datenbank-Schema-Versionen wurden früher mit **Alembic** verwaltet.

### Aktuelle Versionen

```bash
# Status aller Migrationen anzeigen
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
python -m alembic current
python -m alembic history
```

### Migration durchführen

```bash
# Auf die neueste Version upgrade
python -m alembic upgrade head

# Auf eine spezifische Version gehen
python -m alembic upgrade d1be18ce087b  # z.B.

# Eine Version zurück (Downgrade)
python -m alembic downgrade -1
```

### Neue Migration erstellen

```bash
# Neue Migration generieren
python -m alembic revision -m "Add new column xyz"

# Edit: alembic/versions/*.py anpassen
# Dann deployen:
python -m alembic upgrade head
```

**Wichtig:**
- `DELETE FROM alembic_version` **NIEMALS** machen
- Migrations sind Teil der Versionskontrolle

---

## 📊 Datenbankwartung

### DB-Status prüfen

```bash
cd /home/thomas/projects/KI-Mail-Helper && source venv/bin/activate && python3 << 'EOF'
import importlib
models = importlib.import_module('.02_models', 'src')

engine, Session = models.init_db("emails.db")
session = Session()

print("📊 Database Statistics")
print("=" * 60)
print(f"Users: {session.query(models.User).count()}")
print(f"Mail-Accounts: {session.query(models.MailAccount).count()}")
print(f"Raw Emails: {session.query(models.RawEmail).count()}")
print(f"Processed Emails: {session.query(models.ProcessedEmail).count()}")

session.close()
EOF
```

### Waisenkinddatensätze bereinigen

Mails löschen, deren RawEmail gelöscht wurde:

```bash
cd /home/thomas/projects/KI-Mail-Helper && source venv/bin/activate && python3 << 'EOF'
import importlib
models = importlib.import_module('.02_models', 'src')

engine, Session = models.init_db("emails.db")
session = Session()

try:
    # Finde verwaiste ProcessedEmails (RawEmail existiert nicht mehr)
    orphaned = session.query(models.ProcessedEmail).filter(
        ~models.ProcessedEmail.raw_email_id.in_(
            session.query(models.RawEmail.id)
        )
    ).delete(synchronize_session=False)
    
    session.commit()
    print(f"✅ {orphaned} verwaiste ProcessedEmail-Einträge gelöscht")
except Exception as e:
    session.rollback()
    print(f"❌ Fehler: {e}")
finally:
    session.close()
EOF
```

---

## 🔑 Umgebungsvariablen (.env)

Die `.env`-Datei muss im Projektroot vorhanden sein und enthält sensitive Daten.

**Template:**
```bash
# IMAP/SMTP (falls benötigt für Testmail)
TEST_IMAP_SERVER=imap.gmail.com
TEST_IMAP_USERNAME=your-email@gmail.com
TEST_IMAP_PASSWORD=your-app-password

# KI-Provider APIs
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...
MISTRAL_API_KEY=...
OLLAMA_API_URL=http://localhost:11434

# Flask Secret
FLASK_SECRET_KEY=generate-me-randomly

# Optional: Datenbank-Pfad
DATABASE_PATH=emails.db
```

**Security-Hinweise:**
- `.env` ist im `.gitignore` – nicht committen!
- API-Keys sind sensitiv → nicht teilen
- WSL-Debian kann Windows ENV-Variablen nicht lesen → immer `.env` verwenden

---

## 🐳 Docker (optional)

Falls in Zukunft Docker-Support gewünscht:

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ENV FLASK_APP=src.00_main
CMD ["python3", "-m", "src.00_main", "--serve"]
```

---

## 🚀 Deployment Checkliste

Vor jedem Deployment:

- [ ] `.env` mit korrekten API-Keys prüfen
- [ ] `alembic upgrade head` durchführen (neueste DB-Schema)
- [ ] `python -m pytest tests/` alle Tests bestätigen
- [ ] `python3 -m py_compile src/*.py` Syntax checken
- [ ] Worker/Cron-Jobs starten: `python -m src.00_main --worker`
- [ ] Web-App testen: `python -m src.00_main --serve`

---

## 📝 Logging

Logs werden standardmäßig zu `stdout` ausgegeben. Für Persistierung:

```bash
# Web-App im Hintergrund mit Log-Datei
nohup python3 -m src.00_main --serve > logs/webapp.log 2>&1 &

# Worker mit Log-Datei
nohup python3 -m src.00_main --worker > logs/worker.log 2>&1 &

# Logs in Echtzeit anschauen
tail -f logs/webapp.log
tail -f logs/worker.log
```

---

## 🆘 Troubleshooting

### Problem: "no such column: users.preferred_ai_provider_optimize"

**Lösung:**
```bash
python -m alembic upgrade head
```

Die Datenbank-Schema ist nicht aktuell. Führe die neueste Migration aus.

### Problem: "UNIQUE constraint failed"

**Lösung:**
```bash
python3 scripts/reset_base_pass.py --force
```

Duplicate E-Mails möglich. Setzen Sie die Analyse zurück.

### Problem: Ollama nicht erreichbar

**Lösung:**
```bash
# Ollama läuft?
curl http://localhost:11434/api/tags

# Falls nicht, starten:
ollama serve

# Model verfügbar?
ollama list
ollama pull llama3.2  # oder dein Modell
```

### Problem: API-Key ungültig

**Lösung:**
1. `.env` prüfen: API-Key korrekt?
2. API-Account überpüft? (OpenAI, Anthropic, Mistral)
3. Quota/Limits überschritten?
4. Neu starten: `python -m src.00_main --serve`

---

## 📚 Weitere Ressourcen

- **Instruction_&_goal.md** – Projekt-Spezifikation
- **CRON_SETUP.md** – Hintergrund-Jobs & Cron-Konfiguration
- **OAUTH_AND_IMAP_SETUP.md** – OAuth & IMAP-Account Setup
- **TESTING_GUIDE.md** – Test-Anleitung
