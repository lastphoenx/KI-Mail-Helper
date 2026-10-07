#!/usr/bin/env bash
# Phase A bis f7: Backup (Dienste laufen) → Stop → alembic f7.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

kmh_ensure_backup_dir
kmh_load_prod_database_url
kmh_pull_code
cd "$KMH_APP_ROOT"
kmh_expect_db "$PGDATABASE"

DUMP_PATH="$(kmh_pg_dump pre-f7)"

kmh_stop_services
kmh_trap_restart_services_on_err

cd "$KMH_APP_ROOT"
kmh_activate_venv
alembic upgrade f7a8b9c0d1e2
alembic current

KMH_SERVICES_STOPPED=0
trap - ERR

echo ""
echo "f7 fertig. Dump: ${DUMP_PATH}"
echo "Weiter: Neuaufbau (empfohlen) oder Backfill — siehe deploy-known-contacts-encryption.md"
