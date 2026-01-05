# 🎯 KI-Mail-Helper - Roadmap

**Stand:** 05.01.2026  
**Letzte Aktualisierung:** Nach Phase Learning-System  

---

## ✅ Abgeschlossen

| Phase | Feature | Datum |
|-------|---------|-------|
| A-E | Core Infrastructure (Filter, IMAP-Ops, Delta-Sync, Thread-Context) | 12/2025 |
| F | Semantic Intelligence (Search, 3-Settings, Similarity) | 01/2026 |
| G | AI Action Engine (Reply-Draft, Auto-Rules) | 01/2026 |
| H | SMTP Mail-Versand | 01/2026 |
| INV | User-Verwaltung + Exakte Fetch-Filter | 01/2026 |
| Learning | Online-Learning mit 4 SGD-Classifiers + Bewertung korrigieren UI | 05.01.2026 |

**Dokumentation:** Siehe `/doc/erledigt/` für Detail-Dokumentation abgeschlossener Phasen.

---

## 🔲 Offen

### Phase 1: Bulk Email Operations

**Status:** 🔲 Offen  
**Priorität:** 🟡 Mittel  
**Aufwand:** 15-20h  

**Beschreibung:**  
Batch-Aktionen für mehrere Emails gleichzeitig (Archive, Delete, Move, Flag, Read).

**Features:**
- Checkboxen pro Email in Listen-Ansicht
- "Select All" / "Deselect All" Toggle
- Bulk-Action Toolbar mit Aktionen-Dropdown
- Progress-Indicator für laufende Operationen
- Confirmation-Dialog für destruktive Aktionen (Delete)
- Partial-Failure Handling (4/5 erfolgreich, 1 Fehler)

**Mehrwert:** ⭐⭐⭐⭐  
Produktivitäts-Booster für Power-User mit vielen Emails. Ohne Bulk-Aktionen muss jede Email einzeln bearbeitet werden.

**Detail-Dokument:** `/doc/offen/PHASE_1_BULK_OPERATIONS.md`

---

### Phase 2: Action Extraction (Kalender & ToDo)

**Status:** 🔲 Offen  
**Priorität:** 🟢 Niedrig  
**Aufwand:** 8-12h  

**Beschreibung:**  
KI extrahiert Termine und Aufgaben aus Emails. Die Buttons "📅 Kalendereintrag anlegen" und "☑️ Auf ToDo-Liste setzen" in der Email-Detail-Ansicht werden funktional.

**Features:**
- Unified Action Extractor Service
- `ActionItem` DB-Tabelle (type: calendar/todo)
- KI-Extraktion mit Confidence-Score
- .ics Download für Kalender-Integration
- Actions-Übersicht (/actions)
- "Als erledigt markieren" Funktion

**Mehrwert:** ⭐⭐⭐  
Nice-to-have Feature. Buttons existieren bereits im UI, tun aber noch nichts.

**Detail-Dokument:** Bei Bedarf erstellen

---

## 📦 Backlog

### Pipeline & Infrastructure

**Status:** 📦 Zurückgestellt  
**Priorität:** ⚪ Bei Bedarf  
**Aufwand:** 60-80h  

**Beschreibung:**  
Multi-Account Orchestration, parallele Fetches, Job-Queue-System, Performance-Monitoring.

**Wann relevant:**
- 10+ Mail-Accounts
- Tausende Emails pro Tag
- Multi-User Deployment
- Performance-Probleme

**Mehrwert:** ⭐⭐  
Infrastructure ohne direkten User-Value. Nur bei konkretem Bedarf reaktivieren.

**Archiviert:** `/doc/backlog/TASK_6_PIPELINE_INTEGRATION.md`

---

### Reply Templates & Signatures

**Status:** 📦 Zurückgestellt  
**Priorität:** ⚪ Optional  
**Aufwand:** 4-6h  

**Beschreibung:**  
Vordefinierte Antwort-Templates und Signaturen für Reply-Draft-Generator.

**Mehrwert:** ⭐⭐  
Nice-to-have. Reply-Draft-Generator funktioniert bereits gut ohne Templates.

---

## 📝 Hinweise

### Nummerierung
- Offene Phasen: Phase 1, 2, 3...
- Abgeschlossene Phasen: Historisch (A-H, F.1-F.3, etc.)
- Backlog: Keine Nummerierung

### Detail-Dokumente
Für größere Features gibt es Detail-Dokumente:
- Schema: `PHASE_X_FEATURE_NAME.md`
- Speicherort: `/doc/offen/` (aktiv) oder `/doc/backlog/` (zurückgestellt)

### Dokumentations-Struktur
```
doc/
├── ROADMAP.md              # Diese Datei
├── offen/                  # Aktive Feature-Dokumente
├── backlog/                # Zurückgestellte Features
└── erledigt/               # Abgeschlossene Phasen
```
