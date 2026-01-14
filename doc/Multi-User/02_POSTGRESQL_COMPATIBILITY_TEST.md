# PostgreSQL Compatibility Test Leitfaden
## KI-Mail-Helper Multi-User Migration

**Status**: Produktionsreife Test-Strategie  
**Geschätzter Aufwand**: 6-8 Stunden  
**Datum**: Januar 2026  
**Sprache**: Deutsch  

---

## 🎯 ZIEL

Validieren, dass die SQLAlchemy-Modelle und Business-Logic ohne Modifikationen von SQLite zu PostgreSQL migrieren können.

**Akzeptanzkriterium**: 
- ✅ Alle Model-Definitionen sind PostgreSQL-kompatibel
- ✅ Daten-Migration (SQLite → PostgreSQL) ohne Datenverluste möglich
- ✅ Checksummen vor/nach Migration stimmen überein
- ✅ Indizes und Constraints funktionieren in PostgreSQL

---

## 📋 SCHRITT 1: Models Analyse (2h)

### 1.1 Checklist: SQLAlchemy Compatibility

Durchsuche alle Models in `src/02_models.py` nach problematischen Patterns:

```bash
# Terminal:
cd /home/thomas/projects/KI-Mail-Helper-Dev

# 1. Finde AUTOINCREMENT (SQLite-spezifisch)
grep -n "autoincrement" src/02_models.py

# 2. Finde SQLITE-spezifische Types
grep -n "sqlite\|JSON\|UUID" src/02_models.py

# 3. Finde raw SQL Statements
grep -n "text(\|execute(" src/02_models.py

# 4. Finde problematische Constraints
grep -n "PRAGMA\|UNIQUE\|CHECK" src/02_models.py
```

### 1.2 Häufige Probleme & Lösungen

| Problem | SQLite | PostgreSQL | Lösung |
|---------|--------|-----------|--------|
| **AUTOINCREMENT** | `autoincrement=True` | Default auto | ✅ Entfernen |
| **Text-Länge** | Unbegrenzt | Begrenzt | ✅ VARCHAR(n) nutzen |
| **JSON** | TEXT-Workaround | Native JSON | ✅ JSON-Type nutzen |
| **UUID** | TEXT(36) | UUID-Type | ✅ UUID-Type für PG |
| **Boolean** | INTEGER (0/1) | BOOLEAN | ✅ Migriert automatisch |
| **DateTime** | TIMESTAMP | TIMESTAMP | ✅ UTC-aware nutzen |

### 1.3 Script: Models validieren

```python
# test_models_compatibility.py
"""Validiere SQLAlchemy Models auf PostgreSQL Kompatibilität."""

import sys
sys.path.insert(0, "/home/thomas/projects/KI-Mail-Helper-Dev")

from sqlalchemy import inspect
from src.02_models import Base, User, MailAccount, RawEmail

def check_model_compatibility(model_class):
    """Prüfe einzelnes Model auf PG-Kompatibilität."""
    print(f"\n📋 Checking: {model_class.__name__}")
    mapper = inspect(model_class)
    
    issues = []
    
    for column in mapper.columns:
        print(f"  - {column.name}: {column.type}")
        
        # Problem 1: Autoincrement
        if column.autoincrement is True and column.primary_key:
            issues.append(f"⚠️  {column.name}: autoincrement=True nicht nötig in PG")
        
        # Problem 2: String-Länge unklar
        if str(column.type).startswith("VARCHAR()"):
            issues.append(f"⚠️  {column.name}: Unbegrenzte VARCHAR nicht optimal in PG")
        
        # Problem 3: Raw Types
        if "SQLITE" in str(column.type).upper():
            issues.append(f"❌ {column.name}: SQLite-spezifischer Type!")
    
    if issues:
        print(f"\n⚠️  ISSUES in {model_class.__name__}:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print(f"✅ {model_class.__name__} ist PG-kompatibel!")
    
    return issues

# Alle Models prüfen
all_models = [User, MailAccount, RawEmail]  # + weitere...
all_issues = []

for model in all_models:
    all_issues.extend(check_model_compatibility(model))

print(f"\n{'='*60}")
if all_issues:
    print(f"❌ {len(all_issues)} Kompatibilitäts-Probleme gefunden!")
    sys.exit(1)
else:
    print(f"✅ Alle {len(all_models)} Models sind PG-kompatibel!")
    sys.exit(0)
```

