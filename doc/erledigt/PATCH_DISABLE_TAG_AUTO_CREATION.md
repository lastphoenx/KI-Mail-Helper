# PATCH: Disable Tag Auto-Creation

**Problem:** System erstellt automatisch Tags ohne User-Kontrolle  
**Lösung:** Phase 10b deaktivieren - nur existierende Tags zuweisen  
**Aufwand:** ~10 Minuten  
**Risiko:** Niedrig (keine DB-Änderungen)

---

## 📍 Problemstelle

**Datei:** `src/12_processing.py`  
**Funktion:** `process_pending_raw_emails()`  
**Zeilen:** ca. 207-230

```python
# AKTUELL (PROBLEM):
for tag_name in suggested_tags[:5]:
    tag = tag_manager_mod.TagManager.get_or_create_tag(  # ← ERSTELLT TAGS!
        db=session,
        user_id=user.id,
        name=tag_name,
        color="#3B82F6"
    )
    tag_manager_mod.TagManager.assign_tag(...)
```

---

## ✅ Patch

### Schritt 1: `src/12_processing.py` anpassen

**Suche diesen Block** (ca. Zeile 207-230):

```python
# Phase 10: Auto-assign suggested_tags from AI
suggested_tags = ai_result.get("suggested_tags", [])
if suggested_tags and isinstance(suggested_tags, list):
    try:
        tag_manager_mod = importlib.import_module(".services.tag_manager", "src")
        
        # Muss flushen damit processed_email.id verfügbar ist
        session.flush()
        
        for tag_name in suggested_tags[:5]:  # Max 5 Tags
            if not tag_name or not isinstance(tag_name, str):
                continue
            
            tag_name = tag_name.strip()[:50]  # Max 50 chars
            if not tag_name:
                continue
            
            try:
                # Get or create tag für diesen User
                tag = tag_manager_mod.TagManager.get_or_create_tag(
                    db=session,
                    user_id=user.id,
                    name=tag_name,
                    color="#3B82F6"  # Default blue
                )
                
                # Assign tag zu email
                tag_manager_mod.TagManager.assign_tag(
                    db=session,
                    email_id=processed_email.id,
                    tag_id=tag.id,
                    user_id=user.id
                )
                logger.debug(f"📌 Tag '{tag_name}' assigned to email {processed_email.id}")
            except Exception as tag_err:
                logger.warning(f"⚠️  Tag-Assignment fehlgeschlagen für '{tag_name}': {tag_err}")
                
    except Exception as e:
        logger.warning(f"⚠️  Tag-Manager nicht verfügbar oder Fehler: {e}")
```

**Ersetze durch:**

```python
# Phase 10: Auto-assign suggested_tags from AI
# GEÄNDERT 2026-01-05: Nur existierende Tags zuweisen, keine Auto-Creation
# Siehe: PATCH_DISABLE_TAG_AUTO_CREATION.md
suggested_tags = ai_result.get("suggested_tags", [])
if suggested_tags and isinstance(suggested_tags, list):
    try:
        tag_manager_mod = importlib.import_module(".services.tag_manager", "src")
        
        # Muss flushen damit processed_email.id verfügbar ist
        session.flush()
        
        for tag_name in suggested_tags[:5]:  # Max 5 Tags
            if not tag_name or not isinstance(tag_name, str):
                continue
            
            tag_name = tag_name.strip()[:50]  # Max 50 chars
            if not tag_name:
                continue
            
            try:
                # NEU: Nur existierende Tags verwenden, NICHT erstellen
                tag = tag_manager_mod.TagManager.get_tag_by_name(
                    db=session,
                    user_id=user.id,
                    name=tag_name
                )
                
                if tag:
                    # Tag existiert → zuweisen
                    tag_manager_mod.TagManager.assign_tag(
                        db=session,
                        email_id=processed_email.id,
                        tag_id=tag.id,
                        user_id=user.id
                    )
                    logger.debug(f"📌 Tag '{tag_name}' assigned to email {processed_email.id}")
                else:
                    # Tag existiert nicht → nur loggen (später: Queue)
                    logger.debug(f"💡 AI suggested tag '{tag_name}' - nicht vorhanden, übersprungen")
                    
            except Exception as tag_err:
                logger.warning(f"⚠️  Tag-Assignment fehlgeschlagen für '{tag_name}': {tag_err}")
                
    except Exception as e:
        logger.warning(f"⚠️  Tag-Manager nicht verfügbar oder Fehler: {e}")
```

---

### Schritt 2: `get_tag_by_name()` in TagManager hinzufügen

**Datei:** `src/services/tag_manager.py`

**Füge diese Funktion hinzu** (nach `get_or_create_tag`):

```python
@staticmethod
def get_tag_by_name(
    db: Session, user_id: int, name: str
) -> Optional[models.EmailTag]:
    """Gibt existierenden Tag zurück oder None
    
    UNTERSCHIED zu get_or_create_tag(): Erstellt KEINE neuen Tags!
    
    Args:
        db: SQLAlchemy Session
        user_id: User ID
        name: Tag-Name (case-sensitive)
        
    Returns:
        EmailTag object oder None wenn nicht gefunden
    """
    return (
        db.query(models.EmailTag)
        .filter(
            models.EmailTag.user_id == user_id, 
            models.EmailTag.name == name
        )
        .first()
    )
```

**Import hinzufügen** (falls noch nicht vorhanden):
```python
from typing import Optional
```

---

## 🧪 Testen

```bash
# 1. Server neustarten
pkill -f "python.*00_main"
./start_https_server.sh

# 2. Neue Email fetchen (oder bestehende neu verarbeiten)
# Dashboard → "Jetzt verarbeiten"

# 3. Logs prüfen - sollte zeigen:
# 💡 AI suggested tag 'Rechnung' - nicht vorhanden, übersprungen
# 📌 Tag 'Arbeit' assigned to email 123  (wenn Tag existiert)

# 4. Prüfen dass KEINE neuen Tags erstellt wurden
sqlite3 emails.db "SELECT COUNT(*) FROM email_tags;"
# Anzahl sollte gleich bleiben nach Processing
```

---

## 📊 Erwartetes Verhalten

| Szenario | Vorher | Nachher |
|----------|--------|---------|
| AI schlägt "Rechnung" vor, Tag existiert | ✅ Zugewiesen | ✅ Zugewiesen |
| AI schlägt "Rechnung" vor, Tag existiert NICHT | ⚠️ Tag erstellt + zugewiesen | 💡 Nur geloggt |
| Neuer Account, 0 Tags | 20+ Tags auto-erstellt | 0 Tags erstellt |

---

## 🔜 Nächster Schritt

Nach diesem Patch: **DESIGN_TAG_SUGGESTION_QUEUE.md** implementieren für das Queue-System.
