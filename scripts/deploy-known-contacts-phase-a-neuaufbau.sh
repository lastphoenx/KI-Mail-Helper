#!/usr/bin/env bash
# Nach f7 (Homelab-Standard): Kontakte + Import-State leeren, Dienste starten, UI-Import.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

kmh_load_prod_database_url
cd "$KMH_APP_ROOT"
kmh_activate_venv
kmh_expect_db "$PGDATABASE"

echo "== Kontakte löschen + audit_contacts_import_state zurücksetzen =="
"$KMH_PYTHON" scripts/clear_audit_known_contacts_user.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE"

kmh_start_services

cat <<EOF

== Manuell (UI) ==
1. Einloggen, Service-Token / Hintergrund-DEK aktiv
2. Ordner-Audit → Konfiguration → Bekannte Kontakte → Import aus Gesendet
   („Letzter Import“ sollte nach Neuaufbau leer sein.)

Danach (mindestens 1 Kontakt erwartet):
  bash ${SCRIPT_DIR}/deploy-known-contacts-phase-a-verify.sh

EOF
