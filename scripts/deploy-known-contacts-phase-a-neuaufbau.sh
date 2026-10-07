#!/usr/bin/env bash
# Nach f7 (Homelab-Standard): Kontakte leeren, Dienste starten, dann UI-Import.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

kmh_load_prod_database_url
kmh_expect_db "$PGDATABASE"

echo "== DELETE audit_known_contacts user_id=${KMH_USER_ID} =="
sudo -u postgres psql -d "$PGDATABASE" -v ON_ERROR_STOP=1 \
  -c "DELETE FROM audit_known_contacts WHERE user_id = ${KMH_USER_ID};"

kmh_start_services

cat <<EOF

== Manuell (UI) ==
1. Einloggen, Service-Token / Hintergrund-DEK aktiv
2. Ordner-Audit → Konfiguration → Bekannte Kontakte → Import aus Gesendet

Danach:
  bash ${SCRIPT_DIR}/deploy-known-contacts-phase-a-verify.sh

EOF
