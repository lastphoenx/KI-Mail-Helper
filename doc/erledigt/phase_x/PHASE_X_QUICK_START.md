# Phase X Quick Start Guide 🚀

**Nach der Implementierung: So testest du Phase X**

---

## 1. Server Starten

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
python src/01_web_app.py
```

**Erwartete Ausgabe:**
```
🌐 Dashboard läuft auf http://0.0.0.0:5000
```

---

## 2. Web UI Testen

### A) Einloggen
1. Browser öffnen: `http://localhost:5000`
2. Mit deinem Account einloggen

### B) Settings öffnen
1. Navigiere zu `/settings` oder klick auf "⚙️ Einstellungen"
2. Scrolle nach unten zur **Phase X Section**

**Erwartetes UI:**
```
╔═══════════════════════════════════════════════════════╗
║  Phase X: Trusted Senders + UrgencyBooster Settings  ║
║                                               Phase X ✨║
╠═══════════════════════════════════════════════════════╣
║  ⚡ UrgencyBooster aktivieren                         ║
║  [X] Toggle (sollte standardmäßig AN sein)           ║
╠═══════════════════════════════════════════════════════╣
║  📋 Trusted Senders List                              ║
║  (leer beim ersten Mal)                               ║
╠═══════════════════════════════════════════════════════╣
║  ➕ Neuen Trusted Sender hinzufügen                   ║
║  Pattern Type: [Dropdown ▼]                          ║
║  Pattern: [________________]                          ║
║  Label: [________________]                            ║
║  [X] UrgencyBooster nutzen                            ║
║  [➕ Hinzufügen]                                       ║
╠═══════════════════════════════════════════════════════╣
║  🔍 Vorschläge laden                                  ║
╚═══════════════════════════════════════════════════════╝
```

---

## 3. Trusted Sender Hinzufügen

### Test Case 1: Exakte Email

**Input:**
- Pattern Type: `Exakte Email`
- Pattern: `rechnung@firma.de`
- Label: `Buchhaltung`
- UrgencyBooster: ✓ Aktiviert

**Action:** Klick "➕ Hinzufügen"

**Erwartetes Ergebnis:**
- ✅ Erfolgs-Meldung (grüner Alert)
- Tabelle zeigt neuen Eintrag:
  ```
  Pattern               Type    Label         Emails  Last Seen  Booster  Aktionen
  rechnung@firma.de     exact   Buchhaltung   0       -          ✓        [🗑️]
  ```

### Test Case 2: Email-Domain

**Input:**
- Pattern Type: `Email-Domain (@firma.de)`
- Pattern: `@example.com`
- Label: `Kunden`
- UrgencyBooster: ✓ Aktiviert

**Action:** Klick "➕ Hinzufügen"

**Erwartetes Ergebnis:**
- ✅ Erfolgreich hinzugefügt
- Pattern wird normalisiert: `@example.com` → `@example.com` (lowercase)

### Test Case 3: Vollständige Domain

**Input:**
- Pattern Type: `Vollständige Domain (firma.de)`
- Pattern: `GitHub.com`
- Label: `Dev Notifications`
- UrgencyBooster: ✓ Aktiviert

**Action:** Klick "➕ Hinzufügen"

**Erwartetes Ergebnis:**
- ✅ Erfolgreich hinzugefügt
- Pattern wird normalisiert: `GitHub.com` → `github.com`

---

## 4. UrgencyBooster Toggle Testen

### Test: Global Toggle

**Action:** Toggle "⚡ UrgencyBooster aktivieren" ausschalten

**Erwartetes Ergebnis:**
- ✅ Toggle wechselt zu "Aus"
- API Call: `POST /api/settings/urgency-booster {"enabled": false}`
- Erfolgs-Meldung

**Action:** Toggle wieder einschalten

**Erwartetes Ergebnis:**
- ✅ Toggle wechselt zu "An"
- API Call: `POST /api/settings/urgency-booster {"enabled": true}`

---

## 5. API Endpoints Testen (Browser Console)

### A) List Trusted Senders

```javascript
fetch('/api/trusted-senders')
  .then(r => r.json())
  .then(data => console.log(data));
```

**Erwartete Antwort:**
```json
{
  "success": true,
  "senders": [
    {
      "id": 1,
      "sender_pattern": "rechnung@firma.de",
      "pattern_type": "exact",
      "label": "Buchhaltung",
      "use_urgency_booster": true,
      "email_count": 0,
      "last_seen_at": null,
      "added_at": "2026-01-07T12:00:00"
    }
  ]
}
```

### B) Get UrgencyBooster Status

```javascript
fetch('/api/settings/urgency-booster')
  .then(r => r.json())
  .then(data => console.log(data));
```

