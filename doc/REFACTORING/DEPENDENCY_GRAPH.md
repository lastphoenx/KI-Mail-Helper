# DEPENDENCY_GRAPH.md

**Erstellt:** 11. Januar 2026  
**Zweck:** Visualisierung der Modul-Abhängigkeiten für sicheres Refactoring

---

## 📊 ÜBERSICHT

```
┌─────────────────────────────────────────────────────────────┐
│                     01_web_app.py                           │
│                    (123 Routes, ~9500 Zeilen)               │
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │  Models  │    │ Services │    │ Modules  │
    │ 02_*.py  │    │ services/│    │ *.py     │
    └──────────┘    └──────────┘    └──────────┘
```

---

## 🔗 PRIMÄRE ABHÄNGIGKEITEN (Top-Level Imports)

Diese werden am Anfang von `01_web_app.py` geladen (Zeile 6-67, 144-150, 232-234):

| Alias | Modul | Beschreibung |
|-------|-------|--------------|
| - | `dotenv` | Zeile 6 |
| - | `flask` | Zeile 10-20 |
| - | `flask_login` | Zeile 21-28 |
| - | `flask_session` | Zeile 30 |
| - | `flask_limiter` | Zeile 232, 234 |
| - | `flask_wtf.csrf` | Zeile 144-145 |
| `DebugLogger` | `src.debug_logger` | Zeile 67 |
| `thread_api` | `src.thread_api` | Zeile 233 |

---

## 📦 SEKUNDÄRE ABHÄNGIGKEITEN (Lazy Imports)

Diese werden innerhalb von Funktionen geladen:

| Modul | Geladen in | Zeilen |
|-------|------------|--------|
| `src.services.tag_manager` | Tag-bezogene Routes | 1319, 1659, 2738, ... |
| `src.services.tag_suggestion_service` | Tag-Suggestions | 3321, 3353, 3389, ... |
| `src.services.trusted_senders` | Trusted Senders API | 8578, 8917 |
| `src.16_imap_flags` | IMAP Flag Operations | 2201 |
| `src.04_model_discovery` | Model Discovery | 2373 |
| `src.reply_generator` | Reply Generation | 4385, 4619 |
| `src.train_classifier` | Training | 6243 |
| `src.imap_diagnostics` | IMAP Diagnostics | 7324 |

---

## 🔄 DEPENDENCY GRAPH (ASCII)

```
                        ┌──────────────────┐
                        │  01_web_app.py   │
                        └────────┬─────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│    MODELS     │      │    SERVICES     │      │    MODULES      │
├───────────────┤      ├─────────────────┤      ├─────────────────┤
│ 02_models.py  │◄─────│ tag_manager     │      │ 03_ai_client    │
│               │      │ tag_suggestion  │      │ 04_sanitizer    │
│               │      │ trusted_senders │      │ 04_model_discov.│
│               │      │ reply_style     │      │ 05_scoring      │
│               │      │ ensemble_comb.  │      │ 05_embedding_api│
│               │      │ content_sanit.  │      │ 06_mail_fetcher │
│               │      │ hybrid_pipeline │      │ 07_auth         │
│               │      │ imap_sender_sc. │      │ 08_encryption   │
│               │      │ sender_patterns │      │ 10_google_oauth │
│               │      │ spacy_config    │      │ 12_processing   │
│               │      │ spacy_detectors │      │ 14_background   │
│               │      │ urgency_booster │      │ 15_provider_ut. │
└───────────────┘      └─────────────────┘      │ 16_imap_flags   │
                                                │ 16_mail_sync    │
                                                │ 19_smtp_sender  │
                                                │ imap_diagnostics│
                                                │ semantic_search │
                                                │ reply_generator │
                                                │ train_classifier│
                                                │ thread_service  │
                                                │ thread_api      │
                                                │ debug_logger    │
                                                │ auto_rules_eng. │
                                                │ known_newslett. │
                                                │ optim_reply_pr. │
                                                └─────────────────┘
```

---

## ⚠️ POTENZIELLE ZIRKULÄRE IMPORTS

| Von | Nach | Risiko | Lösung |
|-----|------|--------|--------|
| `02_models` | `08_encryption` | NIEDRIG | Bereits via importlib gelöst |
| `services/*` | `02_models` | NIEDRIG | Services importieren Models, nicht umgekehrt |
| Blueprints | `app` | MITTEL | Blueprint-Factory-Pattern verwenden |

### Lösung für Blueprint-Zirkularität:

```python
# FALSCH:
from src.app_factory import app  # Zirkulär!

# RICHTIG:
from flask import current_app
# oder Blueprint-Pattern ohne app-Import
```

---

## 📋 BLUEPRINT-ABHÄNGIGKEITEN

Nach dem Refactoring werden die Blueprints folgende Module brauchen:

### auth_bp
```python
import importlib
models = importlib.import_module(".02_models", "src")
auth = importlib.import_module(".07_auth", "src")
encryption = importlib.import_module(".08_encryption", "src")
```

### emails_bp
```python
import importlib
models = importlib.import_module(".02_models", "src")
processing = importlib.import_module(".12_processing", "src")
encryption = importlib.import_module(".08_encryption", "src")
```

### api_bp
```python
import importlib
models = importlib.import_module(".02_models", "src")
# Plus diverse Services je nach Endpoint
```

### accounts_bp
```python
import importlib
models = importlib.import_module(".02_models", "src")
encryption = importlib.import_module(".08_encryption", "src")
mail_fetcher = importlib.import_module(".06_mail_fetcher", "src")
google_oauth = importlib.import_module(".10_google_oauth", "src")
```

---

## ✅ VERIFIZIERUNG

```bash
# Prüfen auf zirkuläre Imports:
python -c "from src.01_web_app import app"  # Muss ohne Fehler laufen

# Nach Refactoring:
python -c "from src.app_factory import create_app; create_app()"
```

---

## 🎯 SCHLUSSFOLGERUNG

- **Keine kritischen Zirkel-Probleme** dank importlib
- **Services sind unabhängig** von Routes
- **Blueprint-Pattern ist sicher** wenn importlib verwendet wird
- **Alle Abhängigkeiten sind dokumentiert**

**BEREIT FÜR REFACTORING** ✅