**Ausführen:**
```bash
python test_models_compatibility.py
```

---

## 📊 SCHRITT 2: Lokale Test-Umgebung (2h)

### 2.1 PostgreSQL + Redis starten

```bash
# PostgreSQL starten (Docker)
docker run -d \
  --name test-pg \
  -e POSTGRES_PASSWORD=test_pass_123 \
  -e POSTGRES_DB=mail_test \
  -p 5433:5432 \
  postgres:15

# Redis starten (Docker)
docker run -d \
  --name test-redis \
  -p 6380:6379 \
  redis:7

# Verifikation
sleep 3
psql postgresql://postgres:test_pass_123@localhost:5433/mail_test -c "SELECT 1" && echo "✅ PostgreSQL ready"
redis-cli -p 6380 ping && echo "✅ Redis ready"
```

### 2.2 Alembic Initialisierung

```bash
# .env.test erstellen
cat > .env.test << 'EOF'
DATABASE_URL=postgresql://postgres:test_pass_123@localhost:5433/mail_test
FLASK_ENV=test
EOF

# Alembic prüfen
ls -la migrations/

# Wenn leer: Initialisieren
if [ ! -f migrations/env.py ]; then
    alembic init migrations
fi

# Migration generieren (automatisch)
alembic revision --autogenerate -m "PostgreSQL initial schema"

# Lokal testen (NICHT in Produktion anwenden!)
alembic upgrade head
```

### 2.3 Verifizierung: PostgreSQL Schema

```bash
# PostgreSQL Schema inspizieren
psql postgresql://postgres:test_pass_123@localhost:5433/mail_test << 'EOF'
-- Alle Tabellen
\dt

-- Tabellenstruktur
\d raw_emails
\d processed_emails
\d users

-- Indizes
\di

-- Constraints
\dC
EOF
```

---

## 🔄 SCHRITT 3: Daten-Migration Test (2h)

### 3.1 Test-Daten vorbereiten

```bash
# Aktuellen SQLite-DB als Backup kopieren
cp emails.db emails.db.backup_$(date +%Y%m%d_%H%M%S)

# Oder: Test-DB mit Beispiel-Daten erstellen
python << 'EOF'
import sys
sys.path.insert(0, "/home/thomas/projects/KI-Mail-Helper-Dev")

from src.helpers.database import get_session, get_engine
from src.02_models import User, MailAccount, RawEmail

# Engine stellt sicher, dass Models existieren
engine = get_engine()

session = get_session()()
try:
    # Test User
    test_user = User(
        email="test@example.com",
        username="testuser",
        password_hash="hashed_test_password"
    )
    session.add(test_user)
    session.flush()
    
    # Test Account
    test_account = MailAccount(
        user_id=test_user.id,
        email="test@mail.example.com",
        provider="imap",
        server_host="imap.example.com",
        imap_port=993,
        smtp_port=587
    )
    session.add(test_account)
    session.flush()
    
    # Test Emails (10 Stück)
    for i in range(10):
        email = RawEmail(
            user_id=test_user.id,
            account_id=test_account.id,
            message_id=f"<test-{i}@example.com>",
            sender="sender@example.com",
            subject=f"Test Email {i}",
            folder="INBOX",
            uid=1000 + i,
            is_deleted=False
        )
        session.add(email)
    
    session.commit()
    print(f"✅ Test-Daten erstellt: {test_user.id}, {test_account.id}")
    
finally:
    session.close()
EOF
```

### 3.2 SQLite → PostgreSQL Migration

