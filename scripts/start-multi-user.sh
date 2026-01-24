#!/bin/bash
# Quick-Start für Multi-User Version (App-Factory + Celery)
# Usage: bash scripts/start-multi-user.sh

set -e

# In das Projekt-Root-Verzeichnis wechseln
cd "$(dirname "$0")/.."

# Info: Aktueller Branch
BRANCH=$(git branch --show-current)
echo "🚀 Starting Multi-User Mail-Helper (App-Factory + Celery Architecture)"
echo "   Branch: $BRANCH"
echo "════════════════════════════════════════════════════════════════"

# 1. Check Services
echo ""
echo "1️⃣  Checking Infrastructure Services..."
systemctl is-active --quiet postgresql || { echo "❌ PostgreSQL not running! Bitte mit 'sudo systemctl start postgresql' starten."; exit 1; }
echo "   ✅ PostgreSQL running"

systemctl is-active --quiet redis-server || { echo "❌ Redis not running! Bitte mit 'sudo systemctl start redis-server' starten."; exit 1; }
echo "   ✅ Redis running"

systemctl is-active --quiet ollama 2>/dev/null || echo "   ℹ️  Ollama not running (KI features may be limited)"

echo ""
echo "2️⃣  Checking Celery Components..."
CELERY_WORKER_ACTIVE=true
systemctl is-active --quiet mail-helper-celery-worker || CELERY_WORKER_ACTIVE=false

CELERY_BEAT_ACTIVE=true
systemctl is-active --quiet mail-helper-celery-beat || CELERY_BEAT_ACTIVE=false

if [ "$CELERY_WORKER_ACTIVE" = true ]; then
    echo "   ✅ Celery Worker running (systemd)"
else
    echo "   ⚠️  Celery Worker NOT running as systemd service!"
    echo "      Start manual: celery -A src.celery_app worker --loglevel=info"
fi

if [ "$CELERY_BEAT_ACTIVE" = true ]; then
    echo "   ✅ Celery Beat running (systemd)"
else
    echo "   ⚠️  Celery Beat NOT running as systemd service!"
    echo "      Start manual: celery -A src.celery_app beat --loglevel=info"
fi

systemctl is-active --quiet mail-helper-celery-flower || echo "   ℹ️  Flower not running (optional)"

# 3. Check Environment
echo ""
echo "3️⃣  Checking Environment..."
ENV_FILE=".env.local"
if [ ! -f ".env.local" ]; then
    if [ -f ".env" ]; then
        ENV_FILE=".env"
        echo "   ℹ️  Using .env (no .env.local found)"
    else
        echo "❌ No .env or .env.local found!"
        exit 1
    fi
fi

# Prüfe wichtige Multi-User Variablen
USE_PG=$(grep "^USE_POSTGRESQL=" "$ENV_FILE" | cut -d'=' -f2 || echo "false")
DB_URL=$(grep "^DATABASE_URL=" "$ENV_FILE" | cut -d'=' -f2 || echo "")

if [[ "$USE_PG" != "true" && ! "$DB_URL" =~ ^postgresql ]]; then
    echo "❌ Multi-User Mode requires PostgreSQL. Please check USE_POSTGRESQL or DATABASE_URL in $ENV_FILE"
    exit 1
fi
echo "   ✅ PostgreSQL Configuration found"

# Start Flask
echo ""
echo "4️⃣  Starting Flask App (App-Factory)..."
echo "   Port: 5003 (HTTPS)"
echo "   Mode: Multi-User / Blueprint Architecture"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📊 Monitoring:"
echo "   App:    https://localhost:5003"
echo "   Flower: http://localhost:5555/flower"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Virtual Environment aktivieren
if [ -d "venv" ]; then
    source venv/bin/activate
fi

export FLASK_RUN_PORT=5003
# Die App-Factory wird über src.00_main --serve gestartet
exec python3 -m src.00_main --serve --https --port 5003
