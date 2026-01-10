# 🔍 Phase 15: Semantic Search - Implementierungs-Checkliste

**Status:** ✅ Code komplett erstellt  
**Geschätzter Aufwand:** 8-11 Stunden  
**Erstellt:** 02. Januar 2026

---

## 📁 Erstellte Dateien

| Datei | Typ | Beschreibung |
|-------|-----|--------------|
| `ph15_semantic_search.py` | Migration | DB-Felder für Embeddings |
| `semantic_search.py` | Service | Such-Logik & Embedding-Generierung |
| `PATCH_background_jobs.py` | Patch | Integration in Email-Fetch |
| `PATCH_web_app_semantic_search.py` | Patch | API Endpoints |
| `PATCH_models_semantic_search.py` | Patch | Model-Erweiterung |
| `generate_embeddings.py` | Script | Bestehende Emails nachträglich |
| `semantic_search_frontend.js` | Frontend | UI-Integration |

---

## ✅ Implementierungs-Schritte

### Schritt 1: Migration hinzufügen (5 min)
```bash
# Kopiere Migration in Alembic-Verzeichnis
cp ph15_semantic_search.py migrations/versions/

# Prüfe down_revision (anpassen falls nötig!)
# down_revision = 'ph14a_rfc_unique_key_uidvalidity'
```

### Schritt 2: Model updaten (5 min)
```python
# In src/02_models.py, zur RawEmail Klasse hinzufügen:

    # ===== PHASE 15: SEMANTIC SEARCH =====
    email_embedding = Column(LargeBinary, nullable=True)
    embedding_model = Column(String(50), nullable=True)
    embedding_generated_at = Column(DateTime, nullable=True)
```

### Schritt 3: Service erstellen (5 min)
```bash
# Kopiere Service
cp semantic_search.py src/semantic_search.py
```

### Schritt 4: Background Jobs patchen (15 min)
```python
# In src/14_background_jobs.py:

# 1. Import hinzufügen (oben)
from src.semantic_search import generate_embedding_for_email

# 2. In _persist_raw_emails() VOR Verschlüsselung:
#    Embedding generieren (siehe PATCH_background_jobs.py)
```

### Schritt 5: Web App patchen (15 min)
```python
# In src/01_web_app.py:

# 1. Import hinzufügen
from src.semantic_search import SemanticSearchService

# 2. API Endpoints hinzufügen (siehe PATCH_web_app_semantic_search.py):
#    - GET  /api/search/semantic
#    - GET  /api/emails/<id>/similar
#    - GET  /api/embeddings/stats
#    - POST /api/embeddings/generate
```

### Schritt 6: Frontend einbinden (10 min)
```html
<!-- In templates/base.html oder liste.html -->
<script src="/static/js/semantic_search.js"></script>

<!-- Oder inline das Script aus semantic_search_frontend.js -->
```

### Schritt 7: Migration ausführen (2 min)
```bash
# Backup
cp emails.db emails.db.backup_phase15

# Migration
alembic upgrade head

# Verify
sqlite3 emails.db ".schema raw_emails" | grep embedding
```

### Schritt 8: Embeddings generieren (5-30 min je nach Anzahl Emails)
```bash
# Script kopieren
cp generate_embeddings.py scripts/

# Ausführen
python scripts/generate_embeddings.py --user deine@email.com
```

---

## 🧪 Test-Checkliste

### API Tests
```bash
# Stats prüfen
curl -X GET "http://localhost:5000/api/embeddings/stats" \
  -H "Cookie: session=..."

# Semantic Search
curl -X GET "http://localhost:5000/api/search/semantic?q=Budget" \
  -H "Cookie: session=..."

# Similar Emails
curl -X GET "http://localhost:5000/api/emails/123/similar" \
  -H "Cookie: session=..."
```

### UI Tests
- [ ] Semantic Toggle erscheint neben Suchfeld
- [ ] Toggle aktiviert/deaktiviert semantische Suche
- [ ] Suchergebnisse zeigen Similarity-Prozent
- [ ] "Ähnliche Emails" Widget funktioniert in Email-Detail
- [ ] Embedding-Warnung erscheint wenn Coverage < 100%
- [ ] "Embeddings generieren" Button funktioniert

### Funktions-Tests
- [ ] "Budget" findet auch "Kostenplanung", "Finanzen"
- [ ] Embeddings werden bei neuem Fetch automatisch generiert
- [ ] Bestehende Emails können nachträglich Embeddings bekommen
- [ ] Performance: Suche < 1 Sekunde bei 1000 Emails

---

## 📊 Erwartete Ergebnisse

### Vorher (Text-Suche)
```
Query: "Budget"
→ Findet: "Projektbudget Q1", "Budget Review"
→ Findet NICHT: "Kostenplanung", "Finanzübersicht"
```

### Nachher (Semantic Search)
```
Query: "Budget"
→ Findet: 
  - "Projektbudget Q1" (94% Match)
  - "Budget Review" (91% Match)
  - "Kostenplanung Meeting" (78% Match)
  - "Finanzübersicht 2025" (72% Match)
  - "Ausgaben Q2" (65% Match)
```

---

## 🔧 Troubleshooting

### Ollama nicht erreichbar
```bash
# Prüfen
curl http://localhost:11434/api/tags

# Starten
ollama serve
```

### Kein Embedding generiert
```python
# Debug in Python
from src.semantic_search import SemanticSearchService
from src.03_ai_client import LocalOllamaClient

client = LocalOllamaClient(model="all-minilm:22m")
result = client._get_embedding("Test Text")
print(result)  # Sollte 384 floats sein
```

### Migration fehlgeschlagen
```bash
# Rollback
alembic downgrade -1

# Prüfe down_revision in Migration
# Muss zur letzten vorhandenen Migration passen!
```

---

## 📈 Performance-Hinweise

| Emails | Embedding-Generierung | Suche |
|--------|----------------------|-------|
| 100 | ~30 Sekunden | ~50ms |
| 1.000 | ~5 Minuten | ~200ms |
| 10.000 | ~50 Minuten | ~1-2 Sekunden |

**Optimierungen für viele Emails:**
- Batch-Processing mit --batch-size 100
- Embedding-Generierung im Hintergrund
- Optional: FAISS oder Annoy für ANN-Suche (>10k Emails)

---

## 🎯 Nächste Schritte nach Implementation

1. **Auto-Actions (4-6h):** Newsletter automatisch archivieren
2. **Reply Draft (4-6h):** KI-Antwort-Entwürfe
3. **Thread Summary (2-3h):** KI-Zusammenfassung von Konversationen

---

**Ready to implement! 🚀**
