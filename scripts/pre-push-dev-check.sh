#!/usr/bin/env bash
# Vor git push: Syntax unter src/ + volle pytest-Suite (Release-Gate Dev-Repo).
set -eu
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python}"
echo "pre-push-dev-check: compileall src/" >&2
"$PYTHON" -m compileall -q src
echo "pre-push-dev-check: pytest tests/ -q" >&2
"$PYTHON" -m pytest tests/ -q
