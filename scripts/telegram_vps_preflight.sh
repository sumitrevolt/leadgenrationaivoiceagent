#!/usr/bin/env bash
# READ-ONLY preflight for the Telegram VPS ingress owner.
# Prints env var NAMES and value LENGTHS only -- never a token value.
set -uo pipefail
cd /opt/leadgen || exit 1

echo "=== .env key names (telegram/postgres) ==="
grep -oE '^[A-Z0-9_]+' .env | grep -iE 'TELEGRAM|POSTGRES|APP_VERSION' | sort -u

echo
echo "=== presence + length (values never printed) ==="
for k in TELEGRAM_JARVIS_BOT_TOKEN TELEGRAM_NOTIFY_BOT_TOKEN TELEGRAM_BOT_TOKEN \
         TELEGRAM_OWNER_CHAT_IDS TELEGRAM_OWNER_USERNAMES TELEGRAM_INGRESS_OWNER \
         POSTGRES_PASSWORD POSTGRES_USER POSTGRES_DB; do
  v=$(grep -E "^${k}=" .env | head -1 | cut -d= -f2- | tr -d '"'"'"'' | tr -d '\r')
  printf '%-32s len=%s\n' "$k" "${#v}"
done

echo
echo "=== git state ==="
git rev-parse --short HEAD
git status --short | head -5

echo
echo "=== running services ==="
docker compose -f docker-compose.vps.yml ps --format '{{.Service}} {{.Image}} {{.Status}}' 2>/dev/null | head -25

echo
echo "=== app image tag (drift detector) ==="
docker inspect -f '{{.Config.Image}}' leadgen_worker 2>/dev/null || echo missing
curl -s --max-time 8 http://127.0.0.1:8000/health | head -c 300 || echo "(health unreachable)"
echo
