# Phase 11.5 IMAP - Sauberer Neuaufbau (Option B)

**Status:** Analyse & Planung (kein Code!)  
**Datum:** 2025-12-29  
**Ziel:** Entscheidungsgrundlage für Sauberer Neuaufbau vs Quick-Fix

---

## 📊 PUNKT 1: COMMIT-HISTORY ANALYSE

### 🔴 Aktueller Zustand (Commit 1b5c191 - HEAD)

```
1b5c191  Bugfixes Phase 11 Review  ← AKTUELL (HEAD)
├─ Phase 11a-d: AI/ML Features (embeddings, tagging)
├─ UNTRACKED FILES (nie committed!):
│  ├── src/11_imap_diagnostics.py (20.8 KB)
│  ├── src/11_imap_flags_detector.py (14.8 KB)
│  ├── src/11_imap_sync_engine.py (33.6 KB)
│  ├── src/services/provider_knowledge_base.py
│  ├── docs/PHASE_11_IMAP_ARCHITECTURE.md (47 KB - 1532 Zeilen!)
│  ├── docs/IMAP_SEARCH_FIXES.md
│  ├── templates/test_phase11.html
│  └── templates/account_sync_settings.html
├─ MODIFIED FILES (lokal geändert, nicht committed):
│  ├── src/01_web_app.py (neue endpoints für Phase 11.5)
│  ├── src/02_models.py (schema changes)
│  ├── src/06_mail_fetcher.py (änderungen)
│  └── requirements.txt (neue dependencies)
└─ Phase 10a-f: Tag-System (funktioniert)
```

### ⚠️ KERNPROBLEM: Work-In-Progress nie finalisiert

| Aspekt | Status | Details |
|--------|--------|---------|
| **Dokumentation** | ✅ Umfangreich | 1532 Zeilen - aber nie reviewt |
| **Code** | 🔴 Fehler 500 | Untracked, Bugs vorhanden |
| **Testing** | ❌ Keine | Null Tests |
| **Git Tracking** | ❌ Nicht committed | Nur lokal |
| **Dependencies** | ⚠️ Unklar | Welche neuen Libs? |

---

### 🟢 Letzter Stabiler Punkt

**Commit:** `a40b9fb` oder `170c942`  
**Beschreibung:** "fix: Tags und E-Mail-Filter verbessert" / "Phase 10f"  
**Zustand:** 
- ✅ Tag-System funktioniert
- ✅ Security-Fixes aus Phase 9 integriert
- ✅ Mail-Fetcher für OAuth/IMAP vorhanden
- ✅ Alle Dependencies committed und tested
- ✅ Git-History clean

**IMAP-State bei stabilen Commits:**
```
- Phase 8b (af19229): Zero-Knowledge + DEK/KEK Pattern
  → MailFetcher (06_mail_fetcher.py) arbeitet mit imaplib
  → Funktioniert aber sehr basic

- Kein Phase 11.5 IMAP-Sync-System vorhanden
  → Keine Folder-Management
  → Keine Flag-Detection
  → Keine Priority-Based Fetching
```

---

## 📋 PUNKT 2: PHASE-PLAN für Sauberen Neuaufbau

### **Phase 11.5 - Realisierung mit IMAPClient**

#### **Phase 11.5.0: Vorbereitung (0.5h)**
```
Status: Vorbereitung
□ Alte untracked Files sichern (Archiv)
□ HEAD auf stabilen Commit zurücksetzen
□ requirements.txt mit IMAPClient-Dependencies aktualisieren
□ Neue DB-Migration für mail_account_sync_configs planen
```

**Abhängigkeiten zu prüfen:**
- imapclient (>=3.0.0) - offiziell unterstützte Library
- imaplib (stdlib) - nicht nötig, IMAPClient nutzt es intern

---

#### **Phase 11.5a: IMAP Connection Diagnostics (2-3h)**
```
Status: Neuer Code aus reiner IMAPClient-API
Datei: src/11_imap_diagnostics.py (neu, clean)

Ziele:
  □ Provider-Erkennung (Gmail, GMX, Outlook, etc.)
  □ Server-Capabilities testen (IDLE, COMPRESS, OAUTH2)
  □ Folder-Struktur auslesen (mit UTF-7 Decoding ✓)
  □ Provider-Level Caching (30 Tage TTL)

Tests:
  □ Unit-Tests mit Mock-IMAP-Server
  □ Integration-Test mit echtem Account (GMX)
  □ Error-Handling bei Timeout/Auth-Fehler
```

