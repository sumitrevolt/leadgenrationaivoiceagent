#!/bin/bash
# =============================================================
# WAHA Activation Script — VPS pe run karo (ek baar)
# SSH: ssh -i ~/.ssh/id_rsa root@72.61.245.204
# =============================================================

set -e
cd /opt/leadgen

echo "=== Step 1: .env me WAHA vars add kar raha hoon ==="

# Pehle purani Cloud API line comment karo (agar hai)
sed -i 's/^WHATSAPP_BUSINESS_TOKEN=/#WHATSAPP_BUSINESS_TOKEN=/' .env
sed -i 's/^WHATSAPP_PHONE_NUMBER_ID=/#WHATSAPP_PHONE_NUMBER_ID=/' .env

# WAHA vars add karo (agar pehle se nahi hain)
grep -q "WHATSAPP_PROVIDER=waha" .env || cat >> .env << 'ENVVARS'

# === WAHA Self-Hosted WhatsApp ===
WHATSAPP_PROVIDER=waha
WAHA_BASE_URL=http://waha:3000
WAHA_SESSION=default
WAHA_API_KEY=P__AeDD_iZh-Ul0xp0HcHsTmM4_nswGZDtqv88WycpU
WAHA_WEBHOOK_TOKEN=FfUj25Z9dx61s4DWKin816ZwkOvTcT_4
WHATSAPP_BUSINESS_NUMBER=918261030181
WHATSAPP_AUTO_SEND=0
ENVVARS

echo "=== Step 2: WAHA container start kar raha hoon ==="
docker compose -f docker-compose.waha.yml up -d

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
