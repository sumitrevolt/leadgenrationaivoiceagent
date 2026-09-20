#!/bin/bash
# Refresh TypeSafe key into running containers WITHOUT rebuilding the image.
# Targeted recreate of `app` + `worker` services with SAME APP_VERSION (404e5309).
set -euo pipefail

cd /opt/leadgen
export APP_VERSION=404e5309   # matches running image tag — bina-rebuild recreate

echo "=== BEFORE: leadgen_app TYPESAFE key length ==="
docker exec leadgen_app python -c 'import os; k=os.getenv("TYPESAFE_API_KEY",""); print(f"len={len(k)} prefix={k[:14]}...")' 2>&1 || echo "(pre-check failed)"

# `up -d` re-reads .env, no image rebuild. Worker rolled via compose; app via systemctl.
docker compose -f docker-compose.vps.yml up -d worker 2>&1 | tail -6
systemctl restart leadgen 2>/dev/null || true

echo "=== waiting 14s for startup ==="
sleep 14

echo "=== AFTER: leadgen_app TYPESAFE key length ==="
docker exec leadgen_app python -c 'import os; k=os.getenv("TYPESAFE_API_KEY",""); print(f"len={len(k)} prefix={k[:14]}... enabled={bool(k)}")' 2>&1

echo "=== smoke: TypeSafe integration live check ==="
docker exec leadgen_app python -c '
from app.platform.typesafe_integration import get_typesafe_client, typesafe_choice
c = get_typesafe_client()
print(f"client.enabled={c.enabled}")
try:
    r = typesafe_choice(
        "Is the TypeSafe integration live?",
        {"context": "smoke", "step": "cicd_recovery_2026-09-19"},
        {"yes": "Live", "no": "Broken"}
    )
    print(f"smoke_success={r.success} value={r.value} confidence={r.confidence} model={r.model}")
    if not r.success:
        print(f"smoke_error={(r.error or "")[:200]}")
except Exception as e:
    print(f"smoke_exception={e}")
' 2>&1

echo "=== health ==="
curl -s http://127.0.0.1:8000/health 2>&1 | head -c 400
echo ""
echo "DONE"
