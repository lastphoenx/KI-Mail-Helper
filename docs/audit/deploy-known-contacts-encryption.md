# Deploy: Bekannte Kontakte verschlüsseln (f7 → Backfill → f8)

**Reihenfolge:** Probelauf auf DB-Kopie → dann Produktion. **Kein f8**, bevor Backfill und Verify grün sind.

Code-Stand: **`origin/main`** (≥ `229737e`) — Passwort-Backfill, Phase-2-Model; nach f7 sind Klartext-Spalten in der DB noch vorhanden, bis **f8** läuft.

**Wichtig:** App, Alembic (`migrations/env.py`) und Backfill/Verify-Skripte nutzen **`DATABASE_URL`** (`src/helpers/database.py`), nicht `PGDATABASE`. `PGDATABASE` gilt nur für `psql`, `pg_dump` und `pg_restore`.

---

## Variablen (am Anfang anpassen)

```bash
set -euo pipefail

# App (Beispiel Homelab — Werte vor dem Kopieren prüfen)
export KMH_APP_ROOT=/opt/KI-Mail-Helper
export KMH_VENV="${KMH_APP_ROOT}/venv"
export KMH_USER_ID=1

# PostgreSQL (pg_dump/psql — Name muss zum DB-Segment in DATABASE_URL passen)
export PGDATABASE=mail_helper
export PGBACKUP_DIR=/var/backups/mail-helper

# systemd — Produktion während Migration stoppen (nicht für Probelauf nötig)
export KMH_SVC_WEB=mail-helper.service
export KMH_SVC_CELERY_WORKER=mail-helper-celery-worker.service
export KMH_SVC_CELERY_BEAT=mail-helper-celery-beat.service
```

### DATABASE_URL aus `.env` laden und Ziel prüfen

Vor **jedem** Schritt mit Alembic, Backfill oder Verify in der **gleichen Shell**:

```bash
kmh_load_database_url() {
  local env_file="${KMH_APP_ROOT}/.env"
  if [ ! -f "$env_file" ]; then
    echo "FEHLER: $env_file fehlt" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^DATABASE_URL=' "$env_file" | sed 's/^/export /')
  set +a
}

kmh_database_url_for_db() {
  local dbname="$1"
  python3 -c "
import os, sys
from sqlalchemy.engine.url import make_url
u = make_url(os.environ['DATABASE_URL'])
print(u.set(database=sys.argv[1]))
" "$dbname"
}

kmh_assert_target_db() {
  local expected="$1"
  kmh_load_database_url
  local actual
  actual="$(python3 -c "
import os
from sqlalchemy.engine.url import make_url
print(make_url(os.environ['DATABASE_URL']).database)
")"
  if [ "$actual" != "$expected" ]; then
    echo "FEHLER: DATABASE_URL zeigt auf '$actual', erwartet '$expected' — abbrechen." >&2
    exit 1
  fi
  echo "OK: Ziel-Datenbank = $actual"
}
```

**Produktion (Phase A/B):** nach `kmh_load_database_url` einmal `kmh_assert_target_db "$PGDATABASE"` — typisch `mail_helper`.

### Dienste stoppen / prüfen / starten

```bash
kmh_stop_services() {
  sudo systemctl stop "$KMH_SVC_CELERY_BEAT" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_WEB"
  sleep 2
  for u in "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"; do
    if systemctl is-active --quiet "$u"; then
      echo "FEHLER: $u läuft noch — Migration abbrechen." >&2
      exit 1
    fi
  done
  echo "OK: Web + Celery Worker + Beat gestoppt."
}

kmh_start_services() {
  sudo systemctl start "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"
  sudo systemctl is-active "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"
}
```

---

## Probelauf (Pflicht vor Produktion)

Gleiche Befehle wie Phase A/B, aber **`DATABASE_URL` zeigt auf eine Kopie**. **Produktions-Dienste müssen dafür nicht gestoppt werden** — nur `pg_dump`/`pg_restore`, Alembic und die Operator-Skripte in einer Shell mit umgestellter `DATABASE_URL`.

```bash
set -euo pipefail
# Variablen wie oben; Funktionen kmh_* einmal definieren (siehe oben)

export PGDATABASE_TEST="${PGDATABASE}_contacts_encrypt_drill"
export PGPASSFILE=   # ggf. leeren, wenn lokal peer-auth

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
sudo mkdir -p "$PGBACKUP_DIR"

# 1) Sicherung Produktion (nur lesend)
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" -f "$PGBACKUP_DIR/${PGDATABASE}-drill-source-${STAMP}.dump"

# 2) Test-DB anlegen und einspielen
sudo -u postgres dropdb --if-exists "$PGDATABASE_TEST"
sudo -u postgres createdb -O postgres "$PGDATABASE_TEST"
sudo -u postgres pg_restore -d "$PGDATABASE_TEST" "$PGBACKUP_DIR/${PGDATABASE}-drill-source-${STAMP}.dump"

# 3) App/Alembic/Skripte auf die Kopie umstellen (nicht nur PGDATABASE!)
kmh_load_database_url
export DATABASE_URL="$(kmh_database_url_for_db "$PGDATABASE_TEST")"
export PGDATABASE="$PGDATABASE_TEST"
kmh_assert_target_db "$PGDATABASE_TEST"

# → Phase A + Phase B unten vollständig durchspielen (ohne kmh_stop_services am Produktions-CT)
# Vor jedem Alembic-/Backfill-/Verify-Schritt: kmh_assert_target_db "$PGDATABASE_TEST"

# 4) Drill beenden — Produktions-URL wiederherstellen
unset DATABASE_URL
kmh_load_database_url
export PGDATABASE=mail_helper
kmh_assert_target_db "$PGDATABASE"
```