**Erwartete Antwort:**
```json
{
  "success": true,
  "urgency_booster_enabled": true
}
```

---

## 6. Email Processing Testen

### A) Email Fetch ausführen

**Terminal:**
```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate

# Mail-Abruf starten (mit deinem Account)
python -c "
from src.01_web_app import app
from src.11_email_fetch import fetch_emails_for_account
# ... (benötigt Account-ID und Credentials)
"
```

**Oder:** Web UI nutzen → Dashboard → "📧 Mails abrufen"

### B) Logs prüfen

**Check ob UrgencyBooster aktiviert wurde:**

```bash
tail -f logs/app.log | grep -E "UrgencyBooster|Trusted"
```

**Erwartete Logs (wenn Trusted Sender Email verarbeitet wird):**
```
INFO - UrgencyBooster: High confidence (0.85) for trusted sender
INFO - 🤖 Analysiere gespeicherte Mail: Rechnung #12345...
INFO - UrgencyBooster for user 1: True
```

**Erwartete Logs (wenn NICHT Trusted Sender):**
```
INFO - 🤖 Analysiere gespeicherte Mail: Newsletter...
INFO - Phase X checks failed: not trusted sender
```

---

## 7. UrgencyBooster Direkttest (Python)

### Standalone Test

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate

python -c "
import sys
sys.path.insert(0, 'src')
from services.urgency_booster import get_urgency_booster

booster = get_urgency_booster()

# Test Email mit hoher Dringlichkeit
result = booster.analyze_urgency(
    subject='EILIG: Rechnung #12345 - Zahlung bis MORGEN!',
    body='''
    Sehr geehrter Kunde,
    
    bitte überweisen Sie den ausstehenden Betrag von 1.500€ 
    bis spätestens 08.01.2026 auf unser Konto.
    
    Bei Rückfragen kontaktieren Sie unsere Geschäftsführerin Frau Müller.
    
    Mit freundlichen Grüßen
    Buchhaltung
    ''',
    sender='rechnung@firma.de'
)

print('═' * 60)
print('UrgencyBooster Analysis Result:')
print('═' * 60)
print(f'Urgency Score:    {result[\"urgency_score\"]}/10')
print(f'Importance Score: {result[\"importance_score\"]}/10')
print(f'Category:         {result[\"category\"]}')
print(f'Confidence:       {result[\"confidence\"]:.2%}')
print(f'Method:           {result[\"method\"]}')
print()
print('Signals:')
for key, val in result['signals'].items():
    print(f'  - {key}: {val}')
print('═' * 60)
"
```

**Erwartete Ausgabe:**
```
════════════════════════════════════════════════════════════
UrgencyBooster Analysis Result:
════════════════════════════════════════════════════════════
Urgency Score:    8/10
Importance Score: 9/10
Category:         aktion_erforderlich
Confidence:       85.00%
Method:           spacy_ner

Signals:
  - time_pressure: True
  - deadline_hours: 24
  - money_amount: 1500.0
  - action_verbs: ['überweisen', 'kontaktieren']
  - authority_person: True
  - invoice_detected: True
════════════════════════════════════════════════════════════
```

**Was getestet wird:**
- ✅ Deadline Detection ("bis MORGEN", "08.01.2026")
- ✅ Money Parsing ("1.500€")
- ✅ Action Verbs ("überweisen", "kontaktieren")
- ✅ Authority Person ("Geschäftsführerin Frau Müller")
- ✅ Invoice Keywords ("Rechnung", "Betrag")
- ✅ High Confidence (>= 0.6 → würde LLM überspringen)

---

## 8. Suggestions Testen

### A) Vorschläge laden

**Voraussetzung:** Du hast bereits mehrere Emails von gleichen Absendern

**Action:** Klick auf "🔍 Vorschläge laden"

**Erwartetes Ergebnis:**
```
╔═══════════════════════════════════════════════════════╗
║  Vorschläge (basierend auf deiner Email-Historie)     ║
╠═══════════════════════════════════════════════════════╣
║  newsletter@firma.com (15 Emails)        [➕]         ║
║  info@kunde.de (8 Emails)                [➕]         ║
║  noreply@github.com (25 Emails)          [➕]         ║
╚═══════════════════════════════════════════════════════╝
```

### B) Vorschlag übernehmen

**Action:** Klick [➕] bei einem Vorschlag

**Erwartetes Ergebnis:**
- ✅ Sender wird zu Trusted Senders hinzugefügt
- Tabelle aktualisiert sich automatisch
- Vorschlag verschwindet aus Liste

---

## 9. Fehlerfall-Tests

### Test A: Ungültige Email

**Input:**
- Pattern Type: `Exakte Email`
- Pattern: `keine-email`

**Erwartetes Ergebnis:**
- ❌ Fehler-Meldung (roter Alert)
- "Invalid email pattern format"

### Test B: Duplikat hinzufügen

**Input:** Gleicher Pattern wie bereits vorhanden

**Erwartetes Ergebnis:**
- ❌ Fehler-Meldung
- "Sender pattern already exists"

### Test C: Limit erreicht

**Voraussetzung:** 500 Trusted Senders bereits hinzugefügt

**Erwartetes Ergebnis:**
- ❌ Fehler-Meldung
- "Maximum 500 trusted senders reached"

---

## 10. Performance Messung

### Test: Verarbeitungszeit

**Setup:**
1. Füge 5 Trusted Senders hinzu
2. Fetch neue Emails von diesen Sendern
3. Prüfe Logs für Verarbeitungszeiten

**Expected Log Pattern:**
```
INFO - 🤖 Analysiere gespeicherte Mail: Rechnung #123...
INFO - UrgencyBooster: High confidence (0.75) for trusted sender
DEBUG - Email processing took 0.15s (UrgencyBooster)
```

**Benchmark:**
- UrgencyBooster (Trusted): **0.1-0.3s**
- Standard LLM (Non-Trusted): **5-10 Minuten** (CPU) oder **10-30s** (GPU)

**Performance-Gewinn:**
```
CPU-only System:
- Trusted: 0.2s
- Standard: 300s
- Speedup: 1500x 🚀