**Kritische Punkte:**
- ✅ IMAPClient.list_folders() gibt (flags, delimiter, name) zurück
  - flags sind BYTES → müssen dekodiert werden
  - name ist bereits UTF-7 decodiert ✓
- ✅ IMAP CAPABILITY command für Provider-Features
- ✅ Caching in DB: `MailProviderCapabilities` table

---

#### **Phase 11.5b: IMAP Flag Detection (1.5-2h)**
```
Status: Neuer Code aus reiner IMAPClient-API
Datei: src/11_imap_flags_detector.py (neu, clean)

Ziele:
  □ Standard-Flags erkennen (\\Seen, \\Answered, \\Flagged, etc.)
  □ Custom-Flags detektieren (GMX: $Spam, $NotSpam, etc.)
  □ Provider-spezifische Flags mappen
  □ Fallback-Strategie bei leeren Mailboxen

Tests:
  □ Unit-Tests für Flag-Parsing
  □ Test mit verschiedenen Providern
  □ Fallback-Test (empty mailbox)
```

**Kritische Punkte:**
- ✅ IMAPClient.append() mit test-flag + delete für Detection
- ✅ CAPABILITY-Parsing für erweiterte Flags
- ✅ Caching in DB: `MailAccountFlagMapping` table

---

#### **Phase 11.5c: Selective Sync Config (1h)**
```
Status: DB-Schema + API-Layer
Dateien:
  □ src/02_models.py - MailAccountSyncConfig ORM-Model
  □ Migration - mail_account_sync_configs table
  □ src/01_web_app.py - API: GET/POST /api/accounts/{id}/sync-config

Ziele:
  □ User-definierte Sync-Settings speichern
  □ Folder-Whitelist/Blacklist
  □ High-Priority Sender/Keywords
  □ Bandbreitenlimits
  □ Timing (full/incremental sync schedule)

Tests:
  □ API-Tests für CRUD
  □ Validation-Tests (invalid folder names, etc.)
  □ Default-Config-Tests
```

**Kritische Punkte:**
- ✅ JSON fields für flexible Konfiguration (folders, senders, keywords)
- ✅ Defaults setzen (z.B. sync_mode="ALL", max_days_back=90)

---

#### **Phase 11.5d: IMAP Sync Engine (3-4h)**
```
Status: Core-Logic mit IMAPClient
Datei: src/11_imap_sync_engine.py (neu, clean)

Ziele:
  □ 3-Phase Priority Fetching
    Phase A: High-Priority (senders + keywords)
    Phase B: Recent (SINCE last_sync)
    Phase C: Older (BEFORE last_sync, limited date range)
  
  □ Folder-Iteration (mit Fehlertoleranz)
  □ UID-Tracking für Deduplication
  □ Email-Speicherung in RawEmail table
  □ Metadaten-Erfassung (size, flags, folder)
  □ Error Recovery (retry logic)

Tests:
  □ Unit-Tests für Search-Query-Buildup
  □ Integration-Test: Kompletter Sync-Flow
  □ Error-Scenario-Tests (timeout, connection lost, etc.)
  □ Performance-Tests (Sync-Zeiten)
```

**Kritische Punkte:**
- ✅ IMAPClient.search() mit RFC3501-konformen Queries
- ✅ IMAPClient.fetch() mit FLAGS + RFC822.SIZE metadata
- ✅ Deduplication via UID + folder in RawEmail table
- ✅ Error-Handling: reconnect, retry, skip folder

---

#### **Phase 11.5e: API Integration (1.5h)**
```
Status: Endpoints in src/01_web_app.py
Endpoints:
  □ GET /api/accounts/{id}/diagnose
  □ POST /api/accounts/{id}/detect-flags
  □ GET /api/accounts/{id}/sync-config
  □ POST /api/accounts/{id}/sync-config (update)
  □ POST /api/accounts/{id}/sync (trigger manual sync)
  □ GET /api/accounts/{id}/sync-status
  □ GET /api/accounts/{id}/folders
  □ GET /api/accounts/{id}/emails (with filtering)

Tests:
  □ Auth-Tests (must login)
  □ Endpoint-Tests mit real account
  □ Error-Response-Tests
  □ JSON-Serialization-Tests (NO BYTES!)
```

