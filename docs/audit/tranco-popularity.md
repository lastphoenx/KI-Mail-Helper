# Tranco Popularität (Ordner-Audit)

## Zweck

**Kein Echtheits-Beweis** — nur Fehlalarm-Dämpfer für den Marken-Abgleich und später Nachahmer-Erkennung (Schicht 2 der Roadmap).

Regel in Code (`tranco_exempts_brand_mismatch`):

1. Tranco-SQLite geladen (Top **N**, Default `TRANCO_TOP_N=100000`)
2. Absender-Domain **nicht** Freemail / Versandplattform / Shared Hosting (`shared_mail_infrastructure.py`)
3. **Anzeigename passt zum Domain-Label** (min. 5 Zeichen, Wortgleichheit — z. B. Der Bund ↔ derbund.ch)
4. Mail-Beweise (Spam-Flag, Auth, Zufalls-Absender) werden **nicht** abgeschwächt

Beliebtheit allein reicht **nicht** (`PayPal` + `gmail.com` → kein Freifahrt).

## Liste — nicht im Repo

| | |
|--|--|
| Quelle | Default: `https://tranco-list.eu/top-1m.csv.zip` (daily ZIP, ~10 MB); optional `TRANCO_DOWNLOAD_URL` oder `TRANCO_DOWNLOAD_MODE=csv` für `/download/{LIST_ID}/1000000` |
| Listen-ID | ZIP-Modus: `daily_list_id` **gestern UTC** zuerst, bei Fehler **heute**; Download bei HTTP-Fehler optional CSV mit gestern; fest mit `TRANCO_LIST_ID` |
| Ablage | `data/tranco/tranco.db` oder `TRANCO_DB_PATH` |
| Rhythmus | Celery Beat wöchentlich (`update_tranco_popularity_list`, Worker muss Task kennen) |
| UI | POST startet Celery-Task (nur App-Admin), kein synchroner Download im Request |
| Tests | Mini-CSV + SQLite in pytest |

**Deploy:** Verzeichnis `data/tranco/` muss für User **mailhelper** schreibbar sein (`chown mailhelper:mailhelper`), sonst «unable to open database file».

## Lizenz / Zitat

Tranco kombiniert mehrere Quellen (u. a. Majestic CC BY 3.0, CrUX CC BY-SA 4.0, Cloudflare Radar **CC BY-NC 4.0**, Umbrella, Farsight). **Liste nicht ausliefern oder ins Git legen.** Bei kommerzieller Nutzung Bedingungen prüfen.

Zitat: Le Pochat et al., *Tranco: A Research-Oriented Top Sites Ranking Hardened Against Manipulation*, NDSS 2019, [doi:10.14722/ndss.2019.23386](https://doi.org/10.14722/ndss.2019.23386)

## Download-Sicherheit

- HTTPS, Hostname exakt `tranco-list.eu`, Redirects nur auf gleichen Host (`allow_redirects=False` pro Hop)
- ZIP-/CSV-Größenlimits beim Stream, Mindest-Zeilenzahl
- Overlap Top-10k zur Vorgänger-Liste ≥ 70 %, sonst alte DB behalten
- Atomares Ersetzen (`.tmp` → `.db`, `.bak`); Gunicorn/Worker: SQLite bei Dateiwechsel neu öffnen (mtime)

## Env

| Variable | Default |
|----------|---------|
| `TRANCO_LIST_ID` | leer → daily API |
| `TRANCO_TOP_N` | `100000` |
| `TRANCO_DATA_DIR` | `<repo>/data/tranco` |
| `TRANCO_DB_PATH` | override Pfad |
| `TRANCO_AUTO_UPDATE` | `true` |
| `TRANCO_DOWNLOAD_URL` | leer → `top-1m.csv.zip` |
| `TRANCO_DOWNLOAD_MODE` | `zip` (Alternativ: `csv` = grosser CSV-Stream) |
| `APP_ADMIN_USERNAMES` | leer → nur User **`id=1`** darf Tranco-Update starten (Login-Namen kommagetrennt) |

## App-Administrator

Tranco-Update (UI-Button und Celery Beat) erlaubt nur **App-Admins**: entweder **`APP_ADMIN_USERNAMES`** (Login-Namen, lowercase-Vergleich) oder — wenn unset — ausschließlich der Benutzer mit **`id=1`**.

## TRANCO_TOP_N messen

Default **100000** bewusst — nicht erhöhen ohne Daten:

```bash
python scripts/tranco_domain_coverage.py /path/to/top-1m.csv domains.txt
```

`domains.txt`: eine Domain pro Zeile (Markenliste oder Newsletter-Absender; Unterdomains werden auf die registrierbare Domain gekürzt, z. B. `news.twint.ch` → `twint.ch`). Ausgabe: Abdeckung pro Schwelle → dann `TRANCO_TOP_N` in `.env` setzen und Update ausführen.

Später (Roadmap Schicht 2): separate kleinere Grenze für Nachahmer-Erkennung (z. B. 20k–50k), DB bis max(exempt, impersonation) füllen.

## Auswertung (CT)

```bash
python scripts/tranco_rank_domains.py meine_scam_domains.txt
```

Messung vor Ausbau: Anteil Scam-Domains vs. sichere Absender in Top-10k / Top-N — Zahlen hier dokumentieren, wenn gemessen.

## UI

Ordner-Audit → Marken-Domains: Statuszeile + «Tranco aktualisieren» (`GET /api/audit-config/tranco-status`, `POST …/tranco-update` → 202 + Celery).

Siehe [scam-detection-layers.md](scam-detection-layers.md).
