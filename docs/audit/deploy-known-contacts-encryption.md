# Deploy: Bekannte Kontakte verschlüsseln (f7 → Backfill → f8)

**Code:** `origin/main` ≥ `67e3f40`  
**Reihenfolge:** Probelauf auf DB-Kopie → Produktion. **Kein f8**, bevor Backfill und Verify grün sind.

Alembic, Backfill und Verify nutzen **`DATABASE_URL`** aus der Shell (`migrations/env.py`, `src/helpers/database.py`). `PGDATABASE` nur für `pg_dump` / `psql`.

**Ziel-DB:** `--expect-db NAME` (Backfill/Verify) oder `python scripts/kmh_expect_db.py --expect-db NAME` vor Alembic — Prüfung via `SELECT current_database()`, **ohne** `.env` neu einzulesen.

**Ausführung auf dem CT:** Die Blöcke unten sind zum Kopieren gedacht. **`set -euo pipefail` nicht in eine interaktive Shell einfügen** (beendet die Session beim ersten Fehler). Stattdessen: Block in eine Datei schreiben (z. B. `/root/kmh-contacts-deploy-phase-a.sh`), darin Zeile 2 `set -euo pipefail`, dann `bash /root/kmh-contacts-deploy-phase-a.sh` — oder einen Block mit `bash -c 'set -euo pipefail; …'`.

---

## 0) Variablen und Hilfsfunktionen (einmal pro Session)

```bash
export KMH_APP_ROOT=/opt/KI-Mail-Helper
export KMH_VENV="${KMH_APP_ROOT}/venv"
export KMH_USER_ID=1
export PGDATABASE=mail_helper
export PGBACKUP_DIR=/var/backups/mail-helper

export KMH_SVC_WEB=mail-helper.service
export KMH_SVC_CELERY_WORKER=mail-helper-celery-worker.service
export KMH_SVC_CELERY_BEAT=mail-helper-celery-beat.service

sudo mkdir -p "$PGBACKUP_DIR"

# Produktions-DATABASE_URL einmal aus .env (nur wenn noch nicht gesetzt — Drill setzt URL danach selbst)
if [ -z "${DATABASE_URL:-}" ]; then
  export DATABASE_URL="$(
    grep -E '^DATABASE_URL=' "${KMH_APP_ROOT}/.env" | sed 's/^DATABASE_URL=//' | tr -d '"' | tr -d "'"
  )"
fi

kmh_stop_services() {
  sudo systemctl stop "$KMH_SVC_CELERY_BEAT" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_WEB"
  sleep 2
  for u in "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"; do
    if systemctl is-active --quiet "$u"; then
      echo "FEHLER: $u läuft noch." >&2
      return 1
    fi
  done
  echo "OK: Dienste gestoppt."
}

kmh_start_services() {
  sudo systemctl start "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"
  sudo systemctl is-active "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"
}

kmh_pull_code() {
  cd "$KMH_APP_ROOT"
  git fetch origin
  git checkout main
  git pull origin main
  source "${KMH_VENV}/bin/activate"
  pip install -r requirements.txt
}
```

Alembic `env.py` lädt `.env` ohne `override` — eine **bereits exportierte** `DATABASE_URL` bleibt für Alembic erhalten.

---

## 1) Probelauf (Pflicht, Dienste laufen weiter)

Gleiche Schritte wie Phase A/B, aber auf **`mail_helper_contacts_encrypt_drill`**. Danach Drill-URL verwerfen und Produktion mit `--expect-db mail_helper` fahren.

```bash
export PGDATABASE_TEST="${PGDATABASE}_contacts_encrypt_drill"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

# 1) Dump der Produktion (nur lesend)
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" \
  -f "${PGBACKUP_DIR}/${PGDATABASE}-drill-source-${STAMP}.dump"

# 2) Test-DB
sudo -u postgres dropdb --if-exists "$PGDATABASE_TEST"
sudo -u postgres createdb -O postgres "$PGDATABASE_TEST"
sudo -u postgres pg_restore -d "$PGDATABASE_TEST" \
  "${PGBACKUP_DIR}/${PGDATABASE}-drill-source-${STAMP}.dump"

# 3) DATABASE_URL auf Drill (gleiche Credentials, anderer DB-Name)
export DATABASE_URL="$(
  python3 -c "
import os
from sqlalchemy.engine.url import make_url
u = make_url(os.environ['DATABASE_URL'])
print(u.set(database=os.environ['PGDATABASE_TEST']))
"
)"
export PGDATABASE="$PGDATABASE_TEST"

cd "$KMH_APP_ROOT"
source "${KMH_VENV}/bin/activate"
python scripts/kmh_expect_db.py --expect-db "$PGDATABASE_TEST"

# 4) Phase A + B unten — überall PGDATABASE=$PGDATABASE_TEST und --expect-db "$PGDATABASE_TEST"
#    kmh_stop_services im Drill optional (nur wenn du Worker-Kollision testen willst)

# 5) Drill beenden — wieder Produktion
unset DATABASE_URL
export PGDATABASE=mail_helper
export DATABASE_URL="$(
  grep -E '^DATABASE_URL=' "${KMH_APP_ROOT}/.env" | sed 's/^DATABASE_URL=//' | tr -d '"' | tr -d "'"
)"
cd "$KMH_APP_ROOT" && source "${KMH_VENV}/bin/activate"
python scripts/kmh_expect_db.py --expect-db mail_helper
```

