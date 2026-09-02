#!/usr/bin/env bash
# ==========================================================================
# FreeSWITCH deploy (VPS pe chalta hai, root) — Vobiz trunk wala telephony core.
# Usage:  bash /opt/leadgen/scripts/fs_deploy.sh
# Idempotent — dobara chalane pe sirf compose up + status. deploy_vps.sh STEP 6c
# isse call karta hai. Creds /opt/leadgen/.env se aate hain (VOBIZ_*, ESL_*).
# ==========================================================================
set -u

APP_DIR=/opt/leadgen
FS_DIR="$APP_DIR/app/telephony/freeswitch"

echo "===FS STEP 1: env load (VOBIZ_* / ESL_* from .env)==="
cd "$FS_DIR" || { echo "(freeswitch dir missing: $FS_DIR)"; exit 1; }
# .env se sirf telephony keys export karo (compose ${VAR} substitution ke liye).
export $(grep -E '^(VOBIZ_|ESL_)' "$APP_DIR/.env" | xargs) 2>/dev/null || true

echo "===FS STEP 2: firewall (5060 sip + 10000-20000 rtp)==="
if command -v ufw >/dev/null 2>&1; then
  ufw allow 5060/udp || true
  ufw allow 5060/tcp || true
  ufw allow 10000:20000/udp || true
else
  echo "(ufw not found — firewall rules skip; Hostinger panel firewall check karo)"
fi

echo "===FS STEP 3: docker compose up==="
docker compose up -d || { echo "(docker compose failed)"; exit 1; }
sleep 8
docker compose ps || true

echo "===FS STEP 4: gateway status (vobiz REGED dikhna chahiye)==="
docker exec leadgen-freeswitch fs_cli -H 127.0.0.1 -P 8021 -p "${ESL_PASSWORD:-ClueCon}" \
  -x "sofia status gateway vobiz" || echo "(gateway status check failed — container logs dekho: docker logs leadgen-freeswitch)"

echo "===FS DEPLOY DONE==="
echo "Verify : docker exec leadgen-freeswitch fs_cli -x 'sofia status gateway vobiz'"
echo "Test   : docker exec leadgen-freeswitch fs_cli -x 'originate sofia/gateway/vobiz/+91XXXXXXXXXX &echo' (own number only — DLT pending)"
