# Ordner-Audit — Regel-Kaskade

Stand: was der Scan heute entscheidet, und was bewusst nicht als nummerierte Kaskade gebaut ist.

## Umgesetzt

Der Scan bleibt die bestehende Entscheidung (Score, frühe Ausstiege, Lösch-Veto). Die folgenden Punkte sind im Code, nicht nur im Plan.

**Ordner-Ausschluss.** Ordner in «vom Scan ausnehmen», dazu Gesendet und Entwürfe, werden nicht bewertet.

**Meine Domains und Meine Adressen.** Weiche Identitätsregeln und Marken-Abweichung gelten nicht. Die feste Ebene bleibt: Verdacht, wenn SPF, DKIM und DMARC alle drei `fail` sind, oder wenn die Absender-Domain auf der Spamhaus-Liste steht. Ein einzelner Fail oder `none` reicht nicht. Die Mail wird dadurch nicht automatisch wichtig oder sicher löschbar.

**Vertrauenswürdige Domains.** Identität und Marken-Abweichung gelten nicht. Ein Auth-Fehler wird kein Verdacht (Weiterleitungen und Listen erzeugen sonst Fehlalarme). Ein Spamhaus-Treffer bleibt Verdacht.

**Bekannte Kontakte und VIP.** Schalten die weiche Identität aus. Ein harter Markentreffer bleibt.

**Wichtige Ordner.** Genau dieser Ordner oder ein Ordner darin. Der Löschschutz nennt den Ordnernamen. Der reine Posteingang ist nie ein wichtiger Ordner.

**Aufbewahrung und Wortlisten.** Vier Listen: sensibel, Alarm, Erfolg, Versand. Fristen pro Konto, 1–3650 Tage. Alarm ohne Werbe-Signal bleibt wichtig. Erfolg und Versand werden erst nach der Frist sicher löschbar.

**Domain-Alter.** Nur im Zweifel (verdächtig oder Markenname). «Jünger als N Tage» mit Markenname kann Scam sein. Ein zweites, höheres N setzt nur den Hinweis.

**Fallback.** Trifft nichts zu, bleibt die Kategorie Prüfen mit dem Text «Keine Signale, Absender unbekannt».

**Entscheidend.** Die Detailansicht zeigt die Zeile, die die Kategorie gesetzt hat (`decision_reason`, aus `DECISION_REASON_TEXT` oder der Identitätszeile). Der Regel-Test schickt Absender und Betreff durch `analyze_email`, ohne den Ordner zu lesen.

### Reihenfolge im Lösch-Veto (implementiert)

`safe_delete_veto_reason` prüft in dieser Reihenfolge. Der erste Treffer verhindert «sicher löschbar»:

1. **Alarm.** Ein Alarmwort ohne Werbe-Signal (kein List-Unsubscribe) bleibt wichtig. Fehler und Alarme werden nie nach den Aufbewahrungstagen freigegeben.
2. **Löschschutz der Ordner.** Gesendet und Entwürfe. Danach ein wichtiger Ordner aus der Kontoliste: genau dieser Ordner oder ein Ordner darin. Der Hinweis nennt den Ordnernamen.
3. **Provider-Spam.** Direkt danach: ein Newsletter, den der Provider als Spam markiert hat, wird nicht allein wegen des Newsletter-Merkmals sicher löschbar («Provider-Spam trotz Newsletter-Merkmalen»). Gibt `provider_spam_newsletter_safe` die Mail frei, greift dieser Veto nicht.
4. **Aufbewahrung.** Kein eigener Veto-Satz. Ist die Erfolgsfrist erreicht, entfallen danach der Schutz «eigene Adresse oder Domain» und «vertrauenswürdiger Absender». Ist die Versandfrist erreicht, entfällt der Schutz für geschützte Betreffmuster. Davor bleiben diese Mails in Prüfen. Fristen pro Konto, 1–3650 Tage. Wörter in «Status- und Erfolgswörter» und «Versand-Wörter».

Danach, soweit die Aufbewahrung sie nicht ausnimmt: eigene Adresse oder Domain, Konversation, Antwort-Betreff, vertrauenswürdiger Absender, geschützte Betreffmuster.

**Harmonize (Clustering):** Hebt Mails von Prüfen auf sicher löschbar. Folgt dem Löschschutz wie jede andere SAFE-Entscheidung.

## Zurückgestellt

Nicht gebaut, und nicht als Ersatz der heutigen Logik vorgesehen:

- Die nummerierte Kaskade Nr. 5 bis 10 (Einstufungs-Regeln, Newsletter-Pattern, Marken, Keywords, Clustering) als einzige Entscheidungsquelle mit `deciding_rule_id`.
- Spezifität über alle Stufen (exakte Adresse schlägt Domain schlägt Teilstring, auch über Listen hinweg).
- Konflikt-Warnungen (zum Beispiel VIP und Newsletter-Pattern auf derselben Domain).

Die heutige Logik erklärt die Kategorie über «Entscheidend» und den Regel-Test. Eine spätere Konflikt-Warnung kann dazukommen, ohne die Kaskade umzubauen.

## Referenz

- Betrieb Scam-Layer: [ordner-audit-scam.md](ordner-audit-scam.md)
- Konfiguration: [ordner-audit-konfiguration.md](ordner-audit-konfiguration.md)
- Scan-Hinweis: `src/services/audit_scan_config_notice.py`
