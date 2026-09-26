# KI-Mail-Helper-Dev — Hinweise für KI-Assistenten

## Versions-Wahrheit

Kanonisch auf `main`: `requirements.txt`, `requirements-venv.txt`, `requirements-ml.txt` (Root). Keine Pins in Doku/Chat erfinden — Dateien lesen oder Produktions-venv nach `git pull` prüfen.

## Dependabot

- **Security updates** in GitHub-Repo-Einstellungen aktivieren (CVE-PRs).
- **Version updates:** `.github/dependabot.yml` — weekly, **eine gruppierte pip-PR**, semver-major ignoriert (Majors bewusst testen).

## Deploy

Kein standardisierter CT in diesem öffentlichen Repo — Betriebspfad steht in privater `doku/` des Betreibers. Nach Dependency-Merge auf `main`: venv neu installieren + Services neu starten (vom Betreiber).

## Git

**`main`** für Produktionsfixes. Commit/Push nur auf Nutzeranweisung.
