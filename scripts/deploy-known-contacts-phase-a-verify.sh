#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

kmh_load_prod_database_url
cd "$KMH_APP_ROOT"
kmh_activate_venv
kmh_expect_db "$PGDATABASE"

"$KMH_PYTHON" scripts/verify_audit_known_contacts_encrypt.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE" --require-full --sample 0 \
  --expect-min "${KMH_EXPECT_MIN_CONTACTS:-1}"

echo "Verify OK — Phase B: bash ${SCRIPT_DIR}/deploy-known-contacts-phase-b.sh"
