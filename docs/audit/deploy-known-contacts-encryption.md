# Deploy: Bekannte Kontakte verschlüsseln (f7 → Backfill → f8)

**Reihenfolge:** Probelauf auf DB-Kopie → dann Produktion. **Kein f8**, bevor Backfill und Verify grün sind.

Code-Stand: **`origin/main`** (≥ `229737e`) — Passwort-Backfill, Phase-2-Model; nach f7 sind Klartext-Spalten in der DB noch vorhanden, bis **f8** läuft.

---

## Variablen (am Anfang anpassen)

```bash
set -euo pipefail

# App (Beispiel Homelab — Werte vor dem Kopieren prüfen)
export KMH_APP_ROOT=/opt/KI-Mail-Helper
export KMH_VENV="${KMH_APP_ROOT}/venv"
export KMH_USER_ID=1

# PostgreSQL
export PGDATABASE=mail_helper
export PGBACKUP_DIR=/var/backups/mail-helper

# systemd — alle Worker stoppen, sonst läuft die App während der Migration weiter
export KMH_SVC_WEB=mail-helper.service
export KMH_SVC_CELERY_WORKER=mail-helper-celery-worker.service
export KMH_SVC_CELERY_BEAT=mail-helper-celery-beat.service
```

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

Gleiche Befehle wie unten, aber gegen eine **Kopie** der Datenbank.

```bash
set -euo pipefail
# Variablen wie oben; zusätzlich:
export PGDATABASE_TEST="${PGDATABASE}_contacts_encrypt_drill"
export PGPASSFILE=   # ggf. leeren, wenn lokal peer-auth

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
sudo mkdir -p "$PGBACKUP_DIR"

# 1) Sicherung Produktion
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" -f "$PGBACKUP_DIR/${PGDATABASE}-drill-source-${STAMP}.dump"

# 2) Test-DB anlegen und einspielen
sudo -u postgres dropdb --if-exists "$PGDATABASE_TEST"
sudo -u postgres createdb -O postgres "$PGDATABASE_TEST"
sudo -u postgres pg_restore -d "$PGDATABASE_TEST" "$PGBACKUP_DIR/${PGDATABASE}-drill-source-${STAMP}.dump"

# 3) Drill mit Test-DB (App-Dienste auf dem CT weiterhin stoppen für echten Drill,
#    oder Drill auf separatem Host mit gleichem Code-Stand)
export PGDATABASE="$PGDATABASE_TEST"
# → Phase A + Phase B unten vollständig durchspielen
# → Kontaktliste UI, Import, Ordner-Scan gegen Test-Instanz prüfen

# 4) Produktion: PGDATABASE wieder auf mail_helper setzen
export PGDATABASE=mail_helper
```

Nach erfolgreichem Drill: **neues** `pg_dump` der Produktion, dann Phase A auf dem echten `PGDATABASE`.

---

## Phase A — f7 + Backfill + Verify (Code bereits `main`)

1. **Dienste stoppen:**

```bash
kmh_stop_services
```

2. **Backup:**

```bash
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
alembic upgrade f7a8b9c0d1e2
alembic current
```

5. **Dienste starten** (Backfill braucht nur DB + venv; UI optional für manuelle Checks):

```bash
kmh_start_services
```

6. **Backfill** (Masterpasswort interaktiv — DEK wird wie beim Login abgeleitet):

```bash
cd "$KMH_APP_ROOT"
source "$KMH_VENV/bin/activate"
python scripts/backfill_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID" --dry-run
python scripts/backfill_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID"
```

7. **Verify (alle Zeilen):**

```bash
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
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" -f "$PGBACKUP_DIR/${PGDATABASE}-pre-f8-${STAMP}.dump"
```

3. **Backfill + Verify** (falls seit Phase A noch Import/Übergangs-Klartext in der DB):

```bash
cd "$KMH_APP_ROOT"
source "$KMH_VENV/bin/activate"
python scripts/backfill_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID"
python scripts/verify_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID" --require-full --sample 0
```

4. **Alembic f8** (bricht ab, wenn noch Zeilen ohne `encrypted_email` / HMAC):

```bash
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
