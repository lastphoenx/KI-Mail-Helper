# Changelog - 2026-01-06: Phase F.2 Queue-Flag Fix & CSP Compliance

**Datum:** 06. Januar 2026  
**Fixes:** 2 kritische Bugfixes + Security-Verbesserung  
**Aufwand:** ~30 Minuten  
**Risiko:** Niedrig (keine DB-Änderungen)

---

## ✅ Fix #1: Phase F.2 respektiert jetzt Queue-Flag (KRITISCH)

### Problem
Phase F.2 (Embedding-basierte Tag Auto-Suggestions) ignorierte den User-Flag `enable_tag_suggestion_queue`, was zu inkonsistentem Verhalten führte:
- Phase 10 (KI-basierte Tags) respektierte den Flag ✅
- Phase F.2 (Embedding-basierte Tags) ignorierte ihn ❌
- User konnte Auto-Actions nicht vollständig kontrollieren

### Lösung
- ✅ Phase F.2 prüft jetzt `user.enable_tag_suggestion_queue` vor Auto-Assignment
- ✅ Bei deaktiviertem Flag: Tags werden nur als Suggestions gespeichert, NICHT automatisch zugewiesen
- ✅ Konsistentes Logging: `"⏭️ SKIP AUTO-ASSIGN: Tag 'Rechnung' (85%) - Auto-Actions disabled by user"`

### Geänderte Dateien
- `src/12_processing.py`: Phase F.2 Auto-Assignment Logic erweitert (Zeile ~596-636)

### Code-Änderung
```python
# VORHER:
if similarity >= AUTO_ASSIGN_THRESHOLD:
    # Tag wurde IMMER auto-assigned (Bug!)
    TagManager.assign_tag(db, processed.id, tag.id, user.id)

# NACHHER:
if similarity >= AUTO_ASSIGN_THRESHOLD:
    if user.enable_tag_suggestion_queue:
        # User erlaubt Auto-Actions → zuweisen
        TagManager.assign_tag(db, processed.id, tag.id, user.id)
    else:
        # User hat Auto-Actions deaktiviert → nur loggen
        logger.info(f"⏭️ SKIP AUTO-ASSIGN: Tag '{tag.name}' ({similarity:.0%})")
        manual_suggestions.append({...})  # Als Suggestion speichern
```

### Erwartetes Verhalten
| Szenario | Queue aktiviert | Queue deaktiviert |
|----------|----------------|-------------------|
| Email mit 85% Tag-Similarity | ✅ Auto-assigned | 💡 Nur Suggestion |
| Email mit 75% Tag-Similarity | 💡 Nur Suggestion | 💡 Nur Suggestion |
| Email mit 60% Tag-Similarity | ⏭️ Skip | ⏭️ Skip |

### Impact
- **Konsistenz**: Beide Tag-Phasen verhalten sich jetzt gleich
- **User-Kontrolle**: Flag wirkt jetzt systemweit
- **UX**: Keine unerwarteten Auto-Zuweisungen mehr

---

## ✅ Fix #2: CSP-Violations auf /tag-suggestions behoben

### Problem
Content-Security-Policy blockierte inline Event Handler und Scripts auf `/tag-suggestions`:
```
CSP violation: script-src-attr (inline onclick="saveSettings()")
CSP violation: script-src-elem (script ohne nonce)
```

### Lösung
- ✅ Alle inline `onclick` Handler entfernt (6x)
- ✅ Event Listeners mit `addEventListener` implementiert
- ✅ Script-Tag mit CSP-Nonce versehen
- ✅ `csp_nonce` zu `render_template` hinzugefügt

### Geänderte Dateien
- `src/01_web_app.py`: `csp_nonce=g.csp_nonce` zu `/tag-suggestions` Route hinzugefügt
- `templates/tag_suggestions.html`: 
  - Alle `onclick="..."` → `data-action` Attribute
  - Script-Tag: `<script nonce="{{ csp_nonce }}">`
  - Event Listeners in `DOMContentLoaded` implementiert

