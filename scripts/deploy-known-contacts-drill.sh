#!/usr/bin/env bash
# Probelauf: DB-Kopie + DATABASE_URL auf Drill. Dienste auf Prod laufen weiter.
# Ausführung auf CT: bash /opt/KI-Mail-Helper/scripts/deploy-known-contacts-drill.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

sudo mkdir -p "$PGBACKUP_DIR"
kmh_load_prod_database_url

export PGDATABASE_TEST="${PGDATABASE}_contacts_encrypt_drill"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

echo "== 1) pg_dump Produktion (${PGDATABASE}) =="
sudo -u postgres pg_dump -Fc -d "$PGDATABASE" \
  -f "${PGBACKUP_DIR}/${PGDATABASE}-drill-source-${STAMP}.dump"

echo "== 2) Test-DB ${PGDATABASE_TEST} =="
sudo -u postgres dropdb --if-exists "$PGDATABASE_TEST"
sudo -u postgres createdb -O postgres "$PGDATABASE_TEST"
sudo -u postgres pg_restore -d "$PGDATABASE_TEST" \
  "${PGBACKUP_DIR}/${PGDATABASE}-drill-source-${STAMP}.dump"

echo "== 3) DATABASE_URL auf Drill =="
export DATABASE_URL="$(kmh_database_url_for_db "$PGDATABASE_TEST")"
export PGDATABASE="$PGDATABASE_TEST"
kmh_expect_db "$PGDATABASE_TEST"

echo ""
echo "Drill-DB bereit. Phase A/B mit --expect-db ${PGDATABASE_TEST} ausführen."
echo "Dump: ${PGBACKUP_DIR}/${PGDATABASE}-drill-source-${STAMP}.dump"
echo ""
echo "Drill beenden (Prod-URL wiederherstellen):"
echo "  bash ${SCRIPT_DIR}/deploy-known-contacts-drill-end.sh"
