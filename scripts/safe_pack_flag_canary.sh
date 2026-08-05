#!/usr/bin/env bash
# Safe-pack canary for Revenue Automation Max (owner-locked 2026-08-05).
# Run ON VPS under /opt/leadgen with APP_VERSION discipline — never invent aliases.
#
# Exact keys:
#   FLOW_RUNNER=1
#   FLOW_AUTO_TRIGGERS=1   # required for flow_cron
#   PROCESS_ENGINE=1
#   PROCESS_AUTOSTART=1
#   REVENUE_TRENDS=1
#   CONTENT_APPROVAL_AUTO=1  # approval QUEUE submit only — not publish/approve
#
# NEVER touch: SALES_AUTOPILOT_WHATSAPP_ENABLED, REPLY_AUTO_SEND*, UPI_AUTO_ACTIVATE
#              (open), ALLOW_TOS_SCRAPE, CREATIVE_OS_ENABLED, EXTERNAL_AGENT_*,
#              SOCIAL autopost masters, VOICE_LAUNCH_KILL / PLATFORM_DIAL_*
#
# Usage:
#   DRY_RUN=1 bash scripts/safe_pack_flag_canary.sh   # print plan only
#   APPLY=1 bash scripts/safe_pack_flag_canary.sh     # backup .env + set keys
set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/leadgen/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/leadgen/docker-compose.vps.yml}"
DRY_RUN="${DRY_RUN:-1}"
APPLY="${APPLY:-0}"

# Keep in sync with scripts/safe_pack_flags.py SAFE_PACK_KEYS (contract-tested).
KEYS=(
  FLOW_RUNNER
  FLOW_AUTO_TRIGGERS
  PROCESS_ENGINE
  PROCESS_AUTOSTART
  REVENUE_TRENDS
  CONTENT_APPROVAL_AUTO
)

echo "== Safe-pack canary =="
echo "env: $ENV_FILE"
echo "dry_run=$DRY_RUN apply=$APPLY"

capture() {
  local k="$1"
  if [[ -f "$ENV_FILE" ]]; then
    grep -E "^${k}=" "$ENV_FILE" || echo "${k}=<unset>"
  else
    echo "${k}=<no-env-file>"
  fi
}

echo "-- current values --"
for k in "${KEYS[@]}"; do
  capture "$k"
done

if [[ "$APPLY" != "1" ]]; then
  echo "DRY: set APPLY=1 to backup .env and write =1 for each key (then recreate app services with APP_VERSION)."
  exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE missing" >&2
  exit 1
fi

TS="$(date -u +%Y%m%d%H%M%S)"
BAK="${ENV_FILE}.bak-safepack-${TS}"
cp -a "$ENV_FILE" "$BAK"
echo "backup: $BAK"

for k in "${KEYS[@]}"; do
  if grep -qE "^${k}=" "$ENV_FILE"; then
    sed -i "s/^${k}=.*/${k}=1/" "$ENV_FILE"
  else
    printf '\n%s=1\n' "$k" >>"$ENV_FILE"
  fi
  echo "set ${k}=1"
done

echo "NEXT (manual):"
echo "  cd /opt/leadgen"
echo "  export APP_VERSION=\$(docker inspect -f '{{.Config.Image}}' leadgen_app | sed 's/.*://')"
echo "  docker compose -f docker-compose.vps.yml up -d --no-deps --force-recreate app worker scheduler"
echo "  curl -sS http://127.0.0.1:8000/health"
echo "ROLLBACK: cp -a $BAK $ENV_FILE && recreate with same APP_VERSION"
