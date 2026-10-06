# Deploy: Bekannte Kontakte verschlüsseln (f7 → Backfill → f8)

**Reihenfolge:** Probelauf auf DB-Kopie → dann Produktion. **Kein f8**, bevor Backfill und Verify grün sind.

Alembic, Backfill und Verify nutzen **`DATABASE_URL`** aus der Shell-Umgebung (`migrations/env.py`, `src/helpers/database.py`). `PGDATABASE` nur für `pg_dump` / `psql`.

**Ziel-DB absichern:** `--expect-db NAME` (Backfill/Verify) bzw. `python scripts/kmh_expect_db.py --expect-db NAME` vor Alembic. Prüfung per `SELECT current_database()` — **ohne** `.env` neu einzulesen.

---

## Variablen

```bash
set -euo pipefail

export KMH_APP_ROOT=/opt/KI-Mail-Helper
export KMH_VENV="${KMH_APP_ROOT}/venv"
export KMH_USER_ID=1
export PGDATABASE=mail_helper
export PGBACKUP_DIR=/var/backups/mail-helper

export KMH_SVC_WEB=mail-helper.service
export KMH_SVC_CELERY_WORKER=mail-helper-celery-worker.service
export KMH_SVC_CELERY_BEAT=mail-helper-celery-beat.service
```

### Dienste stoppen / starten (nur Produktion Phase A/B)

```bash
kmh_stop_services() {
  sudo systemctl stop "$KMH_SVC_CELERY_BEAT" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_WEB"
  sleep 2
  for u in "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"; do
    if systemctl is-active --quiet "$u"; then
      echo "FEHLER: $u läuft noch." >&2
      return 1
    fi
  done
}

kmh_start_services() {
  sudo systemctl start "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"
  sudo systemctl is-active "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"
}
```

`DATABASE_URL` für Operator-Schritte: in der **gleichen Shell** setzen (Drill: Kopie; Produktion: wie in `.env`, z. B. einmal `export DATABASE_URL=…` — **nicht** per Skript aus `.env` nachladen, das überschreibt einen Drill-Export). Alembic `env.py` lädt `.env`, überschreibt aber eine **bereits exportierte** `DATABASE_URL` nicht (`load_dotenv` ohne override).

---

## Probelauf (Pflicht)

Kopie anlegen, dann `DATABASE_URL` auf die Kopie setzen. **Dienste nicht stoppen.**

```bash
export PGDATABASE_TEST="${PGDATABASE}_contacts_encrypt_drill"
# … pg_dump Prod, createdb, pg_restore auf PGDATABASE_TEST (wie bisher) …

# Gleiche URL wie Prod, nur anderer Datenbankname (Beispiel — Werte anpassen):
export DATABASE_URL='postgresql://USER:PASS@localhost:5432/mail_helper_contacts_encrypt_drill'
export PGDATABASE="$PGDATABASE_TEST"

# Phase A + B unten mit --expect-db "$PGDATABASE_TEST" / kmh_expect_db.py
```

Drill Ende: `unset DATABASE_URL` und für Produktion wieder die Prod-URL exportieren.

---

## Phase A — f7 + Backfill + Verify

1. `kmh_stop_services`
2. `pg_dump` → `$PGBACKUP_DIR/${PGDATABASE}-pre-f7-….dump`
3. `git pull`, `pip install -r requirements.txt`
4. Alembic f7:

```bash
cd "$KMH_APP_ROOT" && source "$KMH_VENV/bin/activate"
python scripts/kmh_expect_db.py --expect-db "$PGDATABASE"
alembic upgrade f7a8b9c0d1e2
```

5. `kmh_start_services` — **kein Kontakt-Import**, bis Backfill + Verify grün (Duplikat-Zeilen vermeidet der Backfill, Import ist trotzdem unnötiges Risiko).

6. Backfill:

```bash
python scripts/backfill_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE" --dry-run
python scripts/backfill_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE"
```

7. Verify:

```bash
python scripts/verify_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE" --require-full --sample 0
```

8. Manuell: Kontaktliste, Ordner-Scan (kein `known_contacts_backfill_required`).

---

## Phase B — f8

1. `kmh_stop_services`
2. `pg_dump` pre-f8
3. Backfill + Verify mit `--expect-db "$PGDATABASE"` (falls nötig)
4. `python scripts/kmh_expect_db.py --expect-db "$PGDATABASE"` → `alembic upgrade f8a9b0c1d2e3`
5. `kmh_start_services`, Smoke-Tests

---

## Rollback

| Situation | Aktion |
|-----------|--------|
| Nach f7, Backfill fehlgeschlagen | Restore pre-f7-Dump |
| Nach f8 | Restore pre-f8-Dump |

Siehe `docs/audit/ADR-audit-known-contacts-encryption.md`.
