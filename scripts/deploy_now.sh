#!/usr/bin/env bash
# =============================================================================
# deploy_now.sh — one-shot app deploy (infra-upgrade session).
#   * PostHog env set (KEY arg se aata — committed file me KABHI nahi)
#   * sirf `app` service rebuild + recreate (data/observability/tools untouched)
#   * boot-grace + /health verify
# Run on VPS AFTER `git pull`:
#   bash scripts/deploy_now.sh <POSTHOG_API_KEY> [POSTHOG_HOST]
# =============================================================================
set -euo pipefail
cd /opt/leadgen
COMPOSE="docker compose -f docker-compose.vps.yml"

PH_KEY="${1:-}"
PH_HOST="${2:-https://us.i.posthog.com}"
LF_PUB="${3:-}"
LF_SEC="${4:-}"
LF_BASE="${5:-https://us.cloud.langfuse.com}"

set_env() {  # key value -> .env me set/replace (idempotent)
  local k="$1" v="$2"
  if grep -q "^${k}=" .env 2>/dev/null; then
    sed -i "s|^${k}=.*|${k}=${v}|" .env
  else
    printf '%s=%s\n' "$k" "$v" >> .env
  fi
}

if [ -n "$PH_KEY" ]; then
  set_env POSTHOG_API_KEY "$PH_KEY"
  set_env POSTHOG_HOST "$PH_HOST"
  echo "[deploy] POSTHOG env set in .env"
fi

if [ -n "$LF_PUB" ] && [ -n "$LF_SEC" ]; then
  set_env LANGFUSE_PUBLIC_KEY "$LF_PUB"
  set_env LANGFUSE_SECRET_KEY "$LF_SEC"
  set_env LANGFUSE_BASE_URL "$LF_BASE"
  set_env ENABLE_LLM_OBS "1"
  echo "[deploy] LANGFUSE env set in .env (ENABLE_LLM_OBS=1)"
fi

echo "[deploy] building app image (chown layer slow — few min ho sakta)..."
$COMPOSE build app
echo "[deploy] recreating app container (no-deps)..."
$COMPOSE up -d --no-deps app
echo "[deploy] boot-grace 16s..."
sleep 16
# 12x5s retry loop (audit 2026-07-04) — CLAUDE.md deploy-loop + CI health-gate
# parity; a single check flaked on slow cold-boots and failed a good deploy.
echo "[deploy] health check (12x5s) ->"
ok=0
for i in $(seq 1 12); do
  if curl -fsS http://127.0.0.1:8000/health; then
    echo ""
    ok=1
    break
  fi
  echo "[deploy] health attempt $i/12 failed — retry in 5s"
  sleep 5
done
if [ "$ok" = "1" ]; then
  echo "[deploy] HEALTH OK"
else
  echo "[deploy] HEALTH FAIL — logs: docker logs --tail 80 leadgen_app"
  exit 1
fi