```bash
# Dump aus SQLite
sqlite3 emails.db .dump > emails_dump.sql

# In PostgreSQL importieren
psql postgresql://postgres:test_pass_123@localhost:5433/mail_test < emails_dump.sql

# ODER: Mit SQLAlchemy (empfohlen)
python << 'EOF'
import sys
sys.path.insert(0, "/home/thomas/projects/KI-Mail-Helper-Dev")

from sqlalchemy import text
from src.helpers.database import get_session, get_engine

# Quell-DB (SQLite)
import os
sqlite_url = f"sqlite:///{os.path.expanduser('emails.db')}"
from sqlalchemy import create_engine
sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

# Ziel-DB (PostgreSQL)
pg_engine = get_engine()  # Nutzt DATABASE_URL aus Env

# Alle Tabellen kopieren
with sqlite_engine.connect() as sqlite_conn:
    with pg_engine.connect() as pg_conn:
        # User
        users = sqlite_conn.execute(text("SELECT * FROM user")).fetchall()
        for user in users:
            pg_conn.execute(text("""
                INSERT INTO user (id, email, username, password_hash)
                VALUES (:id, :email, :username, :password_hash)
            """), {
                "id": user[0],
                "email": user[1],
                "username": user[2],
                "password_hash": user[3]
            })
        
        print(f"✅ {len(users)} User migriert")
        pg_conn.commit()

EOF
```

### 3.3 Checksummen-Vergleich

```python
# test_data_integrity.py
"""Vergleiche Daten SQLite vs PostgreSQL."""

import sys
sys.path.insert(0, "/home/thomas/projects/KI-Mail-Helper-Dev")

from sqlalchemy import text, func
from sqlalchemy import create_engine
import hashlib
import os

def get_table_checksum(engine, table_name):
    """Berechne Checksum für ganze Tabelle."""
    with engine.connect() as conn:
        # Zähle Zeilen
        count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        
        # PostgreSQL: ORDER BY für deterministisches Hashing
        query = f"""
        SELECT string_agg(MD5(row(*)::text), '|' ORDER BY id)
        FROM {table_name}
        ORDER BY id
        """
        
        try:
            result = conn.execute(text(query)).scalar() or ""
            checksum = hashlib.md5(result.encode()).hexdigest()
        except Exception as e:
            print(f"⚠️  {table_name}: {e}")
            return None, count
        
        return checksum, count

# SQLite
sqlite_url = f"sqlite:///{os.path.expanduser('emails.db')}"
sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

# PostgreSQL
from src.helpers.database import get_engine
pg_engine = get_engine()

print("\n📊 CHECKSUMMEN-VERGLEICH")
print("=" * 60)

for table in ["user", "mail_account", "raw_emails", "processed_emails"]:
    try:
        sqlite_sum, sqlite_count = get_table_checksum(sqlite_engine, table)
        pg_sum, pg_count = get_table_checksum(pg_engine, table)
        
        if sqlite_count == 0:
            print(f"⏭️  {table}: Keine Daten (0 Zeilen)")
            continue
        
        if sqlite_sum == pg_sum:
            print(f"✅ {table}: {sqlite_count} Zeilen, Checksum identisch")
        else:
            print(f"❌ {table}: Checksummen unterschiedlich!")
            print(f"   SQLite: {sqlite_sum}")
            print(f"   PG:     {pg_sum}")
    except Exception as e:
        print(f"⚠️  {table}: Fehler - {e}")

```

**Ausführen:**
```bash
DATABASE_URL=postgresql://postgres:test_pass_123@localhost:5433/mail_test python test_data_integrity.py
```

---

## 🚨 SCHRITT 4: Performance-Tests (1h)

### 4.1 Abfrage-Performance

