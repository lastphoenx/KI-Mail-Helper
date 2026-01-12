# VALIDATION_CHECKLIST.md

**Erstellt:** 11. Januar 2026  
**Zweck:** Checkliste zur Validierung des Refactorings

---

## 🔍 PHASE 1: SYNTAX-VALIDIERUNG

### Python-Syntaxcheck

```bash
# Alle Blueprint-Dateien auf Syntaxfehler prüfen
python3 -m py_compile src/app_factory.py
python3 -m py_compile src/blueprints/__init__.py
python3 -m py_compile src/blueprints/auth.py
python3 -m py_compile src/blueprints/emails.py
python3 -m py_compile src/blueprints/email_actions.py
python3 -m py_compile src/blueprints/accounts.py
python3 -m py_compile src/blueprints/tags.py
python3 -m py_compile src/blueprints/api.py
python3 -m py_compile src/blueprints/rules.py
python3 -m py_compile src/blueprints/training.py
python3 -m py_compile src/blueprints/admin.py
python3 -m py_compile src/helpers/__init__.py
python3 -m py_compile src/helpers/database.py
python3 -m py_compile src/helpers/validation.py
python3 -m py_compile src/helpers/responses.py
```

---

## 🔢 PHASE 2: ROUTE-ZÄHLUNG

### Anzahl Routes pro Blueprint

```bash
# Muss exakt übereinstimmen mit ROUTE_MAPPING.md
grep -c "@auth_bp.route" src/blueprints/auth.py              # Erwarte: 7
grep -c "@emails_bp.route" src/blueprints/emails.py          # Erwarte: 5
grep -c "@email_actions_bp.route" src/blueprints/email_actions.py  # Erwarte: 11
grep -c "@accounts_bp.route" src/blueprints/accounts.py      # Erwarte: 22
grep -c "@tags_bp.route" src/blueprints/tags.py              # Erwarte: 2
grep -c "@api_bp.route" src/blueprints/api.py                # Erwarte: 64
grep -c "@rules_bp.route" src/blueprints/rules.py            # Erwarte: 10
grep -c "@training_bp.route" src/blueprints/training.py      # Erwarte: 1
grep -c "@admin_bp.route" src/blueprints/admin.py            # Erwarte: 1
```

### Gesamt-Routen-Zählung

```bash
# Summe muss 123 sein
grep -r "@.*_bp.route" src/blueprints/ | wc -l
# Erwarte: 123
```

---

## 📋 PHASE 3: CHECKLISTE NACH BLUEPRINT

### ✅ auth.py (7 Routes)

| Nr | Route | Funktion | Status |
|----|-------|----------|--------|
| 1 | `/` | `index` | ⬜ |
| 2 | `/login` | `login` | ⬜ |
| 3 | `/register` | `register` | ⬜ |
| 4 | `/2fa/verify` | `verify_2fa` | ⬜ |
| 5 | `/logout` | `logout` | ⬜ |
| 6 | `/settings/2fa/setup` | `setup_2fa` | ⬜ |
| 7 | `/settings/2fa/recovery-codes/regenerate` | `regenerate_recovery_codes` | ⬜ |

### ✅ emails.py (5 Routes)

| Nr | Route | Funktion | Status |
|----|-------|----------|--------|
| 1 | `/dashboard` | `dashboard` | ⬜ |
| 2 | `/list` | `list_view` | ⬜ |
| 3 | `/threads` | `threads_view` | ⬜ |
| 4 | `/email/<id>` | `email_detail` | ⬜ |
| 5 | `/email/<id>/render-html` | `render_email_html` | ⬜ |

### ✅ email_actions.py (11 Routes)

| Nr | Route | Funktion | Status |
|----|-------|----------|--------|
| 1 | `/email/<id>/done` | `mark_done` | ⬜ |
| 2 | `/email/<id>/undo` | `mark_undone` | ⬜ |
| 3 | `/email/<id>/reprocess` | `reprocess_email` | ⬜ |
| 4 | `/email/<id>/optimize` | `optimize_email` | ⬜ |
| 5 | `/email/<id>/correct` | `correct_email` | ⬜ |
| 6 | `/email/<id>/delete` | `delete_email` | ⬜ |
| 7 | `/email/<id>/move-trash` | `move_email_to_trash` | ⬜ |
| 8 | `/email/<id>/move-to-folder` | `move_email_to_folder` | ⬜ |
| 9 | `/email/<id>/mark-read` | `mark_email_read` | ⬜ |
| 10 | `/email/<id>/toggle-read` | `toggle_email_read` | ⬜ |
| 11 | `/email/<id>/mark-flag` | `toggle_email_flag` | ⬜ |

### ✅ accounts.py (22 Routes)

| Nr | Route | Funktion | Status |
|----|-------|----------|--------|
| 1 | `/settings` | `settings` | ⬜ |
| 2-22 | (siehe ROUTE_MAPPING.md) | ... | ⬜ |

### ✅ tags.py (2 Routes)

| Nr | Route | Funktion | Status |
|----|-------|----------|--------|
| 1 | `/tags` | `tags_view` | ⬜ |
| 2 | `/tag-suggestions` | `tag_suggestions_page` | ⬜ |

### ✅ api.py (64 Routes)

| Status | Beschreibung |
|--------|--------------|
| ⬜ | Alle 64 API-Routes (Details in ROUTE_MAPPING.md) |

