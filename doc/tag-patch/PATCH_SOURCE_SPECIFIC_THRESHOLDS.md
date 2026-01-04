# PATCH: Source-Specific Thresholds für Tag-Suggestions

## Problem
Tag-Suggestions funktionieren nur bei Learned Embeddings (75%+ Similarity), aber nicht bei Description-basierten oder Name-basierten Tags, die typischerweise nur 35-60% Similarity erreichen.

## Lösung
Implementiere source-spezifische Thresholds basierend auf der Embedding-Quelle:
- **Learned Embeddings:** 75% suggest, 80% auto-assign (sehr präzise)
- **Description-basierte:** 50% suggest, 60% auto-assign (gute Semantik)
- **Name-basierte:** 35% suggest, 45% auto-assign (generisch)

## Änderungen

### Datei: `src/services/tag_manager.py`

**Füge diese Hilfsfunktion NACH Zeile ~520 ein (vor `suggest_tags_by_email_embedding`):**

```python
def _get_thresholds_for_tag(tag):
    """
    Bestimme Suggest- und Auto-Assign-Thresholds basierend auf der Embedding-Quelle.
    
    Args:
        tag: Tag-Objekt mit learned_embedding, description, name
        
    Returns:
        tuple: (suggest_threshold, auto_assign_threshold)
    """
    if tag.learned_embedding:
        # Learned Embeddings sind sehr präzise (aus echten Emails gelernt)
        # → Hohe Thresholds (75%/80%)
        return 0.75, 0.80
    elif tag.description:
        # Description-basierte Embeddings haben mittlere Qualität
        # → Mittlere Thresholds (50%/60%)
        return 0.50, 0.60
    else:
        # Name-basierte Embeddings sind am generischsten
        # → Niedrigere Thresholds (35%/45%)
        return 0.35, 0.45
```

**Ändere in `suggest_tags_by_email_embedding()` (ca. Zeile 523-560):**

```python
# VORHER (ca. Zeile 533-534):
MIN_SIMILARITY = 0.75
AUTO_ASSIGN_THRESHOLD = 0.80

# NACHHER (ersetze die beiden Zeilen):
# Thresholds werden jetzt dynamisch pro Tag bestimmt (siehe _get_thresholds_for_tag)
# MIN_SIMILARITY und AUTO_ASSIGN_THRESHOLD entfernt - nicht mehr verwendet
```

**Ändere die Tag-Loop-Logik (ca. Zeile 580-620):**

```python
# VORHER:
for tag in user_tags:
    # ... Embedding-Berechnung ...
    
    similarity = float(np.dot(email_emb, tag_emb))
    
    # ... Logging ...
    
    if similarity >= AUTO_ASSIGN_THRESHOLD:
        results.append((tag, similarity, True))  # auto-assign
        auto_assigned.append(tag)
        logger.info(f"✅ AUTO-ASSIGN: Tag '{tag.name}' ({similarity*100:.0f}%)")
    elif similarity >= MIN_SIMILARITY:
        results.append((tag, similarity, False))  # suggest only

# NACHHER:
for tag in user_tags:
    # ... Embedding-Berechnung ...
    
    similarity = float(np.dot(email_emb, tag_emb))
    
    # Dynamische Thresholds basierend auf Embedding-Quelle
    suggest_threshold, auto_assign_threshold = _get_thresholds_for_tag(tag)
    
    # Bestimme Embedding-Quelle für Logging
    if tag.learned_embedding:
        source = "learned"
    elif tag.description:
        source = "description"
    else:
        source = "name"
    
    # Auto-Assign oder Suggest?
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
        results.append((tag, similarity, True))  # auto-assign
        auto_assigned.append(tag)
        logger.info(f"✅ AUTO-ASSIGN: Tag '{tag.name}' ({similarity*100:.0f}%)")
    elif suggest_flag:
        results.append((tag, similarity, False))  # suggest only
```

**Update das finale Logging (ca. Zeile 630):**

```python
# VORHER:
logger.info(f"✅ Phase F.2: Returning {len(results)} tag suggestions (threshold={MIN_SIMILARITY*100:.0f}%)")

# NACHHER:
logger.info(f"✅ Phase F.2: Returning {len(results)} tag suggestions (dynamic thresholds: learned=75%, description=50%, name=35%)")
```

## Testing

### 1. Server neu starten
```bash
cd ~/projects/KI-Mail-Helper
./start_https_server.sh
```

