#!/bin/bash
# Production Go-Live Check für Multi-User Setup
# Prüft ob PostgreSQL, Redis, Celery ready sind

set -euo pipefail

echo "🚀 KI-Mail-Helper Production Go-Live Check"
echo "======================================================================"
echo ""

FAIL=0

# ════════════════════════════════════════════════════════════════════════
# 1. Environment Check
# ════════════════════════════════════════════════════════════════════════
echo "1️⃣  Environment Variables..."

if [ -f ".env.local" ]; then
    echo "   ✅ .env.local found"
    
    # Load variables (set -a exports all variables)
    set -a
    source <(grep -E '^[A-Z_]+=' .env.local)
    set +a
    
    if [ "${USE_POSTGRESQL:-}" = "true" ]; then
        echo "   ✅ USE_POSTGRESQL=true"
    else
        echo "   ❌ USE_POSTGRESQL nicht true!"
        FAIL=1
    fi
    
    if [ "${USE_LEGACY_JOBS:-}" = "false" ]; then
        echo "   ✅ USE_LEGACY_JOBS=false (Celery aktiv)"
    else
        echo "   ⚠️  USE_LEGACY_JOBS nicht false (Legacy noch aktiv)"
    fi
    
    if [ -n "${DATABASE_URL:-}" ]; then
        echo "   ✅ DATABASE_URL gesetzt"
    else
        echo "   ❌ DATABASE_URL fehlt!"
        FAIL=1
    fi
    
    if [ -n "${REDIS_URL:-}" ]; then
        echo "   ✅ REDIS_URL gesetzt"
    else
        echo "   ❌ REDIS_URL fehlt!"
        FAIL=1
    fi
else
    echo "   ❌ .env.local nicht gefunden!"
    FAIL=1
fi

echo ""

# ════════════════════════════════════════════════════════════════════════
# 2. Services Check
# ════════════════════════════════════════════════════════════════════════
echo "2️⃣  System Services..."

# PostgreSQL
if systemctl is-active --quiet postgresql; then
    echo "   ✅ PostgreSQL running"
else
    echo "   ❌ PostgreSQL NOT running!"
    FAIL=1
fi

# Redis
if systemctl is-active --quiet redis-server; then
    echo "   ✅ Redis running"
else
    echo "   ❌ Redis NOT running!"
    FAIL=1
fi

# Celery Worker
if systemctl is-active --quiet mail-helper-celery-worker; then
    echo "   ✅ Celery Worker running"
else
    echo "   ❌ Celery Worker NOT running!"
    FAIL=1
fi

# Celery Beat (optional but recommended)
if systemctl is-active --quiet mail-helper-celery-beat; then
    echo "   ✅ Celery Beat running"
else
    echo "   ⚠️  Celery Beat not running (optional)"
fi

# Flower (optional)
if systemctl is-active --quiet mail-helper-celery-flower; then
    echo "   ✅ Flower running (http://localhost:5555)"
else
    echo "   ⚠️  Flower not running (optional)"
fi

echo ""

# ════════════════════════════════════════════════════════════════════════
# 3. Database Connection
# ════════════════════════════════════════════════════════════════════════
echo "3️⃣  Database Connection..."

if PGPASSWORD=dev_mail_helper_2026 psql -h localhost -U mail_helper -d mail_helper -c "SELECT 1" &>/dev/null; then
    echo "   ✅ PostgreSQL connection OK"
    
    # Check table count
    TABLE_COUNT=$(PGPASSWORD=dev_mail_helper_2026 psql -h localhost -U mail_helper -d mail_helper -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'" | tr -d ' ')
    echo "   ✅ Tables: $TABLE_COUNT"
    
    if [ "$TABLE_COUNT" -lt 20 ]; then
        echo "   ⚠️  Weniger als 20 Tabellen - Migration OK?"
    fi
else
    echo "   ❌ PostgreSQL connection FAILED!"
    FAIL=1
fi

echo ""

# ════════════════════════════════════════════════════════════════════════
# 4. Redis Connection
# ════════════════════════════════════════════════════════════════════════
echo "4️⃣  Redis Connection..."

if redis-cli ping &>/dev/null; then
    echo "   ✅ Redis PING OK"
else
    echo "   ❌ Redis connection FAILED!"
    FAIL=1
fi

echo ""

# ════════════════════════════════════════════════════════════════════════
# 5. Celery Worker Status
# ════════════════════════════════════════════════════════════════════════
echo "5️⃣  Celery Worker Status..."

cd /home/thomas/projects/KI-Mail-Helper-Dev
source venv/bin/activate

WORKER_COUNT=$(python3 -c "
from src.celery_app import celery_app
inspect = celery_app.control.inspect()
workers = inspect.active()
print(len(workers) if workers else 0)
" 2>/dev/null || echo "0")

if [ "$WORKER_COUNT" -gt 0 ]; then
    echo "   ✅ Celery Workers: $WORKER_COUNT"
    
    # Check registered tasks
    TASK_COUNT=$(python3 -c "
from src.celery_app import celery_app
inspect = celery_app.control.inspect()
registered = inspect.registered()
if registered:
    tasks = list(registered.values())[0]
    print(len([t for t in tasks if 'sync' in t or 'rule' in t]))
else:
    print(0)
" 2>/dev/null || echo "0")
    
    echo "   ✅ Registered Tasks: $TASK_COUNT"
else
    echo "   ❌ Keine aktiven Celery Workers!"
    FAIL=1
fi

echo ""

# ════════════════════════════════════════════════════════════════════════
# 6. Git Branch Check
# ════════════════════════════════════════════════════════════════════════
echo "6️⃣  Git Branch..."

BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "   Branch: $BRANCH"

if [ "$BRANCH" = "feature/multi-user-native" ]; then
    echo "   ✅ Korrekter Branch (feature/multi-user-native)"
else
    echo "   ⚠️  Nicht auf feature/multi-user-native!"
fi

echo ""

# ════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════
echo "======================================================================"

if [ $FAIL -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED - READY FOR PRODUCTION!"
    echo ""
    echo "🚀 Starte Flask App mit:"
    echo "   cd /home/thomas/projects/KI-Mail-Helper-Dev"
    echo "   source venv/bin/activate"
    echo "   USE_BLUEPRINTS=1 python3 -m src.00_main --serve --https --port 5003"
    echo ""
    echo "📊 Monitoring:"
    echo "   Flower:  http://localhost:5555"
    echo "   Logs:    tail -f /var/log/mail-helper/celery-worker.log"
    echo ""
    exit 0
else
    echo "❌ CHECKS FAILED - NOT READY!"
    echo ""
    echo "Behebe die Fehler und führe Check erneut aus."
    echo ""
    exit 1
fi
