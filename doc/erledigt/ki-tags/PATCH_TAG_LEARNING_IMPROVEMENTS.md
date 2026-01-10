# Tag-Learning Verbesserungen - Code Patches

## Übersicht der Änderungen

### P0 (KRITISCH):
1. ✅ `remove_tag()` ruft `update_learned_embedding()` auf

### P1 (WICHTIG):
2. ✅ Dynamische Similarity-Thresholds basierend auf Tag-Anzahl
3. ✅ Separate Thresholds für Auto-Assignment vs. Suggestions
4. ✅ MIN_EMAILS_FOR_LEARNING eingeführt
5. ✅ Besseres Logging für Debugging

---

## Datei 1: src/services/tag_manager.py

### Änderung 1: Konstanten am Anfang der Datei hinzufügen

**Nach Zeile 33 (nach `models = import_module("02_models")`) einfügen:**

```python
# ============================================================================
# Phase F.2 Enhanced: Learning Configuration
# ============================================================================

# Minimum Anzahl Emails für stabiles Learning
MIN_EMAILS_FOR_LEARNING = 3

# Auto-Assignment: Nur sehr sichere Matches (80%)
AUTO_ASSIGN_SIMILARITY_THRESHOLD = 0.80

# Manuelle Vorschläge: Auch weniger sichere Matches zeigen
def get_suggestion_threshold(total_tags: int) -> float:
    """Dynamischer Threshold basierend auf Tag-Anzahl
    
    Logik: Bei wenigen Tags lockerer, bei vielen Tags strenger
    - <= 5 Tags: 70% (User hat wenige Tags, mehr Vorschläge helfen)
    - 6-15 Tags: 75% (Mittelfeld)
    - >= 16 Tags: 80% (Viele Tags, nur beste Matches)
    """
    if total_tags <= 5:
        return 0.70
    elif total_tags <= 15:
        return 0.75
    else:
        return 0.80
```

---

### Änderung 2: remove_tag() - Learning-Update hinzufügen

**Zeile 284-299 ERSETZEN durch:**

```python
    @staticmethod
    def remove_tag(db: Session, email_id: int, tag_id: int, user_id: int) -> bool:
        """Entfernt Tag von Email
        
        Args:
            db: SQLAlchemy Session
            email_id: ProcessedEmail ID
            tag_id: EmailTag ID
            user_id: User ID (zur Validierung)
            
        Returns:
            True wenn erfolgreich, False wenn nicht zugewiesen
        """
        # Validiere dass Email und Tag zu User gehören
        assignment = (
            db.query(models.EmailTagAssignment)
            .join(models.ProcessedEmail)
            .join(models.RawEmail)
            .join(models.EmailTag)
            .filter(
                models.EmailTagAssignment.email_id == email_id,
                models.EmailTagAssignment.tag_id == tag_id,
                models.RawEmail.user_id == user_id,
                models.EmailTag.user_id == user_id,
            )
            .first()
        )
        
        if not assignment:
            return False
        
        db.delete(assignment)
        db.commit()
        
        # Phase F.2 Learning: Update learned_embedding nach Tag-Entfernung
        # WICHTIG: Embedding muss neu berechnet werden, da sich die assigned emails geändert haben
        TagManager.update_learned_embedding(db, tag_id, user_id)
        logger.debug(f"🎓 Tag-Learning aktualisiert nach Entfernung von Email {email_id}")
        
        return True
```

---

### Änderung 3: update_learned_embedding() - MIN_EMAILS_FOR_LEARNING

**Zeile 372-442 ERSETZEN durch:**

