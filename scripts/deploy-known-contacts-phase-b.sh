#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

kmh_ensure_backup_dir
kmh_load_prod_database_url

cd "$KMH_APP_ROOT"
kmh_activate_venv
kmh_expect_db "$PGDATABASE"
"$KMH_PYTHON" scripts/verify_audit_known_contacts_encrypt.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE" --require-full --sample 0 \
  --expect-min "${KMH_EXPECT_MIN_CONTACTS:-1}"

DUMP_PATH="$(kmh_pg_dump pre-f8)"

kmh_stop_services
kmh_trap_restart_services_on_err

cd "$KMH_APP_ROOT"
kmh_activate_venv
kmh_expect_db "$PGDATABASE"
alembic upgrade f8a9b0c1d2e3
alembic current

KMH_SERVICES_STOPPED=0
trap - ERR

kmh_start_services
bash "${KMH_APP_ROOT}/scripts/pytest-audit-smoke.sh"

echo "Phase B fertig. pre-f8 dump: ${DUMP_PATH}"
