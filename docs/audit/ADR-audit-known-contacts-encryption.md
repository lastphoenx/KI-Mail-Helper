# ADR: Verschlüsselung von `audit_known_contacts` (at-rest wie Mails)

**Status:** Accepted (Umsetzung ausstehend)  
**Datum:** 2026-10-06  
**Kontext:** Ordner-Audit, Bekannte Kontakte, Git-Hooks / AGENTS (kein Kontospezifisches im Repo)

## Problem

`audit_known_contacts` speichert `email_normalized` und `display_name` **im Klartext** (`src/02_models.py`, Klasse `AuditKnownContact`). Jede DB-Sicherung und jeder SQL-Abzug enthält dieselben PII. Das widerspricht dem Modell bei **Mails** und **Zugangsdaten** (Felder `encrypted_*`, Entschlüsselung mit Benutzer-DEK).

Eine **zusätzliche Verschlüsselung nur der Backups** wäre doppelte Arbeit und löst nicht das Grundproblem (laufende DB, Logs, Replikate). **Schutz an der Quelle:** beim Schreiben verschlüsseln — dann reicht eine normale Sicherung.

## Entscheidung

1. **E-Mail und Anzeigename** werden wie Mail-Metadaten mit dem **bestehenden Benutzer-DEK** (`EncryptionManager.encrypt_data` / `encrypt_email_address`, `src/08_encryption.py`) persistiert.
2. **Abgleich ohne Klartext in der DB:** zusätzliche Spalte **`email_lookup_hmac`** (Index, Unique mit `user_id` + `account_id`). Wert = **HMAC-SHA256** über normalisierte E-Mail, Schlüsselmaterial **aus dem DEK abgeleitet** (z. B. HKDF/HMAC-Key pro User/Account — **kein** neues `CONTACT_PII_KEY` in `.env`).
3. **Kein separater Backup-Verschlüsselungs-Track** als Lösung — gestrichen.
4. **Laufzeit:** UI-API und Audit-Scan **entschlüsseln** mit Session-DEK bzw. Service-Token-DEK (gleiches Muster wie Menü «Liste», Mail-Listen, Ordner-Audit-IMAP).

## Begründung DEK / Service-Token (Code-Beleg)

| Pfad | DEK verfügbar? |
|------|----------------|
| Celery **Kontakt-Import** | Ja — `import_audit_known_contacts_task` ruft `get_dek_from_service_token(service_token_id, session)` auf, danach IMAP (`src/tasks/audit_contacts_tasks.py`). |
| UI **Import auslösen** | Ja — `ServiceTokenManager.create_token(..., master_key=flask_session["master_key"])` (`audit_config.py`, Route Import). |
| **Ordner-Audit-Scan** | Ja — gleiches Muster in `folder_audit_tasks.py` (`get_dek_from_service_token`). |

Service-Token: TTL typisch **1–7 Tage** (konfigurierbar), Zeile wird beim **Logout** gelöscht. Der DEK in `service_tokens.encrypted_dek` ist **nicht** Klartext in der DB, sondern mit **app-spezifischem Key aus `SECRET_KEY`** verschlüsselt (`src/helpers/service_token_storage.py`, Präfix `stenc1:`). Siehe `docs/SECURITY.md`.

Ein neuer Umgebungs-Schlüssel für Kontakte ist **nicht nötig**, solange HMAC-Ableitung deterministisch aus dem DEK erfolgt (pro User; bei DEK-Rotation Migration der HMACs + Re-Encrypt der Felder).

**Hinweis:** `EncryptionManager.hash_email_address()` (SHA256 ohne User-Secret) ist für diesen Use-Case **nicht** ausreichend — Lookup-HMAC muss **keyed** sein.

## Ohne gültigen Schlüssel: kein stilles Weiterlaufen

Wenn **kein gültiges Service-Token** (abgelaufen, gelöscht beim Logout, nie angelegt) und **keine Session mit DEK** vorliegt, können **Kontakt-Import**, **Migration** und **Ordner-Audit-Scan** verschlüsselte Kontakte **nicht** entschlüsseln.

**Pflicht bei Implementierung:**

- Scan/Import **abbrechen** oder Task mit **klarem Fehler** (`token`, `master_key_required`, o. ä.) — **nicht** mit leerem `KnownContactContext` weiterlaufen (sonst Fehlalarme bei Familie/Freunden).
- UI: Hinweis «Bitte einloggen / Hintergrund-Token aktivieren», nicht leere Liste ohne Erklärung.

Gilt analog für die **Datenmigration**: Backfill braucht den DEK — nur während **eingeloggtem Nutzer** (Session) oder **aktivem Service-Token** (Batch-Job).

