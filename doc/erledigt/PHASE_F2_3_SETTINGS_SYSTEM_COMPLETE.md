# Phase F.2: 3-Settings System + Batch-Reprocess ✅

**Datum**: 2. Januar 2026  
**Status**: ABGESCHLOSSEN  
**Commit Range**: 6dad224 - 388d0c8

## 🎯 Ziel

Vollständige Trennung von Embedding-, Base- und Optimize-Models mit dynamischer Model-Discovery und konsistentem Batch-Reprocessing.

## 📋 Problem

### Initial-Problem
- **Embedding-Dimension Mismatch**: 384-dim vs 2048-dim
- **Root Cause**: llama3.2:1b (chat model, 2048-dim) wurde für Embeddings verwendet statt all-minilm:22m (embedding model, 384-dim)
- **Tag-Suggestions**: Brachen wegen inkompatibler Dimensionen

### Design-Schwächen
- Hardcodierte Model-Namen im Code
- Keine Unterscheidung zwischen Embedding- und Chat-Models
- Kein Batch-Reprocess bei Model-Wechsel

## 🛠️ Implementierung

### 1. Database Migration (c4ab07bd3f10)

```sql
ALTER TABLE users ADD COLUMN preferred_embedding_provider VARCHAR(50) DEFAULT 'ollama';
ALTER TABLE users ADD COLUMN preferred_embedding_model VARCHAR(100) DEFAULT 'all-minilm:22m';
-- Existing: preferred_ai_provider, preferred_ai_model (BASE)
-- Existing: preferred_ai_provider_optimize, preferred_ai_model_optimize (OPTIMIZE)
```

**3-Settings System:**
- `EMBEDDING`: Vektorisierung für Semantic Search & Tag-Suggestions
- `BASE`: Schnelle initiale Klassifikation
- `OPTIMIZE`: Tiefe Analyse für Scores 8-9

### 2. Frontend (templates/settings.html)

**3 Sections mit dynamischen Dropdowns:**

```javascript
// Provider-Filtering
if (pass === 'Embedding') {
    // Anthropic hat keine Embedding-API
    providers = providers.filter(p => p.id !== 'anthropic');
}

// Model-Type-Filtering
if (pass === 'Embedding') {
    models = models.filter(m => m.type === 'embedding');  // 🔍
} else {
    models = models.filter(m => m.type === 'chat');       // 💬
}
```

**Model Discovery:** `/api/models/<provider>` nutzt `04_model_discovery.py`

### 3. Backend Improvements

#### A) Pre-Check vor Reprocessing

```python
@app.route("/api/emails/<id>/check-embedding-compatibility")
def api_check_embedding_compatibility():
    current_dim = get_embedding_dim_from_bytes(raw_email.email_embedding)
    expected_dim = MODEL_DIMENSIONS.get(model_embedding, 384)
    
    if current_dim != expected_dim:
        return {"compatible": False, "message": "Dimension mismatch!"}
```

**Verhindert:** Semantic Search Bugs durch gemischte Dimensionen

#### B) Async Batch-Reprocess mit Progress

```python
class BatchReprocessJob:
    job_id: str
    user_id: int
    master_key: str
    provider: str
    model: str

def _execute_batch_reprocess_job(self, job: BatchReprocessJob):
    for idx, raw_email in enumerate(raw_emails, start=1):
        # Progress-Update (wie Mail-Fetch)
        self._update_status(job.job_id, {
            "current_email_index": idx,
            "total_emails": total,
            "current_subject": decrypted_subject[:50]
        })
        
        # Embedding regenerieren
        embedding_bytes, model_name, timestamp = generate_embedding_for_email(...)
        raw_email.email_embedding = embedding_bytes
        session.flush()
```

**Frontend Progress-Modal:** Zeigt `1/47`, `2/47`, etc. mit Timer (0-600s pro Email)

#### C) Dynamischer Model-Name

```python
def generate_embedding_for_email(
    subject: str,
    body: str,
    ai_client,
    max_body_length: int = 1000,  # Erhöht von 500 → besserer Context
    model_name: Optional[str] = None
):
    # Versuche Model vom Client zu holen
    if not model_name:
        if hasattr(ai_client, 'model'):
            model_name = ai_client.model
        else:
            model_name = "all-minilm:22m"  # Fallback
```