### Entfernte inline Handlers
```html
<!-- VORHER (CSP-Violation): -->
<button onclick="saveSettings()">💾 Speichern</button>
<button onclick="approveSuggestion(123)">✅ Annehmen</button>
<button onclick="rejectSuggestion(123)">❌ Ablehnen</button>
<a onclick="mergeSuggestion(123, 456)">🔀 Mergen</a>
<button onclick="batchApprove()">✅ Alle annehmen</button>
<button onclick="batchReject()">❌ Alle ablehnen</button>

<!-- NACHHER (CSP-Compliant): -->
<button id="saveSettingsBtn">💾 Speichern</button>
<button data-action="approve" data-suggestion-id="123">✅ Annehmen</button>
<button data-action="reject" data-suggestion-id="123">❌ Ablehnen</button>
<a data-action="merge" data-suggestion-id="123" data-tag-id="456">🔀 Mergen</a>
<button id="batchApproveBtn">✅ Alle annehmen</button>
<button id="batchRejectBtn">❌ Alle ablehnen</button>

<script nonce="{{ csp_nonce }}">
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('saveSettingsBtn').addEventListener('click', saveSettings);
    document.querySelectorAll('[data-action="approve"]').forEach(btn => {
        btn.addEventListener('click', function() {
            approveSuggestion(parseInt(this.getAttribute('data-suggestion-id')));
        });
    });
    // ... etc
});
</script>
```

### Impact
- **Security**: Keine CSP-Violations mehr (strict CSP enforcement)
- **Best Practice**: Event Listeners statt inline handlers
- **Funktion**: Alle Buttons funktionieren identisch wie vorher

---

## 🐛 Fix #3: Import-Fehler in tag_suggestion_service.py

### Problem
```python
ModuleNotFoundError: No module named '02_models'
```

### Lösung
```python
# VORHER:
models = import_module("02_models")

# NACHHER:
models = import_module("src.02_models")
```

### Geänderte Dateien
- `src/services/tag_suggestion_service.py`: Korrekter Import-Pfad

---

## 📋 Testing

### Test #1: Queue-Flag Verhalten
```bash
# Test A: Queue aktiviert
1. Dashboard → /tag-suggestions → Einstellungen → Queue aktivieren
2. Email mit hoher Tag-Similarity (>80%) verarbeiten
3. ✅ Tag wird auto-assigned
4. Log: "🏷️ ✅ AUTO-ASSIGNED Tag 'Rechnung' (85% similarity)"

# Test B: Queue deaktiviert
1. Dashboard → /tag-suggestions → Einstellungen → Queue deaktivieren
2. Email mit hoher Tag-Similarity (>80%) verarbeiten
3. ✅ Tag wird NICHT zugewiesen (nur Suggestion)
4. Log: "⏭️ SKIP AUTO-ASSIGN: Tag 'Rechnung' (85%) - Auto-Actions disabled"
```

### Test #2: CSP Compliance
```bash
1. Browser → /tag-suggestions öffnen
2. F12 → Console öffnen
3. ✅ KEINE CSP-Violations mehr
4. Alle Buttons testen (Save Settings, Approve, Reject, Merge, Batch)
5. ✅ Alles funktioniert wie vorher
```

---

## 🔗 Referenzen

- **Dokument**: `doc/erledigt/PATCH_PHASE_F2_QUEUE_FLAG_BUG.md`
- **Code-Review**: Gefunden durch unabhängige Reviews
- **Kritikalität**: HOCH (Inkonsistentes User-Verhalten)

---

## ✅ Checkliste

- [x] Phase F.2 Queue-Flag implementiert
- [x] CSP-Violations behoben (6x inline handlers)
- [x] Import-Fehler gefixt
- [x] Server getestet (läuft ohne Fehler)
- [x] Dokumentation aktualisiert
- [x] PATCH-Dokument nach /erledigt verschoben

---

**Status:** ✅ Alle Fixes implementiert und getestet  
**Nächster Schritt:** FEATURE_NEGATIVE_TAG_FEEDBACK_v2.md implementieren (optional)
