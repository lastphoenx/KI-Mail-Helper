# 🚫 Phase F.3: Negative Feedback für Tag-Learning

**Datum:** 2026-01-06
**Status:** ✅ Vollständig implementiert

## Übersicht
Implementierung des kompletten Negative-Feedback-Systems gemäß FEATURE_NEGATIVE_TAG_FEEDBACK_v2.md.
Tags lernen jetzt nicht nur von Positiv-Beispielen, sondern auch von abgelehnten Vorschlägen.

## Implementierte Phasen

### Phase 1: Datenbank-Schema ✅
- **Migration:** `b6d112c59087_add_negative_feedback_support_for_tag_.py`
- **Neue Tabelle:** `tag_negative_examples`
  - Speichert abgelehnte Tag-Zuweisungen
  - Unique constraint: (tag_id, email_id)
  - Index auf tag_id für Performance
  - Cascade delete bei Tag/Email-Löschung
- **EmailTag erweitert:**
  - `negative_embedding` (BLOB) - Aggregiertes Anti-Pattern
  - `negative_updated_at` (DateTime) - Letzte Aktualisierung
  - `negative_count` (Integer) - Anzahl negativer Beispiele

### Phase 2: Backend Core ✅
**Datei:** `src/services/tag_manager.py`

6 neue Funktionen implementiert:

1. **`add_negative_example(db, tag_id, email_id, rejection_source)`**
   - Speichert abgelehnte Tag-Vorschläge
   - Extrahiert Email-Embedding aus RawEmail
   - Triggert automatisch Update des negative_embedding

2. **`remove_negative_example(db, tag_id, email_id)`**
   - Entfernt negative Beispiele (z.B. bei nachträglicher Zuweisung)
   - Aktualisiert negative_embedding

3. **`update_negative_embedding(db, tag_id)`**
   - Berechnet Mittelwert aller negativen Embeddings
   - Identische Logik wie learned_embedding (np.mean)
   - Invalidiert Cache nach Update

4. **`get_negative_similarity(email_embedding, tag)`**
   - Berechnet Cosine-Similarity zu negativem Embedding
   - Gibt 0.0 zurück wenn kein negative_embedding existiert

5. **`calculate_negative_penalty(positive_sim, negative_sim, negative_count, max_penalty)`**
   - **Strategie:**
     - Ratio = negative_sim / positive_sim
     - Wenn ratio >= 1.0 → volle Penalty
     - Sonst: graduelle Penalty basierend auf Verhältnis
   - **Count-Bonus:** Mehr Beispiele = höhere Confidence = stärkere Penalty
     - 1 Beispiel: 1.0x
     - 3 Beispiele: 1.15x
     - 5+ Beispiele: 1.3x (max)
   - **Default max_penalty:** 0.20 (kann bis 20% vom Score abziehen)

6. **Integration in `suggest_tags_by_email_embedding()`**
   - Berechnet negative_similarity für jeden Tag
   - Zieht Penalty vom Similarity-Score ab VOR Threshold-Check
   - Logging: Original-Score → penalized Score

### Phase 3: API Endpoints ✅
**Datei:** `src/01_web_app.py`

2 neue Endpoints:

1. **`POST /api/emails/<email_id>/tags/<tag_id>/reject`**
   - Lehnt Tag-Vorschlag ab
   - Speichert als negatives Beispiel mit `rejection_source="ui"`
   - Triggert automatisch Embedding-Update
   - **Security:** Requires @login_required

2. **`GET /api/tags/<tag_id>/negative-examples`**
   - Listet alle negativen Beispiele eines Tags
   - Zeigt: Email-ID, Subject, Timestamp, Source
   - Für Admin/Debug-Zwecke
   - **Security:** Validiert User-Ownership des Tags

### Phase 4: UI Integration ✅
**Datei:** `templates/email_detail.html`

**Tag-Suggestion-Badges erweitert:**
- **Neues Layout:** Container mit Badge + Reject-Button
- **Reject-Button (×):**
  - Position: Absolute, rechts oben im Badge
  - Hover-Effekt: Größer & opaker
  - Click: Stoppt Event-Propagation (kein versehentliches Assign)
  - Confirm-Dialog: "Tag ablehnen? Wird als negatives Beispiel gespeichert."
  
**Funktionalität:**
- Bei Reject: API-Call an `/api/emails/{id}/tags/{tag_id}/reject`
- Bei Success: Badge wird aus UI entfernt
- Wenn keine Suggestions mehr: Box wird versteckt
- Console-Log: "🚫 Tag '{name}' als negatives Beispiel gespeichert"

## Technische Details

