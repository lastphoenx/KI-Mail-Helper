# Changelog - 2026-01-05: Tag & Job Modal Patches

**Datum:** 05. Januar 2026  
**Patches:** 2 kritische Bugfixes implementiert  
**Aufwand:** ~55 Minuten  
**Risiko:** Niedrig (keine DB-Änderungen)

---

## ✅ Patch #1: Tag Auto-Creation deaktiviert

### Problem
System erstellte automatisch Tags ohne User-Kontrolle, was zu Tag-Explosion führte.

### Lösung
- ✅ Neue Methode `get_tag_by_name()` in `TagManager` (nur lesen, nicht erstellen)
- ✅ Phase 10 in `12_processing.py` geändert: Nutzt nur noch existierende Tags
- ✅ Nicht-existierende Tags werden geloggt für späteres Queue-System

### Geänderte Dateien
- `src/services/tag_manager.py`: `get_tag_by_name()` hinzugefügt (Zeile ~421)
- `src/12_processing.py`: Phase 10 nutzt jetzt `get_tag_by_name()` statt `get_or_create_tag()` (Zeile ~505)

### Erwartetes Verhalten
| Szenario | Vorher | Nachher |
|----------|--------|---------|
| AI schlägt "Rechnung" vor, Tag existiert | ✅ Zugewiesen | ✅ Zugewiesen |
| AI schlägt "Rechnung" vor, Tag existiert NICHT | ⚠️ Tag erstellt + zugewiesen | 💡 Nur geloggt |
| Neuer Account, 0 Tags | 20+ Tags auto-erstellt | 0 Tags erstellt |

### Logs
```
💡 AI suggested tag 'Rechnung' - nicht vorhanden, übersprungen (email 123)
📌 Tag 'Arbeit' assigned to email 124
```

---

## ✅ Patch #2: Job Modal Race Condition behoben

### Problem
Wenn zwei Jobs parallel laufen, springt das Progress-Modal wild zwischen beiden hin und her.

### Lösung
- ✅ Neue Variable `currentActiveJobId` trackt welcher Job das Modal "besitzt"
- ✅ Updates von nicht-aktiven Jobs werden ignoriert
- ✅ "Neuer Job gewinnt" bei Konflikt (bessere UX)
- ✅ Alle Exit-Punkte resetten `currentActiveJobId = null`

### Geänderte Dateien
- `templates/settings.html`:
  - `currentActiveJobId` Variable hinzugefügt (Zeile ~475)
  - `pollJobStatus()`: Job-Tracking + Guards (Zeile ~487)
  - `pollBatchReprocessStatus()`: Job-Tracking + Guards (Zeile ~977)
  - Alle Exit-Punkte (done, error, timeout, catch) resetten Job-ID

### Erwartetes Verhalten

**Szenario:**
```
17:34:00 - User startet Job 1 (Batch-Reprocess, 53 Mails)
           → Modal zeigt "0/53"
           
17:34:30 - Job 1 pollt → Modal zeigt "23/53"

17:36:00 - User startet Job 2 (Fetch, 3 Mails)
           → Console: ⚠️ Job {job2} übernimmt Modal von {job1}
           → Modal zeigt "0/3" (Job 2)

17:36:15 - Job 1 pollt → Console: 🛑 Poll ignoriert
           → Modal bleibt bei Job 2 (kein Springen mehr!)
```

### Console Logs
```
⚠️ Job abc-123 übernimmt Modal von xyz-456
🛑 Poll ignoriert: Job xyz-456 nicht aktiv (aktiv: abc-123)
```

---

## 🧪 Test-Anleitung

### Test Patch #1 (Tag Auto-Creation)

```bash
cd /home/thomas/projects/KI-Mail-Helper
source venv/bin/activate

# Server starten
python3 -m src.00_main --serve --https

# Im Browser:
# 1. Neue Emails fetchen (mit AI-Analyse)
# 2. Logs prüfen:
#    - Sollte "💡 AI suggested tag..." Einträge zeigen
#    - Sollte KEINE neuen Tags erstellen

# Prüfen dass keine neuen Tags erstellt wurden:
sqlite3 emails.db "SELECT COUNT(*) FROM email_tags WHERE user_id=1;"
# Anzahl sollte gleich bleiben nach mehrmaligem Fetchen
```

### Test Patch #2 (Job Modal Tracking)

```bash
# Im Browser:
# 1. Starte Job A (z.B. Batch-Reprocess mit vielen Mails)
#    → Modal öffnet sich

# 2. WÄHREND Job A läuft: Starte Job B (z.B. Fetch)
#    → Console sollte zeigen: "⚠️ Job {B} übernimmt Modal von {A}"
#    → Modal zeigt nur noch Job B Progress

# 3. Job A pollt weiter → Console: "🛑 Poll ignoriert"
#    → Modal springt NICHT mehr hin und her ✅

# 4. Job B beenden (OK klicken)
# 5. Neuen Job starten → sollte normal funktionieren
```

---

## 📊 Statistik

| Metrik | Wert |
|--------|------|
| Dateien geändert | 3 |
| Zeilen hinzugefügt | ~85 |
| Zeilen geändert | ~35 |
| Breaking Changes | 0 |
| DB Migrations nötig | Nein |
| Tests geschrieben | Manuelle UI-Tests |

---

## 🔜 Nächste Schritte (Optional)

### Tag Suggestion Queue (später, ~6h)
Falls nach 2-3 Wochen viele "übersprungene Tags" in Logs:
- Siehe: `doc/offen/DESIGN_TAG_SUGGESTION_QUEUE.md`
- Implementiert Queue-System mit User-Approval
- User kann AI-Vorschläge annehmen/ablehnen/mergen

---

## ✍️ Autor

**Implementiert:** 2026-01-05  
**Review:** Automatisierte Fehlerprüfung (0 Errors)  
**Dokumentation:** 
- `/doc/offen/PATCH_DISABLE_TAG_AUTO_CREATION.md`
- `/doc/offen/REFACTORING_JOB_MODAL_TRACKING.md`