Nach erfolgreichem Drill: **neues** `pg_dump` der Produktion, dann Phase A auf dem echten `PGDATABASE` mit `kmh_assert_target_db "$PGDATABASE"` vor jedem DB-Schritt.

---

## Phase A — f7 + Backfill + Verify (Code bereits `main`)

1. **Dienste stoppen:**

```bash
kmh_stop_services
```

2. **Backup:**

```bash
kmh_assert_target_db "$PGDATABASE"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
sudo mkdir -p "$PGBACKUP_DIR"
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" -f "$PGBACKUP_DIR/${PGDATABASE}-pre-f7-${STAMP}.dump"
ls -la "$PGBACKUP_DIR" | tail -3
```

3. **Code** (`main`, enthält f7 + f8 Migrationen im Repo — **nur f7 ausführen**):

```bash
cd "$KMH_APP_ROOT"
git fetch origin
git checkout main
git pull origin main
source "$KMH_VENV/bin/activate"
pip install -r requirements.txt
```

4. **Alembic nur bis f7** (Klartext-Spalten bleiben in der DB):

```bash
cd "$KMH_APP_ROOT"
source "$KMH_VENV/bin/activate"
kmh_load_database_url
kmh_assert_target_db "$PGDATABASE"
alembic upgrade f7a8b9c0d1e2
alembic current
```

5. **Dienste starten** (Backfill braucht nur DB + venv; UI optional für manuelle Checks):

```bash
kmh_start_services
```

**Kein Kontakt-Import** (UI oder Scan-Import), **bevor Schritt 6–7 grün sind.** Läuft die App mit neuem Code vor dem Backfill, können für dieselbe Adresse eine Klartext-Zeile und eine bereits verschlüsselte Zeile existieren. Der Backfill führt solche Duplikate zusammen (`mail_count` addieren, Anzeigename der neueren Zeile); Import vor dem Backfill vermeidet trotzdem unnötige Arbeit und UI-Seiteneffekte.

6. **Backfill** (Masterpasswort interaktiv — DEK wird wie beim Login abgeleitet):

```bash
cd "$KMH_APP_ROOT"
source "$KMH_VENV/bin/activate"
kmh_load_database_url
kmh_assert_target_db "$PGDATABASE"
python scripts/backfill_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID" --dry-run
python scripts/backfill_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID"
```

7. **Verify (alle Zeilen):**

```bash
kmh_assert_target_db "$PGDATABASE"
python scripts/verify_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID" --require-full --sample 0
```

8. **Manuell:** Kontaktliste, Ordner-Audit-Scan (kein Fehler `known_contacts_backfill_required`).

9. **Optional:** Kontakt-Import über UI, dann Schritte 6–7 wiederholen.

**Hinweis:** Läuft die App vor dem Backfill mit neuem Code, meldet der Scan **`known_contacts_backfill_required`** statt still fehlender Kontakte.

---

## Phase B — nur f8 (Drop Klartext-Spalten)

**Erst nach grünem Verify in Phase A.** Code ist bereits `main` — kein erneutes Downgrade/Checkout nötig.

1. **Dienste stoppen:**

```bash
kmh_stop_services
```

2. **Backup vor Drop:**

```bash
kmh_assert_target_db "$PGDATABASE"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" -f "$PGBACKUP_DIR/${PGDATABASE}-pre-f8-${STAMP}.dump"
```

3. **Backfill + Verify** (falls seit Phase A noch Import/Übergangs-Klartext in der DB):

```bash
cd "$KMH_APP_ROOT"
source "$KMH_VENV/bin/activate"
kmh_load_database_url
kmh_assert_target_db "$PGDATABASE"
python scripts/backfill_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID"
python scripts/verify_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID" --require-full --sample 0
```

4. **Alembic f8** (bricht ab, wenn noch Zeilen ohne `encrypted_email` / HMAC):

```bash
kmh_assert_target_db "$PGDATABASE"
alembic upgrade f8a9b0c1d2e3
alembic current
```

5. **Dienste starten:**

```bash
kmh_start_services
```

6. **Smoke:** Kontaktliste, Import, Ordner-Scan.

---

## Rollback

| Situation | Aktion |
|-----------|--------|
| Nach f7, Backfill fehlgeschlagen | `pg_restore` aus pre-f7-Dump; Alembic-Downgrade nur nach Doku |
| Nach f8 | `pg_restore` aus **pre-f8**-Dump; Code-Stand + Alembic manuell zurücksetzen |

Backfill/Verify-Skripte lesen Klartext nur per SQL, solange die Spalten in der DB existieren (**vor f8**).

Siehe `docs/audit/ADR-audit-known-contacts-encryption.md`.