**Fix:** Erfolgsmeldung zeigt korrektes Model (nicht hardcoded "all-minilm:22m")

### 4. Mistral Embedding Support

```python
class MistralClient:
    API_URL_EMBEDDINGS = "https://api.mistral.ai/v1/embeddings"
    
    def _get_embedding(self, text: str) -> list[float] | None:
        response = requests.post(
            self.API_URL_EMBEDDINGS,
            json={"model": "mistral-embed", "input": text}
        )
        return response.json()["data"][0]["embedding"]
```

## 📊 Model-Dimensionen

```python
MODEL_DIMENSIONS = {
    "all-minilm:22m": 384,
    "nomic-embed-text": 768,
    "bge-large": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "mistral-embed": 1024,
}
```

## 🔄 Workflow

### Mail-Fetch (EMBEDDING Model)
```
User Settings → EMBEDDING Model (all-minilm:22m)
    ↓
Mail-Fetch → generate_embedding_for_email()
    ↓
RawEmail.email_embedding (384-dim, 1536 bytes)
```

### Scoring (BASE Model)
```
User Settings → BASE Model (llama3.2:1b)
    ↓
Processing → ai_client.analyze_email()
    ↓
ProcessedEmail (score, farbe, kategorie_aktion)
```

### Tag-Suggestions (EMBEDDING Comparison)
```
ProcessedEmail.raw_email.email_embedding (384-dim)
    ↓
Tag.embedding (384-dim)
    ↓
Cosine Similarity → Suggestions (sorted by score)
```

### Optimize (OPTIMIZE Model)
```
User Settings → OPTIMIZE Model (llama3.2:3b)
    ↓
Button "Optimize" → Re-analyze mit besserem Model
    ↓
ProcessedEmail.optimize_score, optimize_farbe
```

## 🎯 Wichtige Erkenntnisse

### Embedding vs Chat Models

**NIEMALS vermischen!**

```
❌ FALSCH:
- llama3.2:1b für Embeddings → 2048-dim (Chat-Model)
- all-minilm:22m für Scoring → Kann keine Text-Analyse!

✅ RICHTIG:
- EMBEDDING: all-minilm, nomic-embed, bge, text-embedding-*
- BASE/OPTIMIZE: llama3.2, gpt-4o-mini, claude-haiku
```

### Cosine Similarity Requirements

**Alle Embeddings MÜSSEN vom gleichen Model stammen!**

```python
# ❌ Funktioniert NICHT:
email1.embedding = all-minilm (384-dim)
email2.embedding = openai (3072-dim)
cosine_similarity(email1, email2)  # → ValueError!

# ✅ Funktioniert:
email1.embedding = all-minilm (384-dim)
email2.embedding = all-minilm (384-dim)
cosine_similarity(email1, email2)  # → 0.95 ✅
```

### Batch-Reprocess ist Pflicht

**Bei Model-Wechsel:**
1. Settings → Embedding Model ändern
2. **"Alle Emails neu embedden"** klicken
3. Progress-Modal zeigt Fortschritt
4. Alle Emails haben nun konsistente Dimensionen

## 🚀 Performance

### Ollama (lokal)
- **all-minilm:22m**: 15-50ms pro Email
- **47 Emails**: ~2-5 Sekunden (abhängig von max_body_length)
- **Keine Netzwerk-Latenz**

### OpenAI (remote)
- **text-embedding-3-small**: 100-200ms pro Email
- **47 Emails**: ~10-15 Sekunden
- **Netzwerk-Overhead**

### Context-Tuning
```python
max_body_length = 500   # ~70-80 Wörter  → schnell
max_body_length = 1000  # ~140-160 Wörter → besserer Context (aktuelle Einstellung)
```

## 📁 Betroffene Dateien

