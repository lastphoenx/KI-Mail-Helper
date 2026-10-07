# Deploy: Bekannte Kontakte verschlüsseln (f7 → Verify → f8)

**Code:** `origin/main` (Skripte `scripts/deploy-known-contacts-*.sh`)

**Sicherheitsnetz:** `pg_dump` vor f7 (in `deploy-known-contacts-phase-a-f7.sh`, **während die Dienste noch laufen**). Backup-Verzeichnis: `sudo install -d -o postgres -g postgres -m 750 /var/backups/mail-helper` (in Skripten: `kmh_ensure_backup_dir`).

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

Nach `phase-a-f7.sh` sind die Dienste **gestoppt** (bis `neuaufbau.sh` oder manuell `kmh_start_services`). **Ohne** DELETE:

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
| `deploy-known-contacts-phase-a-f7.sh` | `pull` → `expect-db` → pre-f7 dump (Dienste laufen) → Stop → `alembic f7` |
| `deploy-known-contacts-phase-a-neuaufbau.sh` | DELETE Kontakte → Dienste starten |
| `deploy-known-contacts-phase-a-verify.sh` | `verify --require-full` |
| `deploy-known-contacts-phase-b.sh` | verify → pre-f8 dump (Dienste laufen) → Stop → `alembic f8` → Start → smoke |

`export KMH_USER_ID=1` / `PGDATABASE=mail_helper` vor Aufruf möglich.

**Neuaufbau:** `clear_audit_known_contacts_user.py` löscht Kontakte **und** setzt `mail_accounts.audit_contacts_import_state` zurück (sonst Import 0 Mails).

**Verify (`--require-full`):** Entschlüsselung/HMAC pro Zeile; `--expect-min 1` in `phase-a-verify.sh` (Override: `KMH_EXPECT_MIN_CONTACTS`). Ohne `--expect-min` und `total=0` → Warnung, Exit 1.

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

**Skript-Test (CT/WSL, vor Push):** `bash scripts/test-deploy-known-contacts-scripts.sh`

---

`docs/audit/ADR-audit-known-contacts-encryption.md`