## Masterpasswort-Verlust

Wie bei **Mails:** Ohne DEK (Passwort vergessen, Recovery Codes nicht nutzbar) sind verschlüsselte Kontaktdaten **unwiederbringlich**. Recovery-Codes stellen den User-Zugang wieder her, **nicht** automatisch alle offline gespeicherten Klartext-Kopien. Der ADR nimmt dasselbe Risikomodell wie für Mail-Inhalte an.

## Ziel-Schema (skizze)

| Spalte | Zweck |
|--------|--------|
| `email_lookup_hmac` | Eindeutiger Lookup, kein Klartext |
| `encrypted_email` | Anzeige / Export in UI |
| `encrypted_display_name` | Anzeige (nullable) |
| ~~`email_normalized`~~ / ~~`display_name`~~ | Nach Migration entfernen |

`_upsert_contact` (`audit_contact_import.py`) und alle Lesepfade anpassen.

## Laufzeit-Verhalten

### UI (Konfiguration → Bekannte Kontakte)

- GET `/api/audit-config/known-contacts`: Zeilen laden, **im App-Layer entschlüsseln** (`master_key` aus Session), JSON an Frontend — wie andere Listen mit `encrypted_*`.
- **Sortieren/Suchen:** nicht auf Klartext-Spalten in SQL; entschlüsselte Werte im Prozess sortieren/filtern (Pagination ggf. anpassen — heute `order_by(display_name, email_normalized)` in SQL).
- Import-Button: unverändert Service-Token; Worker schreibt nur noch verschlüsselt + HMAC.

### Ordner-Audit / Scam

- `load_known_contact_context(..., master_key)` (Signatur erweitern): Kontakte entschlüsseln, `trusted_emails` / `name_keys` / `name_domains` wie heute im Speicher aufbauen.
- Aufrufer mit DEK: Ordner-Audit-Task (Service-Token), synchrone Pfade nur mit Session-DEK.
- **VIP/Trusted-Domains** bleiben vorerst Klartext (separate Sensibilität; nicht Teil dieses ADR).

## Migration

1. **Backup** der DB vor Migration; dokumentierter Rollback (Klartext-Spalten erst droppen, wenn Backfill verifiziert).
2. Alembic: neue Spalten; Backfill nur mit verfügbarem DEK (Session oder Service-Token).
3. Pro Zeile: `normalize_sender_email` → HMAC → encrypt email + display_name; Duplikate vermeiden (Unique auf HMAC).
4. Verifikation: keine Klartext-Adressen/Namen mehr in Tabelle, Logs, Fehlermeldungen; dann Klartext-Spalten droppen.

## Implementierungs-Checkliste (Abnahme)

| Kriterium | Erwartung |
|-----------|-----------|
| Migration | Bestehende Zeilen vollständig; Backup + Rollback; keine Duplikat-Lücken (gleiche Adresse, eine Normalisierung) |
| Klartext weg | Spalten `email_normalized` / `display_name` entfernt; keine PII in Logs/Errors |
| HMAC | Identisch zu bisherigem `normalize_sender_email` |
| Ohne DEK/Token | Scan/Import **Fehler**, nicht leerer Kontext |
| UI | Liste mit Entschlüsselung, Suche, Sortierung |
| Tests | Roundtrip, Import mit Mock-DEK, Scan-Kontext ohne Klartext-Spalten; nur `.example`-Adressen |

## Aufwand & Risiko (kurz)

| | |
|--|--|
| **Aufwand** | ~4–6 Tage (Schema, Import, Context-Loader, API/UI, Migration, Tests) |
| **Risiko hoch** | DEK-Rotation / Passwort-Reset ohne Re-Migration; Sort/Pagination-Regression UI |
| **Risiko mittel** | Performance Kontaktliste (Entschlüsselung N Zeilen) — gleiche Klasse wie «Liste» |
| **Risiko niedrig** | Audit-Scan (Context einmal pro Lauf entschlüsseln) |

## Nicht im Scope

- Verschlüsselung von `audit_trusted_domains`, `audit_vip_senders`, Marken-JSON, `audit_own_domains` (eigene ADR möglich).
- Git-Hooks / `kmh-denylist` (Commit-Schutz, nicht DB).

## Offene Implementierungsdetails

- Exakte HMAC-Normalisierung muss **identisch** zu `normalize_sender_email` bleiben.
- Eindeutigkeit: Unique `(user_id, account_id, email_lookup_hmac)`.
- Legacy-Zeilen in `service_tokens.encrypted_dek` ohne `stenc1:`-Präfix: `decrypt_service_token_dek` liefert Pass-through (Altlasten) — bei Kontakt-Migration nicht relevant, aber Token-Pfad beachten.
