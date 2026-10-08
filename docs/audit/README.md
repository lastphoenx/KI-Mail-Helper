# Ordner-Audit — Scam & Domain-Reputation

Index für Technik und Betrieb der Ordner-Audit-Funktionen in dieser App.

| Dokument | Inhalt |
|----------|--------|
| [ordner-audit-konfiguration.md](ordner-audit-konfiguration.md) | Einstellungen: Zweck, Wirkung, Beispiel, Speicherort |
| [ordner-audit-regel-kaskade.md](ordner-audit-regel-kaskade.md) | Entscheidung inkl. Alarm, Löschschutz, Aufbewahrung |
| [ordner-audit-scam.md](ordner-audit-scam.md) | Layer 1/2, Listen, **Marken-Domains**, Wirkung im Scan |
| [scam-detection-layers.md](scam-detection-layers.md) | Roadmap: Tranco, Domain-Nachahmer, Gedächtnis, Liste zurückstufen |
| [spamhaus-dbl.md](spamhaus-dbl.md) | Spamhaus DBL, Resolver, Cache, Grenzen im Alltag |
| [firstnames-import.md](firstnames-import.md) | Vornamen-CLI → `audit_firstnames` (E9/N1) |
| [ADR-audit-known-contacts-encryption.md](ADR-audit-known-contacts-encryption.md) | Bekannte Kontakte: at-rest wie Mails (DEK, HMAC-Lookup) |
| [deploy-known-contacts-encryption.md](deploy-known-contacts-encryption.md) | Deploy f7 → Verify → f8 (`scripts/deploy-known-contacts-*.sh`) |

**Deploy, `.env`, systemd:** privates Betriebsdokument des Betreibers (nicht in diesem Repo).

**Endnutzer:** `docs/BENUTZERHANDBUCH.md` §12 (Kacheln, Scam, Konfiguration, Aufbewahrung, Wortlisten, wichtige Ordner).

**Konfiguration im Code:** `src/services/audit_quality_rules.py` (Fristen, Wortlisten, wichtige Ordner), `src/services/audit_domain_intel.py` (DNS/RDAP), `src/services/audit_own_domains.py` (eigene Domains und Adressen). Spalten stehen in [ordner-audit-konfiguration.md](ordner-audit-konfiguration.md).
