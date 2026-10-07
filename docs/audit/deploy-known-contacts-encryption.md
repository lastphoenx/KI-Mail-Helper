# Deploy: Bekannte Kontakte verschlüsseln (f7 → Verify → f8)

**Code:** `origin/main` (Skripte `scripts/deploy-known-contacts-*.sh`)

**Sicherheitsnetz:** `pg_dump` vor f7 (in `deploy-known-contacts-phase-a-f7.sh`). Kein separater DB-Drill — eine Drill-`DATABASE_URL` überlebt nicht den Skript-Prozess; Phase-Skripte laden Prod aus `.env`.

| Mechanismus | Details |
|-------------|---------|
| `DATABASE_URL` | Alembic, Backfill, Verify |
| `PGDATABASE` | `pg_dump` / `psql` |
| `--expect-db` | `kmh_expect_db.py` / Backfill / Verify → `current_database()` |

Python auf dem CT: **`/opt/KI-Mail-Helper/venv/bin/python`** (in Skripten `KMH_PYTHON`).

---

## Ablauf Produktion (empfohlen: Neuaufbau)

```bash
cd /opt/KI-Mail-Helper && git pull origin main

bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-phase-a-f7.sh
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-phase-a-neuaufbau.sh
```

**UI:** Ordner-Audit → Bekannte Kontakte → Import aus Gesendet (eingeloggt, DEK/Service-Token).

```bash
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-phase-a-verify.sh
bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-phase-b.sh
```

### Alternative: Backfill (Klartext-Zeilen behalten)

Nach `phase-a-f7.sh`, **ohne** DELETE, Dienste laufen lassen:

```bash
cd /opt/KI-Mail-Helper && source venv/bin/activate
venv/bin/python scripts/backfill_audit_known_contacts_encrypt.py \
  --user-id 1 --expect-db mail_helper --dry-run
venv/bin/python scripts/backfill_audit_known_contacts_encrypt.py \
  --user-id 1 --expect-db mail_helper
bash scripts/deploy-known-contacts-phase-a-verify.sh
```

Kein Kontakt-Import vor Verify (sonst Duplikat-Zeilen — Backfill führt zusammen, trotzdem unnötig).

---

## Skripte

| Skript | Aktion |
|--------|--------|
| `deploy-known-contacts-lib.sh` | Variablen, `KMH_PYTHON`, `kmh_*` (gesourct) |
| `deploy-known-contacts-phase-a-f7.sh` | `expect-db` → Stop → pre-f7 dump → pull → `alembic f7` |
| `deploy-known-contacts-phase-a-neuaufbau.sh` | DELETE Kontakte → Dienste starten |
| `deploy-known-contacts-phase-a-verify.sh` | `verify --require-full` |
| `deploy-known-contacts-phase-b.sh` | `expect-db` + verify → Stop → pre-f8 dump → `alembic f8` → Start → smoke |

`export KMH_USER_ID=1` / `PGDATABASE=mail_helper` vor Aufruf möglich.

**Verify (`--require-full`):** Jede Zeile mit `encrypted_email` + HMAC muss sich entschlüsseln lassen. Klartext nur optional (Backfill-Übergang). Fehler: `plain_only`, Klartext-Name ohne `encrypted_display_name`, HMAC/Decrypt mismatch. `total=0` ist ok.

---

## Rollback

| Situation | Aktion |
|-----------|--------|
| Nach f7 | Restore `…-pre-f7-….dump` |
| Nach f8 | Restore `…-pre-f8-….dump` |

```bash
sudo systemctl stop mail-helper mail-helper-celery-worker mail-helper-celery-beat
sudo -u postgres dropdb mail_helper
sudo -u postgres createdb -O postgres mail_helper
sudo -u postgres pg_restore -d mail_helper /var/backups/mail-helper/mail_helper-pre-f8-….dump
sudo systemctl start mail-helper mail-helper-celery-worker mail-helper-celery-beat
```

---

`docs/audit/ADR-audit-known-contacts-encryption.md`
