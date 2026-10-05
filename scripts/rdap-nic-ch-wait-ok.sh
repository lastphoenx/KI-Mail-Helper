#!/usr/bin/env bash
# Warten bis nic.ch wieder HTTP 200 liefert (IP-Cooldown nach zu vielen RDAP-Anfragen).
#
# Hinweis: Während 429 kann jede weitere Anfrage die Sperre verlängern (Registry unbekannt).
# Deshalb Default: alle 5 Minuten, nicht jede Minute. Sicherer: 30–60 Min gar nichts
# an nic.ch senden (kein Domain-Check, kein Probe), dann EIN curl-Test.
#
#   bash scripts/rdap-nic-ch-wait-ok.sh
#   bash scripts/rdap-nic-ch-wait-ok.sh --interval 600 --max 12

set -euo pipefail

DOMAIN="${RDAP_NIC_CH_PROBE_DOMAIN:-sbb.ch}"
INTERVAL=300
MAX=24

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="${2:-sbb.ch}"; shift 2 ;;
    --interval) INTERVAL="${2:-60}"; shift 2 ;;
    --max) MAX="${2:-60}"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--interval SEC] [--max N] [--domain name.ch]"
      exit 0
      ;;
    *) echo "Unbekannt: $1" >&2; exit 2 ;;
  esac
done

URL="https://rdap.nic.ch/domain/${DOMAIN}"
echo "Prüfe ${URL} alle ${INTERVAL}s (max ${MAX} Versuche). Ctrl+C abbruch."
for ((n = 1; n <= MAX; n++)); do
  code="$(curl -sS -o /dev/null -w '%{http_code}' -H 'Accept: application/rdap+json' "$URL" 2>/dev/null || echo "000")"
  ts="$(date -Is 2>/dev/null || date)"
  echo "[$ts] Versuch $n/$MAX -> HTTP $code"
  if [[ "$code" == "200" ]]; then
    echo "OK — nic.ch antwortet wieder. Erst jetzt Domain-Prüfung / große Probes starten."
    exit 0
  fi
  if [[ "$code" != "429" ]]; then
    echo "Unerwarteter Status (nicht 429) — Netz/Registry prüfen." >&2
    exit 1
  fi
  [[ "$n" -lt "$MAX" ]] && sleep "$INTERVAL"
done

echo "Nach $((MAX * INTERVAL / 60)) Minuten weiterhin 429 — IP-Cooldown länger als erwartet oder Hintergrund lastet nic.ch." >&2
echo "Prüfen: laufende Celery RDAP-Tasks (grep brand_health im celery-worker.log)." >&2
exit 2
