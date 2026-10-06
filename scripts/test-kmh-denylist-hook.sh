#!/usr/bin/env bash
# Self-test: temporäre Sperrliste + Fake-Staged-Diff — kein privates Wort im Repo.
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="${REPO_ROOT}/scripts/kmh-denylist-hook-lib.sh"
# shellcheck source=/dev/null
. "$LIB"

TOKEN="KMH_HOOK_SELFTEST_TOKEN_XYZ"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
printf '%s\n' "$TOKEN" > "$TMP"

export KMH_DENYLIST_FILE="$TMP"

if _kmh_check_text_against_denylist "selftest-clean" "hello example.com"; then
  echo "ok: clean text passed"
else
  echo "FAIL: clean text blocked" >&2
  exit 1
fi

if _kmh_check_text_against_denylist "selftest-block" "placeholder $TOKEN here"; then
  echo "FAIL: blocked word was allowed" >&2
  exit 1
else
  echo "ok: blocked word rejected"
fi

echo "kmh-denylist hook logic: PASS"
