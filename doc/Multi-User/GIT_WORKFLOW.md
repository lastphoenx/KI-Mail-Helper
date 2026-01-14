# Git Workflow für Multi-User Migration
**Feature-Branch:** `feature/multi-user-native`  
**Backup-Tag:** `v1.0-pre-multi-user`  
**Datum:** 14. Januar 2026

---

## 🎯 ÜBERSICHT

```
main Branch                    feature/multi-user-native
├── SQLite                     ├── PostgreSQL (nativ)
├── Legacy Job Queue           ├── Celery (nativ)
├── STABIL ✅                  ├── EXPERIMENTELL ⚙️
└── Port 5003                  └── Port 5004
```

---

## 📋 WICHTIGSTE BEFEHLE (Quick Reference)

### Branch wechseln
```bash
# Zu Feature-Branch (Multi-User) wechseln
git checkout feature/multi-user-native

# Zurück zu main (alte SQLite-Version)
git checkout main

# Aktuellen Branch anzeigen
git branch
```

### Änderungen committen
```bash
# Status prüfen
git status

# Dateien stagen
git add .
# ODER einzelne Datei:
git add requirements.txt

# Commit erstellen
git commit -m "feat: PostgreSQL native Setup"

# Zu Remote pushen
git push origin feature/multi-user-native
```

### Beide Branches synchron halten
```bash
# Bugfix in main machen
git checkout main
git add fix.py
git commit -m "fix: Bug XYZ"
git push

# Bugfix in Feature-Branch übernehmen
git checkout feature/multi-user-native
git merge main -m "merge: Bugfix von main"
git push
```

---

## 🚀 WORKFLOW: Tägliche Arbeit

### Tag 1-5: PostgreSQL Setup (auf Feature-Branch)
```bash
# Morgen: Feature-Branch aktivieren
cd /home/thomas/projects/KI-Mail-Helper-Dev
git checkout feature/multi-user-native

# Änderungen vornehmen (PostgreSQL installieren, etc.)
# ...

# Abend: Committen
git add .
git status  # Prüfen was committed wird
git commit -m "feat: PostgreSQL native Installation (apt install postgresql-15)"
git push origin feature/multi-user-native
```

### Tag 6-10: Celery Setup
```bash
git checkout feature/multi-user-native

# Celery installieren
source venv/bin/activate
pip install celery redis
pip freeze > requirements.txt

# Committen
git add requirements.txt
git add src/celery_app.py
git commit -m "feat: Celery native Setup mit Redis"
git push origin feature/multi-user-native
```

### Tag 11+: Testing parallel
```bash
# Terminal 1: Alte Version testen (main)
git checkout main
USE_BLUEPRINTS=1 python3 -m src.00_main --serve --https --port 5003

# Terminal 2: Neue Version testen (feature branch)
git checkout feature/multi-user-native
USE_BLUEPRINTS=1 DATABASE_URL=postgresql://localhost/mail_helper python3 -m src.00_main --serve --https --port 5004
```

---

## 🛡️ ROLLBACK-SZENARIEN

### Szenario 1: "Multi-User funktioniert nicht, zurück zu SQLite!"
```bash
# Option A: Einfach Branch wechseln
git checkout main
# ✅ Sofort wieder SQLite-Version läuft!

# Option B: Zurück zum Tag (exakt Stand vor Migration)
git checkout v1.0-pre-multi-user
# ✅ Wie eine Zeitmaschine!

# Option C: Feature-Branch löschen (VORSICHT!)
git branch -D feature/multi-user-native
# ⚠️ Nur wenn wirklich alles verwerfen!
```

### Szenario 2: "Nur eine Datei zurücksetzen"
```bash
# Auf Feature-Branch, aber eine Datei von main holen
git checkout feature/multi-user-native
git checkout main -- src/app_factory.py
# ✅ app_factory.py von main übernommen
```

### Szenario 3: "Merge zu main (nach erfolgreicher Migration)"
```bash
# Feature-Branch ist fertig und getestet
git checkout main
git merge feature/multi-user-native -m "feat: Multi-User Migration abgeschlossen"
git push

# Feature-Branch kann gelöscht werden (optional)
git branch -d feature/multi-user-native
git push origin --delete feature/multi-user-native
```

---

## 📊 STATUS PRÜFEN

### Was ist wo?
```bash
# Alle Branches anzeigen
git branch -a

# Unterschiede zwischen Branches
git diff main feature/multi-user-native

# Log von Feature-Branch
git checkout feature/multi-user-native
git log --oneline -10

# Files die geändert wurden
git diff main --name-only
```

### Remote Status
```bash
# Remote Branches anzeigen
git remote -v
git branch -r

# Feature-Branch zu Remote pushen (erstes Mal)
git push -u origin feature/multi-user-native

# Danach nur noch:
git push
```

---

## 🔄 TYPISCHE WORKFLOWS

### Workflow 1: Normale Weiterentwicklung auf Feature-Branch
```bash
# 1. Branch aktivieren
git checkout feature/multi-user-native

# 2. Änderungen machen
nano src/celery_app.py

# 3. Testen
USE_BLUEPRINTS=1 python3 -m src.00_main --serve --https --port 5004

# 4. Committen
git add src/celery_app.py
git commit -m "feat: Celery Task für Mail-Sync"
git push
```