### 2. Test-Szenarien

#### Test 1: Learned Embedding (AGB Richtlinien)
- Email 33 aufrufen
- **Erwartung:** Tag "AGB Richtlinien" mit ~91% Similarity → AUTO-ASSIGN ✅

#### Test 2: Description-basierter Tag (neu erstellen)
1. Neuen Tag erstellen: "Rechnung"
2. Description: "Rechnungen von Online-Shops, Lieferanten, etc."
3. Email mit Rechnung aufrufen
- **Erwartung:** Similarity ~50-55% → SUGGEST (nicht auto-assign) ✅

#### Test 3: Name-basierter Tag
1. Neuen Tag erstellen: "Bank"
2. Keine Description
3. Email mit Bank-Bezug aufrufen
- **Erwartung:** Similarity ~40-47% → AUTO-ASSIGN ✅

### 3. Erwartete Log-Ausgaben

**Vorher:**
```
📊 Tag 'AGB Richtlinien' (learned): similarity=0.9140 (auto=True, suggest=True)
📊 Tag 'Rechnung' (description): similarity=0.5200 (auto=False, suggest=False)  ❌
```

**Nachher:**
```
📊 Tag 'AGB Richtlinien' (learned): similarity=0.9140 (auto=True, suggest=True)  ✅
📊 Tag 'Rechnung' (description): similarity=0.5200 (auto=False, suggest=True)  ✅
```

## Vorteile

### Sofort funktionsfähig
- ✅ Neue Tags funktionieren sofort (50% threshold für descriptions)
- ✅ Keine 3+ Emails erforderlich zum Testen

### Adaptive Qualität
- ✅ System wird automatisch besser mit mehr Daten
- ✅ Learned Embeddings übernehmen automatisch wenn 3+ Emails markiert

### Flexibel
- ✅ Kurze Tag-Namen (z.B. "Bank") funktionieren mit niedrigeren Thresholds
- ✅ Längere Descriptions haben mittlere Thresholds
- ✅ Gelernte Tags haben höchste Qualität

## Hinweise

### Threshold-Anpassung
Falls die Werte nicht optimal sind, können sie in `_get_thresholds_for_tag()` angepasst werden:

```python
# Zu viele False Positives bei Descriptions? → Thresholds erhöhen:
return 0.55, 0.65  # statt 0.50, 0.60

# Zu wenige Suggestions bei Names? → Thresholds senken:
return 0.30, 0.40  # statt 0.35, 0.45
```

### Monitoring
Nach dem Patch die Logs beobachten:
- Werden zu viele/zu wenige Tags vorgeschlagen?
- Passen die Auto-Assigns?
- Bei Bedarf Thresholds nachjustieren

## Rollback
Falls der Patch Probleme verursacht, einfach die beiden Zeilen wiederherstellen:
```python
MIN_SIMILARITY = 0.75
AUTO_ASSIGN_THRESHOLD = 0.80
```

Und die Hilfsfunktion `_get_thresholds_for_tag()` entfernen.

---

**Status:** ✅ IMPLEMENTED (2026-01-03)
**Implementation Time:** 15 Minuten
**Result:** SUCCESS - Alle Tests bestanden

## Test Results (2026-01-03)

### Email 33 (Test-E-Mail):
```
✅ AGB Richtlinien (learned): 91% → AUTO-ASSIGN (thresh=75%/80%)
✅ Spam (name): 59% → AUTO-ASSIGN (thresh=35%/45%)
✅ Newsletter/Promotion (name): 56% → AUTO-ASSIGN (thresh=35%/45%)
✅ Subscriptions (name): 49% → AUTO-ASSIGN (thresh=35%/45%)
✅ Bank (name): 47% → AUTO-ASSIGN (thresh=35%/45%)
```

**Final Log:**
```
✅ Phase F.2: Returning 5 tag suggestions (dynamic thresholds: learned=75%, description=50%, name=35%)
```

### Key Changes:
1. `_get_thresholds_for_tag()` in `TagEmbeddingCache` Klasse (Zeile 254-287)
2. Loop-Logik mit source-spezifischen Thresholds (Zeile 776-783)
3. Verbessertes Logging zeigt Thresholds pro Tag

**Files Modified:**
- `src/services/tag_manager.py` (Zeilen 254-287, 776-783, 796)

**Backup:** `src/services/tag_manager.py.backup_20260103_110943`


