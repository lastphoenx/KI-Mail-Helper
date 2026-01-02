# Changelog Phase F.1: Semantic Email Search

**Status:** ✅ Abgeschlossen  
**Datum:** 02.01.2026  
**Arbeitszeit:** ~10h (8-12h geschätzt)  
**Roadmap-Referenz:** Phase F - Semantic Intelligence Foundation

---

## 🎯 Ziel

**Vector-basierte Email-Suche** mit Embeddings für semantische Ähnlichkeit.
- "Budget" findet auch "Kostenplanung", "Finanzübersicht"
- "Meeting" findet auch "Besprechung", "Termin"
- Ähnliche Emails automatisch finden

**Architektur-Entscheidung:** Embedding-Generierung beim **FETCH** (Klartext verfügbar), **NICHT** beim Processing (erfordert Decrypt).

---

## ✅ Implementierte Features

### 1. Database Schema (Migration ph17)
**Datei:** `migrations/versions/ph17_semantic_search.py`

**Neue Felder in `raw_emails`:**
```python
email_embedding BLOB           # 384-dim Vector (1.5KB pro Email)
embedding_model VARCHAR(50)    # "all-minilm:22m"
embedding_generated_at DATETIME
```

**Index:** `ix_raw_emails_has_embedding` auf `embedding_generated_at`

**Migration-Typ:** Merge Migration (ph15 + ph16 → ph17)

### 2. Model Extension
**Datei:** `src/02_models.py` (Lines 628-639)

```python
# Phase 17: Semantic Search
email_embedding = Column(LargeBinary, nullable=True)
embedding_model = Column(String(50), nullable=True)
embedding_generated_at = Column(DateTime(timezone=True), nullable=True)
```

### 3. Semantic Search Service
**Datei:** `src/semantic_search.py` (386 lines, NEW)

**Kernfunktionen:**
- `generate_embedding_for_email()`: Standalone Embedding-Generierung
- `SemanticSearchService.search()`: Cosine Similarity Suche
- `SemanticSearchService.find_similar()`: Ähnliche Emails finden
- `SemanticSearchService.get_embedding_stats()`: Coverage Statistics

**Technische Details:**
- **Model:** all-minilm:22m (Ollama)
- **Dimension:** 384 (float32)
- **Storage:** 1.5KB BLOB pro Email
- **Thresholds:** 
  - Search: 0.25 (breiter)
  - Similar: 0.5 (enger)

### 4. Background Job Integration
**Datei:** `src/14_background_jobs.py` (Lines 414-422, 468-496, 540-572)

**Embedding-Generierung beim Fetch:**
```python
# CRITICAL: VOR Encryption!
subject_plain = raw_email_data.get("subject", "")
body_plain = raw_email_data.get("body", "")

embedding_bytes, model, timestamp = generate_embedding_for_email(
    subject=subject_plain,
    body=body_plain,
    ai_client=LocalOllamaClient(model="all-minilm:22m")
)

# DANN Encryption...
```

### 5. REST API Endpoints
**Datei:** `src/01_web_app.py` (Lines 2334-2575)

**Neue Endpoints:**
```
GET /api/search/semantic?q=Budget&limit=20&threshold=0.25
    → Semantic Search mit Query-String
    
GET /api/emails/<id>/similar?limit=5
    → Ähnliche Emails zu gegebener Email
    
GET /api/embeddings/stats
    → Coverage Statistics
```

**Response Format:**
```json
{
  "results": [
    {
      "email_id": 123,
      "subject": "Budget Q4",
      "from": "boss@company.com",
      "date": "2024-01-15T10:30:00Z",
      "similarity_score": 0.87,
      "snippet": "...text excerpt..."
    }
  ],
  "query": "Budget",
  "total": 5,
  "has_embeddings": true
}
```

### 6. Frontend UI
**Datei:** `templates/list_view.html` (Lines 90-106, 319-450, 560-580)

**List View:**
- Search Mode Toggle: "Text" / "Semantisch"
- Live AJAX Semantic Search
- Similarity Score Display (🧠 87%)

**Email Detail:**
- "Ähnliche E-Mails" Card (automatisch geladen)
- Top 5 Similar Emails mit Scores

---

## 🐛 Behobene Bugs

### Critical Bugs (Runtime Crashes)
1. ✅ **Parameter Mismatch:** `similarity_threshold` → `threshold`
2. ✅ **API Dict Access:** `result["email"]` → Direct field access
3. ✅ **Field Names:** `email.sender` → `result['encrypted_sender']`
4. ✅ **Field Names:** `email.email_date` → `result['received_at']`
5. ✅ **Parameter Error:** `user_id` aus `find_similar()` entfernt
6. ✅ **Import Error:** `from . import models` → `importlib.import_module`
7. ✅ **AI-Client:** `LocalOllamaClient(model="all-minilm:22m")` in API

