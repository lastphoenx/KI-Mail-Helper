# PATCH: Phase F.2 Queue-Flag Bug Fix

## 🔴 Kritikalität: HOCH

**Problem:** Phase F.2 (Embedding-basierte Tag-Suggestions) respektiert den User-Flag `enable_tag_suggestion_queue` NICHT. Das führt zu inkonsistentem Verhalten.

**Gefunden durch:** Code-Review (3 unabhängige Reviewer)

---

## 🐛 Das Problem

### Aktuelles Verhalten (FALSCH)

```python
# src/12_processing.py, Zeile ~580-620
# Phase F.2: Embedding-basierte Suggestions
for tag, similarity, auto_assign in tag_matches:
    if auto_assign:  # >= 80% Similarity
        # Tag wird IMMER auto-assigned, EGAL ob User Queue aktiviert hat!
        TagManager.assign_tag(db, email_id, tag.id, user_id)
```

### Erwartetes Verhalten (RICHTIG)

- Wenn `user.enable_tag_suggestion_queue = True` → Auto-Assignment erlaubt
- Wenn `user.enable_tag_suggestion_queue = False` → Nur Suggestions, KEIN Auto-Assignment

### Warum ist das ein Problem?

1. **Inkonsistenz:** Phase 10 (KI-basierte Tags) respektiert den Flag, Phase F.2 nicht
2. **User-Erwartung verletzt:** User hat Auto-Actions deaktiviert, aber bekommt trotzdem Auto-Tags
3. **Kontrollverlust:** User kann nicht steuern, ob Tags automatisch zugewiesen werden

---

## ✅ Die Lösung

### Datei: `src/12_processing.py`

**Zeile ~580-620 (in der Phase F.2 Loop)**

```python
# VORHER:
for tag, similarity, auto_assign in tag_matches:
    if auto_assign:
        # Auto-assign high-confidence tags
        TagManager.assign_tag(db, processed.id, tag.id, user.id)
        logger.info(f"✅ AUTO-ASSIGN: Tag '{tag.name}' ({similarity:.0%})")

# NACHHER:
for tag, similarity, auto_assign in tag_matches:
    if auto_assign:
        # 🆕 NEU: Respektiere User-Einstellung!
        if user.enable_tag_suggestion_queue:
            # User erlaubt Auto-Actions → Auto-assign
            TagManager.assign_tag(db, processed.id, tag.id, user.id)
            logger.info(f"✅ AUTO-ASSIGN: Tag '{tag.name}' ({similarity:.0%})")
        else:
            # User hat Auto-Actions deaktiviert → Nur loggen, nicht zuweisen
            logger.info(
                f"⏭️ SKIP AUTO-ASSIGN: Tag '{tag.name}' ({similarity:.0%}) - "
                f"Auto-Actions disabled by user (enable_tag_suggestion_queue=False)"
            )
            # Tag trotzdem als Suggestion zurückgeben (aber nicht auto_assign flag)
            auto_assign = False  # Downgrade zu Suggestion
```

---

## 📍 Genaue Code-Stelle finden

```bash
# Suche nach der Stelle:
grep -n "AUTO-ASSIGN" src/12_processing.py
grep -n "auto_assign" src/12_processing.py
grep -n "tag_matches" src/12_processing.py
```

Typische Zeilen: **~580-620** in der Funktion `process_single_email()` oder `_process_email_tags()`

---

## 🧪 Testing

### Test 1: Queue AKTIVIERT (enable_tag_suggestion_queue = True)

1. Settings → Tag-Suggestions → Queue aktivieren
2. Email mit hoher Tag-Similarity (>80%) verarbeiten
3. **Erwartung:** Tag wird AUTO-ASSIGNED ✅

### Test 2: Queue DEAKTIVIERT (enable_tag_suggestion_queue = False)

1. Settings → Tag-Suggestions → Queue deaktivieren
2. Email mit hoher Tag-Similarity (>80%) verarbeiten
3. **Erwartung:** Tag wird NICHT auto-assigned, erscheint nur als Suggestion ✅

### Test 3: Log-Prüfung

```bash
# Bei deaktivierter Queue sollte erscheinen:
grep "SKIP AUTO-ASSIGN" /var/log/mail-helper.log
# → "⏭️ SKIP AUTO-ASSIGN: Tag 'Rechnung' (85%) - Auto-Actions disabled by user"
```

---

## 📋 Implementierungs-Checkliste

- [ ] Code-Stelle in `src/12_processing.py` finden (~Zeile 580-620)
- [ ] `user.enable_tag_suggestion_queue` Check hinzufügen
- [ ] Logging für Skip-Case hinzufügen
- [ ] Server neu starten
- [ ] Test 1 durchführen (Queue aktiviert)
- [ ] Test 2 durchführen (Queue deaktiviert)
- [ ] Log-Ausgaben verifizieren

---

## ⏱️ Geschätzter Aufwand

**10-15 Minuten**

---

## 🔗 Abhängigkeiten

- **VOR** FEATURE_NEGATIVE_TAG_FEEDBACK implementieren
- Keine DB-Migration nötig
- Keine UI-Änderungen nötig
