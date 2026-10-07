# Gemeinsame Variablen/Helfer für Kontakt-Verschlüsselung (Deploy/Drill).
# Nutzung: source "$(dirname "$0")/deploy-known-contacts-lib.sh"
# oder: source /opt/KI-Mail-Helper/scripts/deploy-known-contacts-lib.sh

export KMH_APP_ROOT="${KMH_APP_ROOT:-/opt/KI-Mail-Helper}"
export KMH_VENV="${KMH_VENV:-${KMH_APP_ROOT}/venv}"
export KMH_USER_ID="${KMH_USER_ID:-1}"
export PGDATABASE="${PGDATABASE:-mail_helper}"
export PGBACKUP_DIR="${PGBACKUP_DIR:-/var/backups/mail-helper}"

export KMH_SVC_WEB="${KMH_SVC_WEB:-mail-helper.service}"
export KMH_SVC_CELERY_WORKER="${KMH_SVC_CELERY_WORKER:-mail-helper-celery-worker.service}"
export KMH_SVC_CELERY_BEAT="${KMH_SVC_CELERY_BEAT:-mail-helper-celery-beat.service}"

KMH_PYTHON="${KMH_VENV}/bin/python"

kmh_load_prod_database_url() {
  if [ -z "${DATABASE_URL:-}" ]; then
    export DATABASE_URL="$(
      grep -E '^DATABASE_URL=' "${KMH_APP_ROOT}/.env" | sed 's/^DATABASE_URL=//' | tr -d '"' | tr -d "'"
    )"
  fi
}

kmh_database_url_for_db() {
  local dbname="$1"
  KMH_TARGET_DB="$dbname" "$KMH_PYTHON" -c "
import os
from sqlalchemy.engine.url import make_url
u = make_url(os.environ['DATABASE_URL'])
print(u.set(database=os.environ['KMH_TARGET_DB']))
"
}

kmh_activate_venv() {
  # shellcheck disable=SC1091
  source "${KMH_VENV}/bin/activate"
}

kmh_stop_services() {
  sudo systemctl stop "$KMH_SVC_CELERY_BEAT" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_WEB"
  sleep 2
  for u in "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"; do
    if systemctl is-active --quiet "$u"; then
      echo "FEHLER: $u läuft noch." >&2
      return 1
    fi
  done
  echo "OK: Dienste gestoppt."
}

kmh_start_services() {
  sudo systemctl start "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"
  sudo systemctl is-active "$KMH_SVC_WEB" "$KMH_SVC_CELERY_WORKER" "$KMH_SVC_CELERY_BEAT"
}

kmh_pull_code() {
  cd "$KMH_APP_ROOT"
  git fetch origin
  git checkout main
  git pull origin main
  kmh_activate_venv
  pip install -r requirements.txt
}

kmh_expect_db() {
  cd "$KMH_APP_ROOT"
  kmh_activate_venv
  "$KMH_PYTHON" scripts/kmh_expect_db.py --expect-db "$1"
}
