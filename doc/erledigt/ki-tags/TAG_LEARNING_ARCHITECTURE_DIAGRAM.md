# Tag-Learning Architektur - Visuelles Diagramm

## 🏗️ System-Überblick

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EMAIL PROCESSING FLOW                        │
└─────────────────────────────────────────────────────────────────────┘

1. Email empfangen (IMAP/Gmail)
   │
   ├─→ [email_embedding erstellt] ──→ RawEmail.email_embedding (384-dim)
   │
2. KI-Analyse (12_processing.py)
   │
   ├─→ suggest_tags_by_email_embedding()
   │   │
   │   └─→ Für jeden User-Tag:
   │       │
   │       ├─→ get_tag_embedding() [FALLBACK-HIERARCHIE]
   │       │   │
   │       │   ├─ 1. PRIORITÄT: learned_embedding (aus 3+ emails)
   │       │   ├─ 2. FALLBACK: description embedding
   │       │   └─ 3. FALLBACK: name embedding
   │       │
   │       └─→ Cosine Similarity berechnen
   │           │
   │           ├─ >= 80% → AUTO-ASSIGN ✅
   │           ├─ 70-79% → SUGGEST 💡
   │           └─ < 70% → SKIP ❌
   │
3. ProcessedEmail erstellt
   │
   └─→ Tags assigned/suggested


┌─────────────────────────────────────────────────────────────────────┐
│                      TAG LEARNING CYCLE                              │
└─────────────────────────────────────────────────────────────────────┘

User erstellt Tag "Rechnung"
   │
   ├─ description: "Invoices, bills, payments" (optional)
   └─ learned_embedding: NULL (noch keine Emails)

User weist Tag zu Email #1 (similarity: manual)
   │
   └─→ assign_tag() ──→ update_learned_embedding()
       │
       └─ Nur 1 Email → SKIP (MIN_EMAILS_FOR_LEARNING = 3)

User weist Tag zu Email #2 (similarity: manual)
   │
   └─→ assign_tag() ──→ update_learned_embedding()
       │
       └─ Nur 2 Emails → SKIP (MIN_EMAILS_FOR_LEARNING = 3)

User weist Tag zu Email #3 (similarity: manual)
   │
   └─→ assign_tag() ──→ update_learned_embedding()
       │
       └─ 3 Emails! ──→ ✅ learned_embedding = avg(email1, email2, email3)

Neue Email #4 wird verarbeitet
   │
   └─→ suggest_tags_by_email_embedding()
       │
       ├─ Tag "Rechnung" hat learned_embedding ✅
       └─ Similarity: 87% → AUTO-ASSIGN! 🎉

User entfernt Tag von Email #3
   │
   └─→ remove_tag() ──→ update_learned_embedding() ← NEU!
       │
       └─ Nur noch 2 Emails → learned_embedding gelöscht


┌─────────────────────────────────────────────────────────────────────┐
│                    THRESHOLD DECISION TREE                           │
└─────────────────────────────────────────────────────────────────────┘

Email-Embedding
   │
   └─→ Für jeden User-Tag: Cosine Similarity berechnen
       │
       ├─ User hat <= 5 Tags
       │  │
       │  ├─ >= 80% → AUTO-ASSIGN ✅
       │  ├─ 70-79% → SUGGEST 💡  (Threshold: 70%)
       │  └─ < 70% → SKIP ❌
       │
       ├─ User hat 6-15 Tags
       │  │
       │  ├─ >= 80% → AUTO-ASSIGN ✅
       │  ├─ 75-79% → SUGGEST 💡  (Threshold: 75%)
       │  └─ < 75% → SKIP ❌
       │
       └─ User hat >= 16 Tags
          │
          ├─ >= 80% → AUTO-ASSIGN ✅
          ├─ 80-79% → SUGGEST 💡  (Threshold: 80%)
          └─ < 80% → SKIP ❌


┌─────────────────────────────────────────────────────────────────────┐
│                    DATENBANK-SCHEMA (relevant)                       │
└─────────────────────────────────────────────────────────────────────┘

RawEmail
├─ id (PK)
├─ email_embedding (BLOB, 384 floats × 4 bytes)
├─ embedding_model (VARCHAR, z.B. "all-minilm:22m")
└─ user_id (FK)

