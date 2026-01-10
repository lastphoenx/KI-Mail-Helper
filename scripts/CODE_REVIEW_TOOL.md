# 🔍 Automated Code Review Tool - Dokumentation

**Version:** 3.1  
**Erstellt:** 31. Dezember 2025  
**Tool:** `scripts/automated_code_review.py`

---

## 📋 Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Features](#features)
3. [Voraussetzungen](#voraussetzungen)
4. [Bedienung](#bedienung)
5. [Context-Modi](#context-modi)
6. [Output-Struktur](#output-struktur)
7. [Workflow](#workflow)
8. [Kosten & Performance](#kosten--performance)

---

## 🎯 Überblick

Das **Automated Code Review Tool** analysiert den gesamten Codebase mit **Claude API (Sonnet 4)** und erstellt detaillierte Security- und Architektur-Reviews.

### **Was macht das Tool?**

- ✅ Layer-basierte Code-Analyse (Security → Data → Frontend → Background)
- ✅ Context-aware Reviews mit Projekt-Dokumentation
- ✅ 2-Pass-Reviews für kritische Files (Quick Scan → Deep Dive)
- ✅ Rate-Limit-Protection (30k tokens/minute, 85% buffer)
- ✅ False-Positive-Detection (bekannte Issues werden markiert)
- ✅ Dependency-Graph-Extraction (zeigt Cross-File-Dependencies)

---

## 🚀 Features

### **1. Adaptive Context Loading (3 Modi)**

Das Tool lädt automatisch Projekt-Dokumentation, um False Positives zu vermeiden:

- **REDUCED:** Minimal (3 Docs, ~15k tokens)
- **FULL:** Standard (9 Docs, ~50k tokens) [DEFAULT]
- **DEEP:** Maximum (11 Docs, ~65k tokens)

### **2. Known False Positives & Resolved Issues**

Das Tool kennt bereits gefixte Issues und Design-Decisions:

**RESOLVED Issues (Phase 12 - 2025-12-31):**
- ✅ Issue #18: Multi-Worker DB Engine Consolidation (Commit 0ccac65)
- ✅ Issue #1: CSRF AJAX Protection
- ✅ Issue #3: XSS in Thread View (escapeHtml)
- ✅ Issue #10: N+1 Query Performance (eager loading)

**AI prüft trotzdem ob Fixes korrekt implementiert sind!**

**Known False Positives:**
- Flask app.run() host validation (kein Command Injection)
- In-Memory Rate Limiting (OK für Heimnetz + Fail2Ban)
- Daemon Threads (HTTP Redirector, Sanitizer Timeout)

### **3. Layer-basierte Analyse**

```
Layer 1: Security & Authentication (6 Files)
  - 01_web_app.py, 07_auth.py, 08_encryption.py
  - 09_password_validator.py, 02_models.py, 00_env_validator.py

Layer 2: Data & Processing (4 Files)
  - 02_models.py, 06_mail_fetcher.py, 12_processing.py, 10_google_oauth.py

Layer 3: Templates & Frontend (alle HTML/Jinja2)
Layer 4: Static Assets (JS, CSS)
Layer 5: Background & Infrastructure
```

### **3. 2-Pass-Review für Kritische Files**

- **Pass 1:** Quick Security Scan (6k tokens output)
- **Pass 2:** Deep Dive bei kritischen Findings (12k tokens output)

### **4. Rate-Limit-Safe**

- Automatisches Token-Tracking
- Wartet bei 85% Auslastung (verhindert API-Errors)
- Burst-Allowance für große Requests

---

## 📦 Voraussetzungen

### **1. API-Key**

```bash
# In .env Datei:
ANTHROPIC_API_KEY=sk-ant-...
```

### **2. Python-Abhängigkeiten**

```bash
pip install anthropic python-dotenv
```

### **3. Projekt-Struktur**

Das Tool erwartet folgende Dateien (für Context Loading):

```
/home/thomas/projects/KI-Mail-Helper/
├── README.md                                    # Immer geladen
├── ARCHITECTURE.md                              # Immer geladen
├── docs/
│   ├── SECURITY.md                              # FULL + DEEP
│   ├── DEPLOYMENT.md                            # FULL + DEEP
│   └── CHANGELOG.md                             # FULL + DEEP
└── doc/
    ├── erledigt/
    │   ├── ZERO_KNOWLEDGE_ARCHITECTURE.md       # FULL + DEEP
    │   ├── PHASE_12_FIX_VERIFICATION.md         # Alle Modi (wichtig!)
    │   ├── PHASE_12_CODE_REVIEW.md              # FULL + DEEP
    │   ├── PERFORMANCE_FIX_N+1_QUERY.md         # Nur DEEP
    │   └── PHASE_12_DEEP_REVIEW.md              # Nur DEEP
    └── development/
        └── Instruction_&_goal.md                # FULL + DEEP
```

**Fehlende Dateien** werden übersprungen (nicht kritisch).

---

## 🎮 Bedienung

### **Standard-Nutzung (Automatisch adaptiv)**

```bash
cd /home/thomas/projects/KI-Mail-Helper
python scripts/automated_code_review.py
```

**Verhalten:**
- Files <50k chars → **FULL** Context (9 Docs)
- Files >50k chars → **REDUCED** Context (3 Docs)

### **Manuelles Override**

```bash
# Force REDUCED (schnell, sparsam)
python scripts/automated_code_review.py --context reduced

# Force FULL (Standard, empfohlen)
python scripts/automated_code_review.py --context full

# Force DEEP (Maximum Context, erste Review)
python scripts/automated_code_review.py --context deep
```

### **Help anzeigen**

```bash
python scripts/automated_code_review.py --help
```

---

## 📚 Context-Modi

### **REDUCED (3 Docs, ~15k tokens)**

**Trigger:** Files >50k chars ODER `--context reduced`

**Geladene Docs:**
1. `README.md` - Projekt-Übersicht
2. `ARCHITECTURE.md` - Design Decisions
3. `doc/erledigt/PHASE_12_FIX_VERIFICATION.md` - Gefixte Issues

**Use Cases:**
- ✅ Große Files (>50k) - spart API-Kosten
- ✅ Schnelle Re-Reviews nach Fixes
- ✅ Fokus auf neue Änderungen

**Kosten:** ~$0.15-0.30 pro File

---

### **FULL (9 Docs, ~50k tokens) [DEFAULT]**

**Trigger:** Files <50k chars ODER `--context full`

**Geladene Docs:**
1. `README.md`
2. `ARCHITECTURE.md`
3. `docs/SECURITY.md`
4. `docs/DEPLOYMENT.md`
5. `docs/CHANGELOG.md`
6. `doc/erledigt/ZERO_KNOWLEDGE_ARCHITECTURE.md`
7. `doc/erledigt/PHASE_12_FIX_VERIFICATION.md`
8. `doc/erledigt/PHASE_12_CODE_REVIEW.md`
9. `doc/development/Instruction_&_goal.md`

**Use Cases:**
- ✅ Standard-Reviews
- ✅ Normale Files (<50k)
- ✅ Vollständiger Kontext ohne Overhead

**Kosten:** ~$0.50-1.00 pro File

---

### **DEEP (11 Docs, ~65k tokens)**

**Trigger:** `--context deep`

**Zusätzlich zu FULL:**
10. `doc/erledigt/PERFORMANCE_FIX_N+1_QUERY.md`
11. `doc/erledigt/PHASE_12_DEEP_REVIEW.md`

**Use Cases:**
- ✅ Erste umfassende Review
- ✅ Security-Deep-Dives
- ✅ Architektur-Validierung
- ✅ Nach größeren Refactorings

**Kosten:** ~$0.80-1.50 pro File

---

## 📂 Output-Struktur

```
review_output/
└── reports/
    ├── 00_REVIEW_INDEX.md              # Start hier! (Übersicht)
    ├── 01_layer1_security.md           # Layer 1 Review
    ├── 02_layer2_data.md               # Layer 2 Review
    ├── 03_layer3_templates.md          # Layer 3 Review
    ├── 04_layer4_frontend.md           # Layer 4 Review
    └── 05_layer5_background.md         # Layer 5 Review
```

### **Report-Format**

Jeder Report enthält:

```markdown
# Layer X: Name (Priorität)

## Übersicht
- Analysierte Dateien: 6
- Total Tokens: 250,000
- Review-Dauer: 5min

## 1. Dateiname.py

**Size:** 500 lines, 25,000 characters

### Kritische Findings
[KRITISCH] Issue-Beschreibung
[HOCH] Issue-Beschreibung

### Code-Analyse
[Details...]

---
```

---

## 🔄 Workflow

### **Schritt 1: Erste Review (empfohlen: DEEP)**

```bash
# Erste umfassende Analyse mit maximum Context
python scripts/automated_code_review.py --context deep
```

**Erwartete Dauer:** 15-30 Minuten (je nach Layer-Größe)  
**Kosten:** ~$10-20 (alle Layer)

### **Schritt 2: Reports lesen**

```bash
cd review_output/reports
cat 00_REVIEW_INDEX.md
```

**Priorität:**
1. Layer 1 (Security) - **KRITISCH**
2. Layer 2 (Data) - **HOCH**
3. Layer 5 (Background) - **MITTEL**
4. Layer 3+4 (Frontend) - **NIEDRIG**

### **Schritt 3: Fixes implementieren**

- Arbeite Issues von `[KRITISCH]` → `[NIEDRIG]` ab
- Dokumentiere Fixes in `docs/CHANGELOG.md`

### **Schritt 4: Re-Review (empfohlen: FULL oder REDUCED)**

```bash
# Nach Fixes: Standard-Review zur Verifikation
python scripts/automated_code_review.py --context full

# Oder schnell: Nur geänderte Files
python scripts/automated_code_review.py --context reduced
```

---

## 💰 Kosten & Performance

### **API-Kosten (Claude Sonnet 4)**

| Context Mode | Input Tokens | Output Tokens | Kosten/File | Kosten/Layer (5 Files) |
|--------------|--------------|---------------|-------------|------------------------|
| REDUCED      | ~20k         | ~3k           | $0.15-0.30  | $0.75-1.50            |
| FULL         | ~60k         | ~5k           | $0.50-1.00  | $2.50-5.00            |
| DEEP         | ~80k         | ~8k           | $0.80-1.50  | $4.00-7.50            |

**Gesamt-Review (alle 5 Layer):**
- REDUCED: ~$5-10
- FULL: ~$15-25
- DEEP: ~$20-40

### **Performance**

| Layer | Files | Dauer (FULL) | Tokens (Total) |
|-------|-------|--------------|----------------|
| Layer 1 | 6 | 10-15min | ~300k |
| Layer 2 | 4 | 8-12min | ~200k |
| Layer 3 | ~15 | 15-20min | ~400k |
| Layer 4 | ~5 | 5-10min | ~150k |
| Layer 5 | ~8 | 10-15min | ~250k |

**Total:** ~45-75 Minuten, ~1.3M tokens

---

## 🎯 Best Practices

### **1. Erste Review → DEEP Mode**

```bash
python scripts/automated_code_review.py --context deep
```

Gibt der AI maximum Kontext für präzise Findings.

### **2. Nach Fixes → FULL Mode**

```bash
python scripts/automated_code_review.py --context full
```

Standard-Kontext reicht zur Verifikation.

### **3. Große Files → Automatisch**

```bash
python scripts/automated_code_review.py  # Nutzt AUTO
```

Spart Kosten bei großen Files automatisch.

### **4. Regelmäßige Reviews**

```bash
# Wöchentlich: FULL Mode
# Monatlich: DEEP Mode (Security-Deep-Dive)
```

### **5. Rate-Limit beachten**

- Tool wartet automatisch bei 85% Auslastung
- Keine manuellen Delays nötig
- Bei Unterbrechung: Einfach neu starten

---

## 🐛 Troubleshooting

### **Problem: "ANTHROPIC_API_KEY not found"**

```bash
# Prüfe .env Datei
cat /home/thomas/projects/KI-Mail-Helper/.env | grep ANTHROPIC

# Wenn leer: API-Key eintragen
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
```

### **Problem: "Rate Limit Exceeded"**

Tool wartet automatisch. Falls manuell unterbrochen:

```bash
# Warte 60 Sekunden und starte neu
sleep 60
python scripts/automated_code_review.py
```

### **Problem: Datei nicht gefunden (z.B. ARCHITECTURE.md)**

Nicht kritisch! Tool überspringt fehlende Dateien:

```
⚠️ ARCHITECTURE.md nicht gefunden (erwartet aber nicht kritisch)
```

### **Problem: Zu viele Tokens**

```bash
# Force REDUCED Mode
python scripts/automated_code_review.py --context reduced
```

---

## 📖 Weiterführende Docs

- **Tool-Code:** `scripts/automated_code_review.py`
- **Merge-Tool:** `scripts/merge_files_for_review.py` (für manuelle Reviews)
- **Projekt-Docs:** `ARCHITECTURE.md`, `docs/SECURITY.md`

---

## ✅ Checkliste: Erste Review

- [ ] `ANTHROPIC_API_KEY` in `.env` eingetragen
- [ ] Python-Dependencies installiert (`anthropic`, `python-dotenv`)
- [ ] `README.md` + `ARCHITECTURE.md` vorhanden
- [ ] Review starten: `python scripts/automated_code_review.py --context deep`
- [ ] Reports lesen: `review_output/reports/00_REVIEW_INDEX.md`
- [ ] Issues priorisieren: `[KRITISCH]` zuerst
- [ ] **WICHTIG:** Prüfe RESOLVED Issues - AI verifiziert ob Fixes korrekt sind!
- [ ] Fixes implementieren → `docs/CHANGELOG.md` updaten
- [ ] Re-Review: `python scripts/automated_code_review.py --context full`
- [ ] Neue Fixes in `KNOWN_FALSE_POSITIVES` Database ergänzen

---

## 📝 RESOLVED Issues im Review

Die AI sieht alle als "RESOLVED" markierten Issues und **prüft ob Fixes korrekt sind**:

```
✅ Issue #18 als RESOLVED markiert (Commit 0ccac65)
   Verifikation: 
   - ✅ engine at module level (Zeile 299)
   - ✅ SessionLocal = sessionmaker(bind=engine) (Zeile 300)
   - ✅ Lazy import in thread_api.py (Zeile 47)
   → Fix korrekt implementiert!
```

**Oder bei fehlerhaftem Fix:**
```
⚠️ Issue #18 als RESOLVED markiert, ABER:
   - ❌ thread_api.py erstellt noch eigenen engine (Zeile 123)
   - ❌ Fix unvollständig!
```

**Die AI glaubt nicht blind - sie verifiziert!**

---

**Happy Reviewing! 🚀**
