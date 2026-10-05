# Spamhaus DBL im KI-Mail-Helper

Überblick Scam, Marken-Tabelle, Listen: [ordner-audit-scam.md](ordner-audit-scam.md).

## Was wir nutzen

- **DBL** (Domain Blocklist): DNS-Abfrage `{domain}.dbl.spamhaus.org` — nur Domains, keine IP-Zen-Listen.
- Keine Web-Abfrage, kein API-Key.
- Kostenlos nur **nicht-kommerziell**; Nutzungsbedingungen auf spamhaus.org beachten.

## Resolver (wichtig)

Öffentliche Resolver (Google 8.8.8.8, Cloudflare 1.1.1.1, …) liefern oft **127.255.255.254** — die App wertet das als **«DBL nicht verfügbar»** (Warnung/Log), nicht als «sauber».

Empfehlung auf CT 134:

- Eigener rekursiver Resolver (z. B. **unbound** auf localhost), oder
- Resolver des Providers ohne «open resolver»-Policy.

Prüfen: `cat /etc/resolv.conf` — welche Nameserver nutzt der Mail-Helper-Prozess?

## Antwort-Codes (Auszug)

| A-Record | Bedeutung |
|----------|-----------|
| 127.0.1.2 | Spam-Domain → **gelistet** |
| 127.0.1.4 | Phishing → **gelistet** |
| 127.0.1.5 | Malware → **gelistet** |
| 127.0.1.6 | Botnet C&C → **gelistet** |
| 127.0.1.102–106 | Missbrauch legitimer Domain → **gelistet** |
| 127.0.2.x | u. a. Zero-Reputation → **gelistet** |
| 127.0.0.x | Zen/IP-Liste (falsche Query) → **nicht verfügbar** |
| 127.255.255.252/254/255 | Fehler → **nicht verfügbar** |
| NXDOMAIN | Domain nicht auf DBL → **sauber** |

Implementierung: `classify_spamhaus_dbl_answer()` in `src/services/domain_reputation.py`.

## Cache & Limits

| Variable | Default | Zweck |
|----------|---------|--------|
| `DOMAIN_REPUTATION_CACHE_HOURS` | 24 | DB-Tabelle `domain_reputation_cache` + Memory (clean/listed) |
| `DOMAIN_REPUTATION_UNAVAILABLE_CACHE_MINUTES` | 10 | Kurz-Cache bei «nicht verfügbar» |
| `AUDIT_SCAM_DBL_MAX` | 50 | **Live**-DBL-Lookups pro Scan (Cache-Treffer zählen nicht) |
| `AUDIT_SCAM_GRAY_DNS_MAX` | 40 | DNS NXDOMAIN nur Grauzone/LLM-Gate |
| `AUDIT_SCAM_GRAY_RDAP_MAX` | 20 | RDAP nur Grauzone, Flag `AUDIT_SCAM_RDAP_SENDER` |
| `BRAND_HEALTH_MAX_DOMAINS` | 100 | Marken-Health pro Speichern/Check |

## Erwartung im Betrieb

Viele Wegwerf-Scam-Domains stehen **nicht** in der DBL (NXDOMAIN bei `dig`). Sinnvoller für eure Mails: **Marken-Abgleich** (Layer 1) und optional **RDAP Domain-Alter** (`AUDIT_SCAM_RDAP_SENDER`, Grauzone) — nicht DBL-Ausbau.

Nach **3× «unavailable»** in einem Scan: DBL-Checks werden für den Rest des Scans übersprungen; Hinweis in `scan_notice`.

## Test-Domain

Spamhaus nennt in der DBL-Doku Test-Einträge — vor Go-Live einmal echte DBL-Query gegen den dokumentierten Testnamen (FAQ) und eine saubere Domain vergleichen.