### Workflow 2: Bugfix in main, dann merge zu Feature
```bash
# 1. Bugfix in main
git checkout main
nano src/blueprints/auth.py
git add src/blueprints/auth.py
git commit -m "fix: Login-Bug"
git push

# 2. Merge zu Feature-Branch
git checkout feature/multi-user-native
git merge main
git push
```

### Workflow 3: Täglicher Check (beide Branches funktionieren?)
```bash
# Morgen-Check: main Branch
git checkout main
USE_BLUEPRINTS=1 python3 -m src.00_main --serve --https --port 5003 &
curl https://localhost:5003/health
# ✅ SQLite-Version läuft

# Feature-Branch Check
git checkout feature/multi-user-native
USE_BLUEPRINTS=1 python3 -m src.00_main --serve --https --port 5004 &
curl https://localhost:5004/health
# ✅ PostgreSQL-Version läuft
```

---

## 🎯 COMMIT-CONVENTIONS (für saubere History)

### Format
```
<type>: <beschreibung>

[optional body]
```

### Types
- `feat:` Neue Features (z.B. `feat: PostgreSQL native Setup`)
- `fix:` Bugfixes (z.B. `fix: Celery Connection Error`)
- `refactor:` Code-Umstrukturierung
- `docs:` Dokumentation
- `test:` Tests hinzufügen
- `chore:` Dependencies, Config

### Beispiele
```bash
git commit -m "feat: PostgreSQL native Installation via apt"
git commit -m "feat: Redis native Setup (systemctl)"
git commit -m "feat: Celery Worker Configuration"
git commit -m "refactor: MailSyncService aus 14_background_jobs extrahiert"
git commit -m "test: Integration Tests für Celery Tasks"
git commit -m "docs: GIT_WORKFLOW.md erstellt"
git commit -m "fix: Database Session Leak in Task"
```

---

## 📝 NÜTZLICHE ALIASES (optional)

Füge zu `~/.bashrc` hinzu:
```bash
# Git Aliases für Multi-User Migration
alias git-status='git status --short'
alias git-main='git checkout main'
alias git-feature='git checkout feature/multi-user-native'
alias git-diff-branches='git diff main feature/multi-user-native --stat'
alias git-log-feature='git checkout feature/multi-user-native && git log --oneline -10'

# Server starten (Aliases)
alias run-main='cd /home/thomas/projects/KI-Mail-Helper-Dev && git checkout main && USE_BLUEPRINTS=1 python3 -m src.00_main --serve --https --port 5003'
alias run-feature='cd /home/thomas/projects/KI-Mail-Helper-Dev && git checkout feature/multi-user-native && USE_BLUEPRINTS=1 python3 -m src.00_main --serve --https --port 5004'
```

Aktivieren:
```bash
source ~/.bashrc
```

Nutzen:
```bash
git-feature  # Wechselt zu feature/multi-user-native
run-feature  # Startet Feature-Branch Server
```

---

## ⚠️ WICHTIGE HINWEISE

### Was du NICHT tun solltest:
- ❌ `git push --force` auf main (zerstört Historie!)
- ❌ Direkt auf main committen (erst in Feature, dann merge)
- ❌ Feature-Branch löschen bevor Merge (Arbeit weg!)

### Was du immer tun solltest:
- ✅ Vor Branch-Wechsel: `git status` (uncommitted changes?)
- ✅ Regelmäßig pushen: `git push` (Backup in Remote!)
- ✅ Vor großen Änderungen: `git add . && git commit` (Checkpoint!)

---

## 🆘 HILFE / TROUBLESHOOTING

### "Ich habe uncommitted changes und kann Branch nicht wechseln!"
```bash
# Option 1: Stash (temporär speichern)
git stash
git checkout main
# Später zurück:
git checkout feature/multi-user-native
git stash pop

# Option 2: Committen
git add .
git commit -m "wip: Work in Progress"
git checkout main
```

### "Ich habe aus Versehen in main committed!"
```bash
# Cherry-Pick zu Feature-Branch
git log  # Finde Commit-Hash
git checkout feature/multi-user-native
git cherry-pick <commit-hash>

# Commit von main entfernen
git checkout main
git reset --hard HEAD~1  # ⚠️ VORSICHT! Löscht letzten Commit!
```

### "Merge-Konflikt!"
```bash
# Nach git merge gibt es Konflikt
git status  # Zeigt Konflikt-Dateien

# Konflikt manuell lösen in Editor
nano <konflikt-datei>

# Nach Lösung:
git add <konflikt-datei>
git commit -m "merge: Konflikt gelöst"
```

---

## 🎓 LERNEN: Git visualisiert

```
main Branch:
  ee669e7 ← HEAD (aktuell)
  b6b8838
  c34d36a
  
Nach Tag-Erstellung:
  ee669e7 ← v1.0-pre-multi-user (TAG)
  b6b8838
  
Nach Branch:
  main:                     feature/multi-user-native:
  ee669e7 ← main            ee669e7 ← feature ← HEAD
                            |
                            f123abc (PostgreSQL Setup)
                            |
                            g456def (Celery Setup)
```

---

**Erstellt:** 14. Januar 2026  
**Aktueller Branch:** `feature/multi-user-native`  
**Sicherheits-Tag:** `v1.0-pre-multi-user`