```python
# test_query_performance.py
"""Vergleiche Query-Performance SQLite vs PostgreSQL."""

import time
import sys
sys.path.insert(0, "/home/thomas/projects/KI-Mail-Helper-Dev")

from sqlalchemy import text, create_engine
import os

sqlite_url = f"sqlite:///{os.path.expanduser('emails.db')}"
sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

from src.helpers.database import get_engine
pg_engine = get_engine()

# Test-Queries
queries = [
    ("SELECT COUNT(*)", "Zeilen-Zählung"),
    ("SELECT * FROM raw_emails LIMIT 100", "Einfache SELECT"),
    ("""SELECT u.id, COUNT(e.id) as email_count 
        FROM user u 
        LEFT JOIN raw_emails e ON u.id = e.user_id 
        GROUP BY u.id""", "Komplexer JOIN"),
]

print("\n⚡ PERFORMANCE-VERGLEICH")
print("=" * 70)

for query, description in queries:
    print(f"\n{description}:")
    
    # SQLite
    start = time.time()
    with sqlite_engine.connect() as conn:
        result = conn.execute(text(query)).fetchall()
    sqlite_time = (time.time() - start) * 1000
    
    # PostgreSQL
    start = time.time()
    with pg_engine.connect() as conn:
        result = conn.execute(text(query)).fetchall()
    pg_time = (time.time() - start) * 1000
    
    improvement = (sqlite_time - pg_time) / sqlite_time * 100 if sqlite_time > 0 else 0
    
    print(f"  SQLite:     {sqlite_time:.2f} ms")
    print(f"  PostgreSQL: {pg_time:.2f} ms")
    print(f"  Verbesserung: {improvement:.1f}%")

```

---

## ✅ SCHRITT 5: Rollback-Plan

### 5.1 Backup vor Migration

```bash
# Tag X: Backup erstellen
cp emails.db emails.db.backup_production_$(date +%Y%m%d_%H%M%S)
# → Backup 2 Wochen aufbewahren!

# Wenn Fehler in Produktion:
# 1. PostgreSQL herunterfahren
# 2. Alte SQLite-DB: sqlite3 emails.db.backup_* 
# 3. Flask mit DATABASE_URL=sqlite:///emails.db starten
```

### 5.2 Feature-Flag für Fallback

```python
# app_factory.py - USE_POSTGRESQL Feature-Flag hinzufügen
import os

USE_POSTGRESQL = os.getenv("USE_POSTGRESQL", "false").lower() == "true"

if USE_POSTGRESQL:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://...")
else:
    DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

logger.info(f"Using database: {DATABASE_URL.split('://')[0].upper()}")
```

**Startup:**
```bash
# Mit PostgreSQL
USE_POSTGRESQL=true python3 -m src.00_main --serve

# Mit SQLite (Fallback)
python3 -m src.00_main --serve
```

---

## 📝 CHECKLISTE: Production Rollout

- [ ] Lokal: `pytest test_models_compatibility.py` → ✅ PASS
- [ ] Lokal: `pytest test_data_integrity.py` → ✅ Checksummen identisch
- [ ] Lokal: `pytest test_query_performance.py` → ✅ PG ist schneller oder gleich
- [ ] Staging: PostgreSQL 2 Wochen getestet
- [ ] Staging: Backup erstellt und validiert
- [ ] Backup: 2 Wochen lang aufbewahrt
- [ ] Rollback-Plan: Dokumentiert und getestet
- [ ] Monitoring: PostgreSQL Connection-Logs aktiviert
- [ ] Alarmierung: Bei Connection-Errors konfiguriert

---

## 🔍 Troubleshooting

### Problem: "UnicodeEncodeError bei Migration"
```bash
# Lösung: LANG setzen
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
alembic upgrade head
```

### Problem: "PostgreSQL Schema stimmt nicht mit Models überein"
```bash
# Lösung: Neuere Alembic-Migration generieren
alembic revision --autogenerate -m "Fix schema mismatch"
alembic upgrade head
```

### Problem: "Connection Timeout"
```bash
# Lösung: Pool-Konfiguration in database.py anpassen
pool_size=30,
max_overflow=60,
pool_recycle=1800  # Alle 30 Min recyclen
```

---

## 📚 Weiterführende Links

- Alembic Doku: https://alembic.sqlalchemy.org/
- PostgreSQL Doku: https://www.postgresql.org/docs/
- SQLAlchemy Dialekte: https://docs.sqlalchemy.org/core/dialects/