```python
    @staticmethod
    def update_learned_embedding(db: Session, tag_id: int, user_id: int) -> bool:
        """Phase F.2 Learning: Update Tag-Embedding aus assigned emails
        
        Berechnet Mittelwert aller email_embeddings von Emails mit diesem Tag.
        Wird nach jeder Tag-Zuweisung/Entfernung aufgerufen.
        
        Args:
            db: Database session
            tag_id: EmailTag ID
            user_id: User ID (zur Validierung)
            
        Returns:
            True wenn erfolgreich, False wenn nicht genug Daten
        """
        try:
            # Tag validieren
            tag = db.query(models.EmailTag).filter_by(id=tag_id, user_id=user_id).first()
            if not tag:
                logger.warning(f"Tag {tag_id} nicht gefunden")
                return False
            
            # Alle assigned emails mit Embeddings holen
            assigned_emails = (
                db.query(models.RawEmail)
                .join(models.ProcessedEmail, models.RawEmail.id == models.ProcessedEmail.raw_email_id)
                .join(models.EmailTagAssignment, models.ProcessedEmail.id == models.EmailTagAssignment.email_id)
                .filter(
                    models.EmailTagAssignment.tag_id == tag_id,
                    models.RawEmail.email_embedding.isnot(None),
                    models.RawEmail.user_id == user_id
                )
                .all()
            )
            
            email_count = len(assigned_emails)
            
            if email_count == 0:
                logger.debug(f"🎓 Tag '{tag.name}': Keine Emails mit Embeddings für Learning")
                # Learned embedding löschen falls vorhanden
                if tag.learned_embedding:
                    tag.learned_embedding = None
                    tag.embedding_updated_at = None
                    db.commit()
                    TagEmbeddingCache.invalidate_tag_cache(tag_id, user_id)
                return False
            
            # NEU: Minimum Emails Check für stabiles Learning
            if email_count < MIN_EMAILS_FOR_LEARNING:
                logger.debug(
                    f"🎓 Tag '{tag.name}': Nur {email_count} Email(s), "
                    f"warte auf min. {MIN_EMAILS_FOR_LEARNING} für stabiles Learning"
                )
                return False
            
            # Embeddings sammeln und mitteln
            embeddings = []
            for email in assigned_emails:
                try:
                    emb = np.frombuffer(email.email_embedding, dtype=np.float32)
                    embeddings.append(emb)
                except Exception as e:
                    logger.warning(f"Embedding konvertierung fehlgeschlagen: {e}")
                    continue
            
            if not embeddings:
                return False
            
            # Mittelwert berechnen
            learned_embedding = np.mean(embeddings, axis=0)
            
            # In DB speichern
            tag.learned_embedding = learned_embedding.tobytes()
            tag.embedding_updated_at = datetime.now(UTC)
            db.commit()
            
            # Cache invalidieren
            TagEmbeddingCache.invalidate_tag_cache(tag_id, user_id)
            
            logger.info(
                f"🎓 Tag '{tag.name}': Learned embedding updated from "
                f"{len(embeddings)} emails (min={MIN_EMAILS_FOR_LEARNING})"
            )
            return True
            
        except Exception as e:
            logger.error(f"update_learned_embedding fehlgeschlagen: {e}")
            db.rollback()
            return False
```

---

### Änderung 4: suggest_similar_tags() - Dynamische Thresholds

**Zeile 446-521 ERSETZEN durch:**

```python
    @classmethod
    def suggest_similar_tags(
        cls,
        db: Session,
        user_id: int,
        text: str,
        top_k: int = 5,
        min_similarity: Optional[float] = None
    ) -> List[Tuple[models.EmailTag, float]]:
        """Phase F.2: Findet ähnliche Tags basierend auf Text-Embedding
        
        WICHTIG: Diese Methode ist ein FALLBACK für Emails ohne email_embedding.
        Primär sollte suggest_tags_by_email_embedding() verwendet werden!
        
        Learning-Hierarchie (pro Tag):
        1. learned_embedding (aggregiert aus assigned emails) - BESTE Qualität
        2. description Embedding (semantische Beschreibung)
        3. name Embedding (nur Tag-Name, schwächste Option)
        
        Args:
            db: Database session
            user_id: User ID
            text: Text für Embedding-Generierung
            top_k: Maximale Anzahl Vorschläge
            min_similarity: Minimum Ähnlichkeit (None = dynamisch basierend auf Tag-Anzahl)
            
        Returns:
            Liste von (EmailTag, similarity) Tupeln, sortiert nach Ähnlichkeit
        """
        logger.info(f"📊 Phase F.2: Suggest similar tags for user {user_id} (text-based, FALLBACK)")
        
        # Hole alle User-Tags
        user_tags = db.query(models.EmailTag).filter_by(user_id=user_id).all()
        
        if not user_tags:
            logger.info(f"📊 Phase F.2: Keine Tags für User {user_id}")
            return []
        
        # Dynamischer Threshold basierend auf Tag-Anzahl
        if min_similarity is None:
            min_similarity = get_suggestion_threshold(len(user_tags))
            logger.info(
                f"📊 Phase F.2: Dynamischer Threshold für {len(user_tags)} Tags: {min_similarity:.2%}"
            )
        
        # AI-Client für Text-Embedding
        client = cls._get_ai_client_for_user(user_id, db)
        if not client:
            logger.warning("AI-Client nicht verfügbar")
            return []
        
        # Embedding für Text generieren
        text_embedding = client._get_embedding(text[:512])
        if not text_embedding:
            logger.warning("Text-Embedding konnte nicht erstellt werden")
            return []
        
        text_emb_array = np.array(text_embedding)
        
        # Similarity für alle Tags berechnen
        similarities = []
        for tag in user_tags:
            tag_embedding = cls.get_tag_embedding(tag, db)
            if tag_embedding is None:
                continue
            
            # Cosine Similarity
            similarity = np.dot(text_emb_array, tag_embedding) / (
                np.linalg.norm(text_emb_array) * np.linalg.norm(tag_embedding)
            )
            
            logger.info(
                f"📊 Phase F.2: Tag '{tag.name}' → similarity={similarity:.4f} "
                f"(threshold={min_similarity:.4f})"
            )
            
            if similarity >= min_similarity:
                similarities.append((tag, similarity))
                logger.info(f"✅ Phase F.2: Tag '{tag.name}' MATCHED!")
        
        # Nach Ähnlichkeit sortieren (höchste zuerst)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        result = similarities[:top_k]
        logger.info(
            f"📊 Phase F.2: Returning {len(result)} suggestions "
            f"(threshold={min_similarity:.4f}, total_tags={len(user_tags)})"
        )
        
        return result
```

