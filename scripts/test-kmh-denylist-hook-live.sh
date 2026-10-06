#!/usr/bin/env bash
# Live-Test gegen ~/.config/kmh-denylist.txt — gibt Sperrwörter nicht aus.
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="${REPO_ROOT}/scripts/kmh-denylist-hook-lib.sh"
# shellcheck source=/dev/null
. "$LIB"

deny_file="$(_kmh_denylist_path)"
if [ ! -f "$deny_file" ]; then
  echo "SKIP: $deny_file fehlt (lokal anlegen)"
  exit 0
fi

export KMH_DENYLIST_FILE="$deny_file"

if _kmh_check_text_against_denylist "baseline-check" "align-baseline in css"; then
  echo "ok: baseline substring check (kein =ExampleTown-Treffer nötig)"
else
  echo "FAIL: unerwartet blockiert bei align-baseline" >&2
  exit 1
fi

first=""
first_mode=""
while IFS= read -r line || [ -n "$line" ]; do
  parsed="$(_kmh_parse_deny_entry "$line" || true)"
  [ -z "$parsed" ] && continue
  first_mode="${parsed%%$'\t'*}"
  first="${parsed#*$'\t'}"
  break
done < "$deny_file"

if [ -z "$first" ]; then
  echo "SKIP: Sperrliste leer"
  exit 0
fi

probe="token ${first} token"
if [ "$first_mode" = "word" ]; then
  probe="${first} standalone"
fi

if _kmh_check_text_against_denylist "live-block" "$probe"; then
  echo "FAIL: first denylist entry was not blocked" >&2
  exit 1
fi

echo "ok: first denylist entry blocked (pattern not printed)"
echo "kmh-denylist live: PASS"
