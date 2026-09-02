#!/usr/bin/env bash
# verify_whatsapp.sh — read-only: is the WhatsApp integration_failed recurring or historical?
set +e
echo "===integration_failed events in jiya ledger (last 8)==="
docker exec leadgen_app sh -c "grep integration_failed data/delivery_ledger/jiya-makeover.jsonl 2>/dev/null | tail -8"
echo "===count today==="
docker exec leadgen_app sh -c "grep -c 'integration_failed' data/delivery_ledger/jiya-makeover.jsonl 2>/dev/null"
echo "===WAHA hook port config (must be app:8080, NOT app:8000)==="
grep -rn 'app:8000\|app:8080' /opt/leadgen/.env 2>/dev/null | sed 's/=.*app:/=...app:/' | head -5
echo "===WAHA session state==="
curl -s -m 10 http://127.0.0.1:3111/api/sessions 2>/dev/null | head -c 300; echo
echo "===recent ECONNREFUSED in worker (last 2h)==="
docker logs --since 2h leadgen_worker 2>&1 | grep -ci "econnrefused"
echo "===WA_DONE==="
