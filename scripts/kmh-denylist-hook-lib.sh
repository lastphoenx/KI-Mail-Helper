#!/usr/bin/env bash
# Prüft Text gegen ~/.config/kmh-denylist.txt (ganze Wörter, grep -w).
# Sperrliste liegt nur lokal — nicht im Repo.

set -eu

_kmh_denylist_path() {
  if [ -n "${KMH_DENYLIST_FILE:-}" ]; then
    echo "$KMH_DENYLIST_FILE"
    return 0
  fi
  if [ -n "${HOME:-}" ]; then
    echo "${HOME}/.config/kmh-denylist.txt"
    return 0
  fi
  echo ""
}

# _kmh_check_text_against_denylist "<label>" "<multiline text>"
# Exit 1 wenn ein Sperrwort als ganzes Wort vorkommt.
_kmh_check_text_against_denylist() {
  local label="$1"
  local text="$2"
  local deny_file
  deny_file="$(_kmh_denylist_path)"
  if [ -z "$deny_file" ] || [ ! -f "$deny_file" ]; then
    echo "kmh-denylist: Datei fehlt (${deny_file:-\$HOME/.config/kmh-denylist.txt}) — Commit abgebrochen." >&2
    echo "  Lege die lokale Sperrliste an oder setze KMH_DENYLIST_FILE." >&2
    return 1
  fi
  if [ -z "$(printf '%s' "$text" | tr -d '[:space:]')" ]; then
    return 0
  fi

  local line word
  while IFS= read -r line || [ -n "$line" ]; do
    word="${line%%#*}"
    word="${word#"${word%%[![:space:]]*}"}"
    word="${word%"${word##*[![:space:]]}"}"
    [ -z "$word" ] && continue
    if printf '%s\n' "$text" | grep -qiw -- "$word"; then
      echo "kmh-denylist: BLOCKIERT in ${label} — ganzes Wort «${word}» (nicht ins Repo committen)." >&2
      return 1
    fi
  done < "$deny_file"
  return 0
}

_kmh_staged_added_lines() {
  git diff --cached -U0 --no-color --no-ext-diff 2>/dev/null \
    | grep -E '^\+' \
    | grep -v -E '^\+\+\+' \
    | sed 's/^+//' || true
}

kmh_check_staged_diff() {
  local added
  added="$(_kmh_staged_added_lines)"
  _kmh_check_text_against_denylist "neue Zeilen (staged Diff)" "$added"
}

kmh_check_commit_message_file() {
  local msg_file="$1"
  [ -f "$msg_file" ] || return 0
  _kmh_check_text_against_denylist "Commit-Message" "$(cat "$msg_file")"
}
