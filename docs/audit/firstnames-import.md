# Vornamenliste (Ordner-Audit)

Globale Tabelle `audit_firstnames` — für Personenerkennung (E9, N1). **Pro Instanz**, nicht pro Mail-Account. Kein Import-UI; Zähler in **Ordner-Audit → Konfiguration → Bekannte Kontakte** (API) und CLI.

## Quelle (Standard)

[BFS opendata.swiss](https://opendata.swiss) — weibliche und männliche Vornamen der Bevölkerung nach Jahrgang, Schweiz 2025:

- [36752506](https://dam-api.bfs.admin.ch/hub/api/dam/assets/36752506/master) (weiblich)
- [36752513](https://dam-api.bfs.admin.ch/hub/api/dam/assets/36752513/master) (männlich)

Lizenz: Open use, Quelle angeben.

Fallback Kanton Zug: `python3 scripts/import_firstnames.py --legacy-zg`

## Voraussetzungen

- `alembic upgrade head` (Tabelle `audit_firstnames`)
- `.env` mit `DATABASE_URL`
- venv aktiv

## Befehle

```bash
cd /opt/KI-Mail-Helper
source venv/bin/activate

python3 scripts/import_firstnames.py --test-api
python3 scripts/import_firstnames.py --dry-run
python3 scripts/import_firstnames.py              # BFS → DB
python3 scripts/import_firstnames.py --count-db   # nur Anzahl in DB
```

Nach Import: `Inserted N rows` / `audit_firstnames: N rows inserted`, plus `NOTICE-firstnames.txt`.

## Smoke

```bash
bash scripts/test-opendata-firstnames.sh
```

Erwartung **unique name_key** nach BFS-Import typisch **ca. 60 000–66 000** (weiblich + männlich, inkl. ü/ue-Varianten); exakte Zahl steht im Import-Log, per `--count-db`, und in **Ordner-Audit → Konfiguration** im Kasten «Vornamen-Referenzliste (Server)».
