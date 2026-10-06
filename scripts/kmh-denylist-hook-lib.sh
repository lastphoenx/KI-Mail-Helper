#!/usr/bin/env bash
# Prüft Text gegen ~/.config/kmh-denylist.txt (lokal, nicht im Repo).
#
# Syntax pro Zeile (ein Eintrag):
#   muster          → Teilstring, feste Zeichenkette (kein Regex), case-insensitive
#   =ExampleTown    → nur ganzes Wort (Buchstabe/Ziffer/_), für kurze/breite Begriffe
#   @domain.tld     → @ wird ignoriert; Domain als Teilstring (x@domain.tld)
# UTF-8-BOM am Zeilenanfang wird entfernt.

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

_kmh_strip_bom() {
  local s="$1"
  s="${s//$'\ufeff'/}"
  printf '%s' "$s"
}

# Parst eine Rohzeile → mode (substr|word) + pattern (fest, kein Regex)
_kmh_parse_deny_entry() {
  local raw="$1"
  local entry mode pattern
  entry="$(_kmh_strip_bom "$raw")"
  entry="${entry%%#*}"
  entry="${entry#"${entry%%[![:space:]]*}"}"
  entry="${entry%"${entry##*[![:space:]]}"}"
  [ -z "$entry" ] && return 1
  mode="substr"
  pattern="$entry"
  if [[ "$pattern" == =* ]]; then
    mode="word"
    pattern="${pattern#=}"
    pattern="${pattern#"${pattern%%[![:space:]]*}"}"
    pattern="${pattern%"${pattern##*[![:space:]]}"}"
    [ -z "$pattern" ] && return 1
  elif [[ "$pattern" == @* ]]; then
    pattern="${pattern#@}"
    pattern="${pattern#"${pattern%%[![:space:]]*}"}"
    pattern="${pattern%"${pattern##*[![:space:]]}"}"
    [ -z "$pattern" ] && return 1
  fi
  printf '%s\t%s' "$mode" "$pattern"
}

_kmh_to_lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

_kmh_is_word_char() {
  local c="$1"
  [[ "$c" =~ ^[[:alnum:]_]$ ]]
}

# Feste Teilzeichenkette, case-insensitive (ohne grep -F — bricht unter Git for Windows ab)
_kmh_substr_match_ci() {
  local text_lc pattern_lc
  text_lc="$(_kmh_to_lower "$1")"
  pattern_lc="$(_kmh_to_lower "$2")"
  case "$text_lc" in
    *"$pattern_lc"*) return 0 ;;
  esac
  return 1
}

_kmh_word_match_ci() {
  local text="$1" pattern="$2"
  local text_lc pattern_lc
  text_lc="$(_kmh_to_lower "$text")"
  pattern_lc="$(_kmh_to_lower "$pattern")"
  local plen=${#pattern_lc}
  local len=${#text_lc}
  local i=0
  if [ "$plen" -eq 0 ] || [ "$len" -lt "$plen" ]; then
    return 1
  fi
  while [ "$i" -le $((len - plen)) ]; do
    if [ "${text_lc:i:plen}" = "$pattern_lc" ]; then
      local before="" after=""
      if [ "$i" -gt 0 ]; then
        before="${text_lc:i-1:1}"
      fi
      if [ $((i + plen)) -lt "$len" ]; then
        after="${text_lc:i+plen:1}"
      fi
      if { [ -z "$before" ] || ! _kmh_is_word_char "$before"; } \
        && { [ -z "$after" ] || ! _kmh_is_word_char "$after"; }; then
        return 0
      fi
    fi
    i=$((i + 1))
  done
  return 1
}

_kmh_text_matches_pattern() {
  local mode="$1"
  local pattern="$2"
  local text="$3"
  if [ "$mode" = "word" ]; then
    _kmh_word_match_ci "$text" "$pattern"
  else
    _kmh_substr_match_ci "$text" "$pattern"
  fi
}

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

  local line parsed mode pattern
  while IFS= read -r line || [ -n "$line" ]; do
    parsed="$(_kmh_parse_deny_entry "$line" || true)"
    [ -z "$parsed" ] && continue
    mode="${parsed%%$'\t'*}"
    pattern="${parsed#*$'\t'}"
    if _kmh_text_matches_pattern "$mode" "$pattern" "$text"; then
      if [ "$mode" = "word" ]; then
        echo "kmh-denylist: BLOCKIERT in ${label} — ganzes Wort «=${pattern}» (nicht ins Repo committen)." >&2
      else
        echo "kmh-denylist: BLOCKIERT in ${label} — Teilstring «${pattern}» (nicht ins Repo committen)." >&2
      fi
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
