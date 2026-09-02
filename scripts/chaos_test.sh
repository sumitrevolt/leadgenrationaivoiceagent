#!/usr/bin/env bash
# =============================================================================
# chaos_test.sh — Container kill + auto-restart verification
# =============================================================================
#
# PURPOSE:
#   Yeh script leadgen_app container ko forcefully kill karta hai aur verify
#   karta hai ki Docker's restart:unless-stopped policy (ya selfheal cron)
#   use 90 seconds ke andar wapas live kar deta hai.
#
# ⚠️  WARNING: IS SCRIPT SE BRIEF DOWNTIME HOGA (~10-60 seconds)!
#    SIRF low-traffic window me chalao (e.g. raat 2-4 AM IST).
#    PRODUCTION pe directly mat chalao bina team ko bataye.
#    Staging pe pehle test karo agar possible ho.
#
# RUN ON VPS (not Windows):
#   ssh root@72.61.245.204 'bash /opt/leadgen/scripts/chaos_test.sh'
#
# IDEMPOTENT: Script khatam hote waqt container hamesha up hoga (safety net).
#
# EXIT CODES:
#   0 = PASS (container restarted + health 200 within timeout)
#   1 = FAIL (container did not recover)
# =============================================================================

set +e  # errors pe exit nahi — hum khud handle karte hain

COMPOSE_FILE="/opt/leadgen/docker-compose.vps.yml"
APP_CONTAINER="leadgen_app"
INTERNAL_HEALTH="http://127.0.0.1:8000/health"
RECOVERY_TIMEOUT=90   # seconds — itne me wapas aana chahiye
POLL_INTERVAL=5       # seconds — har poll me check
LOG_PREFIX="[chaos_test]"
RESULT="FAIL"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(ts) ${LOG_PREFIX} $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [ "$EUID" -ne 0 ] && ! groups | grep -q docker; then
  log "ERROR: root ya docker group zaroori hai. 'sudo bash $0' se chalao."
  exit 1
fi

if ! command -v docker &>/dev/null; then
  log "ERROR: docker not found."
  exit 1
fi

log "=== CHAOS TEST START ==="
log "Target container : $APP_CONTAINER"
log "Recovery timeout : ${RECOVERY_TIMEOUT}s"
log "Health endpoint  : $INTERNAL_HEALTH"
echo ""
echo "⚠️  ⚠️  ⚠️  DOWNTIME HOGA — PROCEED KAR RAHE HAIN  ⚠️  ⚠️  ⚠️"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Verify container is running BEFORE chaos
# ---------------------------------------------------------------------------
pre_status=$(docker inspect -f '{{.State.Status}}' "$APP_CONTAINER" 2>/dev/null)
if [ "$pre_status" != "running" ]; then
  log "PRE-CHECK FAIL: $APP_CONTAINER status='$pre_status' (expected running). Chaos mat chalate."
  exit 1
fi

pre_health=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$INTERNAL_HEALTH" 2>/dev/null)
if [ "$pre_health" != "200" ]; then
  log "PRE-CHECK FAIL: health returned HTTP $pre_health (expected 200). Pehle app healthy karo."
  exit 1
fi
log "PRE-CHECK PASS: container=running, health=200"

# ---------------------------------------------------------------------------
# Step 2: Record restart count BEFORE kill (Docker increments this on restart)
# ---------------------------------------------------------------------------
restart_count_before=$(docker inspect -f '{{.RestartCount}}' "$APP_CONTAINER" 2>/dev/null || echo "0")
log "Restart count before kill: $restart_count_before"

# ---------------------------------------------------------------------------
# Step 3: KILL the container (simulate OOM / crash)
# ---------------------------------------------------------------------------
log ">>> KILLING $APP_CONTAINER with SIGKILL..."
docker kill "$APP_CONTAINER" >/dev/null 2>&1
kill_status=$?
if [ $kill_status -ne 0 ]; then
  log "WARN: docker kill returned $kill_status — container already dead ya naam galat?"
fi
log "Kill issued at $(ts)"

# Give Docker a moment to register the kill before we start polling
sleep 2

# ---------------------------------------------------------------------------
# Step 4: Poll for recovery within RECOVERY_TIMEOUT seconds
# ---------------------------------------------------------------------------
log "Polling for recovery (timeout=${RECOVERY_TIMEOUT}s, interval=${POLL_INTERVAL}s)..."
elapsed=0

while [ $elapsed -lt $RECOVERY_TIMEOUT ]; do
  container_status=$(docker inspect -f '{{.State.Status}}' "$APP_CONTAINER" 2>/dev/null)
  health_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "$INTERNAL_HEALTH" 2>/dev/null)

  log "  t+${elapsed}s  container=${container_status:-unknown}  health_http=${health_code:-???}"

  if [ "$container_status" = "running" ] && [ "$health_code" = "200" ]; then
    restart_count_after=$(docker inspect -f '{{.RestartCount}}' "$APP_CONTAINER" 2>/dev/null || echo "?")
    log "RECOVERY CONFIRMED at t+${elapsed}s"
    log "Restart count after : $restart_count_after (was $restart_count_before)"
    RESULT="PASS"
    break
  fi

  sleep $POLL_INTERVAL
  elapsed=$((elapsed + POLL_INTERVAL))
done

# ---------------------------------------------------------------------------
# Step 5: Safety net — ensure container is up regardless of test result
# ---------------------------------------------------------------------------
final_status=$(docker inspect -f '{{.State.Status}}' "$APP_CONTAINER" 2>/dev/null)
if [ "$final_status" != "running" ]; then
  log "SAFETY NET: container still not running — force starting via compose..."
  docker compose -f "$COMPOSE_FILE" up -d app >/dev/null 2>&1
  sleep 8
  safety_health=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$INTERNAL_HEALTH" 2>/dev/null)
  log "SAFETY NET result: health=$safety_health"
  if [ "$safety_health" != "200" ]; then
    log "ERROR: App still not healthy after safety net! Manual intervention zaroori."
    log "Run: docker compose -f $COMPOSE_FILE up -d"
  fi
else
  log "Container is running — no safety net needed."
fi

# ---------------------------------------------------------------------------
# Step 6: Final verdict
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
if [ "$RESULT" = "PASS" ]; then
  echo "  CHAOS TEST: PASS ✓"
  echo "  $APP_CONTAINER recovered within ${elapsed}s"
else
  echo "  CHAOS TEST: FAIL ✗"
  echo "  $APP_CONTAINER did NOT recover within ${RECOVERY_TIMEOUT}s"
  echo ""
  echo "  Debug karo:"
  echo "    docker inspect $APP_CONTAINER"
  echo "    docker logs $APP_CONTAINER --tail 50"
  echo "    docker compose -f $COMPOSE_FILE up -d"
fi
echo "============================================"
echo ""

[ "$RESULT" = "PASS" ] && exit 0 || exit 1
