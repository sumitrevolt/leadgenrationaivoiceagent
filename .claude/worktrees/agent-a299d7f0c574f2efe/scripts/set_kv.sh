#!/usr/bin/env bash
# =============================================================================
# set_kv.sh — upsert ONE KEY=VALUE in /opt/leadgen/.env + recreate `app`
# (NO rebuild — config-only change picks up via container recreate). Reusable
# for any env flip (UPI_VPA now; Razorpay keys later).
#   bash scripts/set_kv.sh UPI_VPA 8459012607@axl
# Secrets: value sirf .env me jaata (committed file me nahi). VALUE me space ho
# to quote karo.
# =============================================================================
set -euo pipefail
cd /opt/leadgen
K="${1:?usage: set_kv.sh KEY VALUE}"
V="${2:?usage: set_kv.sh KEY VALUE}"

if grep -q "^${K}=" .env 2>/dev/null; then
  sed -i "s|^${K}=.*|${K}=${V}|" .env
  echo "[set_kv] ${K} updated"
else
  printf '%s=%s\n' "$K" "$V" >> .env
  echo "[set_kv] ${K} added"
fi

echo "[set_kv] recreating app (no rebuild)..."
docker compose -f docker-compose.vps.yml up -d --no-deps app
echo "[set_kv] boot-grace 12s..."
sleep 12
if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
  echo "[set_kv] HEALTH OK"
else
  echo "[set_kv] HEALTH check failed — docker logs --tail 60 leadgen_app"
  exit 1
fi
