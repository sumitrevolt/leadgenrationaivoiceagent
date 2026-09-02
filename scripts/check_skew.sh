#!/usr/bin/env bash
# check_skew.sh — read-only: is ANY leadgen container still on a stale/unversioned image?
set +e
echo "===IMAGE PER CONTAINER==="
for c in leadgen_app leadgen_worker leadgen_scheduler leadgen_worker_heavy leadgen_worker_video leadgen_app_staging; do
  img=$(docker inspect --format '{{.Config.Image}}' "$c" 2>/dev/null)
  up=$(docker ps --filter "name=^${c}$" --format '{{.Status}}' 2>/dev/null)
  printf '%-24s %-58s %s\n' "$c" "${img:-<absent>}" "$up"
done
echo "===CANONICAL PRODUCTION IMAGE==="
docker inspect --format '{{.Config.Image}} id={{.Image}}' leadgen_app 2>/dev/null
echo "===APP_VERSION INSIDE EACH RUNNING CONTAINER==="
for c in leadgen_app leadgen_worker leadgen_scheduler leadgen_worker_heavy leadgen_worker_video; do
  v=$(docker exec "$c" printenv APP_VERSION 2>/dev/null)
  printf '%-24s APP_VERSION=%s\n' "$c" "${v:-<unset>}"
done
echo "===DOES worker_heavy/video CODE MATTER? (retired symbol present?)==="
docker exec leadgen_worker_heavy sh -c 'grep -c "lead_topup_price" /app/app/api/voice_product.py 2>/dev/null' 2>/dev/null
echo "===SKEW_DONE==="