Nach grünem Drill: **neuer** Produktions-`pg_dump`, dann Abschnitt 2 auf `mail_helper`.

---

## 2) Phase A — f7 + Backfill + Verify

Als Skript ausführen (empfohlen), z. B. `bash /root/kmh-contacts-phase-a.sh` mit `set -euo pipefail` als zweite Zeile im Skript.

### 2.1 Dienste stoppen und Backup

```bash
kmh_stop_services

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" \
  -f "${PGBACKUP_DIR}/${PGDATABASE}-pre-f7-${STAMP}.dump"
ls -la "$PGBACKUP_DIR" | tail -5
```

### 2.2 Code ≥ 67e3f40

```bash
kmh_pull_code
```

### 2.3 Alembic nur f7 (Klartext-Spalten bleiben bis f8)

```bash
cd "$KMH_APP_ROOT"
source "${KMH_VENV}/bin/activate"
python scripts/kmh_expect_db.py --expect-db "$PGDATABASE"
alembic upgrade f7a8b9c0d1e2
alembic current
```

### 2.4 Dienste starten

```bash
kmh_start_services
```

**Kein Kontakt-Import** (UI/Scan), bis Backfill und Verify grün sind.

### 2.5 Backfill (Masterpasswort interaktiv)

```bash
cd "$KMH_APP_ROOT"
source "${KMH_VENV}/bin/activate"
python scripts/backfill_audit_known_contacts_encrypt.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE" --dry-run
python scripts/backfill_audit_known_contacts_encrypt.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE"
```

### 2.6 Verify (alle Zeilen)

```bash
python scripts/verify_audit_known_contacts_encrypt.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE" --require-full --sample 0
```

### 2.7 Manuell

Ordner-Audit → Konfiguration → Bekannte Kontakte; Ordner-Scan ohne `known_contacts_backfill_required`.

Optional danach Kontakt-Import und Schritte 2.5–2.6 wiederholen.

---

## 3) Phase B — f8 (Drop Klartext-Spalten)

Nur nach grünem Verify in Phase A.

### 3.1 Stoppen und Backup

```bash
kmh_stop_services

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" \
  -f "${PGBACKUP_DIR}/${PGDATABASE}-pre-f8-${STAMP}.dump"
ls -la "$PGBACKUP_DIR" | tail -3
```

### 3.2 Backfill + Verify (falls seit Phase A Import/Klartext)

```bash
cd "$KMH_APP_ROOT"
source "${KMH_VENV}/bin/activate"
python scripts/backfill_audit_known_contacts_encrypt.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE"
python scripts/verify_audit_known_contacts_encrypt.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE" --require-full --sample 0
```

### 3.3 Alembic f8

```bash
python scripts/kmh_expect_db.py --expect-db "$PGDATABASE"
alembic upgrade f8a9b0c1d2e3
alembic current
```

### 3.4 Start und Smoke

```bash
kmh_start_services
```

UI: Kontaktliste, Import, Ordner-Scan.

```bash
cd "$KMH_APP_ROOT"
bash scripts/pytest-audit-smoke.sh
```

---

## 4) Alternative: Neuaufbau statt Backfill (kleine Homelab-DB)

Wenn du **keine** Historie in `audit_known_contacts` brauchst (Daten kommen aus Gesendet):

1. Nach **f7** (Schritt 2.3): Kontakte leeren, z. B.  
   `sudo -u postgres psql -d mail_helper -c "DELETE FROM audit_known_contacts WHERE user_id = 1;"`  
   (`user_id` anpassen)
2. Schritt 2.4 → Kontakt-Import in der UI (eingeloggt, Service-Token aktiv)
3. Verify (2.6) → Phase B

Backfill-Skript entfällt; **f7 und f8** bleiben Pflicht.

---

## 5) Rollback

| Situation | Aktion |
|-----------|--------|
| Nach f7, Migration/Backfill fehlgeschlagen | Dienste stoppen; `dropdb`/`createdb` oder DB leeren; `pg_restore -d mail_helper …-pre-f7-….dump`; Code auf Stand vor Pull; Alembic manuell zurücksetzen |
| Nach f8 | Restore aus **pre-f8**-Dump; Code + Alembic-Revision manuell anpassen |

Beispiel Restore (Dienste gestoppt, Pfad anpassen):

```bash
sudo systemctl stop mail-helper mail-helper-celery-worker mail-helper-celery-beat
sudo -u postgres dropdb mail_helper
sudo -u postgres createdb -O postgres mail_helper
sudo -u postgres pg_restore -d mail_helper /var/backups/mail-helper/mail_helper-pre-f8-YYYYMMDDTHHMMSSZ.dump
```

---

Siehe `docs/audit/ADR-audit-known-contacts-encryption.md`.
