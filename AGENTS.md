# KI-Mail-Helper-Dev — Hinweise für KI-Assistenten

## Invarianten Dev-PC — **zuerst lesen, nicht raten**

| Was | Wo |
|-----|-----|
| **Python-venv** | Eine venv, getrennt vom Repo: `~/kmh-venv` auf WSL-ext4. Liegt schon. Kein Symlink ins Repo. **Nie** `venv/` oder `pip install` unter OneDrive |
| **Arbeitskopie** | `~/src/KI-Mail-Helper-Dev` auf WSL-ext4. Dort wird gelesen und getestet. Die OneDrive-Kopie bleibt die Sicherung und der Editor-Ordner |
| **Tests** | Erst die Sicherung nach `~/src/KI-Mail-Helper-Dev` spiegeln, dann dort `source ~/kmh-venv/bin/activate` und `bash scripts/pre-push-dev-check.sh`. PowerShell-`python` zählt nicht |
| **Spiegel** | `public` (öffentliches KI-Mail-Helper) nur auf ausdrückliche Nutzeranweisung, von diesem Dev-Repo aus. Sonst kein Sync dorthin |

**CT-Server** (`/opt/KI-Mail-Helper/venv`): siehe Deploy — nicht mit der Dev-PC-WSL verwechseln.

## Versions-Wahrheit

Kanonisch auf `main`: `requirements.txt`, `requirements-venv.txt`, `requirements-ml.txt` (Root). Keine Pins in Doku/Chat erfinden — Dateien lesen oder Produktions-venv nach `git pull` prüfen.

## Dependabot

- **Security updates** in GitHub-Repo-Einstellungen aktivieren (CVE-PRs).
- **Version updates:** `.github/dependabot.yml` — weekly, **eine gruppierte pip-PR**, semver-major ignoriert (Majors bewusst testen).
- Nach gruppiertem Merge: lokal oder auf dem Deploy-Host `bash scripts/verify-pip-resolve.sh` (frisches venv, alle drei requirements-Dateien).
- Bekannte gekoppelte Pins: `pydantic`/`pydantic_core` (Dependabot: `pydantic-core` ignorieren), `flake8`/`pycodestyle`/`pyflakes`, `mypy`/`pathspec`, `pylint`/`astroid`, `pyOpenSSL`/`cryptography` (pyOpenSSL 26.4 → **cryptography>=49**), `spacy`/`weasel`/`confection` (spacy 3.8 → **weasel>=1.0**, **confection>=1.3.2**), `transformers`/`tokenizers`/`huggingface_hub` gemeinsam.
- Nicht pauschal downgraden: Konflikt lesen — oft muss das **andere** Paket hoch- statt runtergepinnt werden.

## Deploy

**Betrieb (Pull, venv, systemd, Alembic):** nur im **privaten Betriebsdokument** des Betreibers — nicht in diesem Repo. Nach Dependency-Merge auf `main`: venv neu installieren + Services neu starten (vom Betreiber).

**Vor Push (Entwicklung):** `bash scripts/pre-push-dev-check.sh` — `compileall` + `pytest tests/ -q` (nur `tests/`, keine `scripts/test_*.py`). Alias: `bash scripts/ci-local.sh`. Auf dem Windows-Rechner in **WSL** mit `source ~/kmh-venv/bin/activate` (Abschnitt «Tests — wo und wie»). **GitHub:** `.github/workflows/ci.yml` bei Push/PR auf `main` (Python 3.13, `pip install -r requirements.txt`, dann `pre-push-dev-check`).

**Nach Deploy (CT):** `bash scripts/pytest-audit-smoke.sh` — Audit/Tranco/Scam/Marken/DBL. **`pytest tests/`** ist deutlich größer (Legacy, alte Pfade, Integration) und kein Release-Gate.

## Tests — wo und wie (Agent / Entwickler)

| Ort | venv | Befehl |
|-----|------|--------|
| **CT Produktion** (`/opt/KI-Mail-Helper`) | bestehendes `venv/` | `source venv/bin/activate` → `pip install -r requirements.txt` → optional `pip uninstall -y <Paket>` wenn aus requirements entfernt (z. B. `mistralai`) → `pip check` → `bash scripts/pre-push-dev-check.sh` |
| **WSL (Windows-Dev)** | `~/kmh-venv` auf ext4, Tests nur in `~/src/KI-Mail-Helper-Dev` | siehe Block unten |
| **PowerShell ohne WSL** | oft **kein** brauchbares Python | Store-Alias `python`/`python3` reicht **nicht** — nicht als «Tests gelaufen» melden |
| **CI** | frisch in Workflow | wie Zeile «Vor Push» |

### WSL: lesen und testen auf ext4, OneDrive bleibt die Sicherung

**Richtig:** venv `~/kmh-venv`. Arbeitskopie `~/src/KI-Mail-Helper-Dev`. Beides auf der Linux-Platte. Die OneDrive-Kopie wird nicht verschoben und ist nicht das pytest-Verzeichnis. Kein zweites Clone von GitHub: die Arbeitskopie ist eine lokale Spiegelung der Sicherung.

**WSL — einmalig, nur wenn `~/kmh-venv` fehlt** (sie liegt schon):

```bash
python3 -m venv ~/kmh-venv
source ~/kmh-venv/bin/activate
pip install -r requirements.txt
```

