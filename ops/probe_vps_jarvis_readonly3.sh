#!/usr/bin/env bash
set -u
echo "=== container state ==="
docker inspect leadgen_telegram_jarvis -f 'STATE={{.State.Status}} RESTARTS={{.RestartCount}} STARTED={{.State.StartedAt}}'
echo
echo "=== container ingress env (names + safe values) ==="
docker inspect leadgen_telegram_jarvis -f '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'TELEGRAM_(INGRESS|INSTANCE|POLL|OWNER)'
echo
echo "=== last 6 jarvis log lines ==="
docker logs --tail 6 leadgen_telegram_jarvis 2>&1
echo
echo "=== state json ==="
docker exec leadgen_telegram_jarvis sh -c 'cat /opt/leadgen/data/telegram_jarvis_state.json 2>/dev/null || echo MISSING'
