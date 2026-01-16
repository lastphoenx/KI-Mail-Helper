#!/bin/bash
# Quick-Start für Multi-User Version
# Usage: bash scripts/start-multi-user.sh

set -e

cd "$(dirname "$0")/.."

echo "🚀 Starting Multi-User Mail-Helper (feature/multi-user-native)"
echo "════════════════════════════════════════════════════════════════"

# Check Branch
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "feature/multi-user-native" ]; then
    echo "⚠️  WARNING: Du bist auf Branch '$BRANCH', nicht 'feature/multi-user-native'!"
    echo "   Wechsle mit: git checkout feature/multi-user-native"
    exit 1
fi

# Check Services
echo ""
echo "1️⃣  Checking Services..."
systemctl is-active --quiet postgresql || { echo "❌ PostgreSQL not running!"; exit 1; }
echo "   ✅ PostgreSQL running"

systemctl is-active --quiet redis-server || { echo "❌ Redis not running!"; exit 1; }
echo "   ✅ Redis running"

systemctl is-active --quiet mail-helper-celery-worker || { echo "❌ Celery Worker not running!"; exit 1; }
echo "   ✅ Celery Worker running"

systemctl is-active --quiet mail-helper-celery-flower || { echo "⚠️  Flower not running (optional)"; }

# Check Environment (ohne source - nur grep)
echo ""
echo "2️⃣  Checking Environment..."
if [ ! -f ".env.local" ]; then
    echo "❌ .env.local not found!"
    exit 1
fi

USE_PG=$(grep "^USE_POSTGRESQL=" .env.local | cut -d'=' -f2)
USE_LEGACY=$(grep "^USE_LEGACY_JOBS=" .env.local | cut -d'=' -f2)

if [ "$USE_PG" != "true" ]; then
    echo "❌ USE_POSTGRESQL is not 'true' in .env.local!"
    exit 1
fi
echo "   ✅ USE_POSTGRESQL=true"

if [ "$USE_LEGACY" != "false" ]; then
    echo "⚠️  WARNING: USE_LEGACY_JOBS is not 'false' - Legacy-Mode aktiv!"
else
    echo "   ✅ USE_LEGACY_JOBS=false"
fi

# Start Flask
echo ""
echo "3️⃣  Starting Flask App..."
echo "   Port: 5003 (HTTPS)"
echo "   Mode: Multi-User (PostgreSQL + Celery)"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📊 Monitoring:"
echo "   App:    https://localhost:5003"
echo "   Flower: http://localhost:5555/flower  ← WICHTIG: /flower am Ende!"
echo "════════════════════════════════════════════════════════════════"
echo ""

# WICHTIG: .env.local wird von dotenv automatisch geladen!
# Wir setzen nur explizit die kritischen Variablen
source venv/bin/activate
export USE_BLUEPRINTS=1
export USE_LEGACY_JOBS=false
export FLASK_RUN_PORT=5003

exec python3 -m src.00_main --serve --https --port 5003
