#!/usr/bin/env bash
set -uo pipefail
echo "=== design-system tree in container ==="
docker exec leadgen_app ls -la /app/frontend/design-system/ 2>&1 | head -40
echo "=== vendor dir ==="
docker exec leadgen_app ls -la /app/frontend/design-system/vendor/ 2>&1 | head -40
echo "=== find sigma ==="
docker exec leadgen_app find /app/frontend -name 'sigma*.js' 2>/dev/null | head
echo "=== mount points / static ==="
docker exec leadgen_app sh -c 'mount | grep -i frontend || true; ls -la /app/frontend/design-system/vendor/sigma.min.js 2>&1'
echo "=== host /opt/leadgen frontend vendor ==="
ls -la /opt/leadgen/frontend/design-system/vendor/*.js 2>&1 | head
echo "=== which process serves design-system ==="
curl -sI -m 8 http://127.0.0.1:8000/design-system/vendor/sigma.min.js | head -12