### Embedding-Berechnung
```python
# Identisch zu learned_embedding:
negative_embedding = np.mean([example.negative_embedding for example in examples], axis=0)
```

### Penalty-Logik
```python
# Beispiel: positive_sim=0.75, negative_sim=0.60, count=3
ratio = 0.60 / 0.75 = 0.80
base_penalty = 0.20 * 0.80 = 0.16
count_factor = 1.0 + (3-1) * 0.075 = 1.15
penalty = min(0.16 * 1.15, 0.20) = 0.184

final_similarity = 0.75 - 0.184 = 0.566
```

### Cache-Invalidierung
- `TagEmbeddingCache.invalidate_tag_cache()` wird aufgerufen nach:
  - add_negative_example()
  - remove_negative_example()
  - update_negative_embedding()
- Stellt sicher dass UI immer aktuelle Scores sieht

## Zero-Knowledge Compliance ✅
- Negative Embeddings sind verschlüsselt (LargeBinary in SQLite)
- Keine Klartext-Speicherung von Email-Inhalten
- API-Endpoints validieren User-Ownership
- Cascade delete bei User-Löschung

## Testing

### Manueller Test-Flow:
1. Email öffnen mit Tag-Suggestions
2. Auf "×" bei unpassendem Tag klicken
3. Confirm-Dialog bestätigen
4. Badge verschwindet aus UI
5. Nächste ähnliche Email → Tag hat niedrigeren Score / fehlt ganz
6. Nach 3+ Rejects: Penalty-Effekt deutlich sichtbar

### Validierung:
```bash
# Check negative_examples table
sqlite3 emails.db "SELECT * FROM tag_negative_examples;"

# Check EmailTag.negative_count
sqlite3 emails.db "SELECT id, name, negative_count FROM email_tags WHERE negative_count > 0;"
```

## Logging

**Neue Log-Messages:**
- `🚫 Tag '{name}': Negative example added (email={id}, source={source})`
- `✅ Tag '{name}': Negative example removed (email={id})`
- `🚫 Tag '{name}': Negative embedding updated from {count} rejected emails`
- `🚫 Tag '{name}': Negative feedback applied (neg_sim={x}, penalty={y}, {old}→{new})`
- `🚫 Negative penalty: pos={x}, neg={y}, count={z} → penalty={p}`

## Migration

```bash
# Anwenden
alembic upgrade head

# Rückgängig
alembic downgrade 409434712f70
```

**HINWEIS:** Downgrade löscht ALLE negativen Beispiele permanent!

## Performance-Impact

**Minimal:**
- +1 SQL-Query pro Tag-Suggestion (get negative_embedding)
- Embedding-Berechnung: O(n) für n negative examples, aber nur bei Update
- Cache invalidiert nur bei Add/Remove, nicht bei Read
- No impact on existing Tag-Suggestion-Flow (backward compatible)

## Backward Compatibility ✅

**Ohne negative examples:**
- `get_negative_similarity()` gibt 0.0 zurück
- `calculate_negative_penalty()` gibt 0.0 zurück
- Tag-Suggestions funktionieren exakt wie vorher

**Migration-Safe:**
- Neue Spalten haben DEFAULT NULL
- Alte Tags funktionieren ohne Änderungen
- Kein Breaking Change für existierende Daten

## Nächste Schritte (Optional)

1. **Admin-UI für Negative Examples:**
   - Tag-Management-Seite: "View negative examples"
   - Button zum manuellen Löschen einzelner Examples
   
2. **Batch-Reject in Queue:**
   - `/tag-suggestions`: Reject-Button mit Negative-Example-Option
   - Checkbox: "Als negatives Beispiel speichern"
   
3. **Analytics:**
   - Dashboard: Top-Tags mit meisten Rejects
   - Chart: Penalty-Distribution über Zeit
   
4. **Auto-Cleanup:**
   - Alte negative examples löschen (z.B. > 6 Monate)
   - Nur wenn Tag-Bedeutung sich geändert hat

## Files Changed

- ✅ `migrations/versions/b6d112c59087_add_negative_feedback_support_for_tag_.py`
- ✅ `src/02_models.py` (Modelle bereits in vorherigem Commit)
- ✅ `src/services/tag_manager.py` (+247 Zeilen)
- ✅ `src/01_web_app.py` (+95 Zeilen)
- ✅ `templates/email_detail.html` (+80 Zeilen)

**Total:** +422 LOC

---

**Implementiert gemäß:** `/home/thomas/projects/KI-Mail-Helper/doc/offen/FEATURE_NEGATIVE_TAG_FEEDBACK_v2.md`
