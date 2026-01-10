## 🎯 Zielstruktur
```
src/
├── app_factory.py              # NEW - Factory-Funktion
├── config.py                   # NEW - Config-Klassen
├── extensions.py               # NEW - Extensions initialisieren
├── helpers/                    # NEW - Shared Utilities
│   ├── __init__.py
│   ├── crypto.py               # decrypt_raw_email, decrypt_email_subject, etc.
│   ├── decorators.py           # ensure_master_key, require_dek
│   └── response.py             # JSON-Response Formatter
├── blueprints/                 # NEW - Modularisierte Routes
│   ├── __init__.py
│   ├── auth.py                 # login, register, 2fa, logout, change_password
│   ├── emails.py               # list, detail, mark_done, undo, threads
│   ├── email_actions.py        # reprocess, optimize, correct, flags
│   ├── tags.py                 # tags_view + api_* tag routes
│   ├── search.py               # semantic_search, find_similar, embeddings
│   ├── accounts.py             # settings, add_account, delete_account
│   ├── training.py             # retrain, get_training_stats
│   └── api.py                  # General API endpoints
├── 00_main.py                  # Entry Point (nutzt create_app)
├── 01_web_app.py               # OLD - KEEP für Fallback (aber nicht nutzen)
├── 02_models.py                # Unchanged
├── services/                   # Unchanged (tag_manager, sender_patterns, etc.)
└── ...
```