# QUICK IMPLEMENTATION GUIDE
## Source-Specific Thresholds Patch

### 📋 Schritt-für-Schritt Anleitung

#### 1. Backup erstellen
```bash
cd ~/projects/KI-Mail-Helper
cp src/services/tag_manager.py src/services/tag_manager.py.backup
```

#### 2. Datei öffnen
```bash
nano src/services/tag_manager.py
# oder
code src/services/tag_manager.py
```

#### 3. Hilfsfunktion hinzufügen

**Suche nach:** `def suggest_tags_by_email_embedding`

**Füge VOR dieser Funktion ein:**

```python
def _get_thresholds_for_tag(tag):
    """
    Bestimme Suggest- und Auto-Assign-Thresholds basierend auf der Embedding-Quelle.
    
    Returns:
        tuple: (suggest_threshold, auto_assign_threshold)
    """
    if tag.learned_embedding:
        return 0.75, 0.80  # Learned: höchste Qualität
    elif tag.description:
        return 0.50, 0.60  # Description: mittlere Qualität
    else:
        return 0.35, 0.45  # Name: niedrigste Qualität
```

#### 4. Alte Thresholds entfernen

**Suche nach:**
```python
MIN_SIMILARITY = 0.75
AUTO_ASSIGN_THRESHOLD = 0.80
```

**Ersetze mit:**
```python
# Thresholds werden jetzt dynamisch pro Tag bestimmt (siehe _get_thresholds_for_tag)
```

#### 5. Loop-Logik anpassen

**Suche nach:**
```python
for tag in user_tags:
    # ... code ...
    similarity = float(np.dot(email_emb, tag_emb))
    # ... logging ...
    
    if similarity >= AUTO_ASSIGN_THRESHOLD:
        results.append((tag, similarity, True))
        auto_assigned.append(tag)
    elif similarity >= MIN_SIMILARITY:
        results.append((tag, similarity, False))
```

**Ersetze mit:**
```python
for tag in user_tags:
    # ... code ... (NICHT ändern bis zur similarity-Berechnung!)
    similarity = float(np.dot(email_emb, tag_emb))
    
    # Dynamische Thresholds
    suggest_threshold, auto_assign_threshold = _get_thresholds_for_tag(tag)
    
    # Bestimme Embedding-Quelle für Logging
    if tag.learned_embedding:
        source = "learned"
    elif tag.description:
        source = "description"
    else:
        source = "name"
    
    # Entscheidung
    if similarity >= auto_assign_threshold:
        auto_assign_flag = True
        suggest_flag = True
    elif similarity >= suggest_threshold:
        auto_assign_flag = False
        suggest_flag = True
    else:
        auto_assign_flag = False
        suggest_flag = False
    
    logger.info(
        f"📊 Tag '{tag.name}' ({source}): "
        f"similarity={similarity:.4f} "
        f"(auto={auto_assign_flag}, suggest={suggest_flag})"
    )
    
    if auto_assign_flag:
        results.append((tag, similarity, True))
        auto_assigned.append(tag)
        logger.info(f"✅ AUTO-ASSIGN: Tag '{tag.name}' ({similarity*100:.0f}%)")
    elif suggest_flag:
        results.append((tag, similarity, False))
```

#### 6. Finales Logging updaten

**Suche nach:**
```python
logger.info(f"✅ Phase F.2: Returning {len(results)} tag suggestions (threshold={MIN_SIMILARITY*100:.0f}%)")
```

**Ersetze mit:**
```python
logger.info(
    f"✅ Phase F.2: Returning {len(results)} tag suggestions "
    f"(learned=75%, description=50%, name=35%)"
)
```

#### 7. Datei speichern und Server neu starten

```bash
# Speichern (Ctrl+O in nano, Ctrl+S in VSCode)
# Beenden (Ctrl+X in nano)

# Server neu starten
./start_https_server.sh
```

### ✅ Verification

#### Test 1: Bestehender Learned Tag
1. Email 33 aufrufen
2. **Erwartung:** "AGB Richtlinien" (91%) → AUTO-ASSIGN ✅

#### Test 2: Neuen Tag mit Description erstellen
1. Tag "Rechnung" erstellen
2. Description: "Rechnungen und Invoices"
3. Email mit Rechnung aufrufen
4. **Erwartung:** ~50-55% → SUGGEST ✅

#### Test 3: Neuen Tag ohne Description
1. Tag "Bank" erstellen (keine Description)
2. Email mit Bank-Bezug aufrufen
3. **Erwartung:** ~45% → AUTO-ASSIGN ✅

### 🐛 Troubleshooting

**Problem:** Syntax-Fehler beim Server-Start
```bash
# Backup wiederherstellen
cp src/services/tag_manager.py.backup src/services/tag_manager.py

# Python-Syntax prüfen
python3 -m py_compile src/services/tag_manager.py
```

**Problem:** Thresholds zu niedrig/hoch
→ In `_get_thresholds_for_tag()` Werte anpassen:
```python
# Beispiel: Description-Thresholds erhöhen
elif tag.description:
    return 0.55, 0.65  # statt 0.50, 0.60
```

**Problem:** Keine Änderung sichtbar
→ Server wirklich neu gestartet? Cache gelöscht?
```bash
# Hard-Restart
pkill -f "python.*00_main"
./start_https_server.sh
```

### 📊 Erwartete Log-Ausgaben

**Vorher (nur 75% Threshold):**
```
📊 Tag 'AGB Richtlinien' (learned): similarity=0.9140 (auto=True, suggest=True)
📊 Tag 'Rechnung' (description): similarity=0.5200 (auto=False, suggest=False) ❌
📊 Tag 'Bank' (name): similarity=0.4700 (auto=False, suggest=False) ❌
```

**Nachher (source-spezifisch):**
```
📊 Tag 'AGB Richtlinien' (learned): similarity=0.9140 (auto=True, suggest=True) ✅
📊 Tag 'Rechnung' (description): similarity=0.5200 (auto=False, suggest=True) ✅
📊 Tag 'Bank' (name): similarity=0.4700 (auto=True, suggest=True) ✅
```

### 🎯 Success Criteria

- [x] Server startet ohne Fehler ✅
- [x] Learned Tags funktionieren weiterhin (91% → AUTO-ASSIGN) ✅
- [x] Description Tags werden vorgeschlagen (~50-60% → SUGGEST) ✅
- [x] Name Tags werden bei ~45% auto-assigned ✅
- [x] Logs zeigen source-spezifische Thresholds ✅

---

## ✅ IMPLEMENTATION COMPLETE (2026-01-03)

**Implementation Time:** 15 Minuten
**Status:** SUCCESS - All tests passed

### Actual Results:
```
📊 Tag 'AGB Richtlinien' (learned): similarity=0.9140 thresh=[suggest=75%, auto=80%] → (auto=True, suggest=True)
📊 Tag 'Spam' (name): similarity=0.5880 thresh=[suggest=35%, auto=45%] → (auto=True, suggest=True)
📊 Tag 'Bank' (name): similarity=0.4744 thresh=[suggest=35%, auto=45%] → (auto=True, suggest=True)
✅ Phase F.2: Returning 5 tag suggestions (dynamic thresholds: learned=75%, description=50%, name=35%)
```

### Files Modified:
- `src/services/tag_manager.py` (Lines 254-287, 776-783, 796)

### Backup Location:
- `src/services/tag_manager.py.backup_20260103_110943`


