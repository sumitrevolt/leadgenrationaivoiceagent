#!/bin/bash
# VPS: verify all 3 Telegram slots getMe-live (token values never printed).
set -euo pipefail
cd /opt/leadgen
for slot in TELEGRAM_JARVIS_BOT_TOKEN TELEGRAM_NOTIFY_BOT_TOKEN TELEGRAM_BOT_TOKEN; do
  TOK="$(grep -E "^${slot}=" .env | head -1 | cut -d= -f2-)"
  PREFIX="$(printf '%s' "$TOK" | cut -c1-12)"
  HTTP="$(curl -s -o /tmp/getme_${slot}.json -w '%{http_code}' "https://api.telegram.org/bot${TOK}/getMe")"
  USER="$(python3 -c "import json;d=json.load(open('/tmp/getme_${slot}.json'));print(d.get('result',{}).get('username',''))" 2>/dev/null || echo '')"
  echo "${slot} prefix=${PREFIX}... http=${HTTP} user=${USER}"
done
echo "VPS TELEGRAM SLOTS VERIFY DONE"
