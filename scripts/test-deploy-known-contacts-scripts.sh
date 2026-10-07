#!/usr/bin/env bash
# Syntax + Backup-Dir/pg_dump-Integration (postgres) für deploy-known-contacts-*.sh
#
# Auf CT/WSL mit PostgreSQL:
#   cd /opt/KI-Mail-Helper && bash scripts/test-deploy-known-contacts-scripts.sh
#
# Nur Syntax (ohne postgres):
#   KMH_DEPLOY_TEST_SKIP_PG=1 bash scripts/test-deploy-known-contacts-scripts.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "== bash -n deploy-known-contacts-*.sh =="
for f in "${SCRIPT_DIR}"/deploy-known-contacts-*.sh; do
  bash -n "$f"
  echo "  OK $(basename "$f")"
done

if [ "${KMH_DEPLOY_TEST_SKIP_PG:-0}" = "1" ]; then
  echo "SKIP: PostgreSQL-Integration (KMH_DEPLOY_TEST_SKIP_PG=1)"
  exit 0
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "SKIP: psql nicht gefunden"
  exit 0
fi

if ! sudo -u postgres psql -d postgres -c "SELECT 1" >/dev/null 2>&1; then
  echo "SKIP: sudo -u postgres psql nicht verfügbar"
  exit 0
fi

# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

TEST_DB="${KMH_DEPLOY_TEST_DB:-mail_helper_contacts_deploy_test}"
export PGBACKUP_DIR="${PGBACKUP_DIR:-/tmp/kmh-deploy-test-backup}"
export PGDATABASE="$TEST_DB"
export KMH_APP_ROOT="${KMH_APP_ROOT:-$ROOT}"
export KMH_DEPLOY_TEST=1

echo "== Backup-Verzeichnis (postgres schreibbar) =="
sudo rm -rf "$PGBACKUP_DIR"
kmh_ensure_backup_dir
sudo -u postgres test -w "$PGBACKUP_DIR" || {
  echo "FEHLER: postgres kann nicht in $PGBACKUP_DIR schreiben" >&2
  exit 1
}

echo "== Test-DB ${TEST_DB} =="
sudo -u postgres dropdb --if-exists "$TEST_DB"
sudo -u postgres createdb -O postgres "$TEST_DB"
sudo -u postgres psql -d "$TEST_DB" -v ON_ERROR_STOP=1 -c \
  "CREATE TABLE IF NOT EXISTS _kmh_deploy_test (id int);"

if [ -f "${KMH_APP_ROOT}/.env" ]; then
  kmh_load_prod_database_url
  export DATABASE_URL="$(kmh_database_url_for_db "$TEST_DB")"
else
  export DATABASE_URL="postgresql:///${TEST_DB}"
fi

DUMP="$(kmh_pg_dump integration-test)"
sudo -u postgres test -f "$DUMP" || {
  echo "FEHLER: Dump-Datei fehlt: $DUMP" >&2
  exit 1
}

echo "== expect-db gegen Test-DB =="
if [ -x "${KMH_VENV}/bin/python" ]; then
  kmh_expect_db "$TEST_DB"
else
  echo "SKIP: kmh_expect_db (venv fehlt unter ${KMH_VENV})"
fi

echo "== Skript-Hooks (TEST-Modus, kein systemctl) =="
kmh_stop_services
kmh_start_services

sudo -u postgres dropdb --if-exists "$TEST_DB"
sudo rm -rf "$PGBACKUP_DIR"

echo "OK: deploy-known-contacts Integration"
