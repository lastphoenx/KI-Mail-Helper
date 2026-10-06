# Ordner-Audit — Scam-Erkennung & Marken-Domains

Stand: App-Repo **`KI-Mail-Helper-Dev`**, Route `/folder-audit`.

## Was im Scan passiert

Jede Mail wird u. a. nach **SAFE / REVIEW / IMPORTANT / SUSPICION (Verdacht) / SCAM** eingestuft. Scam-relevant sind zwei Ebenen:

| Ebene | Name | Wann |
|-------|------|------|
| **Layer 1** | Regeln + Domains | Immer (Header, Transport, Marken-Abgleich, optional DBL/RDAP in Grauzone) |
| **Layer 2** | Identitäts-KI | Nur **Grauzone** (Regel-Score zwischen Schwellwerten), budgetiert pro Scan |

Schwellwerte: `.env` `AUDIT_SCAM_LAYER1_AUTO` (sofort SCAM), `AUDIT_SCAM_LAYER1_LLM_MIN` (LLM-Kandidat). Details CT: `doku/.../ki-mail-helper-konfiguration.md` §2.

### Erkenntnis aus Betrieb (Homelab)

Viele **Wegwerf-Scam-Domains** (kurzlebig, zufällige Namen) stehen **nicht** in der Spamhaus-DBL (`dig +short {domain}.dbl.spamhaus.org` → leer). DBL bleibt ein **Zusatzsignal** (Phishing-Infrastruktur), nicht der Hauptfilter.

**Wirksamer für Marken-Phishing:** Absender-**Anzeigename** vs. **echte Absender-Domain** (Marken-Tabelle). Optional später: **Domain-Alter per RDAP** nur in der Grauzone (`AUDIT_SCAM_RDAP_SENDER`, Standard **aus** — sonst langsam).

---

## Konfiguration — Listen und Wirkung

Tab **Konfiguration** im Ordner-Audit (`/api/audit-config/*`).

| UI / Liste | Speicher | Wirkung im Scan |
|------------|----------|-----------------|
| **Vertrauenswürdige Domains** | DB, pro User/Account | Erhöht «wichtig», mindert Scam-Verdacht bei bekannter Domain |
| **Meine Domains** (`own_domains`) | DB | Eigene Web-/Marken-Domains — **gelten nicht** als fremde Scam-Absender-Domain |
| **Wichtige Keywords / Safe Patterns / VIP** | DB | Klassifikation (wichtig vs. löschbar); Safe-Pattern-Grundtext: «Marketing-Absender (Pattern)» — nicht identisch mit Scam-Layer |
| **Auto-Regeln** | DB | Disposition SAFE/IMPORTANT/SCAM/REVIEW nach Pattern |
| **Marken-Domains (Scam)** | DB + **eingebaute** System-Map | Layer 1: **B1** (Marke/Domain-Mismatch) plus **E3/E6** → Kategorie **Verdacht** ohne Provider-Flag; **Scam** = Identität + Transport/Auth-Schwäche oder (nur bei Verdacht-Kandidaten) DBL/junge Domain. Auth-**pass** senkt nicht. |
| **Ordner vom Scan ausnehmen** | `audit_exclude_folders` | Kein Audit für diese IMAP-Ordner |

**Nicht mehr in der UI:** Import der Markenliste von GitHub — **eigene Marken nur in der Tabelle** (plus System-Defaults im Code).

### Marken-Domains (Scam) — Bedienung

Accordion **«Marken-Domains (Scam)»**:

1. **Tabelle:** Zeilen = Marke (Key) + kommagetrennte **offizielle Domains** (`paypal.com`, `paypal.ch`, …).
2. **+ Zeile / × löschen**, dann **Speichern** — persistiert in DB (`brand_official_domains_custom` o. ä.).
3. **Domains prüfen:** read-only — **ändert die gespeicherte Liste nicht**. Checkbox **RDAP** wird mit **Speichern** / beim Start des Checks persistiert. Celery-Task — nur **noch nicht verifizierte** Domains (`verified_at` im Health-JSON). Bei **RDAP 429** → **Stopp** (Teilergebnis bleibt); nach nic.ch-Cooldown erneut klicken (überspringt Verifizierte). **Alle neu prüfen** setzt die Verifizierung für alle Tabellen-Domains zurück und prüft von vorn (Bestätigungsdialog). Pro Domain: **↻** neben dem Badge — nur diese Domain erneut (`recheck_domains` in der API). **Speichern** live-checkt nur **neu hinzugefügte** Domains. Spalte **Verifiziert** + Zeitstempel pro Domain in JSON. Auto-Nachzug standard **aus** (`BRAND_HEALTH_RDAP_AUTO_FOLLOWUP=false`).
4. Badges nach Prüfung: DNS, DBL, RDAP; **DBL blockiert** — Domain darf nicht gespeichert werden, erscheint in roter Hinweisbox.
5. Legacy-Textarea «Text in Tabelle übernehmen» für Bulk-Import aus CSV-Zeilen.

**Normalisierung:** Sonderzeichen in Markennamen (z. B. `h&m` → Key `handm`). Private TLDs / PSL beachtet der Server (`brand_domain_policy.py`).

**Wirkung im Scan:** Der **Schlüssel** (linke Spalte) muss als **ganzes Wort** im **Anzeigenamen** vorkommen — nicht in der Domain. Beispiel: Schlüssel `blkb` trifft «BLKB Kundenservice», aber nicht «Kantonalbank - Support…»; dafür System-Schlüssel **`kantonalbank`** (alle KB-Domains) oder eigener Dach-Eintrag. Mehrdeutige Schlüssel (`bund`, `blick`, …): höchstens Review, kein harter +60 allein über Marke.

