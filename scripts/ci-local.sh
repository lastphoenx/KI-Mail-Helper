#!/usr/bin/env bash
# Vor git push (lokal/WSL): gleiche Prüfung wie .github/workflows/ci.yml
set -eu
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"
exec bash scripts/pre-push-dev-check.sh