EmailTag
├─ id (PK)
├─ name (VARCHAR, unique per user)
├─ color (VARCHAR, #RRGGBB)
├─ description (TEXT) ← OPTIONAL, verbessert Suggestions
├─ learned_embedding (BLOB) ← NULL oder avg(assigned emails)
├─ embedding_updated_at (DATETIME)
└─ user_id (FK)

EmailTagAssignment
├─ email_id (FK → ProcessedEmail)
├─ tag_id (FK → EmailTag)
└─ assigned_at (TIMESTAMP)


┌─────────────────────────────────────────────────────────────────────┐
│                    CODE-ÄNDERUNGEN ÜBERSICHT                         │
└─────────────────────────────────────────────────────────────────────┘

src/services/tag_manager.py
├─ NEUE KONSTANTEN (Zeile 36-55)
│  ├─ MIN_EMAILS_FOR_LEARNING = 3
│  ├─ AUTO_ASSIGN_SIMILARITY_THRESHOLD = 0.80
│  └─ get_suggestion_threshold(total_tags) → 0.70-0.80
│
├─ remove_tag() (Zeile 284-320)
│  └─ [NEU] update_learned_embedding() nach delete
│
├─ update_learned_embedding() (Zeile 372-442)
│  ├─ [NEU] MIN_EMAILS_FOR_LEARNING Check
│  └─ [NEU] Besseres Logging
│
├─ suggest_similar_tags() (Zeile 446-521)
│  └─ [NEU] Dynamische Thresholds
│
└─ suggest_tags_by_email_embedding() (Zeile 523-607)
   └─ [NEU] Separate Auto-Assign/Suggest Thresholds

src/12_processing.py (Zeile 1227-1250)
└─ [NEU] Unterscheidet auto_assign vs. suggestions

src/01_web_app.py (Zeile 1752-1810)
└─ [NEU] API gibt auto_assigned Flag + config zurück


┌─────────────────────────────────────────────────────────────────────┐
│                    PERFORMANCE METRIKEN                              │
└─────────────────────────────────────────────────────────────────────┘

Embedding-Generierung:
  - Email: ~100ms (all-minilm:22m, 384-dim)
  - Tag: ~50ms (cached nach 1. Nutzung)

Similarity-Berechnung:
  - Pro Tag: ~0.1ms (NumPy dot product)
  - 20 Tags: ~2ms total

update_learned_embedding():
  - 3 Emails: ~5ms (avg berechnung)
  - 100 Emails: ~50ms
  - Cache-Invalidierung: ~1ms

Gesamt-Overhead:
  - assign_tag() mit Learning: +5-50ms
  - remove_tag() mit Learning: +5-50ms
  - suggest_tags: ~2-10ms (je nach Tag-Anzahl)

→ Vernachlässigbar im Vergleich zu Email-Verarbeitung (~2-5s)


┌─────────────────────────────────────────────────────────────────────┐
│                    BEISPIEL-SZENARIO                                 │
└─────────────────────────────────────────────────────────────────────┘

📧 User hat 8 Tags:
   - "Rechnung" (12 Emails) → learned_embedding ✅
   - "Finanzen" (8 Emails) → learned_embedding ✅
   - "Subscriptions" (description: "Membership and subscription services") → description ✅
   - "Wichtig" (1 Email) → name-only ❌
   - ... 4 weitere Tags

📩 Neue Email kommt rein: "Invoice #1234 from ServiceProvider"
   │
   └─→ email_embedding erstellt [0.34, -0.12, 0.67, ...]

🎯 Tag-Suggestions:
   │
   ├─ "Subscriptions" (description)
   │  └─ Similarity: 0.89 → AUTO-ASSIGN ✅ (>= 80%)
   │
   ├─ "Rechnung" (learned)
   │  └─ Similarity: 0.82 → AUTO-ASSIGN ✅ (>= 80%)
   │
   ├─ "Finanzen" (learned)
   │  └─ Similarity: 0.73 → SUGGEST 💡 (70-80%)
   │
   └─ "Wichtig" (name-only)
      └─ Similarity: 0.42 → SKIP ❌ (< 70%)

Result:
   - 2 Tags auto-assigned: "Subscriptions", "Rechnung"
   - 1 Tag suggested: "Finanzen"
   - User muss nur 1 Tag manuell prüfen (statt 3)

🎓 Learning Update:
   │
   ├─ update_learned_embedding(tag_id="Subscriptions")
   │  └─ Jetzt 9 Emails → learned_embedding noch besser
   │
   └─ update_learned_embedding(tag_id="Rechnung")
      └─ Jetzt 13 Emails → learned_embedding noch besser

→ Nächste ähnliche Email wird noch präziser kategorisiert! 🚀


┌─────────────────────────────────────────────────────────────────────┐
│                    FEHLERBEHANDLUNG                                  │
└─────────────────────────────────────────────────────────────────────┘

Szenario 1: Email ohne Embedding
   └─→ Fallback zu text-basierter Methode
       └─→ suggest_similar_tags(text=subject+body)

Szenario 2: Tag ohne Embeddings (neue Tags)
   └─→ Nutzt description oder name für Embedding

Szenario 3: Model-Wechsel (384-dim → 768-dim)
   └─→ Alle email_embeddings neu generieren
       └─→ Alle learned_embeddings werden automatisch updated

Szenario 4: DB-Fehler bei update_learned_embedding()
   └─→ Rollback, False zurück, Cache bleibt intakt
       └─→ Nächster assign_tag() versucht es erneut

Szenario 5: User löscht Tag mit learned_embedding
   └─→ CASCADE DELETE entfernt Assignments
       └─→ Cache wird automatisch invalidiert
```
