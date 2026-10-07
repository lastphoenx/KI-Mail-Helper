#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=deploy-known-contacts-lib.sh
source "${SCRIPT_DIR}/deploy-known-contacts-lib.sh"

unset DATABASE_URL
export PGDATABASE=mail_helper
kmh_load_prod_database_url
kmh_expect_db mail_helper
echo "OK: wieder auf Produktion (${PGDATABASE})."
