#!/usr/bin/env bash
# Phase A bis f7: Stop, pg_dump pre-f7, git pull, alembic f7.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

sudo mkdir -p "$PGBACKUP_DIR"
kmh_load_prod_database_url
cd "$KMH_APP_ROOT"
kmh_expect_db "$PGDATABASE"

kmh_stop_services

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
echo "== pg_dump pre-f7 =="
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" \
  -f "${PGBACKUP_DIR}/${PGDATABASE}-pre-f7-${STAMP}.dump"
ls -la "$PGBACKUP_DIR" | tail -5

kmh_pull_code
cd "$KMH_APP_ROOT"
alembic upgrade f7a8b9c0d1e2
alembic current

echo ""
echo "f7 fertig. Dump: ${PGBACKUP_DIR}/${PGDATABASE}-pre-f7-${STAMP}.dump"
echo "Weiter: Neuaufbau (empfohlen) oder Backfill — siehe deploy-known-contacts-encryption.md"
