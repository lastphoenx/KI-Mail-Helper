# Deploy: Bekannte Kontakte verschlüsseln (f7 → Verify → f8)

**Code:** `origin/main` ≥ `84a9750` (Skripte unter `scripts/deploy-known-contacts-*.sh`)

**Reihenfolge:** Probelauf (empfohlen) → Produktion Phase A → Phase B. **Kein f8**, bevor Verify grün ist.

| Mechanismus | Details |
|-------------|---------|
| `DATABASE_URL` | Alembic, Backfill, Verify (`migrations/env.py`, `src/helpers/database.py`) |
| `PGDATABASE` | nur `pg_dump` / `psql` |
| `--expect-db` / `kmh_expect_db.py` | `SELECT current_database()`, liest **keine** `.env` neu |
| Python | immer **`/opt/KI-Mail-Helper/venv/bin/python`** (in Skripten: `KMH_PYTHON`) |

**Auf dem CT:** Repo-Skripte sind selbstständig (`set -euo pipefail` + `source deploy-known-contacts-lib.sh`). Kein `set -e` in die interaktive Shell kleben.

---

## Empfohlener Ablauf (Server)

### 0) Code holen (einmal)

```bash
cd /opt/KI-Mail-Helper
git pull origin main
```

### 1) Probelauf (empfohlich, optional)

Dienste laufen weiter. Sicherheitsnetz für Prod bleibt der **pre-f7-`pg_dump`** in Phase A.

```bash
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-drill.sh
```

Auf der Drill-DB Phase A (Neuaufbau oder Backfill) + Phase B testen — jeweils `--expect-db mail_helper_contacts_encrypt_drill` bzw. `export PGDATABASE=mail_helper_contacts_encrypt_drill` vor den Skripten, wenn du die Prod-Skripte gegen die Kopie fährst.

Drill beenden:

```bash
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-drill-end.sh
```

### 2) Phase A — Produktion

```bash
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-phase-a-f7.sh
```

**Homelab (empfohlen) — Neuaufbau statt Backfill** (Daten kommen aus Gesendet):

```bash
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-phase-a-neuaufbau.sh
# → UI: Import aus Gesendet (eingeloggt, DEK/Service-Token)
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-phase-a-verify.sh
```

**Alternative — Backfill** (bestehende Klartext-Zeilen behalten):

```bash
cd /opt/KI-Mail-Helper
source venv/bin/activate
/opt/KI-Mail-Helper/venv/bin/python scripts/backfill_audit_known_contacts_encrypt.py \
  --user-id 1 --expect-db mail_helper --dry-run
/opt/KI-Mail-Helper/venv/bin/python scripts/backfill_audit_known_contacts_encrypt.py \
  --user-id 1 --expect-db mail_helper
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-phase-a-verify.sh
```

(`KMH_USER_ID` / `PGDATABASE` per `export` in `deploy-known-contacts-lib.sh` anpassbar.)

### 3) Phase B — f8

```bash
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-phase-b.sh
```

Falls Verify in Phase B scheitert (noch Klartext): Backfill manuell, dann Phase B erneut.

---

## Skripte (Referenz)

| Skript | Inhalt |
|--------|--------|
| `scripts/deploy-known-contacts-lib.sh` | Variablen, `KMH_PYTHON`, `kmh_*` — wird von allen anderen gesourct |
| `scripts/deploy-known-contacts-drill.sh` | pg_dump, dropdb/createdb, pg_restore, Drill-`DATABASE_URL` |
| `scripts/deploy-known-contacts-drill-end.sh` | Prod-`DATABASE_URL` wiederherstellen |
| `scripts/deploy-known-contacts-phase-a-f7.sh` | Stop, pre-f7 dump, pull, `alembic upgrade f7` |
| `scripts/deploy-known-contacts-phase-a-neuaufbau.sh` | DELETE Kontakte, Dienste starten |
| `scripts/deploy-known-contacts-phase-a-verify.sh` | `verify … --require-full` |
| `scripts/deploy-known-contacts-phase-b.sh` | pre-f8 dump, verify, `alembic upgrade f8`, smoke |

Anpassungen (User-ID, Pfade): `export KMH_USER_ID=1` usw. **vor** dem Skriptaufruf, oder `deploy-known-contacts-lib.sh` editieren.

---

## Manuell (ohne Wrapper-Skripte)

Nur wenn du lieber in der Shell arbeitest: **zuerst** `source /opt/KI-Mail-Helper/scripts/deploy-known-contacts-lib.sh` (definiert `kmh_stop_services`, `KMH_PYTHON`, …). Alle Python-Aufrufe mit `"$KMH_PYTHON"`, nicht `python3` vom System.

### Probelauf

```bash
source /opt/KI-Mail-Helper/scripts/deploy-known-contacts-lib.sh
sudo mkdir -p "$PGBACKUP_DIR"
kmh_load_prod_database_url

export PGDATABASE_TEST="${PGDATABASE}_contacts_encrypt_drill"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

sudo -u postgres pg_dump -Fc -d "$PGDATABASE" \
  -f "${PGBACKUP_DIR}/${PGDATABASE}-drill-source-${STAMP}.dump"
sudo -u postgres dropdb --if-exists "$PGDATABASE_TEST"
sudo -u postgres createdb -O postgres "$PGDATABASE_TEST"
sudo -u postgres pg_restore -d "$PGDATABASE_TEST" \
  "${PGBACKUP_DIR}/${PGDATABASE}-drill-source-${STAMP}.dump"

export DATABASE_URL="$(kmh_database_url_for_db "$PGDATABASE_TEST")"
export PGDATABASE="$PGDATABASE_TEST"
kmh_expect_db "$PGDATABASE_TEST"
```

### Phase A Neuaufbau (Kernbefehle)

```bash
source /opt/KI-Mail-Helper/scripts/deploy-known-contacts-lib.sh
kmh_stop_services
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" \
  -f "${PGBACKUP_DIR}/${PGDATABASE}-pre-f7-${STAMP}.dump"
kmh_pull_code
cd "$KMH_APP_ROOT" && kmh_expect_db "$PGDATABASE" && alembic upgrade f7a8b9c0d1e2

sudo -u postgres psql -d "$PGDATABASE" -v ON_ERROR_STOP=1 \
  -c "DELETE FROM audit_known_contacts WHERE user_id = ${KMH_USER_ID};"
kmh_start_services
# UI Import → dann:
cd "$KMH_APP_ROOT" && kmh_activate_venv
"$KMH_PYTHON" scripts/verify_audit_known_contacts_encrypt.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE" --require-full --sample 0
```

---

## Rollback

| Situation | Aktion |
|-----------|--------|
| Nach f7, fehlgeschlagen | Dienste stoppen; `pg_restore` aus `…-pre-f7-….dump` |
| Nach f8 | `pg_restore` aus `…-pre-f8-….dump` |

```bash
sudo systemctl stop mail-helper mail-helper-celery-worker mail-helper-celery-beat
sudo -u postgres dropdb mail_helper
sudo -u postgres createdb -O postgres mail_helper
sudo -u postgres pg_restore -d mail_helper /var/backups/mail-helper/mail_helper-pre-f8-YYYYMMDDTHHMMSSZ.dump
```

---

Siehe `docs/audit/ADR-audit-known-contacts-encryption.md`.
