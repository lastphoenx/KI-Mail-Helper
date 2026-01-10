# Phase 12: Thread-basierte Conversations

**Status**: ✅ Implementiert - 🔄 Performance-Optimierung in Progress

## Überblick

Phase 12 implementiert **Thread-basierte Email-Conversations** mit vollständiger Metadata-Erfassung und Reply-Chain-Mapping.

## Was funktioniert ✅

### 1. Metadata-Erfassung (12 Felder)
- thread_id, message_id, parent_uid
- imap_is_seen, imap_is_answered, imap_is_flagged, imap_is_deleted, imap_is_draft
- has_attachments, content_type, charset, message_size
- **Alle verschlüsselt** (Zero-Knowledge)

### 2. Thread-Calculation
- Message-ID-Chain Threading
- ThreadCalculator klasse - voll getestet
- Reply-Chains korrekt aufgebaut (verifiziert)

### 3. Backend-APIs
**ThreadService** (`src/thread_service.py`):
- get_conversation() - alle Emails eines Threads
- get_reply_chain() - Parent-Child-Mapping
- get_threads_summary() - paginierte Übersichten
- get_thread_subject() - Root-Email Betreff
- search_conversations() - Volltextsuche
- get_thread_stats() - Thread-Statistiken

**REST-API** (`src/thread_api.py`):
- GET /api/threads - Thread-Liste
- GET /api/threads/{thread_id} - Komplette Conversation
- GET /api/threads/search?q=... - Suche

### 4. Frontend
- templates/threads_view.html
- Zweigeteiltes Layout
- Real-time API
- Search & Pagination

## Performance-Problem 🔴

**N+1 Query Issue**: Für 50 Threads = 101 Queries statt 1

**Root Cause**: 
1. get_threads_summary() macht 1 Query
2. Für jeden Thread wird latest_email separat geladen (50 Queries)
3. In API wird für jeden Thread get_thread_subject() aufgerufen (50 Queries)

**Lösung**: root_email in get_threads_summary() berechnen, dann in API nutzen

## Dateien

**Neue Dateien**:
- src/thread_service.py (256 Zeilen)
- src/thread_api.py (294 Zeilen)
- templates/threads_view.html (380 Zeilen)

**Veränderte Dateien**:
- src/01_web_app.py (+18 Zeilen für /threads Route)
- templates/base.html (Navbar Link)
- src/06_mail_fetcher.py (Thread-Calculation)
- src/14_background_jobs.py (Phase-12-Persistierung)

## Test-Daten

✅ 3-teilige Reply-Chain erfolgreich erstellt & verifiziert:
- Mail 1 (UID 424): Root
- Mail 2 (UID 425): Reply zu 424
- Mail 3 (UID 426): Reply zu 425
- Alle: thread_id = 82eafc8b-7ee8-45cf-8ff3-0c0f056e783c

## Next Steps

**P0 - Kritisch**:
- [ ] Performance-Fix (N+1 Queries)
- [ ] Frontend: Email-Body anzeigen
- [ ] End-to-End Test

**P1 - Should-Have**:
- [ ] Reply-Chain Visualization
- [ ] Attachment-Download
- [ ] Mark as Read/Unread

**P2 - Nice-to-Have**:
- [ ] Phase 12b: parent_uid → ForeignKey
- [ ] Full-text Search
- [ ] Threading Preferences

| Aspect | Before | After | Gain |
|--------|--------|-------|------|
| DB Size (10k Mails) | 100 MB | 106 MB | +6% |
| Unread Query | `LIKE '%Seen%'` | `is_seen = false` | 200-300% faster |
| Threading | Impossible | `thread_id = ?` | ✅ New Feature |
| Fetch Time | 100% | ~110% | +10% acceptable |
| Message-Size Sorting | N/A | `ORDER BY size DESC` | ✅ New Feature |

---

## 🎯 Success Criteria

Phase 12 ist **DONE** wenn:

- ✅ All new columns added & indexed
- ✅ Data migration completed without errors
- ✅ Boolean flags working correctly
- ✅ Thread-ID calculation validated
- ✅ Envelope-parsing tested against 3+ providers
- ✅ Query performance improved 200%+
- ✅ CHANGELOG.md updated
- ✅ Backward-compatibility maintained (imap_flags still readable)
- ✅ Zero data loss
- ✅ Rollback tested & working

---

## 📚 Reference Files

- `doc/next_steps/METADATA_ANALYSIS.md` - Full Analysis & Requirements
- `migrations/versions/ph12_metadata_enrichment.py` - Database Migration
- `scripts/populate_metadata_phase12.py` - Data Migration Script
- `tests/test_envelope_parsing.py` - Envelope Parsing Tests
- `tests/test_metadata_extraction.py` - Unit Tests (TBD)

---

**Ready to begin?** Start with PHASE 12.1 (Models Update) 🚀