Langfristig: Liste nur noch Ausnahmen — siehe [scam-detection-layers.md](scam-detection-layers.md).

Identitäts-KI (Layer 2) kalibriert nur in der Grauzone; sie ersetzt nicht die Marken-Tabelle.

---

## Spamhaus DBL im Scam-Pfad

- Aufruf über `check_dbl()` → `lookup_spamhaus_dbl()` (nur **registrable domain**).
- **Live-Lookups** pro Scan begrenzt: `AUDIT_SCAM_DBL_MAX` (Cache-Treffer zählen nicht).
- **3× «DBL nicht verfügbar»** (falscher Resolver, Rate-Limit): DBL für Rest des Scans aus → Hinweis in **`scan_notice`** am Scan-Ergebnis.
- Technik: [spamhaus-dbl.md](spamhaus-dbl.md).

---

## Grauzone: DNS & RDAP (optional)

Nur wenn Layer 1 **LLM vorschlägt** (`suggest_llm`), nicht für jede Mail:

| Variable | Default | Zweck |
|----------|---------|--------|
| `AUDIT_SCAM_GRAY_DNS_MAX` | 40 | NXDOMAIN-Checks Absender-Domain |
| `AUDIT_SCAM_GRAY_RDAP_MAX` | 20 | RDAP-Alter Absender-Domain |
| `AUDIT_SCAM_RDAP_SENDER` | **false** | RDAP im **Scan** (Sender) — erst bewusst einschalten |

Marken-Health-RDAP (Button «Domains prüfen»): **pro Nutzer** Checkbox «Domain-Alter (RDAP) mitprüfen» in `audit_cluster_settings.brand_health_rdap` (Standard **aus**). Optional Admin-Override `BRAND_DOMAIN_HEALTH_RDAP=false` in `.env`. Pro RDAP-Server Drossel (`RDAP_MIN_INTERVAL_SECONDS` Default 3 s, `RDAP_NIC_CH_INTERVAL_SECONDS` Default 4 s für nic.ch). Bei **429**: Retry-After (max. 15 s), dann **nur diese Domain** `query_failed` — **kein** 600-s-Block mehr (optional `RDAP_USE_CIRCUIT_BREAKER=true`). Beim neuen Check: Cache/Circuit-Reset (`prepare_brand_health_rdap_batch`). Nachzug in **Chunks** (`BRAND_HEALTH_RDAP_FOLLOWUP_CHUNK`, Default 25) mit Pause (`BRAND_HEALTH_RDAP_FOLLOWUP_COOLDOWN`, Default 90 s), RDAP-only-Patch wo DNS schon da ist. Budget `BRAND_HEALTH_RDAP_BUDGET_SECONDS` (8 min), max. 100 Domains pro Lauf (`BRAND_HEALTH_MAX_DOMAINS`). Celery + UI-Poll.

**Zählwerte UI / API `scope`:** Ordner-Scan nutzt **System ∪ Ihre Ergänzungen** (`effective_domains`, unique Hostnames). «Domains prüfen» und Health-JSON gelten nur für **Ihre Custom-Map** (`custom_domains`, `health_verified` / `health_pending`). `system_only_domains` = im Scan aktiv, aber nicht in Ihrer Tabelle / ohne Health-Check. Badge «Marken · Dom.» = Custom, nicht `+219` als reine Marken-Zahl ohne Domains.

**nic.ch Diagnose (CT):** `bash scripts/rdap-nic-ch-probe.sh` — nur wenn `curl …/domain/sbb.ch` **200**. Cooldown: lieber **30–60 Min keine** nic.ch-Anfragen (Celery-Nachzug abwarten), dann **ein** curl; optional `bash scripts/rdap-nic-ch-wait-ok.sh` (Default **5 Min** zwischen Tests — nicht jede 2 Min, das könnte die Sperre verlängern). `RDAP_REDIS_THROTTLE=true` gegen parallele Celery-Worker.

---

## Entwicklung & Deploy (Workflow)

| Schritt | Wo |
|---------|-----|
| Code | Repo **KI-Mail-Helper-Dev**, Branch **`main`** |
| Vor Push (Agent/Dev) | `python -m compileall -q src` und `pytest tests/test_src_compile_smoke.py` (+ betroffene Tests) |
| Produktion | `git pull`, `alembic upgrade head`, optional pytest im venv, Services neu starten — **privates Betriebsdokument** |

Copy-Paste-Befehle und systemd: **privates Betriebsdokument** (nicht in diesem Repo).

**Nach Scam-/Marken-Updates:** Migrationen `brand_*`, `domain_reputation_cache` — immer Alembic auf dem Deploy-Host.

---

## Code-Referenz (kurz)

| Modul | Rolle |
|-------|--------|
| `audit_scam_detection.py` | Layer 1/2, `check_dbl`, Scan-Kontext |
| `brand_domain_policy.py` | Marken-Map, Normalisierung, URL-Import-Härtung |
| `brand_domain_health.py` | Speichern/Health, DBL-Strip |
| `domain_reputation.py` | DBL, DNS, RDAP-Cache |
| `folder_audit_service.py` | Scan, `scan_notice` |
| `blueprints/audit_config.py` | Marken GET/POST, `/health-check` |
