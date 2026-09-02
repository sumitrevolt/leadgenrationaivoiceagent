#!/bin/bash
# =============================================================
# WAHA Activation Script — VPS pe run karo (ek baar / rotation ke baad)
# SSH: ssh -i ~/.ssh/id_rsa root@72.61.245.204
#
# SECURITY (2026-07-14 remediation): yeh script secrets HARDCODE nahi
# karta. WAHA_API_KEY / WAHA_WEBHOOK_TOKEN / WHATSAPP_BUSINESS_NUMBER
# is shell session me export karo (ya inline pass karo) — script missing
# hone par LOUD FAIL karta hai, kabhi silent default nahi deta.
# Purani hardcoded key/token (ab exposed maano — rotate zaroor karo)
# `memory/playbooks.md` → "WAHA secret rotation" runbook me hai.
#
# Usage:
#   export WAHA_API_KEY="<new-strong-random>"
#   export WAHA_WEBHOOK_TOKEN="<new-strong-random>"
#   export WHATSAPP_BUSINESS_NUMBER="91XXXXXXXXXX"
#   ./scripts/activate_waha_vps.sh
# =============================================================

set -e
cd /opt/leadgen

: "${WAHA_API_KEY:?WAHA_API_KEY env var required — export before running, never hardcode}"
: "${WAHA_WEBHOOK_TOKEN:?WAHA_WEBHOOK_TOKEN env var required — export before running, never hardcode}"
: "${WHATSAPP_BUSINESS_NUMBER:?WHATSAPP_BUSINESS_NUMBER env var required (E.164 digits, e.g. 91XXXXXXXXXX)}"

echo "=== Step 1: .env me WAHA vars add/update kar raha hoon ==="

# Pehle purani Cloud API line comment karo (agar hai)
sed -i 's/^WHATSAPP_BUSINESS_TOKEN=/#WHATSAPP_BUSINESS_TOKEN=/' .env
sed -i 's/^WHATSAPP_PHONE_NUMBER_ID=/#WHATSAPP_PHONE_NUMBER_ID=/' .env

# Purani WAHA block hatao (agar hai) — taaki rotation pe stale/duplicate
# key na reh jaaye (idempotent re-run safe).
sed -i '/^# === WAHA Self-Hosted WhatsApp ===$/,/^WHATSAPP_AUTO_SEND=/d' .env

cat >> .env << ENVVARS

# === WAHA Self-Hosted WhatsApp ===
WHATSAPP_PROVIDER=waha
WAHA_BASE_URL=http://waha:3000
WAHA_SESSION=default
WAHA_API_KEY=${WAHA_API_KEY}
WAHA_WEBHOOK_TOKEN=${WAHA_WEBHOOK_TOKEN}
WHATSAPP_BUSINESS_NUMBER=${WHATSAPP_BUSINESS_NUMBER}
WHATSAPP_AUTO_SEND=0
ENVVARS

echo "=== Step 2: WAHA container start kar raha hoon ==="
docker compose -f deploy/compose/docker-compose.waha.yml up -d

echo "=== Step 3: App container restart kar raha hoon (new env pick kare) ==="
docker compose -f docker-compose.vps.yml up -d --no-deps app

echo "=== Step 4: 16 sec wait (uvicorn warmup) ==="
sleep 16

echo "=== Step 5: Health check ==="
curl -sf http://127.0.0.1:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('App:', d.get('status','?'))"

echo "=== Step 6: WAHA container check ==="
docker logs --tail=5 leadgen_waha 2>/dev/null || echo "WAHA logs check karo manually"

echo ""
echo "=============================================="
echo "DONE. Ab browser me kholo:"
echo "  https://leadsgenai.in/app/whatsapp"
echo "  → Self-host card → Start session → QR scan karo"
echo "  Phone pe: WhatsApp → Linked Devices → Link a Device"
echo "=============================================="
