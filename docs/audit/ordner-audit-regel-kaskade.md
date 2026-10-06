# Ordner-Audit — Regel-Kaskade (Design)

Stand: Planungsdokument für Umstellung von **Score + frühen Ausstiegen** auf **nummerierte Entscheidungsregeln**.

## Problem heute

- VIP, Vertrauens-Domains und Marketing-Patterns verschieben nur **Punkte** oder liefern **Hinweise**.
- **Identitäts-Layer** (E9, Marken-Mismatch) kann Nutzerlisten **übersteuern**.
- UI-Labels («VIP = wichtig», «Pattern = sicher löschbar») weichen vom Verhalten ab.
- Scan-Hinweis und geladene Config waren schwer nachvollziehbar (behoben: `audit_scan_config_notice.py`).

## Zielbild

1. **Erste passende Regel** setzt die **Kategorie** (SAFE / REVIEW / IMPORTANT / SUSPICION / SCAM).
2. Alle anderen Signale bleiben **informativ** in der Detailansicht.
3. Detailzeile: **`Entscheidend: Regel Nr. X — …`**
4. **Regel-Test** in der UI: Absender + Betreff → welche Regel würde entscheiden (ohne IMAP-Scan).
5. **Konflikt-Warnung** bei widersprüchlichen Einträgen (z. B. VIP + Newsletter-Pattern auf derselben Domain).

## Feste Sicherheitsebene (über allen Nutzerregeln)

Gilt **auch** bei Vertrauens-Domain / VIP — nur **Meine Domains** + Ordner-Ausschluss können Scam komplett ausnehmen:

| Signal | Typische Aktion |
|--------|-----------------|
| Auth gefälscht / verifizierter Fail | Verdacht / Scam |
| DMARC-Fail + Spam-Flag (Junk ≥ 5) | Verdacht |
| Verdächtiger Anhang ohne Bulk-Kontext | Verdacht |
| Spamhaus DBL (Absender-Domain) | Verdacht / Scam |

Implementiert schrittweise (Quick win: Transport + Auth → Verdacht ohne Identitätsregel).

## Nummerierte Kaskade (Nutzer- + Systemregeln)

| Nr. | Bedingung | Aktion (Ziel-Kategorie) |
|-----|-----------|-------------------------|
| 0 | Ordner in «vom Scan ausnehmen» (+ Gesendet/Entwürfe) | nicht analysieren |
| 1 | **Meine Domains** / eigene Adresse | never_scam; Kategorie über Regeln 3–8 |
| 2 | **Harte Gefahr** | Verdacht / Scam |
| 3 | **Bekannte Kontakte** (exakte Adresse) | wichtig; Identität aus |
| 4 | **VIP** (exakt > Domain > Teilstring) | wichtig; Identität aus |
| 5 | **Vertrauenswürdige Domains** | Identität aus; Rest per Score/Regel 8 |
| 6 | **Newsletter-/Marketing-Pattern** | sicher löschbar (+ Lösch-Veto) |
| 7 | **Marken + Identitätsregeln** | Scam / Verdacht |
| 8 | Keywords, Auto-Regeln, Rest-Score | SAFE / REVIEW / IMPORTANT |
| 9 | **Clustering** | nur Anzeige / Harmonize |

**Priorität innerhalb einer Stufe:** exakte Adresse > Domain > Teilstring.

## Migration

| Phase | Inhalt |
|-------|--------|
| **A (erledigt/teilweise)** | Scan-Hinweis aus DB; LLM-aus → Hinweis trotzdem; Transport+Auth → Verdacht ohne Identität; Auth-Deduplizierung; E3-Bulk ohne Tranco; UI-Texte |
| **B** | `deciding_rule_id` in `TrashEmailInfo`; Kaskade in `analyze_email`; Tests pro Regel |
| **C** | Regel-Test-API + UI; VIP/Pattern/Auto-Regeln in eine Regelliste; Konflikt-Warnungen |

## Auto-Regeln heute

`AuditAutoDeleteRule` mit Disposition — Vorbild für einheitliches Regelmodell (Bedingung + Aktion + Priorität).

## Referenz

- Betrieb Scam-Layer: [ordner-audit-scam.md](ordner-audit-scam.md)
- Scan-Hinweis: `src/services/audit_scan_config_notice.py`
