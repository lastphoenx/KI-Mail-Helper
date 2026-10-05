#!/usr/bin/env bash
# BFS-Vornamen CSV (dam-api.bfs.admin.ch) — CT 134 / Dev mit Python3.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
UA="KI-Mail-Helper-firstnames-test/1.0"

echo "=== 1) BFS DAM-API CSV (firstname-Spalte) ==="
for PAIR in "female:36752506" "male:36752513"; do
  LABEL="${PAIR%%:*}"
  ASSET="${PAIR##*:}"
  URL="https://dam-api.bfs.admin.ch/hub/api/dam/assets/${ASSET}/master"
  HTTP=$(curl -sS -o "/tmp/fn-bfs-${ASSET}.csv" -w "%{http_code}" \
    -H "Accept: text/csv,*/*" -A "$UA" -L "$URL")
  echo "bfs ${LABEL}: HTTP ${HTTP} url=${URL}"
  if [[ "$HTTP" != "200" ]]; then
    echo "FAIL: HTTP ${HTTP}" >&2
    exit 1
  fi
  python3 - <<PY
import sys
p = "/tmp/fn-bfs-${ASSET}.csv"
raw = open(p, encoding="utf-8", errors="replace").read(400)
if raw.lstrip().startswith("<"):
    print("FAIL: HTML statt CSV")
    sys.exit(1)
if "firstname" not in raw.lower():
    print("FAIL: Spalte firstname nicht in Kopfzeile")
    sys.exit(1)
print("  OK head:", raw.splitlines()[0][:80])
PY
done

echo ""
echo "=== 2) Python-Skript --test-api ==="
python3 scripts/import_firstnames.py --test-api

echo ""
echo "=== 3) Dry-run (Zählen, keine DB) ==="
python3 scripts/import_firstnames.py --dry-run

echo ""
echo "OK — DB-Import: python3 scripts/import_firstnames.py"
echo "    Anzahl in DB: python3 scripts/import_firstnames.py --count-db"
