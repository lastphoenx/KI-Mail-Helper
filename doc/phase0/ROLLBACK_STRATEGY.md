# ROLLBACK_STRATEGY.md

**Erstellt:** 11. Januar 2026  
**Zweck:** Notfallplan bei fehlgeschlagenem Refactoring

---

## 🚨 WANN ROLLBACK?

Ein Rollback ist erforderlich wenn:

1. App startet nicht mehr
2. Kritische Funktionen (Login, E-Mail-Abruf) fehlerhaft
3. Mehr als 50% der Tests fehlschlagen
4. Datenbank-Korruption
5. Benutzer können nicht arbeiten

---

## 📦 BACKUP-STRATEGIE

### Vor Refactoring-Start

```bash
# 1. Git Tag für aktuellen Stand
git tag -a "pre-refactoring-v1.0" -m "Stand vor Blueprint-Refactoring"
git push origin pre-refactoring-v1.0

# 2. Vollständiges Backup der Quelldateien
cp -r src/ src_backup_$(date +%Y%m%d_%H%M%S)/

# 3. Datenbank-Backup
cp emails.db emails_backup_$(date +%Y%m%d_%H%M%S).db

# 4. rsync zu externem Backup (existiert bereits)
# Der User hat bestätigt: rsync-Backup vorhanden
```

### Nach jeder Phase

```bash
# Git Commit mit klarer Beschreibung
git add -A
git commit -m "refactor: Phase X - Blueprint Y erstellt"
git push origin main
```

---

## 🔄 ROLLBACK-OPTIONEN

### Option 1: Git Reset (empfohlen)

```bash
# Zu letztem funktionierenden Commit
git log --oneline -10
git reset --hard <commit-hash>

# Oder zum Pre-Refactoring Tag
git reset --hard pre-refactoring-v1.0
```

### Option 2: Backup-Ordner wiederherstellen

```bash
# Aktuellen src/ löschen
rm -rf src/

# Backup wiederherstellen
cp -r src_backup_YYYYMMDD_HHMMSS/ src/
```

### Option 3: 01_web_app.py direkt nutzen

Die Originaldatei `src/01_web_app.py` wird **NICHT GELÖSCHT** bis Refactoring abgeschlossen und validiert!

```bash
# Starten mit Original
cd /home/thomas/projects/KI-Mail-Helper-Dev
source .venv/bin/activate
python3 src/01_web_app.py
```

---

## 🛡️ SICHERHEITSREGELN

### NIEMALS während Refactoring:

1. ❌ 01_web_app.py löschen
2. ❌ Datenbank-Schema ändern
3. ❌ Konfigurationsdateien löschen
4. ❌ Ohne Git Commit arbeiten
5. ❌ Produktionsserver aktualisieren

### IMMER:

1. ✅ Nach jeder Datei: Syntax prüfen
2. ✅ Nach jedem Blueprint: Routes zählen
3. ✅ Vor Git Push: App starten testen
4. ✅ Backups verifizieren

---

## 📋 ROLLBACK-CHECKLISTE

### Schritt 1: Problem identifizieren

```bash
# Fehlermeldung notieren
# Letzte Änderung identifizieren
git diff HEAD~1
```

### Schritt 2: Rollback-Level entscheiden

| Level | Situation | Aktion |
|-------|-----------|--------|
| 1 | Einzelner Blueprint fehlerhaft | Datei aus Git wiederherstellen |
| 2 | Mehrere Blueprints fehlerhaft | Zum letzten guten Commit |
| 3 | App startet nicht | Zum Pre-Refactoring Tag |
| 4 | Datenbank korrupt | DB-Backup + Pre-Refactoring Tag |

### Schritt 3: Rollback ausführen

```bash
# Level 1: Einzelne Datei
git checkout HEAD~1 -- src/blueprints/fehlerhaft.py

# Level 2: Letzter guter Commit
git reset --hard HEAD~3  # oder spezifischer Hash

# Level 3: Pre-Refactoring
git reset --hard pre-refactoring-v1.0

# Level 4: Vollständig
git reset --hard pre-refactoring-v1.0
cp emails_backup_YYYYMMDD.db emails.db
```

### Schritt 4: Verifizieren

```bash
# App starten
python3 src/01_web_app.py

# Login testen
curl http://localhost:5000/login
```

---

## 🔧 SCHNELLE REPARATUREN

### Import-Fehler

```python
# Fehler: ModuleNotFoundError
# Lösung: Lazy Import verwenden

# Alt (problematisch):
from src.02_models import User

# Neu (sicher):
models = None
def _get_models():
    global models
    if models is None:
        models = importlib.import_module(".02_models", "src")
    return models
```

### Route nicht gefunden

```python
# Fehler: 404 auf bekannter Route
# Prüfen:
# 1. Blueprint registriert in app_factory.py?
# 2. url_prefix korrekt?
# 3. @blueprint_bp.route statt @app.route?
```

### url_for Fehler

```python
# Fehler: BuildError für url_for
# Prüfen:
# 1. Blueprint-Qualifizierung: url_for("auth.login") statt url_for("login")
# 2. Funktionsname korrekt?
# 3. Blueprint importiert?
```

---

## 📊 RECOVERY-TIMELINE

| Zeit | Aktion |
|------|--------|
| 0-5 min | Problem identifizieren |
| 5-10 min | Rollback-Level entscheiden |
| 10-15 min | Rollback ausführen |
| 15-20 min | App starten und verifizieren |
| 20-30 min | Ursachenanalyse |

**Maximale Ausfallzeit: 30 Minuten**

---

## 📁 BACKUP-DATEIEN

| Datei | Zweck | Aufbewahrung |
|-------|-------|--------------|
| `src/01_web_app.py` | Originaldatei | Bis Refactoring abgeschlossen |
| `emails_backup_*.db` | Datenbank | 7 Tage |
| `src_backup_*/` | Quellcode | Bis Refactoring abgeschlossen |
| Git Tag `pre-refactoring-v1.0` | Git-Stand | Permanent |
| rsync-Backup | Externes Backup | Permanent |

---

## ✅ FINALE BEREINIGUNG

**Erst nach erfolgreichem Refactoring:**

```bash
# 1. Bestätigen, dass alles funktioniert
# 2. Alle Tests bestanden
# 3. Produktion läuft stabil (mindestens 24h)

# Dann:
rm -rf src_backup_*/
rm emails_backup_*.db

# 01_web_app.py umbenennen (nicht löschen!)
mv src/01_web_app.py src/01_web_app.py.ARCHIVED

# Git Tag für fertiges Refactoring
git tag -a "post-refactoring-v2.0" -m "Blueprint-Refactoring abgeschlossen"
git push origin post-refactoring-v2.0
```