---

### Änderung 5: suggest_tags_by_email_embedding() - Bessere Thresholds

**Zeile 523-607 ERSETZEN durch:**

```python
    @classmethod
    def suggest_tags_by_email_embedding(
        cls,
        db: Session,
        user_id: int,
        email_embedding: bytes,
        top_k: int = 5,
        exclude_tag_ids: Optional[List[int]] = None,
        min_similarity_override: Optional[float] = None
    ) -> List[Tuple[models.EmailTag, float]]:
        """Phase F.2 Enhanced: Tag-Vorschläge basierend auf Email-Embedding
        
        PRIMÄRE Methode für Tag-Suggestions! Nutzt direkt das email_embedding.
        
        Returns:
            Liste von (EmailTag, similarity, auto_assign) Tupeln:
            - auto_assign=True wenn >= AUTO_ASSIGN_SIMILARITY_THRESHOLD (80%)
            - auto_assign=False wenn nur Vorschlag (>= dynamischer Threshold)
        """
        logger.info(f"📊 Phase F.2: Suggest tags by email embedding for user {user_id}")
        
        # Email-Embedding konvertieren
        try:
            email_emb = np.frombuffer(email_embedding, dtype=np.float32)
        except Exception as e:
            logger.error(f"Email-Embedding konvertierung fehlgeschlagen: {e}")
            return []
        
        # Alle User-Tags
        user_tags = db.query(models.EmailTag).filter_by(user_id=user_id).all()
        
        if not user_tags:
            logger.info(f"📊 Phase F.2: Keine Tags für User {user_id}")
            return []
        
        # Dynamischer Suggestion-Threshold
        suggestion_threshold = (
            min_similarity_override 
            if min_similarity_override is not None 
            else get_suggestion_threshold(len(user_tags))
        )
        
        logger.info(
            f"📊 Phase F.2: {len(user_tags)} Tags | "
            f"Auto-Assign Threshold: {AUTO_ASSIGN_SIMILARITY_THRESHOLD:.2%} | "
            f"Suggestion Threshold: {suggestion_threshold:.2%}"
        )
        
        # Filter: exclude_tag_ids
        exclude_set = set(exclude_tag_ids or [])
        
        # Similarity für alle Tags berechnen
        similarities = []
        for tag in user_tags:
            if tag.id in exclude_set:
                continue
            
            tag_embedding = cls.get_tag_embedding(tag, db)
            if tag_embedding is None:
                continue
            
            # Cosine Similarity
            similarity = np.dot(email_emb, tag_embedding) / (
                np.linalg.norm(email_emb) * np.linalg.norm(tag_embedding)
            )
            
            # Embedding-Quelle für Logging
            source = "learned" if tag.learned_embedding else ("description" if tag.description else "name")
            
            logger.info(
                f"📊 Tag '{tag.name}' ({source}): similarity={similarity:.4f} "
                f"(auto={similarity >= AUTO_ASSIGN_SIMILARITY_THRESHOLD}, "
                f"suggest={similarity >= suggestion_threshold})"
            )
            
            # Mindestens Suggestion-Threshold erreicht?
            if similarity >= suggestion_threshold:
                # Auto-Assignment Flag
                auto_assign = similarity >= AUTO_ASSIGN_SIMILARITY_THRESHOLD
                similarities.append((tag, similarity, auto_assign))
                
                if auto_assign:
                    logger.info(f"✅ AUTO-ASSIGN: Tag '{tag.name}' ({similarity:.2%})")
                else:
                    logger.info(f"💡 SUGGEST: Tag '{tag.name}' ({similarity:.2%})")
        
        # Nach Ähnlichkeit sortieren (höchste zuerst)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        result = similarities[:top_k]
        
        auto_count = sum(1 for _, _, auto in result if auto)
        suggest_count = len(result) - auto_count
        
        logger.info(
            f"📊 Phase F.2: Returning {len(result)} matches | "
            f"{auto_count} auto-assign (>={AUTO_ASSIGN_SIMILARITY_THRESHOLD:.0%}) | "
            f"{suggest_count} suggestions (>={suggestion_threshold:.0%})"
        )
        
        return result
```

