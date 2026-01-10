# KRITISCHER BUG: Tag-Embeddings werden falsch generiert

## 🐛 Problem

Tag-Embeddings nutzen `LocalOllamaClient` (ein CHAT-Client) statt einen dedizierten Embedding-Client. Dies führt zu komplett falschen Embeddings, die nicht mit Email-Embeddings vergleichbar sind.

**Symptom:**
- Email-zu-Email Similarity: 100%, 82%, 81% ✅ (funktioniert)
- Tag-zu-Email Similarity: 11.27% ❌ (komplett falsch!)

## 🔧 Fix: src/services/tag_manager.py

### Zeile 47-80: _get_ai_client_for_user() ERSETZEN

**VORHER:**
```python
@classmethod
def _get_ai_client_for_user(cls, user_id: int, db: Session = None):
    """Holt AI-Client für Tag-Embeddings"""
    # Cache Check
    if user_id in cls._ai_client_cache:
        return cls._ai_client_cache[user_id]
    
    try:
        ai_client_mod = import_module(".03_ai_client", "src")
        
        # 1. Ermittle Embedding-Model aus vorhandenen Emails
        embedding_model = "all-minilm:22m"  # Default-Fallback
        
        if db:
            # Sample: Erste Email mit Embedding holen
            sample_email = db.query(models.RawEmail).filter(
                models.RawEmail.user_id == user_id,
                models.RawEmail.email_embedding.isnot(None),
                models.RawEmail.embedding_model.isnot(None)
            ).first()
            
            if sample_email:
                embedding_model = sample_email.embedding_model
                logger.info(f"🔍 Tag-Embeddings: Using model from emails: {embedding_model}")
            else:
                logger.warning(f"⚠️  No emails with embeddings found for user {user_id}, using default: {embedding_model}")
        
        # 2. AI-Client mit dem ermittelten Model erstellen
        # WICHTIG: Dies MUSS ein Embedding-Model sein (nicht Chat!)
        client = ai_client_mod.LocalOllamaClient(model=embedding_model)  # ← FALSCH!
        
        cls._ai_client_cache[user_id] = client
        logger.debug(f"✅ Tag-Embeddings: {embedding_model} (auto-detected from emails)")
        return client
        
    except Exception as e:
        logger.warning(f"AI-Client nicht verfügbar: {e}")
        return None
```

**NACHHER:**
```python
@classmethod
def _get_ai_client_for_user(cls, user_id: int, db: Session = None):
    """Holt dedizierten Embedding-Client für Tag-Embeddings
    
    WICHTIG: Nutzt OllamaEmbeddingClient (05_embedding_api.py), 
    nicht LocalOllamaClient (Chat-Model)!
    
    Returns:
        OllamaEmbeddingClient oder None
    """
    # Cache Check
    if user_id in cls._ai_client_cache:
        return cls._ai_client_cache[user_id]
    
    try:
        # Import des RICHTIGEN Embedding-Clients
        embedding_api = import_module(".05_embedding_api", "src")
        
        # 1. Ermittle Embedding-Model aus vorhandenen Emails
        embedding_model = "all-minilm:22m"  # Default-Fallback
        
        if db:
            # Sample: Erste Email mit Embedding holen
            sample_email = db.query(models.RawEmail).filter(
                models.RawEmail.user_id == user_id,
                models.RawEmail.email_embedding.isnot(None),
                models.RawEmail.embedding_model.isnot(None)
            ).first()
            
            if sample_email:
                embedding_model = sample_email.embedding_model
                logger.info(f"🔍 Tag-Embeddings: Using model from emails: {embedding_model}")
            else:
                logger.warning(f"⚠️  No emails with embeddings found for user {user_id}, using default: {embedding_model}")
        
        # 2. Embedding-Client mit dem ermittelten Model erstellen
        # WICHTIG: OllamaEmbeddingClient nutzt /api/embeddings Endpoint!
        client = embedding_api.OllamaEmbeddingClient(
            model=embedding_model,
            base_url="http://127.0.0.1:11434"
        )
        
        cls._ai_client_cache[user_id] = client
        logger.info(f"✅ Tag-Embeddings: Created OllamaEmbeddingClient with {embedding_model}")
        return client
        
    except Exception as e:
        logger.error(f"Embedding-Client konnte nicht erstellt werden: {e}")
        return None
```

---

### Zeile 145: get_tag_embedding() - Methode anpassen

**VORHER:**
```python
# 2. FALLBACK: Description Embedding (semantische Beschreibung)
text_for_embedding = tag.description if tag.description else tag.name

client = cls._get_ai_client_for_user(tag.user_id, db)
if not client:
    return None

embedding = client._get_embedding(text_for_embedding)  # ← FALSCH! _get_embedding existiert nicht in OllamaEmbeddingClient
```

**NACHHER:**
```python
# 2. FALLBACK: Description Embedding (semantische Beschreibung)
text_for_embedding = tag.description if tag.description else tag.name

client = cls._get_ai_client_for_user(tag.user_id, db)
if not client:
    return None

# OllamaEmbeddingClient nutzt get_embedding() (nicht _get_embedding()!)
embedding = client.get_embedding(text_for_embedding)  # ← KORRIGIERT!
```

---

## 🧪 Testing

Nach dem Fix solltest du sehen:

```bash
# Logs:
🔍 Tag-Embeddings: Using model from emails: all-minilm:22m
✅ Tag-Embeddings: Created OllamaEmbeddingClient with all-minilm:22m
📊 Tag 'AGB Richtlinien' (description): similarity=0.8456 (auto=True, suggest=True)
✅ AUTO-ASSIGN: Tag 'AGB Richtlinien' (85%)
```

Statt:
```bash
🔍 Embedding-Modell erkannt: all-minilm:22m → nutze Heuristiken für Analyse
📊 Tag 'AGB Richtlinien' (description): similarity=0.1127 (auto=False, suggest=False)
```

---

## 📊 Erwartete Verbesserung

| Metrik | Vorher | Nachher |
|--------|--------|---------|
| Tag-zu-Email Similarity | 11.27% | **85%+** |
| Auto-Assignments | 0 | 1-2 pro Email |
| Tag-Suggestions | 0 | 2-5 pro Email |

---

## 🚀 Deployment

```bash
# 1. Backup
cp src/services/tag_manager.py src/services/tag_manager.py.backup

# 2. Änderungen anwenden
# (Code aus diesem Dokument übernehmen)

# 3. Cache löschen (wichtig!)
# Der alte Client-Cache muss invalidiert werden
python3 <<EOF
from src.02_models import get_db_session
from src.services.tag_manager import TagEmbeddingCache

db = get_db_session()
# User ID anpassen!
TagEmbeddingCache.invalidate_user_cache(user_id=1)
print("✅ Tag-Embedding Cache gelöscht")
EOF

# 4. App neu starten
pkill -f "python src/00_main.py"
python3 -m src.00_main --serve --https
```

---

## ⚠️ WICHTIG

**Dieser Bug ist KRITISCH**, weil:

1. Tag-Suggestions funktionieren **gar nicht** (11% statt 85%)
2. Alle bisherigen Tag-Embeddings im Cache sind **falsch**
3. Der Cache muss nach dem Fix **komplett gelöscht** werden

**Nach dem Fix sollte alles sofort funktionieren**, weil:
- Email-Embeddings sind korrekt
- Tag-Embeddings werden jetzt korrekt generiert
- Beide nutzen den gleichen Embedding-Endpunkt (`/api/embeddings`)