### ✅ rules.py (10 Routes)

| Nr | Route | Funktion | Status |
|----|-------|----------|--------|
| 1 | `/rules` | `rules_management` | ⬜ |
| 2-10 | (siehe ROUTE_MAPPING.md) | ... | ⬜ |

### ✅ training.py (1 Route)

| Nr | Route | Funktion | Status |
|----|-------|----------|--------|
| 1 | `/retrain` (POST) | `retrain_models` | ⬜ |

### ✅ admin.py (1 Route)

| Nr | Route | Funktion | Status |
|----|-------|----------|--------|
| 1 | `/api/debug-logger-status` (GET) | `api_debug_logger_status` | ⬜ |

---

## 🔗 PHASE 4: URL_FOR VALIDIERUNG

### Keine alten url_for() mehr vorhanden

```bash
# Alle müssen 0 Treffer haben:
grep -rn 'url_for("login")' src/blueprints/
grep -rn 'url_for("settings")' src/blueprints/
grep -rn 'url_for("dashboard")' src/blueprints/
grep -rn 'url_for("list_view")' src/blueprints/
grep -rn 'url_for("setup_2fa")' src/blueprints/
grep -rn 'url_for("verify_2fa")' src/blueprints/
grep -rn 'url_for("index")' src/blueprints/
```

### Korrekte Blueprint-Qualifizierung

```bash
# Diese sollten Treffer haben:
grep -rn 'url_for("auth\.' src/blueprints/
grep -rn 'url_for("emails\.' src/blueprints/
grep -rn 'url_for("accounts\.' src/blueprints/
```

---

## 🧪 PHASE 5: FUNKTIONSTEST

### App startet ohne Fehler

```bash
cd /home/thomas/projects/KI-Mail-Helper-Dev
source .venv/bin/activate
python3 -c "from src.app_factory import create_app; app = create_app(); print('OK')"
```

### Alle Routes registriert

```bash
python3 -c "
from src.app_factory import create_app
app = create_app()
rules = list(app.url_map.iter_rules())
print(f'Registrierte Routes: {len(rules)}')
for rule in sorted(rules, key=lambda r: r.rule):
    print(f'  {rule.rule} -> {rule.endpoint}')
"
```

### Login-Seite erreichbar

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/login
# Erwarte: 200
```

---

## 🔐 PHASE 6: DEKORATOR-VALIDIERUNG

### @login_required Zählung

```bash
# Muss 116 sein (wie im Original)
grep -r "@login_required" src/blueprints/ | wc -l
```

### @limiter Zählung

```bash
# Muss 8 sein (wie im Original)
grep -r "@limiter" src/blueprints/ | wc -l
```

---

## 📦 PHASE 7: IMPORT-VALIDIERUNG

### Keine zirkulären Imports

```bash
python3 -c "
import sys
sys.path.insert(0, '/home/thomas/projects/KI-Mail-Helper-Dev')
from src.blueprints import auth_bp, emails_bp, email_actions_bp, accounts_bp
from src.blueprints import tags_bp, api_bp, rules_bp, training_bp, admin_bp
print('Alle Blueprints erfolgreich importiert!')
"
```

### Lazy Imports funktionieren

```bash
python3 -c "
from src.app_factory import create_app
app = create_app()
with app.app_context():
    from src.blueprints.auth import _get_models
    models = _get_models()
    print(f'Models: {models}')
"
```

---

## 📊 ZUSAMMENFASSUNG

| Phase | Beschreibung | Status | Aktualisiert |
|-------|--------------|--------|-------------|
| 1 | Syntax-Validierung | ⬜ | - |
| 2 | Route-Zählung (123) | ✅ | 12.01.2026 |
| 3 | Checkliste pro Blueprint | ✅ | 12.01.2026 |
| 4 | url_for Validierung | ✅ | 12.01.2026 |
| 5 | Funktionstest | ⚠️ | 13 Routes mit Stubs/TODOs |
| 6 | Dekorator-Validierung | ✅ | 12.01.2026 |
| 7 | Import-Validierung | ✅ | 12.01.2026 |

---

## 🔍 STATUS UPDATE (12. Januar 2026)

**Siehe: IMPLEMENTATION_STATUS.md für detaillierte Findings**

### ✅ Bestandene Checks

- [x] Alle 123 Routes registriert
- [x] Alle 9 Blueprints korrekt importiert
- [x] Exception Handling Pattern konsistent
- [x] app_factory.py + helpers korrekt
- [x] Security Headers + CSRF + 2FA implementiert
- [x] @login_required auf allen protected Routes

### ⚠️ Fehlende Implementierungen

- [ ] 2 Missing Routes: `scan-account-senders`, `bulk-add-trusted-senders`
- [ ] 7 Routes mit 501 "Not Implemented"
- [ ] 13 Routes mit TODO/Stubs
- [ ] ~1.200 Zeilen Business Logic (Stubs statt Full Implementation)

---

## ⚠️ BEI FEHLERN

1. **Syntaxfehler:** Zeile in Blueprint prüfen
2. **Falsche Route-Anzahl:** ROUTE_MAPPING.md vergleichen
3. **url_for Fehler:** Blueprint-Qualifizierung prüfen
4. **Import-Fehler:** Lazy Imports verwenden
5. **App startet nicht:** Rollback zu 01_web_app.py