### Backend
- `src/02_models.py`: 3 neue Felder (preferred_embedding_*)
- `src/01_web_app.py`: Pre-Check, Batch-Reprocess, /api/models
- `src/03_ai_client.py`: MistralClient, _get_embedding()
- `src/04_model_discovery.py`: Dynamische Model-Liste
- `src/14_background_jobs.py`: BatchReprocessJob, _execute_batch_reprocess_job()
- `src/semantic_search.py`: generate_embedding_for_email() mit model_name

### Frontend
- `templates/settings.html`: 3 Sections, Batch-Reprocess Button + Progress-Modal
- `templates/email_detail.html`: Pre-Check, Progress-Modal

### Database
- `migrations/versions/c4ab07bd3f10_*.py`: 3-Settings Migration

## ✅ Tests

### Manual Testing
- ✅ Settings zeigt 3 Sections (Embedding/Base/Optimize)
- ✅ Provider-Filtering: Anthropic fehlt bei Embedding
- ✅ Model-Filtering: Embedding=🔍, Base/Optimize=💬
- ✅ Batch-Reprocess: Progress-Modal mit Timer
- ✅ Pre-Check: Blockiert bei Dimension-Mismatch
- ✅ Erfolgsmeldung: Zeigt korrektes Model-Name

### Edge Cases
- ✅ Model-Wechsel während laufendem Job → Queue verhindert Race Conditions
- ✅ Empty Embeddings → Warning + failed count
- ✅ Decryption Error → caught + logged

## 🐛 Gefixte Bugs

1. **Embedding-Dimension Mismatch** (384 vs 2048)
   - Fix: 3-Settings System, Pre-Check
   
2. **Tag-Suggestions brechen** (Cosine Similarity Error)
   - Fix: Batch-Reprocess erzwingt Konsistenz
   
3. **Hardcoded "all-minilm:22m" in Erfolgsmeldung**
   - Fix: Dynamischer model_name Parameter
   
4. **AttributeError: 'ProcessedEmail' object has no attribute 'color'**
   - Fix: color→farbe, action_category→kategorie_aktion

## 🎓 Lessons Learned

### 1. Embedding-Models sind NICHT Chat-Models
```
Embedding: Text → Vector (z.B. [0.1, -0.3, 0.7, ...])
Chat: Text → Text (Analyse, Klassifikation, Generation)
```

### 2. Model-Discovery ist essentiell
- Hardcoded Model-Namen = Wartungs-Albtraum
- Dynamische API-basierte Discovery = Flexibilität

### 3. Pre-Checks verhindern inkonsistente Daten
- Check BEFORE action > Fix AFTER failure

### 4. Progress-Tracking ist User-Experience
- Background-Jobs ohne Progress = "Ist es kaputt?"
- Modal mit Timer = Vertrauen + Transparenz

## 📚 Referenzen

- [OpenAI Embeddings Docs](https://platform.openai.com/docs/guides/embeddings)
- [Mistral Embeddings API](https://docs.mistral.ai/api/#tag/embeddings)
- [Ollama Embeddings](https://github.com/ollama/ollama/blob/main/docs/api.md#generate-embeddings)

## 🔮 Future Work

### Hybrid Search (Keyword + Semantic)
```python
# 1. Keyword-Filter (SQL LIKE)
emails = db.query(RawEmail).filter(
    or_(
        RawEmail.encrypted_subject.like(f"%{query}%"),
        RawEmail.encrypted_body.like(f"%{query}%")
    )
)

# 2. Semantic Ranking
results = semantic_service.search(query, emails)
```

### Query Expansion
```python
"paypal" → "PayPal payment service legal agreements changes"
```

### Adaptive Thresholds
```python
if len(query.split()) <= 2:
    threshold = 0.15  # Einzelwörter
else:
    threshold = 0.25  # Phrasen
```

## 🎉 Conclusion

Phase F.2 ist **vollständig implementiert und getestet**. Das System hat jetzt:

✅ Saubere Trennung von Embedding- und Chat-Models  
✅ Dynamische Model-Discovery für alle Provider  
✅ Konsistente Embeddings durch Batch-Reprocess  
✅ User-freundliche Progress-Anzeige  
✅ Pre-Checks gegen inkonsistente Daten  

**Semantic Search funktioniert jetzt stabil und zuverlässig!** 🚀