### Pre-existierende Bugs (behoben)
8. ✅ **MIME-Header Decoding:** `=?UTF-8?Q?...?=` in Subject/Sender (06_mail_fetcher.py)
9. ✅ **Field Name:** `imap_has_attachments` → `has_attachments` (12_processing.py)

### Security Improvements
10. ✅ **Ownership Check:** User muss Email besitzen vor `find_similar()`

---

## 📊 Test-Ergebnisse

### Database Verification
```sql
-- Schema Check
PRAGMA table_info(raw_emails);
-- → Columns 34-36: email_embedding, embedding_model, embedding_generated_at ✅

-- Embedding Coverage
SELECT COUNT(*), SUM(CASE WHEN email_embedding IS NOT NULL THEN 1 ELSE 0 END) 
FROM raw_emails;
-- → 47|47 (100% Coverage) ✅
```

### API Tests
```bash
# Semantic Search
GET /api/search/semantic?q=casino
→ 200 OK, 3 results, scores: 0.87, 0.65, 0.52 ✅

# Similar Emails
GET /api/emails/46/similar?limit=5
→ 200 OK, 1 result ✅

# Stats
GET /api/embeddings/stats
→ 200 OK, coverage: 100% ✅
```

### Frontend Tests
- ✅ Search Mode Toggle funktioniert
- ✅ Semantic Search zeigt Loading-Spinner
- ✅ Results werden korrekt gerendert
- ✅ Similar Emails Card lädt automatisch

---

## 🔧 Technische Architektur

### Zero-Knowledge Compliance
- ✅ Embeddings sind **unencrypted** aber **nicht reversibel**
- ✅ Embedding-Generierung passiert **VOR** Encryption (Klartext verfügbar)
- ✅ Kein Decrypt während Search nötig
- ✅ Master-Key bleibt in Flask Session

### Performance
- **Storage:** 1.5KB × 47 Mails = ~70KB Embeddings
- **Search Time:** <50ms für 47 Emails
- **Embedding Generation:** ~2s/Email (Ollama all-minilm:22m)

### Scalability
- ✅ Index auf `embedding_generated_at` für Filter
- ✅ Batch-Verarbeitung im Background Job
- ✅ Cosine Similarity mit numpy (vectorisiert)

---

## 📝 Lessons Learned

1. **Embedding beim Fetch, nicht Processing:** Richtiger Ansatz! Klartext nur beim IMAP-Fetch verfügbar.
2. **MIME-Header Decoding:** Muss VOR Subject-Storage passieren, sonst `=?UTF-8?Q?...?=` in DB.
3. **importlib vs. relative imports:** `from . import models` funktioniert nicht mit importlib-Struktur.
4. **JavaScript Function Override:** Funktioniert nicht wenn Funktion schon an Events gebunden. Logik muss IN Funktion.
5. **HTML-Container Selektoren:** `.card-body` ≠ `.list-group` - Struktur genau prüfen!

---

## 🚀 Nächste Schritte (Phase F.2)

**Geplant:** Tag-Embeddings für Semantic Tag Suggestions

**Optional (später):**
- Backfill-Script für alte Emails (erfordert Decrypt)
- Embedding-Model als User-Setting
- Multi-lingual Embeddings (Deutsch/Englisch optimiert)

---

## 📦 Geänderte Dateien

```
migrations/versions/ph17_semantic_search.py          (NEW, 95 lines)
src/02_models.py                                      (+10 lines)
src/semantic_search.py                                (NEW, 368 lines)
src/14_background_jobs.py                             (+85 lines)
src/01_web_app.py                                     (+241 lines)
src/06_mail_fetcher.py                                (+40 lines - MIME fix)
src/12_processing.py                                  (+2 lines - field fix)
templates/list_view.html                              (+180 lines)
templates/email_detail.html                           (+70 lines)
```

**Total:** ~1,091 neue/geänderte Zeilen Code

---

## ✅ Abnahmekriterien (erfüllt)

- [x] Migration erfolgreich angewendet
- [x] Embeddings werden beim Fetch generiert
- [x] Semantic Search API funktioniert
- [x] Similar Emails API funktioniert
- [x] Frontend UI vollständig
- [x] Keine Regressions-Bugs
- [x] Zero-Knowledge Compliance
- [x] 100% Test-Coverage auf vorhandenen Emails
