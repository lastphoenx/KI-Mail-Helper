#!/usr/bin/env bash
# Substr (Bootstrap-Standard) vs =Wort — synthetische Muster, keine echten Leaks.
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="${REPO_ROOT}/scripts/kmh-denylist-hook-lib.sh"
# shellcheck source=/dev/null
. "$LIB"

_run_with_list() {
  local list_file="$1"
  export KMH_DENYLIST_FILE="$list_file"
}

_assert_block() {
  if _kmh_check_text_against_denylist "$1" "$2"; then
    echo "FAIL: should block: $1" >&2
    exit 1
  fi
  echo "ok: blocked — $1"
}

_assert_pass() {
  if ! _kmh_check_text_against_denylist "$1" "$2"; then
    echo "FAIL: should pass: $1" >&2
    exit 1
  fi
  echo "ok: pass — $1"
}

SUB="$(mktemp)"
WORD="$(mktemp)"
trap 'rm -f "$SUB" "$WORD"' EXIT

cat > "$SUB" <<'LIST'
tokenalpha
LIST

cat > "$WORD" <<'LIST'
=tokenalpha
LIST

_run_with_list "$SUB"
_assert_block "substr underscore" "mein_tokenalpha_test"
_assert_block "substr digit local" "tokenalpha1@beispiel.example"
_assert_block "substr suffix user" "tokenalpha_user"
_assert_block "substr dotted" "tokenalpha.li path"

_run_with_list "$WORD"
_assert_pass "word underscore" "mein_tokenalpha_test"
_assert_pass "word digit local" "tokenalpha1@beispiel.example"
_assert_pass "word suffix user" "tokenalpha_user"
_assert_block "word dotted label" "tokenalpha.li path"
_assert_pass "word embedded in token" "xtokenalpha.li"
_assert_block "word standalone" "tokenalpha value"

echo "kmh-denylist substr-policy: PASS"
