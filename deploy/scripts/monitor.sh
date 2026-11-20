#!/bin/bash
# India Votes Data API - Monitoring Script

APP_NAME="india-votes-api"
API_URL="http://localhost:8000"
ALERT_EMAIL=""  # Set email for alerts

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "India Votes Data API - Health Monitor"
echo "=========================================="
echo ""

# Check if service is running
echo -n "Service Status: "
if systemctl is-active --quiet $APP_NAME; then
    echo -e "${GREEN}Running${NC}"
else
    echo -e "${RED}Stopped${NC}"
    systemctl status $APP_NAME --no-pager
fi

echo ""

# Check API health endpoint
echo -n "API Health Check: "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" $API_URL/health 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}OK (HTTP $HTTP_CODE)${NC}"
else
    echo -e "${RED}Failed (HTTP $HTTP_CODE)${NC}"
fi

echo ""

# Check memory usage
echo "Resource Usage:"
echo "---------------"
PID=$(systemctl show -p MainPID $APP_NAME | cut -d'=' -f2)
if [ "$PID" != "0" ]; then
    ps -p $PID -o %cpu,%mem,cmd --no-headers | while read cpu mem cmd; do
        echo "  CPU: ${cpu}%"
        echo "  MEM: ${mem}%"
    done
else
    echo "  Process not found"
fi

echo ""

# Check disk usage
echo "Disk Usage:"
echo "----------"
df -h /opt/india-votes-data | tail -1 | awk '{print "  Usage: "$3" / "$2" ("$5")"}'

echo ""

# Check database connection (if PostgreSQL)
if command -v psql &> /dev/null; then
    echo -n "Database Connection: "
    if sudo -u postgres psql -c "SELECT 1" election_results &>/dev/null 2>&1; then
        echo -e "${GREEN}Connected${NC}"
    else
        echo -e "${YELLOW}Not Connected (or not configured)${NC}"
    fi
    echo ""
fi

# Recent errors from logs
echo "Recent Errors (last 10):"
echo "------------------------"
sudo journalctl -u $APP_NAME --since "1 hour ago" | grep -i error | tail -10

echo ""

# Connection stats
echo "Active Connections:"
echo "------------------"
sudo netstat -an | grep :8000 | grep ESTABLISHED | wc -l | xargs echo "  Count:"

echo ""
echo "=========================================="
echo "Monitor complete - $(date)"
echo "=========================================="
