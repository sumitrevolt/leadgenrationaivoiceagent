#!/usr/bin/env bash
# verify_voice_niches.sh — read-only: is the voice revenue route still 500ing?
set +e
echo "===LIVE /api/voice/niches (public revenue route)==="
curl -s -o /tmp/vn.json -w "HTTP %{http_code}\n" -m 20 https://leadsgenai.in/api/voice/niches
echo "--- body (first 320 chars) ---"
head -c 320 /tmp/vn.json; echo
echo "===RELATED VOICE ROUTES==="
for p in /api/voice/packages /voice-agent /api/billing/plans /api/public/pay-info; do
  printf '%-26s -> %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 15 https://leadsgenai.in$p)"
done
echo "===ImportError in app logs since deploy (13:05)?==="
docker logs --since 25m leadgen_app 2>&1 | grep -ci "lead_topup_price\|_IncludedRouter"
echo "===CRITICAL routes present at startup?==="
docker logs --since 25m leadgen_app 2>&1 | grep -i "CRITICAL routes missing" | tail -2 || echo "(none - good)"
echo "===VN_DONE==="
