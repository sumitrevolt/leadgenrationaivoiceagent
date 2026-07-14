#!/usr/bin/env bash
# launch_probe2.sh — read-only: paid-customer truth + version provenance
set +e
cd /opt/leadgen || exit 1
echo "===MARKETING_CLIENTS (name/id/plan/status only)==="
python3 - <<'PY'
import json
p="/opt/leadgen/data/marketing_clients.jsonl"
try:
    for line in open(p, encoding="utf-8"):
        line=line.strip()
        if not line: continue
        try: d=json.loads(line)
        except Exception: continue
        print("|".join(str(d.get(k,"")) for k in ("client_id","business_name","plan","status","paid","phone")))
except Exception as e:
    print("ERR", e)
PY
echo "===APP_VERSION_ENV==="
grep -c '^APP_VERSION' /opt/leadgen/.env
docker exec leadgen_app printenv APP_VERSION 2>/dev/null || echo "APP_VERSION-unset-in-container"
echo "===IMAGE==="
docker inspect --format '{{.Config.Image}}' leadgen_app 2>/dev/null
echo "===PROBE2_DONE==="