---

## Datei 2: src/12_processing.py

### Änderung 6: Auto-Assignment mit neuem Threshold

**Zeile 1227-1250 ERSETZEN durch:**

```python
            # Phase F.2: Email-basierte Tag-Suggestions (nutzt email_embedding direkt!)
            if raw_email.email_embedding:
                from src.services.tag_manager import TagManager
                
                logger.info(f"📊 Phase F.2: Generating tag suggestions for email {raw_email.id}")
                
                # suggest_tags_by_email_embedding() gibt jetzt (tag, similarity, auto_assign) zurück
                tag_suggestions = TagManager.suggest_tags_by_email_embedding(
                    session, 
                    user.id, 
                    raw_email.email_embedding,
                    top_k=10  # Hole mehr Matches (für Auto + Suggestions)
                )
                
                assigned_tags = []
                manual_suggestions = []
                
                for tag, similarity, auto_assign in tag_suggestions:
                    if auto_assign:
                        # Auto-Assignment (>= 80% similarity)
                        try:
                            success = TagManager.assign_tag(session, processed_email.id, tag.id, user.id)
                            if success:
                                assigned_tags.append((tag, similarity))
                                logger.info(
                                    f"🏷️ AUTO-ASSIGNED Tag '{tag.name}' ({similarity:.2%}) "
                                    f"to email {processed_email.id}"
                                )
                        except Exception as e:
                            logger.warning(f"Tag auto-assignment fehlgeschlagen: {e}")
                    else:
                        # Manuelle Suggestion (70-79% similarity)
                        manual_suggestions.append((tag, similarity))
                
                logger.info(
                    f"✅ Phase F.2: {len(assigned_tags)} tags auto-assigned, "
                    f"{len(manual_suggestions)} manual suggestions available"
                )
```

---

## Datei 3: src/01_web_app.py

### Änderung 7: API-Endpoint für Tag-Suggestions anpassen

**Zeile 1752-1810 ERSETZEN durch:**

