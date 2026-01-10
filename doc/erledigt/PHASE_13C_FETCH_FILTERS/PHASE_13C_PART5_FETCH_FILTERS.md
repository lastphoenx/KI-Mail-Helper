# 📋 Phase 13C Part 5: Erweiterte Fetch-Filter

**Datum:** 03. Januar 2026  
**Aufwand:** ~1.5h  
**Status:** 📦 Bereit zur Implementation

---

## 🎯 Features

| Filter | Beschreibung | IMAP Command |
|--------|--------------|--------------|
| **SINCE Datum** | Nur Mails ab z.B. 01.12.2025 | `SEARCH SINCE 01-Dec-2025` |
| **Nur Ungelesene** | Ignoriert bereits gelesene | `SEARCH UNSEEN` |
| **Ordner Include** | Whitelist (nur INBOX, Work) | Ordner-Loop Filter |
| **Ordner Exclude** | Blacklist (Spam, Sent, Trash) | Ordner-Loop Filter |

---

## 📁 Dateien

### Neue Datei
```
migrations/versions/ph13c_p5_fetch_filters.py
```

### Zu ändernde Dateien
```
src/02_models.py          → 4 neue Spalten im User-Model
src/01_web_app.py         → save_fetch_config() erweitern + user_prefs
templates/settings.html   → UI für Filter-Optionen
src/14_background_jobs.py → Filter beim Fetch anwenden
```

---

## 🔧 Schritt-für-Schritt Anleitung

### Schritt 1: Migration erstellen

Kopiere die Datei `fetch_filter_migration.py` nach:
```bash
cp fetch_filter_migration.py migrations/versions/ph13c_p5_fetch_filters.py
```

### Schritt 2: User-Model erweitern

In `src/02_models.py`, nach Zeile ~170 (nach `fetch_use_delta_sync`):

```python
    # Phase 13C Part 5: Erweiterte Fetch-Filter
    fetch_since_date = Column(Date, nullable=True)  # Nur Mails ab diesem Datum
    fetch_unseen_only = Column(Boolean, default=False)  # Nur ungelesene
    fetch_include_folders = Column(Text, nullable=True)  # JSON: ["INBOX", "Work"]
    fetch_exclude_folders = Column(Text, nullable=True)  # JSON: ["Spam", "Trash"]
```

### Schritt 3: web_app.py - user_prefs erweitern

In `src/01_web_app.py`, in der `settings()` Funktion, erweitere `user_prefs`:

```python
        # Phase 13C Part 4 + 5: User Fetch Preferences
        user_prefs = {
            'mails_per_folder': getattr(user, 'fetch_mails_per_folder', 100),
            'max_total_mails': getattr(user, 'fetch_max_total', 0),
            'use_delta_sync': getattr(user, 'fetch_use_delta_sync', True),
            # Part 5: Erweiterte Filter
            'since_date': getattr(user, 'fetch_since_date', None),
            'unseen_only': getattr(user, 'fetch_unseen_only', False),
            'include_folders': getattr(user, 'fetch_include_folders', None),
            'exclude_folders': getattr(user, 'fetch_exclude_folders', None),
        }
```

### Schritt 4: save_fetch_config() Route erweitern

Ersetze die komplette `save_fetch_config()` Funktion - siehe `fetch_filter_code_part1.py`

### Schritt 5: Template erweitern

In `templates/settings.html`, NACH dem Delta-Sync Checkbox-Block, füge ein:
- Siehe `fetch_filter_template.html`

### Schritt 6: Background-Jobs anpassen

In `src/14_background_jobs.py`, in `_fetch_raw_emails()`:
- Siehe `fetch_filter_background_jobs.py`

### Schritt 7: Migration ausführen

```bash
cd ~/projects/KI-Mail-Helper
source venv/bin/activate
alembic upgrade head
```

### Schritt 8: Testen

```bash
python3 -m src.00_main --serve
# Browser: http://localhost:5000/settings
# Fetch-Config Sektion prüfen
```

---

## 🖼️ UI Vorschau

```
┌─────────────────────────────────────────────────────────────────┐
│  📥 Fetch Konfiguration                                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Mails pro Ordner: [====100====]    Max. Gesamt: [___0___]     │
│                                                                 │
│  [x] Delta-Sync aktivieren                                      │
│                                                                 │
│  ─────────────── Erweiterte Filter ───────────────              │
│                                                                 │
│  Nur Mails ab Datum: [2025-12-01    📅]                        │
│                                                                 │
│  [x] Nur ungelesene Mails                                       │
│                                                                 │
│  Ordner-Filter:                                                 │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │ ✅ Include          │  │ ❌ Exclude          │              │
│  │ [x] INBOX           │  │ [x] Spam            │              │
│  │ [x] Work            │  │ [x] Trash           │              │
│  │ [ ] Archive         │  │ [x] Sent            │              │
│  │ [ ] Sent            │  │ [ ] Archive         │              │
│  └─────────────────────┘  └─────────────────────┘              │
│                                                                 │
│  Account: [GMX ▼] [📂 Ordner laden]                            │
│                                                                 │
│                                        [💾 Speichern]           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Erwartete Log-Ausgabe

```
2026-01-03 17:00:00 - INFO - 📁 7 Ordner, FULL SYNC | SINCE 2025-12-01, UNSEEN
2026-01-03 17:00:00 - INFO -   📂 3/7 Ordner nach Filter
2026-01-03 17:00:01 - INFO -   ✓ INBOX: 45 Mails (SINCE + UNSEEN)
2026-01-03 17:00:02 - INFO -   ✓ Work: 12 Mails
2026-01-03 17:00:02 - INFO -   ⏭️  Spam: In Exclude-Liste
2026-01-03 17:00:02 - INFO -   ⏭️  Sent: In Exclude-Liste
```

---

## ⚡ Quick-Setup (Minimal)

Falls du nur **SINCE-Datum** willst (5 Min):

1. Füge in User-Model hinzu:
   ```python
   fetch_since_date = Column(Date, nullable=True)
   ```

2. In settings.html, ein Datepicker:
   ```html
   <input type="date" name="since_date" value="{{ user_prefs.get('since_date', '') }}">
   ```

3. In save_fetch_config():
   ```python
   since_date_str = request.form.get('since_date', '')
   user.fetch_since_date = datetime.strptime(since_date_str, '%Y-%m-%d').date() if since_date_str else None
   ```

4. In background_jobs.py:
   ```python
   since = datetime.combine(user.fetch_since_date, datetime.min.time()) if user.fetch_since_date else None
   fetcher.fetch_new_emails(folder=folder, since=since, ...)
   ```

---

## ✅ Checkliste

- [ ] Migration kopiert nach `migrations/versions/`
- [ ] User-Model erweitert (4 Spalten)
- [ ] web_app.py: user_prefs erweitert
- [ ] web_app.py: save_fetch_config() erweitert
- [ ] settings.html: UI-Block eingefügt
- [ ] settings.html: JavaScript für Ordner-Laden
- [ ] background_jobs.py: Filter-Logik
- [ ] `alembic upgrade head` ausgeführt
- [ ] UI getestet
- [ ] Fetch mit Filtern getestet
