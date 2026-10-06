#!/usr/bin/env bash
# Regression: Teilstring vs. =ganzes Wort, literal dots. Nur synthetische Muster.
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="${REPO_ROOT}/scripts/kmh-denylist-hook-lib.sh"
# shellcheck source=/dev/null
. "$LIB"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
cat > "$TMP" <<'LIST'
# synthetisch — nicht aus echten Leaks
needle_sub
mailuser
=wholeblock
beispiel-uni.example
LIST

export KMH_DENYLIST_FILE="$TMP"

_assert_block() {
  local name="$1"
  local text="$2"
  if _kmh_check_text_against_denylist "$name" "$text"; then
    echo "FAIL: should block: $name" >&2
    exit 1
  fi
  echo "ok: blocked — $name"
}

_assert_pass() {
  local name="$1"
  local text="$2"
  if ! _kmh_check_text_against_denylist "$name" "$text"; then
    echo "FAIL: should pass: $name" >&2
    exit 1
  fi
  echo "ok: pass — $name"
}

_assert_block "underscore substring" "mein_needle_sub_test"
_assert_block "digit in local-part" "mailuser1@beispiel.example"
_assert_block "email domain substring" "max@beispiel-uni.example"
_assert_pass "whole-word prefix" "align-baseline css"
_assert_pass "dot is literal not regex" "unXbeispiel-uniXexample"
_assert_block "self token" "x needle_sub y"

echo "kmh-denylist cases: PASS"
