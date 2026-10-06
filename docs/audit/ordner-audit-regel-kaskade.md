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

## Spezifität (über alle Stufen)

Bei mehreren passenden Regeln gilt **zuerst** die **genauere** Bedingung, **dann** die niedrigere Stufen-Nummer:

**exakte Adresse > Domain > Teilstring**

Das gilt **über Stufen hinweg**. Beispiel: exaktes Newsletter-Pattern auf `newsletter@firma.example` schlägt VIP nur auf `@firma.example` (Domain), auch wenn VIP numerisch früher in der Kaskade steht.

**Teilstring** ist nur für **Newsletter-/Marketing-Pattern** erlaubt, nicht für VIP (UI: VIP nur Adresse oder Domain).

## Feste Sicherheitsebene (über allen Nutzerregeln)

Gilt **auch** bei Vertrauens-Domain, VIP und **Meine Domains** — nur **Ordner-Ausschluss** (Nr. 0) kann Scam-Analyse ganz aussetzen:

| Signal | Typische Aktion |
|--------|-----------------|
| Auth gefälscht / verifizierter Fail | Verdacht / Scam |
| DMARC-Fail + Spam-Flag (Junk ≥ 5) | Verdacht |
| Verdächtiger Anhang ohne Bulk-Kontext | Verdacht |
| Spamhaus DBL (Absender-Domain) | Verdacht / Scam |

**Meine Domains (Nr. 1):** hebt **weiche** Identitätsregeln und Marken-Mismatch ab (`never_scam` für E9-Pfad), **nicht** die feste Sicherheitsebene. Spoofing der eigenen Domain (DMARC-Fail, Auth-Fail) bleibt sichtbar als Verdacht/Scam.

Implementiert schrittweise (Quick win: Transport + Auth → Verdacht ohne Identitätsregel).

## Querschnitt — gilt für alle Stufen

**Löschschutz:** Jede Entscheidung **«sicher löschbar»** (Nutzer-Pattern, Auto-Regel, Score, Harmonize, …) durchläuft den Lösch-Veto — unabhängig von der Regel-Nummer.

**Harmonize (Clustering):** Keine reine Anzeige. Hebt Mails von **Prüfen** auf **sicher löschbar** (Kategorie-Entscheidung). Folgt **Löschschutz** und **kuratierten Ordnern** wie jede andere SAFE-Entscheidung.

## Nummerierte Kaskade (Nutzer- + Systemregeln)

| Nr. | Bedingung | Aktion (Ziel-Kategorie) |
|-----|-----------|-------------------------|
| 0 | Ordner in «vom Scan ausnehmen» (+ Gesendet/Entwürfe) | nicht analysieren |
| 1 | **Meine Domains** / eigene Adresse | never_scam (weich); Kategorie über Regeln 3–7; **kein** Bypass der festen Sicherheitsebene |
| 2 | **Harte Gefahr** (feste Sicherheitsebene) | Verdacht / Scam |
| 3 | **Bekannte Kontakte** (exakte Adresse) | wichtig; Identität aus |
| 4 | **VIP** (nur exakt oder Domain) | wichtig; Identität aus |
| 5 | **Auto-Regeln** (Nutzer: Absender + Betreff + Aktion) | gemäß Disposition; untereinander nach Spezifität |
| 6 | **Vertrauenswürdige Domains** | Identität aus; Rest über Regeln 7–8 / Score |
| 7 | **Newsletter-/Marketing-Pattern** (exakt > Domain > Teilstring) | sicher löschbar |
| 8 | **Marken + Identitätsregeln** | Scam / Verdacht |
| 9 | Keywords, Rest-Score | SAFE / REVIEW / IMPORTANT |
| 10 | **Clustering / Harmonize** | sicher löschbar (nach Querschnitt Löschschutz) |

Konflikt-Auflösung: **Spezifität** (siehe oben), dann **Nr.** — nicht allein Listen-Typ.

## Fallback «Prüfen»

Trifft **keine** Regel zu: Kategorie **Prüfen** mit Begründung **«Keine Regel passt»** — kein Alters- oder Heuristik-Hinweis als Ersatz-«Grund».

## Beschriftung in der Konfiguration (Phase A/B)

Jede Liste in der UI: **ein Satz**, was sie **auslöst** und was **nicht** (z. B. VIP ≠ «alles von der Domain ist Newsletter»; Vertrauens-Domain ≠ Scam-Ausnahme bei Auth-Fail).

## Abnahmekriterien (pro Stufe / Phase B)

| Kriterium | Erkennbar wenn … |
|-----------|------------------|
| Regel implementiert | Synthetischer Testfall pro Nr.; erwartete Kategorie + `deciding_rule_id` |
| Regel-Test = Scan | Regel-Test-API liefert dieselbe Nr. wie Analyse im Ordner-Audit für denselben Absender/Betreff |
| Spezifität | Konflikt-Test (exaktes Pattern vs. Domain-VIP) entscheidet für die genauere Regel |
| Meine Domains + Spoof | Synthetisch: From eigene Domain, DMARC-Fail → Verdacht/Scam, nicht «sicher» |
| Löschschutz | SAFE aus Nr. 7/10/Auto-Regel wird bei Veto auf Prüfen zurückgestellt |
| Keine Regel | Score/Keyword trifft nicht → «Keine Regel passt», nicht Alters-Text |

## Migration

| Phase | Inhalt |
|-------|--------|
| **A (erledigt/teilweise)** | Scan-Hinweis aus DB; LLM-aus → Hinweis trotzdem; Transport+Auth → Verdacht ohne Identität; Auth-Deduplizierung; E3-Bulk ohne Tranco; UI-Texte pro Liste |
| **B** | `deciding_rule_id` in `TrashEmailInfo`; Kaskade in `analyze_email`; Tests pro Regel; Spezifität über Stufen |
| **C** | Regel-Test-API + UI; VIP/Pattern/Auto-Regeln in eine Regelliste; Konflikt-Warnungen |

## Auto-Regeln heute

`AuditAutoDeleteRule` mit Disposition — gleiche Priorität wie andere **Nutzerregeln** (Nr. 5), sortiert nach Spezifität; Vorbild für einheitliches Regelmodell in Phase C.

## Referenz

- Betrieb Scam-Layer: [ordner-audit-scam.md](ordner-audit-scam.md)
- Scan-Hinweis: `src/services/audit_scan_config_notice.py`
