#!/bin/bash
#
# Mail Processor Cron-Job Script
# Führt `python -m src.00_main --process-once` aus
# Sollte als Cron-Job alle X Minuten/Stunden aufgerufen werden
#

set -a
source /home/thomas/projects/KI-Mail-Helper/.env
set +a

cd /home/thomas/projects/KI-Mail-Helper

/home/thomas/projects/KI-Mail-Helper/venv/bin/python \
    -m src.00_main \
    --process-once \
    >> /var/log/mail-helper-processor.log 2>&1

exit $?
