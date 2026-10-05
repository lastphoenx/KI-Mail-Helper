# Scam-Erkennung — Schichten statt 219-Marken-Liste

Stand: Konzept / Roadmap (noch nicht vollständig implementiert).

## Problem der Marken-Tabelle

Aktuell: **Schlüssel** (linke Spalte) muss als **ganzes Wort** im **Anzeigenamen** vorkommen; **Domains** (rechte Spalte) dienen nur zum Abgleich der Absender-Domain.

| Effekt | Beispiel |
|--------|----------|
| Schlüssel trifft nicht | `blkb` matcht nicht «Kantonalbank - Support…» → nur Regel E3 (Privatpostfach), kein Marken-Mismatch |
| Alltagswörter | `bund`, `blick` → Fehlalarm bei Zeitungen / normalen Wörtern |
| Pflege | 219 Zeilen, Duplikate, Synonyme, Zeitung vs. Behörde |

Die Liste bleibt sinnvoll als **Ausnahme-/Übersteuerungsliste** (z. B. «bluewin.ch → Swisscom»), nicht als Hauptmechanismus.

Implementierung Marken heute: `find_brand_domain_mismatch()` in `brand_domain_policy.py`; mehrdeutige Keys: `AMBIGUOUS_SHORT_BRANDS` (nur Review-Boost, kein +60 allein).

---

## Zielbild (5 Schichten)

| # | Schicht | Zweck | Pflege | Status |
|---|---------|--------|--------|--------|
| 1 | **Tranco Top-N** | Bekannte Absender-Domain → kein Marken-/Nachahmer-Alarm | wöchentlicher Download | **offen** |
| 2 | **Marke im Domain-Label** | `paypal-secure.com`, `swisscom-…` ohne paypal.com | Labels aus Top-N | **offen** |
| 3 | **Name ↔ Domain-Wörter** | Org-Name, Wörter nicht in Domain (E3, LLM) | keiner | **teilweise** (E3, Identitäts-KI) |
| 4 | **Name-Domain-Gedächtnis** | «ZKB» schon oft von `zkb.ch` gesehen | lernt aus Postfach | **offen** |
| 5 | **LLM + Fakten** | Grauzone mit Alter, Rang, Plattform, Gedächtnis | wie bisher | **teilweise** |
| — | **Marken-Liste** | Synonyme, Sonderfälle | klein | **läuft** (builtin + DB) |

Reihenfolge Umsetzung: **1–3 als reine Funktionen + Tests**, messen auf Golden Set + privatem Echtset (keine Mailbox-Daten in Git), dann Liste zurückstufen.

---

## Messung (Pflicht vor Umbau)

1. **Golden Set:** `scripts/golden_set.py` / `tests/test_scam_golden_rules.py`
2. **Privates Echtset:** lokal auf CT, nie committen (Policy `AGENTS.md`)
3. Metriken: TP/FN Scam-Mails, FP legitime Newsletter/Behörden
4. Pro Schicht einzeln einschalten (Feature-Flag oder `.env`)

---

## Kurzfristige Mitigations (ohne Tranco)

| Maßnahme | Nutzen |
|----------|--------|
| **Dach-Schlüssel** `kantonalbank` + alle KB-Domains (builtin) | «Kantonalbank …» im Namen → Domain-Check |
| **`AMBIGUOUS_*` erweitern** (`bund`, `blick`, …) | Kein Auto-+60 allein über Marke → eher Review |
| **Custom-Map aufräumen** | Keine Kürzel ohne passenden Anzeigenamen; Duplikate weg (Speichern dedupliziert) |
| **Später: Spalte «mehrdeutig»** pro Zeile (DB) | User ersetzt hardcodierte `AMBIGUOUS_SHORT_BRANDS` |

---

## Schicht 1 — Tranco (Skizze)

- Download z. B. [Tranco list](https://tranco-list.eu/) (Lizenz/Attribution in Doku)
- Lokal: Sorted-Set oder Bloom der Top **100k** registrable Domains
- Vor Marken-Check: `registrable_domain(sender) in tranco_top` → Marken-Mismatch für diese Mail **überspringen** (kein Scam allein deswegen)
- Kein «sicher», nur **Fehlalarm-Schutz**

Modul-Vorschlag: `src/services/domain_popularity.py` — `is_well_known_domain(host) -> bool`

---

## Schicht 2 — Nachahmer im Domain-Label

- Aus Top-10k Labels (`paypal`, `swisscom`, `postfinance`, …) automatisch
- Regel: Token in **Absender-Domain** (nicht Anzeigename), registrable Domain ≠ offizielle Marke, optional Levenshtein ≤ 1
- Unabhängig von 219-Zeilen-Liste

---

## Schicht 4 — Name-Domain-Gedächtnis (Vorsicht)

- Tabelle: `(normalized_display_name, registrable_domain) -> count, first_seen, last_seen, auth_ok`
- Nur aus Mails mit **dkim/dmarc pass**, nicht Spam, optional User «wichtig»/beantwortet
- Bei Scam-Check: Name bekannt, neue Domain → starker Score
- Erstkontakt: Schichten 2–3 + LLM, kein FP aus leerem Gedächtnis

---

## Nächste Code-Schritte (Vorschlag)

1. `domain_popularity.py` + Test mit Mini-Fixture-Top-Liste
2. `find_domain_brand_impersonation()` + Tests
3. Golden-Set-Benchmark-Skript (stdout TP/FP)
4. UI: Marken-Tabelle «nur Ausnahmen» + Alias-Hinweis (Dach-Schlüssel)
5. Erst danach: Custom-219 reduzieren, Tranco in Produktion

Siehe auch: [ordner-audit-scam.md](ordner-audit-scam.md), [spamhaus-dbl.md](spamhaus-dbl.md).