**WSL — Arbeitskopie spiegeln, dann Gate vor Push.** `QUELLE` ist das geöffnete Repo (OneDrive-Sicherung). Den Windows-Benutzerpfad nicht in diese Datei schreiben.

```bash
mkdir -p ~/src
rsync -a --delete \
  --exclude '.pytest_cache/' \
  --exclude '__pycache__/' \
  --exclude 'venv/' \
  --exclude '.venv/' \
  "$QUELLE/" ~/src/KI-Mail-Helper-Dev/
cd ~/src/KI-Mail-Helper-Dev
source ~/kmh-venv/bin/activate
bash scripts/pre-push-dev-check.sh
```

**WSL — einzelne Tests** (nur in der Arbeitskopie, nach dem Spiegeln):

```bash
cd ~/src/KI-Mail-Helper-Dev
source ~/kmh-venv/bin/activate
PYTHONPATH=. python -m pytest tests/test_audit_own_domains.py -q
```

**Falsch:** `pytest` mit cwd unter OneDrive. `python3 -m venv` oder `pip install` unter OneDrive. PowerShell-`python` ohne WSL zählt nicht.

**Agent-Pflicht:** Kein `pip`/`venv` unter OneDrive. Kein zweites Clone von GitHub. Lesen und Testen nur in `~/src/KI-Mail-Helper-Dev`, vorher aus der Sicherung spiegeln. `public` nicht anfassen, ausser der Nutzer verlangt den Spiegel. Vor «grün» / Push: **`pre-push-dev-check.sh` in der Arbeitskopie** mit `~/kmh-venv` (oder CT-Ergebnis vom Betreiber). Nach Entfernen von Pins aus `requirements.txt`: auf dem CT **`pip uninstall`** + **`pip check`**.

**CT:** Produktion nur **`/opt/KI-Mail-Helper/venv`** — kein separates `/tmp`-Test-venv als Deploy-Schritt.

**Scam / Marken / DBL:** `docs/audit/README.md` (Index), `docs/audit/ordner-audit-scam.md`, `docs/audit/spamhaus-dbl.md`.

## Git

**`main`** für Produktionsfixes. Commit/Push nur auf Nutzeranweisung.

**Remote für Entwicklung:** `origin` → **KI-Mail-Helper-Dev** (Deploy-Ziel). Feature-Branches und KI-Arbeit **nur** hier — nicht im öffentlichen `KI-Mail-Helper` entwickeln (nur Spiegel/Sync von Dev).

**Keine Mailbox-Daten in Git:** Keine IMAP-Exports, Absenderlisten oder «Validierungs-Fixtures» aus echten Postfächern — weder in Tests noch in `scripts/`. Clustering-Tests nur mit synthetischen `TrashEmailInfo` in pytest; optionale Stats-Skripte erzeugen Daten im Speicher (`example.com`-Absender).

## Kontospezifisches — nie im Repo

**Keine kontospezifischen Werte im Repo** — auch nicht als Platzhalter, Beispiel, Kommentar oder Test. Alles Kontospezifische pflegt der Benutzer in der Oberfläche; Audit-Kontakte künftig verschlüsselt in der DB (siehe ADR).

**Erlaubte generische Beispiele:** `example.com`, `beispiel.example`, `meine-domain.ch`, «Max Muster» — nichts aus Screenshots, Mail oder Infrastruktur-Bezeichnern des Betreibers.

**Hooks (dieses Repo):** Lokale Sperrliste **`~/.config/kmh-denylist.txt`** (Windows: **`%USERPROFILE%\.config\kmh-denylist.txt`**) — **nicht** ins Repo (Vorlage: `scripts/kmh-denylist.example.txt`; Kopien `kmh-denylist.txt` / `denylist.txt` im Tree → `.gitignore`). **Syntax:** Teilstring (Punkte literal); **`=Wort`** = ganzes Wort; Domains **ohne** `@`; UTF-8 **ohne BOM**. Zusätzlich Safe-CLI `git-hooks/denylist.txt` (gitignored). Unter PowerShell ist **`bash`** oft **WSL** — **`"C:\Program Files\Git\bin\bash.exe" scripts/…`** oder **`KMH_DENYLIST_FILE`**. Install: `powershell -File scripts/install-git-hooks-kmh.ps1`. **Liste:** `scripts/bootstrap-kmh-denylist.ps1` + optional `~/.config/kmh-denylist-broad-words.txt`. Tests: `scripts/test-kmh-denylist-hook*.sh`, `scripts/test-bootstrap-kmh-denylist.ps1`.

**Remotes:** Deploy **`origin`** → `KI-Mail-Helper-Dev`. `public` ist der Spiegel ins öffentliche KI-Mail-Helper — nur auf ausdrückliche Nutzeranweisung, von Dev nach `public`. «ahead of public/main» ist normal.

**Produktion nach Force-Push auf `main`:** `git fetch origin && git reset --hard origin/main` (kein Merge-Pull), dann Deploy/Restart — Ablauf im privaten Betriebsdokument.

**History-Neustart (selten):** Erst wenn Hook steht und Working Tree sauber — ein Commit ohne Leak-Historie; Backup `git bundle`; Betreiber synchronisiert Deploy-Clone. Details: privates Ops-Dokument (Privacy/History), nicht im Repo.