**Kritische Punkte:**
- ✅ JSON serialization: Bytes → str conversions
- ✅ Error handling: try-except mit proper logging
- ✅ Session security: account ownership check

---

#### **Phase 11.5f: Frontend Dashboard (1.5-2h)**
```
Status: templates/test_phase11.html (rewrite clean)
Features:
  □ Account Selector (dropdown)
  □ Diagnose Button → Shows provider info
  □ Flag Detection → Button + Results
  □ Sync Config UI → Form with validation
  □ Manual Sync Trigger → Button + Progress
  □ Folder Listing → Table with metadata
  □ Email List → With filters (folder, read, flagged)
  □ Live Logs → WebSocket oder Polling

Tests:
  □ UI-Rendering-Tests
  □ Form-Validation-Tests
  □ API-Integration-Tests
```

**Kritische Punkte:**
- ✅ Error handling in JS
- ✅ Loading states
- ✅ Real-time log display

---

### **Phase 11.5g: Documentation Update (1h)**
```
Status: Dokumentation während Implementation aktualisieren
Dateien:
  □ PHASE_11_IMAP_ARCHITECTURE.md → Actual Implementation
  □ IMAP_SEARCH_FIXES.md → Move to docs/IMAP/
  □ API Docs → Update endpoints
  □ Testing Guide → Add Phase 11.5 tests
```

---

## 📈 IMPLEMENTATION ROADMAP

```
Week 1:
  Mon 12/30: Phase 11.5.0 + 11.5a (Diagnostics)  [3-4h]
  Tue 12/31: Phase 11.5b (Flags)                 [2-3h]
  Wed 01/01: Phase 11.5c (Config) + Testing      [2-3h]
  Thu 01/02: Phase 11.5d (Engine)                [3-4h]
  Fri 01/03: Phase 11.5e (API) + Phase 11.5f     [3-4h]
  
Week 2:
  Mon 01/06: Phase 11.5f (Frontend complete)     [2h]
  Tue 01/07: Full Integration Testing            [4-5h]
  Wed 01/08: Performance Testing + Optimization  [3h]
  Thu 01/09: Documentation finalize              [2h]
  Fri 01/10: Review + Bug Fixes                  [2h]

Total Estimate: 35-40 hours
```

---

## 🎯 Success Criteria (Acceptance Tests)

### Must Have ✅
```
□ Folder listing endpoint returns valid JSON (no bytes serialization)
□ 100% of discoverable emails fetched successfully
□ Sync engine completes without errors
□ API endpoints return proper HTTP status codes
□ Database integrity maintained (no duplicates)
□ All Python files pass flake8 + mypy checks
```

### Should Have ⭐
```
□ ≥80% test coverage
□ Performance: Full sync in <5 minutes (10000 emails)
□ Error logging with context (account_id, folder, error_type)
□ Graceful degradation (continue on single folder error)
```

### Nice To Have 🚀
```
□ Incremental sync in <1 second
□ IMAP IDLE support (real-time push)
□ WebSocket live logs
□ Provider-specific optimizations
```

---

## 🔴 Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| UTF-7 Encoding Issues | High | Test heavily, use IMAPClient native handling |
| Email Fetch Failures | High | Comprehensive error handling + retry logic |
| Performance (many emails) | Medium | Pagination + batch processing |
| Provider Variations | Medium | Provider detection + fallbacks |
| Database Locks | Low | WAL mode + connection pooling |

---

## ✨ ENTSCHEIDUNG

### Wenn YES zu Option B:
1. ✅ Untracked files sichern (als Referenz)
2. ✅ HEAD auf stabilen Commit zurücksetzen
3. ✅ Fresh start mit Phase 11.5.0-g
4. ✅ Proper Git commits bei jedem Phase-Abschluss
5. ✅ Testing als integral part (nicht am Ende!)

### Wenn NO zu Option B (Quick Fix):
1. ⚠️ Nur Bytes-Bug fixen
2. ⚠️ Minimale Testing
3. ⚠️ Technische Schulden bleiben
4. ⚠️ Später mehr Zeit für Maintenance

---

**RECOMMENDATION:** Option B ist klarer Gewinner.  
**NEXT STEP:** Bestätigung + Start Phase 11.5.0
