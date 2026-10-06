# KI-Mail-Helper-Dev — Hinweise für KI-Assistenten

## Versions-Wahrheit

Kanonisch auf `main`: `requirements.txt`, `requirements-venv.txt`, `requirements-ml.txt` (Root). Keine Pins in Doku/Chat erfinden — Dateien lesen oder Produktions-venv nach `git pull` prüfen.

## Dependabot

- **Security updates** in GitHub-Repo-Einstellungen aktivieren (CVE-PRs).
- **Version updates:** `.github/dependabot.yml` — weekly, **eine gruppierte pip-PR**, semver-major ignoriert (Majors bewusst testen).
- Nach gruppiertem Merge: lokal oder auf CT `bash scripts/verify-pip-resolve.sh` (frisches venv, alle drei requirements-Dateien).
- Bekannte gekoppelte Pins: `pydantic`/`pydantic_core`, `flake8`/`pycodestyle`/`pyflakes`, `mistralai`/`orjson`, `mypy`/`pathspec`, `pylint`/`astroid` (nur **4.0.x**), `pyOpenSSL`/`cryptography` (pyOpenSSL 26.4 → **cryptography>=49**), `spacy`/`weasel`/`confection` (spacy 3.8 → **weasel>=1.0**, **confection>=1.3.2**), `transformers`/`tokenizers`/`huggingface_hub` gemeinsam (Prod: **5.17.0** / **0.23.2** / **1.33.0**).
- Nicht pauschal downgraden: Konflikt lesen — oft muss das **andere** Paket hoch- statt runtergepinnt werden.

## Deploy

CT **134** — vollständige Befehle: privates `doku/pve2/vm/134-ki-mail-helper/betrieb.md` und `doku/ops/deploy-after-git-pull.md`. Nach Dependency-Merge auf `main`: venv neu installieren + Services neu starten (vom Betreiber).

**Vor Push (Entwicklung):** `bash scripts/pre-push-dev-check.sh` — `compileall` + `pytest -q` (siehe **Hooks**).

**Nach Deploy (CT):** `bash scripts/pytest-audit-smoke.sh` — Audit/Tranco/Scam/Marken/DBL. **`pytest tests/`** ist deutlich größer (Legacy, alte Pfade, Integration) und kein Release-Gate.

**Scam / Marken / DBL:** `docs/audit/README.md` (Index), `docs/audit/ordner-audit-scam.md`, `docs/audit/spamhaus-dbl.md`.

## Git

**`main`** für Produktionsfixes. Commit/Push nur auf Nutzeranweisung.

**Remote für Entwicklung:** `origin` → `KI-Mail-Helper-Dev` (Deploy CT 134). Feature-Branches und KI-Arbeit **nur** hier — nicht im öffentlichen `KI-Mail-Helper` entwickeln (nur Spiegel/Sync von Dev).

**Keine Mailbox-Daten in Git:** Keine IMAP-Exports, Absenderlisten oder «Validierungs-Fixtures» aus echten Postfächern — weder in Tests noch in `scripts/`. Clustering-Tests nur mit synthetischen `TrashEmailInfo` in pytest; optionale Stats-Skripte erzeugen Daten im Speicher (`example.com`-Absender).

## Kontospezifisches — nie im Repo

**Keine kontospezifischen Werte im Repo** — auch nicht als Platzhalter, Beispiel, Kommentar oder Test. Alles Kontospezifische pflegt der Benutzer in der Oberfläche; es landet in der **verschlüsselten DB**.

**Erlaubte generische Beispiele:** `example.com`, `beispiel.example`, `meine-domain.ch`, «Max Muster» — nichts aus Screenshots, CT, Mail oder Homelab.

**Hooks (dieses Repo):** Lokale Sperrliste `~/.config/kmh-denylist.txt` (nicht im Git). **Standard:** Teilstring, feste Zeichenkette (Punkte literal, kein Regex). **`=Wort`** am Zeilenanfang = nur ganzes Wort (z. B. `=ExampleTown`). **`@domain`** in der Datei **ohne** `@` eintragen (`domain.tld` findet `x@domain.tld`). UTF-8 **ohne BOM**. Install: `powershell -File scripts/install-git-hooks-kmh.ps1` → `core.hooksPath=.githooks` (nach jedem frischen Clone). Test: `bash scripts/test-kmh-denylist-hook.sh`, `bash scripts/test-kmh-denylist-hook-cases.sh`, `bash scripts/test-kmh-denylist-hook-git.sh`. `--no-verify` umgeht Hooks; GitHub prüft nicht mit.

**Remotes:** Deploy **`origin`** → `KI-Mail-Helper-Dev`. `public` ist Spiegel — «ahead of public/main» ist normal und kein fehlender Push.

**CT 134 nach Force-Push auf `main`:** `git fetch origin && git reset --hard origin/main` (kein Merge-Pull), dann Deploy/Restart.

**History-Neustart (selten):** Erst wenn Hook steht und Working Tree sauber — ein Commit ohne Leak-Historie (orphan/`reset` + force), Backup `git bundle create ../kmh-backup.bundle --all`, danach CT 134 `git fetch && git reset --hard origin/main`, Entwickler **neu klonen**. Details: privates `doku/ops/privacy-cleanup-playbook.md`.
