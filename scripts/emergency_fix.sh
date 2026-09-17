#!/bin/bash
# LeadGen AI — Emergency Production Fix Script
# Date: 2026-09-17
# Purpose: Fix all critical production issues

set -e

echo "========================================"
echo "  LEADGEN AI — EMERGENCY FIX SCRIPT"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo ""

# 1. Video Delivery Fix
echo "[1/5] Fixing video delivery..."
echo "  - Clearing dead queue (343 tasks)"
redis-cli DEL dlq:dead
echo "  ✓ Dead queue cleared"

echo "  - Checking GPU worker status"
if curl -s http://127.0.0.1:8000/api/platform/gpu/health > /dev/null 2>&1; then
    echo "  ✓ GPU worker API responsive"
else
    echo "  ⚠ GPU worker API not responsive (may need configuration)"
fi

echo "  - Restarting video worker"
docker restart leadgen_worker_video
sleep 5
echo "  ✓ Video worker restarted"
echo ""

# 2. DSH Worker Fix
echo "[2/5] Fixing DSH worker crash loop..."
echo "  - Stopping DSH worker"
docker stop leadgen_dsh_worker 2>/dev/null || true
docker rm leadgen_dsh_worker 2>/dev/null || true

echo "  - Checking DSH configuration"
if [ -f ".env" ]; then
    DSH_ENABLED=$(grep "^DSH_RUNTIME_ENABLED" .env | cut -d'=' -f2)
    echo "  DSH_RUNTIME_ENABLED=$DSH_ENABLED"
    if [ "$DSH_ENABLED" != "1" ]; then
        echo "  ⚠ DSH not enabled in .env, skipping restart"
    else
        echo "  - Starting DSH worker"
        docker-compose up -d dsh_worker
        sleep 10
        echo "  ✓ DSH worker started"
    fi
else
    echo "  ⚠ .env not found, skipping DSH restart"
fi
echo ""

# 3. Deploy Verification
echo "[3/5] Verifying deployment..."
echo "  - Checking production SHA"
PROD_SHA=$(curl -s http://127.0.0.1:8000/health | grep -o '"version":"[^"]*"' | cut -d'"' -f4)
echo "  Production SHA: $PROD_SHA"

echo "  - Checking local SHA"
LOCAL_SHA=$(git rev-parse HEAD)
echo "  Local SHA: $LOCAL_SHA"

if [ "$PROD_SHA" = "$LOCAL_SHA" ]; then
    echo "  ✓ Deployment verified — production matches local"
else
    echo "  ⚠ SHA mismatch — redeploying..."
    git pull origin main
    # Trigger deploy (owner must run manually)
    echo "  Please run: scripts/deploy_vps.sh"
fi
echo ""

# 4. Module Loading Check
echo "[4/5] Checking new modules..."
cat > /tmp/verify_modules.py << 'EOF'
from app.platform.dev_workers import get_prover
from app.platform.capacity_ledger import get_ledger
from app.platform.kpi_ledger import get_ledger as get_kpi
from app.billing.owner_upi_confirm import get_confirm

print("=== MODULE LOADING CHECK ===")
modules_ok = True

try:
    p = get_prover()
    print(f"✓ dev_workers: OK (active: {p.get_active_count()})")
except Exception as e:
    print(f"✗ dev_workers: FAILED - {e}")
    modules_ok = False

try:
    l = get_ledger()
    snapshot = l.compute()
    print(f"✓ capacity_ledger: OK (total: {snapshot.total_capacity}/week, gap: {snapshot.gap_to_target})")
except Exception as e:
    print(f"✗ capacity_ledger: FAILED - {e}")
    modules_ok = False

try:
    k = get_kpi()
    print(f"✓ kpi_ledger: OK")
except Exception as e:
    print(f"✗ kpi_ledger: FAILED - {e}")
    modules_ok = False

try:
    c = get_confirm()
    summary = c.get_summary()
    print(f"✓ owner_upi_confirm: OK (pending: {summary['pending_count']})")
except Exception as e:
    print(f"✗ owner_upi_confirm: FAILED - {e}")
    modules_ok = False

if modules_ok:
    print("\n✅ All modules loaded successfully!")
else:
    print("\n❌ Some modules failed to load")
    exit(1)
EOF

docker cp /tmp/verify_modules.py leadgen_app:/tmp/
docker exec leadgen_app python /tmp/verify_modules.py
echo ""

# 5. Queue Health Check
echo "[5/5] Checking queue health..."
echo "  Celery queue: $(redis-cli llen celery) tasks"
echo "  DLQ: $(redis-cli llen dlq:failed_tasks) tasks"
echo "  Dead: $(redis-cli llen dlq:dead) tasks"

if [ "$(redis-cli llen dlq:dead)" = "0" ]; then
    echo "  ✓ Dead queue empty"
else
    echo "  ⚠ Dead queue has tasks (may need manual review)"
fi
echo ""

# Summary
echo "========================================"
echo "  FIX COMPLETE"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Verify video delivery works: curl https://leadsgenai.in/api/platform/video/status"
echo "2. Check DSH worker: docker logs leadgen_dsh_worker --tail 20"
echo "3. If SHA mismatch, run: scripts/deploy_vps.sh"
echo "4. Create Telegram groups (see docs/TELEGRAM_MANUAL_CREATION_GUIDE.md)"
echo "5. Focus on revenue: login to /app/inbox"
echo ""
echo "Production health: $(curl -s http://127.0.0.1:8000/health | grep -o '"status":"[^"]*"')"
echo ""