```python
@app.route("/api/emails/<int:email_id>/tag-suggestions", methods=["GET"])
@login_required
def api_get_tag_suggestions(email_id):
    """API: Tag-Vorschläge für Email (Phase F.2 Enhanced)
    
    Returns:
        {
            "suggestions": [
                {"id": 1, "name": "Rechnung", "color": "#3B82F6", "similarity": 0.87, "auto_assigned": false}
            ],
            "email_id": 123,
            "method": "embedding|text-fallback",
            "embedding_available": true|false,
            "config": {
                "auto_assign_threshold": 0.80,
                "suggestion_threshold": 0.70,
                "total_user_tags": 8
            }
        }
    """
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        # Email holen
        raw_email = (
            db.query(models.RawEmail)
            .join(models.ProcessedEmail)
            .filter(
                models.ProcessedEmail.id == email_id,
                models.RawEmail.user_id == user.id
            )
            .first()
        )

        if not raw_email:
            return jsonify({"error": "Email nicht gefunden"}), 404

        try:
            tag_manager_mod = importlib.import_module("src.services.tag_manager")
            TagManager = tag_manager_mod.TagManager
            
            # Bereits zugewiesene Tags ausschließen
            assigned_tag_ids = [
                assignment.tag_id 
                for assignment in db.query(models.EmailTagAssignment).filter_by(
                    email_id=email_id
                ).all()
            ]
            
            # Count total user tags für Config-Info
            total_user_tags = db.query(models.EmailTag).filter_by(user_id=user.id).count()
            
            # Phase F.2: Email-Embedding nutzen (PRIMÄR)
            if raw_email.email_embedding:
                logger.info(f"📊 Using email_embedding for tag suggestions (email {email_id})")
                
                # suggest_tags_by_email_embedding() gibt (tag, similarity, auto_assign) zurück
                tag_matches = TagManager.suggest_tags_by_email_embedding(
                    db, 
                    user.id, 
                    raw_email.email_embedding,
                    top_k=7,  # Mehr Vorschläge für bessere UX
                    exclude_tag_ids=assigned_tag_ids
                )
                
                suggestions = [
                    {
                        "id": tag.id,
                        "name": tag.name,
                        "color": tag.color,
                        "similarity": round(similarity, 3),
                        "auto_assigned": auto_assign  # Wird in UI anders dargestellt
                    }
                    for tag, similarity, auto_assign in tag_matches
                ]
                
                # Dynamischer Threshold aus tag_manager
                from src.services.tag_manager import get_suggestion_threshold, AUTO_ASSIGN_SIMILARITY_THRESHOLD
                
                return jsonify({
                    "suggestions": suggestions,
                    "email_id": email_id,
                    "method": "embedding",
                    "embedding_available": True,
                    "config": {
                        "auto_assign_threshold": AUTO_ASSIGN_SIMILARITY_THRESHOLD,
                        "suggestion_threshold": get_suggestion_threshold(total_user_tags),
                        "total_user_tags": total_user_tags
                    }
                }), 200
            
            else:
                # Fallback: Text-basierte Suggestions (alte Methode für Emails vor Phase F.1)
                logger.warning(f"⚠️  Email {email_id} hat kein embedding, Fallback zu text-based")
                
                suggestions = TagManager.get_tag_suggestions_for_email(
                    db, email_id, user.id, top_k=5
                )
                
                return jsonify({
                    "suggestions": suggestions, 
                    "email_id": email_id,
                    "method": "text-fallback",
                    "embedding_available": False,
                    "config": {
                        "auto_assign_threshold": 0.85,  # Legacy
                        "suggestion_threshold": 0.70,
                        "total_user_tags": total_user_tags
                    }
                }), 200
                
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Tag-Vorschläge: {e}")
            return jsonify({"suggestions": [], "email_id": email_id}), 200

    finally:
        db.close()
```

---

## Testing-Checkliste

Nach dem Anwenden der Patches:

### ✅ Funktionale Tests

1. **Learning Update bei remove_tag():**
   ```bash
   # Tag von Email entfernen
   # → Logs prüfen: "🎓 Tag-Learning aktualisiert nach Entfernung"
   ```

2. **Dynamische Thresholds:**
   ```bash
   # Mit 3 Tags: Threshold sollte 70% sein
   # Mit 10 Tags: Threshold sollte 75% sein
   # Mit 20 Tags: Threshold sollte 80% sein
   ```

3. **MIN_EMAILS_FOR_LEARNING:**
   ```bash
   # Tag mit nur 1-2 Emails: Kein learned_embedding
   # Tag mit 3+ Emails: learned_embedding wird erstellt
   ```

4. **Auto-Assignment vs. Suggestions:**
   ```bash
   # >= 80% similarity: Auto-assigned
   # 70-79% similarity: Nur Vorschlag
   # < 70% similarity: Nicht angezeigt
   ```

### 📊 Log-Output Beispiel

```
📊 Phase F.2: {len(user_tags)} Tags | Auto-Assign Threshold: 80% | Suggestion Threshold: 70%
📊 Tag 'Rechnung' (learned): similarity=0.8542 (auto=True, suggest=True)
✅ AUTO-ASSIGN: Tag 'Rechnung' (85%)
📊 Tag 'Finanzen' (description): similarity=0.7234 (auto=False, suggest=True)
💡 SUGGEST: Tag 'Finanzen' (72%)
📊 Phase F.2: Returning 5 matches | 2 auto-assign (>=80%) | 3 suggestions (>=70%)
```

---

## Migration Notes

**KEINE Datenbank-Migration nötig!** Alle Änderungen sind Code-only.

**Breaking Changes:** Keine - abwärtskompatibel

**Performance Impact:** Minimal - nur ein zusätzlicher Funktionsaufruf in `remove_tag()`

---

## Rollback

Falls Probleme auftreten, einfach die Original-Dateien aus Git wiederherstellen:

```bash
git checkout HEAD -- src/services/tag_manager.py
git checkout HEAD -- src/12_processing.py
git checkout HEAD -- src/01_web_app.py
```
