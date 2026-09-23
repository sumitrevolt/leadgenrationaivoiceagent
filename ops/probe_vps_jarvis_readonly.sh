#!/usr/bin/env bash
# Read-only VPS telegram-jarvis inspection (no destructive actions)
echo "=== image tag (provenance check) ==="
docker inspect -f '{{.Config.Image}}' leadgen_telegram_jarvis
echo "=== relevant env (names + values masked; TELEGRAM flags only) ==="
docker inspect leadgen_telegram_jarvis | python3 -c '
import json,sys
d=json.load(sys.stdin)[0]
for e in d["Config"]["Env"]:
    if e.startswith(("TELEGRAM_INGRESS","TELEGRAM_INSTANCE","TELEGRAM_POLL")):
        print(e)
'
echo "=== jarvis state file in shared volume ==="
ls -la /opt/leadgen/data/telegram_jarvis_state.json 2>&1
cat /opt/leadgen/data/telegram_jarvis_state.json 2>/dev/null | head -c 600
echo
echo "=== last 5 log lines (tail) ==="
docker logs --tail 5 leadgen_telegram_jarvis 2>&1 | tail -5