GPU System:
- Trusted: 0.2s
- Standard: 20s
- Speedup: 100x 🚀
```

---

## 11. Debugging

### Problem: UI lädt nicht

**Check 1:** Browser Console öffnen (F12)
```javascript
// Sollte keine Fehler zeigen
// Wenn "404 Not Found": API Endpoints fehlen
```

**Check 2:** Network Tab prüfen
```
GET /api/trusted-senders → 200 OK
GET /api/settings/urgency-booster → 200 OK
```

### Problem: UrgencyBooster gibt niedrige Scores

**Debug Script:**
```python
import sys
sys.path.insert(0, 'src')
from services.urgency_booster import get_urgency_booster

booster = get_urgency_booster()

# Test mit verschiedenen Emails
test_cases = [
    ("Rechnung fällig", "Bitte zahlen Sie 500€", "rechnung@firma.de"),
    ("Meeting Reminder", "Meeting um 14:00 Uhr", "calendar@google.com"),
    ("Newsletter", "Neue Angebote diese Woche", "newsletter@shop.de")
]

for subject, body, sender in test_cases:
    result = booster.analyze_urgency(subject, body, sender)
    print(f"{subject}: Confidence={result['confidence']:.2f}, Method={result['method']}")
```

**Erwartete Ausgabe:**
```
Rechnung fällig: Confidence=0.65, Method=spacy_ner
Meeting Reminder: Confidence=0.30, Method=spacy_ner
Newsletter: Confidence=0.15, Method=spacy_ner
```

### Problem: spaCy Fehler

**Error:** `OSError: [E050] Can't find model 'de_core_news_sm'`

**Fix:**
```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate
python -m spacy download de_core_news_sm
```

**Verify:**
```bash
python -c "import spacy; spacy.load('de_core_news_sm'); print('OK')"
```

---

## 12. Success Criteria ✅

**Phase X ist erfolgreich implementiert wenn:**

- [ ] Server startet ohne Fehler
- [ ] Settings Seite zeigt Phase X Section
- [ ] UrgencyBooster Toggle funktioniert
- [ ] Trusted Sender hinzufügen funktioniert
- [ ] Trusted Sender löschen funktioniert
- [ ] Vorschläge laden funktioniert
- [ ] API Endpoints geben 200 OK zurück
- [ ] Email Processing nutzt UrgencyBooster für Trusted Senders
- [ ] Logs zeigen "UrgencyBooster: High confidence" für Trusted
- [ ] Performance-Gewinn messbar (< 1s vs. Minuten)

**Alle Checks bestanden? 🎉 Phase X läuft!**

---

## 13. Nächste Schritte

**Nach erfolgreichem Test:**

1. **Produktiv nehmen:**
   - Trusted Senders für häufige Absender hinzufügen
   - Performance über 1 Woche messen
   - User Feedback sammeln

2. **Optimieren:**
   - Confidence Threshold anpassen (0.6 → 0.5 für mehr Coverage)
   - spaCy Model upgraden (sm → md für bessere Genauigkeit)
   - Custom Entity Training für spezifische Keywords

3. **Monitoring:**
   - UrgencyBooster Usage Statistics tracken
   - Confidence Distribution analysieren
   - Performance Metriken dashboard erstellen

---

**Happy Testing! 🚀**

Bei Fragen/Problemen: Check `PHASE_X_IMPLEMENTATION_COMPLETE.md` für Details
