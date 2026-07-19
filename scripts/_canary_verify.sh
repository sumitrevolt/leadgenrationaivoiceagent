#!/bin/bash
set -e
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

echo "=== HOST ==="
hostname
date -Iseconds

echo "=== HEALTH ==="
curl -s http://127.0.0.1:8000/health | head -c 400
echo

echo "=== CONTAINERS ==="
if command -v docker >/dev/null 2>&1; then
  docker ps --format '{{.Names}} {{.Image}}' | grep leadgen | sort
else
  echo "docker not in PATH, trying common locations..."
  for d in /usr/bin/docker /usr/local/bin/docker /snap/bin/docker; do
    if [ -x "$d" ]; then DOCKER="$d"; break; fi
  done
  if [ -n "$DOCKER" ]; then
    echo "found: $DOCKER"
    $DOCKER ps --format '{{.Names}} {{.Image}}' | grep leadgen | sort
  else
    echo "NO DOCKER FOUND"
    ls -la /usr/bin/docker* 2>/dev/null || true
  fi
fi

APP=leadgen_app
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx leadgen_app; then
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx voice_agent_app; then
    APP=voice_agent_app
  fi
fi
echo "APP=$APP"

echo "=== OMNIROUTE CHECK ==="
docker exec "$APP" python -c "
import os
try:
    from app.voice_agent.omniroute_client import omniroute_available
    oa = omniroute_available()
except Exception as e:
    oa = f'ERROR:{e}'
print('OMNIROUTE_ENABLED', os.getenv('OMNIROUTE_ENABLED'))
print('OMNIROUTE_VOICE', os.getenv('OMNIROUTE_VOICE'))
print('OMNIROUTE_BASE_URL set', bool(os.getenv('OMNIROUTE_BASE_URL')))
print('omniroute_available', oa)
"

echo "=== GATEWAY REACH ==="
docker exec "$APP" python -c "
import urllib.request
try:
    r = urllib.request.urlopen('http://172.16.1.1:20128/health', timeout=5)
    print('gateway_status', r.status)
    print('gateway_body', r.read().decode()[:200])
except Exception as e:
    print('gateway_error', type(e).__name__, str(e)[:200])
" 2>&1

echo "=== IMAGE VERSIONS ==="
docker ps --format '{{.Names}} {{.Image}}' | grep -E 'leadgen|voice_agent' | sort

echo "=== ALLOWLIST ==="
docker exec "$APP" python -c "
from app.telephony.dial_gate import allowlist, test_mode
print('test_mode', test_mode())
print('allowlist', sorted(allowlist()))
print('9359984977 in allowlist', '9359984977' in allowlist())
"

echo "DONE_VERIFY"
