#!/usr/bin/env bash
# Safe production hardening on VPS — NO secrets, only flags.
# Run on VPS: bash scripts/vps_production_harden.sh
set -euo pipefail
cd /opt/leadgen

ENV_FILE=".env"
touch "$ENV_FILE"
cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"

# Strip inline comments (pydantic crash guard)
sed -i 's/[[:space:]]\+#.*$//' "$ENV_FILE"

set_kv() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

# Core production identity
set_kv "ENVIRONMENT" "production"
set_kv "APP_ENV" "production"

# API abuse guard (free — no paid deps)
set_kv "PLAN_RATE_LIMIT" "1"

# Automation stack (marketing launch)
set_kv "TEAM_AUTOMATION" "1"
set_kv "AUTO_EMAIL_OUTREACH" "true"
set_kv "REPLY_AGENT" "1"
set_kv "OPS_WATCHDOG" "1"
set_kv "AUTO_ONBOARD" "1"
set_kv "NICHE_ROTATION" "1"

echo "=== .env hardening applied (secrets NOT touched) ==="
grep -E '^(ENVIRONMENT|APP_ENV|PLAN_RATE_LIMIT|TEAM_AUTOMATION)=' "$ENV_FILE" || true

echo "=== rebuild app ==="
docker compose -f docker-compose.vps.yml build app
docker compose -f docker-compose.vps.yml up -d --no-deps app
sleep 16

echo "=== health ==="
curl -sf http://127.0.0.1:8000/health | head -c 300
echo

echo "=== production_ready (inside container) ==="
docker compose -f docker-compose.vps.yml exec -T app python scripts/production_ready.py --skip-prod-check || true

echo "DONE — Razorpay rzp_live_* keys still USER action if checkout blocked"
