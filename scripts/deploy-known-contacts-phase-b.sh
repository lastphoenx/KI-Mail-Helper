#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

sudo mkdir -p "$PGBACKUP_DIR"
kmh_load_prod_database_url

kmh_stop_services

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" \
  -f "${PGBACKUP_DIR}/${PGDATABASE}-pre-f8-${STAMP}.dump"

cd "$KMH_APP_ROOT"
kmh_activate_venv
kmh_expect_db "$PGDATABASE"

"$KMH_PYTHON" scripts/verify_audit_known_contacts_encrypt.py \
  --user-id "$KMH_USER_ID" --expect-db "$PGDATABASE" --require-full --sample 0

kmh_expect_db "$PGDATABASE"
alembic upgrade f8a9b0c1d2e3
alembic current

kmh_start_services
bash "${KMH_APP_ROOT}/scripts/pytest-audit-smoke.sh"

echo "Phase B fertig. pre-f8 dump: ${PGBACKUP_DIR}/${PGDATABASE}-pre-f8-${STAMP}.dump"
