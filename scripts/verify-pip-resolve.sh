#!/usr/bin/env bash
# Dry-run: alle Requirement-Dateien in frischem venv auflösbar? (Python 3.13 wie Produktion)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$PY" -m venv "$TMP/venv"
# shellcheck source=/dev/null
source "$TMP/venv/bin/activate"
python -m pip install -q -U pip
python -m pip install \
  -r "$ROOT/requirements.txt" \
  -r "$ROOT/requirements-venv.txt" \
  -r "$ROOT/requirements-ml.txt"
echo "verify-pip-resolve: OK"
