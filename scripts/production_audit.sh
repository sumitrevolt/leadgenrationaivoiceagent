#!/bin/bash
# LeadGen AI — Production Health Audit Script
# Run as: bash production_audit.sh

echo "========================================"
echo "  LEADGEN AI — PRODUCTION HEALTH AUDIT"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo ""

# 1. App Health
echo "1. APP HEALTH:"
curl -s http://127.0.0.1:8000/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'   Status: {d[\"status\"]}')
print(f'   SHA: {d[\"version\"]}')
print(f'   Uptime: {d[\"uptime\"]}')
print(f'   Environment: {d[\"environment\"]}')
" 2>/dev/null || echo "   Cannot parse health endpoint"
echo ""

# 2. Docker Services
echo "2. DOCKER SERVICES:"
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep leadgen
echo ""

# 3. Queue Status
echo "3. QUEUE STATUS:"
echo "   Celery: $(redis-cli llen celery)"
echo "   DLQ: $(redis-cli llen dlq:failed_tasks)"
echo "   Dead: $(redis-cli llen dlq:dead)"
echo ""

# 4. Disk Space
echo "4. DISK SPACE:"
df -h / | tail -1 | awk '{print "   Used: " $3 " / " $2 " (" $5 ")"}'
echo ""

# 5. Memory Usage
echo "5. MEMORY USAGE:"
free -h | grep Mem | awk '{print "   Used: " $3 " / " $2 " (" $5 ")"}'
echo ""

# 6. Recent Errors
echo "6. RECENT ERRORS (last 1h):"
ERROR_COUNT=$(docker logs leadgen_app --since 1h 2>&1 | grep -i error | wc -l)
echo "   Errors found: $ERROR_COUNT"
if [ "$ERROR_COUNT" -gt 0 ]; then
    echo "   Sample errors:"
    docker logs leadgen_app --since 1h 2>&1 | grep -i error | head -3 | sed 's/^/      /'
fi
echo ""

# 7. Database Size
echo "7. DATABASE SIZE:"
docker exec leadgen_db psql -U postgres -d leadgen_db -c 'SELECT pg_size_pretty(pg_database_size("leadgen_db"));' 2>/dev/null || echo "   Cannot query (postgrest not available)"
echo ""

# 8. Key Data Files
echo "8. KEY DATA FILES:"
ls -lh /opt/leadgen/data/*.jsonl 2>/dev/null | awk '{print "   " $9 ": " $5}' | head -10
echo ""

# 9. Recent Deployments
echo "9. RECENT DEPLOYMENTS:"
cd /opt/leadgen && git log --oneline -5 2>/dev/null || echo "   Not a git repo"
echo ""

# 10. Critical Warnings
echo "10. CRITICAL WARNINGS:"
WARNINGS=0

# Check disk usage
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "   ⚠️  Disk usage high: ${DISK_USAGE}%"
    WARNINGS=$((WARNINGS+1))
fi

# Check dead queue
DEAD_COUNT=$(redis-cli llen dlq:dead)
if [ "$DEAD_COUNT" -gt 100 ]; then
    echo "   ⚠️  Dead queue large: $DEAD_COUNT tasks"
    WARNINGS=$((WARNINGS+1))
fi

# Check app health
HEALTH=$(curl -s http://127.0.0.1:8000/health | grep -o '"status":"[^"]*"')
if [ -n "$HEALTH" ] && [ "$HEALTH" != '"status":"healthy"' ]; then
    echo "   ⚠️  App not healthy: $HEALTH"
    WARNINGS=$((WARNINGS+1))
fi

if [ "$WARNINGS" -eq 0 ]; then
    echo "   ✅ No critical warnings"
fi
echo ""

# Summary
echo "========================================"
echo "  AUDIT COMPLETE"
echo "========================================"
echo ""
echo "Next actions:"
echo "1. Review warnings above"
echo "2. Check /app/inbox for new leads"
echo "3. Process pending UPI payments"
echo "4. Create Telegram groups (see guide)"
echo ""
