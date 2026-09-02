#!/usr/bin/env bash
# verify_sentry_live.sh — read-only: which Sentry-reported errors STILL fire post-deploy?
set +e
echo "===SINCE DEPLOY (app) — counts==="
for pat in "_IncludedRouter" "lead_topup_price" "different loop" "Event loop is closed" "Too many connections" "No response returned"; do
  n=$(docker logs --since 30m leadgen_app 2>&1 | grep -ci "$pat")
  printf '%-24s %s\n' "$pat" "$n"
done
echo "===SINCE DEPLOY (worker) — counts==="
for pat in "different loop" "Event loop is closed" "Too many connections"; do
  n=$(docker logs --since 30m leadgen_worker 2>&1 | grep -ci "$pat")
  printf '%-24s %s\n' "$pat" "$n"
done
echo "===ROUTE_HIT_COUNTER flag==="
docker exec leadgen_app printenv ROUTE_HIT_COUNTER 2>/dev/null || echo "(unset = middleware not registered)"
echo "===REDIS clients / maxclients==="
docker exec leadgen_redis redis-cli info clients 2>/dev/null | head -4
docker exec leadgen_redis redis-cli config get maxclients 2>/dev/null
echo "===QDRANT fastembed since deploy==="
docker logs --since 30m leadgen_app 2>&1 | grep -ci "fastembed model not ready"
docker logs --since 30m leadgen_app 2>&1 | grep -i "fastembed model loaded" | tail -2
echo "===SENTRY_LIVE_DONE==="
