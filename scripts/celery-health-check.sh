#!/bin/bash
# Health-Check Script für KI-Mail-Helper Celery Services
# Prüft Worker, Beat, Flower + Redis + PostgreSQL

set -euo pipefail

echo "🏥 KI-Mail-Helper Celery Health Check"
echo "======================================"
echo ""

# Farben für Output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Status-Zähler
HEALTHY=0
UNHEALTHY=0

check_service() {
    local service_name=$1
    local display_name=$2
    
    if systemctl is-active --quiet "$service_name"; then
        echo -e "${GREEN}✅ $display_name${NC} - running"
        ((HEALTHY++))
        return 0
    else
        echo -e "${RED}❌ $display_name${NC} - not running"
        ((UNHEALTHY++))
        return 1
    fi
}

check_port() {
    local port=$1
    local service=$2
    
    if nc -z localhost "$port" 2>/dev/null; then
        echo -e "${GREEN}✅ $service (Port $port)${NC} - reachable"
        ((HEALTHY++))
        return 0
    else
        echo -e "${RED}❌ $service (Port $port)${NC} - not reachable"
        ((UNHEALTHY++))
        return 1
    fi
}

# 1. Infrastructure Services
echo "📦 Infrastructure:"
check_service "postgresql" "PostgreSQL"
check_service "redis-server" "Redis"
echo ""

# 2. Celery Services
echo "⚙️  Celery Services:"
check_service "mail-helper-celery-worker" "Celery Worker"
check_service "mail-helper-celery-beat" "Celery Beat"
check_service "mail-helper-celery-flower" "Flower Monitoring"
echo ""

# 3. Port-Checks
echo "🔌 Port Checks:"
check_port 5432 "PostgreSQL"
check_port 6379 "Redis"
check_port 5555 "Flower Web UI"
echo ""

# 4. Redis Ping
echo "🏓 Redis Ping:"
if redis-cli ping &>/dev/null; then
    echo -e "${GREEN}✅ Redis PING${NC} - OK"
    ((HEALTHY++))
else
    echo -e "${RED}❌ Redis PING${NC} - FAILED"
    ((UNHEALTHY++))
fi
echo ""

# 5. PostgreSQL Connection
echo "🔗 PostgreSQL Connection:"
if PGPASSWORD=dev_mail_helper_2026 psql -h localhost -U mail_helper -d mail_helper -c "SELECT 1" &>/dev/null; then
    echo -e "${GREEN}✅ PostgreSQL Connection${NC} - OK"
    ((HEALTHY++))
else
    echo -e "${RED}❌ PostgreSQL Connection${NC} - FAILED"
    ((UNHEALTHY++))
fi
echo ""

# 6. Celery Inspect (nur wenn Worker läuft)
if systemctl is-active --quiet mail-helper-celery-worker; then
    echo "🔍 Celery Worker Inspect:"
    cd /home/thomas/projects/KI-Mail-Helper-Dev
    source venv/bin/activate
    
    # Active Tasks
    ACTIVE_TASKS=$(celery -A src.celery_app inspect active 2>/dev/null | grep -c "celery@" || echo "0")
    echo "   Active Tasks: $ACTIVE_TASKS"
    
    # Registered Tasks
    REGISTERED=$(celery -A src.celery_app inspect registered 2>/dev/null | grep -c "tasks\." || echo "0")
    echo "   Registered Tasks: $REGISTERED"
    echo ""
fi

# 7. Log-File Check
echo "📝 Recent Logs:"
if [ -f /var/log/mail-helper/celery-worker.log ]; then
    echo "   Last 3 lines from celery-worker.log:"
    tail -n 3 /var/log/mail-helper/celery-worker.log | sed 's/^/   /'
else
    echo -e "${YELLOW}   ⚠️  No worker log yet${NC}"
fi
echo ""

# Final Summary
echo "======================================"
echo "📊 Summary:"
echo -e "   ${GREEN}Healthy:   $HEALTHY${NC}"
echo -e "   ${RED}Unhealthy: $UNHEALTHY${NC}"

if [ $UNHEALTHY -eq 0 ]; then
    echo ""
    echo -e "${GREEN}🎉 All systems operational!${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}⚠️  Some services need attention!${NC}"
    exit 1
fi
