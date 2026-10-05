#!/usr/bin/env bash
# RDAP nic.ch — Rate-Limit / Erreichbarkeit vom Host (CT oder Dev).
# Keine Secrets. Ausgabe: HTTP-Status, Retry-After, grobe Latenz.
#
#   cd /opt/KI-Mail-Helper && bash scripts/rdap-nic-ch-probe.sh
#   bash scripts/rdap-nic-ch-probe.sh --burst 12 --interval 3
#   bash scripts/rdap-nic-ch-probe.sh --python 5

set -euo pipefail

BASE="https://rdap.nic.ch"
ACCEPT="Accept: application/rdap+json"
DOMAINS=(sbb.ch coop.ch post.ch ethz.ch helsana.ch bluewin.ch)

burst=8
interval=3
python_n=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --burst) burst="${2:-8}"; shift 2 ;;
    --interval) interval="${2:-3}"; shift 2 ;;
    --python) python_n="${2:-5}"; shift 2 ;;
    -h|--help)
      sed -n '1,8p' "$0"
      exit 0
      ;;
    *) echo "Unbekannt: $1" >&2; exit 2 ;;
  esac
done

one_curl() {
  local dom="$1"
  local hdr body code elapsed retry
  hdr="$(mktemp)"
  body="$(mktemp)"
  elapsed="$(
    curl -sS -o "$body" -D "$hdr" -w '%{http_code} %{time_total}' \
      -H "$ACCEPT" \
      "${BASE}/domain/${dom}" 2>/dev/null || echo "000 0"
  )"
  code="${elapsed%% *}"
  elapsed="${elapsed#* }"
  retry="$(grep -i '^Retry-After:' "$hdr" 2>/dev/null | head -1 | tr -d '\r' || true)"
  if [[ "$code" == "200" ]]; then
    reg="$(grep -o '"eventAction"[[:space:]]*:[[:space:]]*"registration"' "$body" | head -1 || true)"
    echo "  $dom  HTTP $code  ${elapsed}s  ${retry:-no Retry-After}  reg_event=${reg:+yes}${reg:-no}"
  else
    echo "  $dom  HTTP $code  ${elapsed}s  ${retry:-no Retry-After}"
  fi
  rm -f "$hdr" "$body"
}

preflight_code="$(
  curl -sS -o /dev/null -w '%{http_code}' -H "$ACCEPT" "${BASE}/domain/sbb.ch" 2>/dev/null || echo "000"
)"
if [[ "$preflight_code" == "429" ]]; then
  echo "nic.ch liefert sofort HTTP 429 (IP-Cooldown nach früheren Bursts)." >&2
  echo "Kein sinnvoller Probe-Lauf — warten bis einzelner curl 200:" >&2
  echo "  bash scripts/rdap-nic-ch-wait-ok.sh --interval 300" >&2
  echo "Parallel prüfen, ob Celery noch RDAP feuert:" >&2
  echo "  grep -E 'brand_health|RDAP 429' /var/log/mail-helper/celery-worker.log | tail -15" >&2
  exit 1
fi

echo "=== nic.ch RDAP — Einzelcheck (curl, ${interval}s Abstand) ==="
for d in "${DOMAINS[@]}"; do
  one_curl "$d"
  sleep "$interval"
done

echo ""
echo "=== Burst: ${burst} Anfragen, Abstand ${interval}s (Domain-Rotation) ==="
first_429=""
for ((i = 1; i <= burst; i++)); do
  d="${DOMAINS[$(( (i - 1) % ${#DOMAINS[@]} ))]}"
  code="$(
    curl -sS -o /dev/null -w '%{http_code}' -H "$ACCEPT" "${BASE}/domain/${d}" 2>/dev/null || echo "000"
  )"
  ts="$(date +%H:%M:%S)"
  echo "  [$ts] #$i $d -> HTTP $code"
  if [[ "$code" == "429" && -z "$first_429" ]]; then
    first_429="$i"
    curl -sS -D - -o /dev/null -H "$ACCEPT" "${BASE}/domain/${d}" 2>/dev/null | grep -iE '^(HTTP/|Retry-After:|X-RateLimit|RateLimit)' | head -5 || true
  fi
  [[ "$i" -lt "$burst" ]] && sleep "$interval"
done
if [[ -n "$first_429" ]]; then
  echo "  → Erste 429 bei Anfrage #$first_429"
else
  echo "  → Keine 429 in diesem Burst"
fi

echo ""
echo "=== Schnellburst (1 s, gleiche Domain — Limit-Test) ==="
d="sbb.ch"
for ((i = 1; i <= 10; i++)); do
  code="$(curl -sS -o /dev/null -w '%{http_code}' -H "$ACCEPT" "${BASE}/domain/${d}" 2>/dev/null || echo "000")"
  echo "  #$i $d -> HTTP $code"
  [[ "$code" == "429" ]] && break
  sleep 1
done

if [[ "$python_n" -gt 0 ]]; then
  echo ""
  echo "=== Python (domain_reputation, wie Celery) — ${python_n} Domains ==="
  root="$(cd "$(dirname "$0")/.." && pwd)"
  cd "$root"
  if [[ ! -d venv ]]; then
    echo "  venv fehlt unter $root — übersprungen" >&2
    exit 0
  fi
  # shellcheck disable=SC1091
  source venv/bin/activate
  export PYTHONPATH="$root"
  python3 - "$python_n" <<'PY'
import sys
import time

n = int(sys.argv[1])
domains = ["sbb.ch", "coop.ch", "post.ch", "ethz.ch", "helsana.ch", "bluewin.ch", "google.ch", "migros.ch"]

from src.services.domain_reputation import (
    lookup_rdap_registration_date,
    prepare_brand_health_rdap_batch,
    reset_rdap_rate_limit_state_for_tests,
)

reset_rdap_rate_limit_state_for_tests()
prepare_brand_health_rdap_batch(domains[:n])
for d in domains[:n]:
    t0 = time.monotonic()
    reg, st = lookup_rdap_registration_date(d, bypass_cache=True)
    print(f"  {d}: {st}  reg={reg.date() if reg else '-'}  ({time.monotonic() - t0:.2f}s)")
PY
fi

echo ""
echo "Fertig. 429 + Retry-After = Registry-Drossel; 000/Timeout = Netz/Firewall."
