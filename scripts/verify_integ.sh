#!/usr/bin/env bash
# verify_integ.sh — read-only: LIVE integration health snapshot (rolling 24h)
set +e
cat > /tmp/vinteg.py <<'PY'
from app.platform import integration_health as ih
snap = ih.snapshot(24)
print("redis_status:", snap.get("redis_status"), "| degraded:", snap.get("degraded"))
print("%-16s %-7s %-7s %-10s %s" % ("integration", "fail", "ok", "fail_rate", "last_error"))
for name, d in sorted((snap.get("integrations") or {}).items()):
    print("%-16s %-7s %-7s %-10s %s" % (
        name, d.get("fail"), d.get("ok"), d.get("fail_rate"), str(d.get("last_error"))[:40]))
if not snap.get("integrations"):
    print("(no integration activity recorded in window)")
PY
docker cp /tmp/vinteg.py leadgen_app:/tmp/vinteg.py >/dev/null 2>&1
docker exec leadgen_app python3 /tmp/vinteg.py 2>&1 | grep -v '"level"'
echo "===WHATSAPP LIVE SEND-PATH CHECK (in-network, correct port)==="
docker exec leadgen_app sh -c 'curl -s -o /dev/null -w "app:8080/health -> %{http_code}\n" -m 8 http://app:8080/health'
docker exec leadgen_app sh -c 'curl -s -o /dev/null -w "app:8000/health -> %{http_code} (expect FAIL: wrong in-network port)\n" -m 5 http://app:8000/health'
echo "===INTEG_DONE==="
