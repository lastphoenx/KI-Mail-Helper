#!/usr/bin/env bash
set -eu
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
TMP="$(mktemp)"
OUT="$(mktemp)"
echo "KMH_HOOK_SELFTEST_TOKEN_XYZ" > "$TMP"
export KMH_DENYLIST_FILE="$TMP"
PROBE=".kmh-hook-probe.tmp"
echo "x KMH_HOOK_SELFTEST_TOKEN_XYZ y" > "$PROBE"
git add -f "$PROBE"
set +e
git commit -m "probe should fail" > "$OUT" 2>&1
ec=$?
set -e
cat "$OUT"
rm -f "$PROBE" "$TMP"
git reset HEAD "$PROBE" 2>/dev/null || true
if [ "$ec" -eq 0 ]; then
  rm -f "$OUT"
  echo "FAIL: commit succeeded but should be blocked" >&2
  exit 1
fi
if ! grep -q "kmh-denylist: BLOCKIERT" "$OUT"; then
  rm -f "$OUT"
  echo "FAIL: commit failed but not by kmh-denylist" >&2
  exit 1
fi
rm -f "$OUT"
echo "git pre-commit: REJECTED blocked word — OK"
