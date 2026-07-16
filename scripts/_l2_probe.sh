#!/usr/bin/env bash
set -uo pipefail
echo "=== vendor in image ==="
docker exec leadgen_app ls -la /app/frontend/design-system/vendor/*.js
echo "=== HEAD vs GET graph ==="
curl -sI -m 10 http://127.0.0.1:8000/app/control-center/graph | head -15
echo "----"
curl -sD - -o /tmp/g.html -m 15 http://127.0.0.1:8000/app/control-center/graph | head -20
echo "body_bytes=$(wc -c </tmp/g.html)"
grep -o 'graphology\|Sigma\|ELK\|error-banner\|Missing CDN' /tmp/g.html | sort | uniq -c | head
echo "=== route registered? ==="
docker exec leadgen_app python -c "from app.main import app; print([ (getattr(r,'path',None), getattr(r,'methods',None)) for r in app.routes if 'control-center' in str(getattr(r,'path','')) ])"
