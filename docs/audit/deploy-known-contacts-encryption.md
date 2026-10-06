# Deploy: Bekannte Kontakte verschlüsseln (f7 → Backfill → f8)

Schrittfolge für **CT** (Pfade anpassen). **Kein f8**, bevor Backfill und Verify grün sind.

Variablen setzen:

```bash
export KMH_APP_ROOT=/opt/kmh
export KMH_VENV=$KMH_APP_ROOT/venv
export KMH_USER_ID=1
export PGDATABASE=kmh
export PGBACKUP_DIR=/var/backups/kmh
```

---

## Phase A — Code bis f7 (ohne Phase-2-Model)

1. **Dienste stoppen** (Celery + Web — Namen laut eurem systemd):

```bash
sudo systemctl stop kmh-celery kmh-web
```

2. **Backup (Pflicht vor jeder Migration):**

```bash
sudo mkdir -p "$PGBACKUP_DIR"
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" -f "$PGBACKUP_DIR/kmh-pre-f7-$(date -u +%Y%m%dT%H%M%SZ).dump"
ls -la "$PGBACKUP_DIR" | tail -3
```

3. **Code** (Stand mit f7-Migration, **noch** Klartext-Spalten im Model — z. B. `394916c` auf `origin/main`):

```bash
cd "$KMH_APP_ROOT"
git fetch origin
git checkout 394916c
source "$KMH_VENV/bin/activate"
pip install -r requirements.txt
```

4. **Alembic nur bis f7:**

```bash
cd "$KMH_APP_ROOT"
source "$KMH_VENV/bin/activate"
alembic upgrade f7a8b9c0d1e2
alembic current
```

5. **Dienste starten** (für UI/Import optional; Backfill geht auch bei gestopptem Web, braucht DB):

```bash
sudo systemctl start kmh-web kmh-celery
```

6. **Backfill** (Masterpasswort interaktiv — DEK wird intern abgeleitet, nichts exportieren):

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

8. **Manuell:** Ordner-Audit-Scan + Kontaktliste in UI; Verhalten wie vor Migration.

9. **Optional:** Kontakt-Import erneut (Service-Token über UI), dann Backfill + Verify **wiederholen** (neue Klartext-Zeilen aus Übergangs-Import).

---

## Phase B — f8 + Phase-2-Code (gemeinsam)

**Erst nach grünem Verify in Phase A.**

1. **Dienste stoppen:**

```bash
sudo systemctl stop kmh-celery kmh-web
```

2. **Backup vor Drop:**

```bash
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" -f "$PGBACKUP_DIR/kmh-pre-f8-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

3. **Letzten Backfill** (falls seit Phase A Import lief — noch auf **394916c** oder Phase-A-Stand):

```bash
cd "$KMH_APP_ROOT"
source "$KMH_VENV/bin/activate"
python scripts/backfill_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID"
python scripts/verify_audit_known_contacts_encrypt.py --user-id "$KMH_USER_ID" --require-full --sample 0
```

4. **Phase-2-Code pullen** (Model ohne Klartext-Spalten + f8-Migration im Repo):

```bash
cd "$KMH_APP_ROOT"
git fetch origin
git checkout main
git pull origin main
source "$KMH_VENV/bin/activate"
pip install -r requirements.txt
```

5. **Alembic f8** (bricht ab, wenn noch unverschlüsselte Zeilen):

```bash
alembic upgrade f8a9b0c1d2e3
alembic current
```

6. **Dienste starten:**

```bash
sudo systemctl start kmh-web kmh-celery
```

7. **Smoke:** Kontaktliste (eingeloggt), Kontakt-Import, Ordner-Scan.

---

## Rollback

| Situation | Aktion |
|-----------|--------|
| Nach f7, Backfill fehlgeschlagen | Restore pg_dump pre-f7; `alembic downgrade f7a8b9c0d1e2` nur nach Doku |
| Nach f8 | Restore pg_dump **pre-f8**; Code auf Phase-A-Commit; `alembic downgrade` Kette manuell prüfen |

Verify/Backfill-Skripte funktionieren nur, solange Klartext-Spalten in der **DB** existieren (vor f8).

Siehe auch `docs/audit/ADR-audit-known-contacts-encryption.md`.
