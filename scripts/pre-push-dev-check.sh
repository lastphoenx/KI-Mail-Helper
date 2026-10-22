#!/usr/bin/env bash
# Vor git push: Syntax unter src/ + volle pytest-Suite (Release-Gate Dev-Repo).
set -eu
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python}"
echo "pre-push-dev-check: compileall src/" >&2
"$PYTHON" -m compileall -q src
echo "pre-push-dev-check: pytest tests/ -q (ohne geerbte Umgebungsvariablen, CI-ähnlich)" >&2
env -i PATH="${PATH}" HOME="${HOME:-/tmp}" LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 \
  SECRET_KEY="${SECRET_KEY:-ci-test-secret-key-not-for-production-use}" \
  OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}" \
  OLLAMA_MODEL="${OLLAMA_MODEL:-test}" \
  "$PYTHON" -m pytest tests/ -q
