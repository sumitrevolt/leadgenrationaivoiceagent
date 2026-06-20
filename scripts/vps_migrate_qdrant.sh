#!/usr/bin/env bash
# Migrate legacy standalone Qdrant -> docker-compose in-stack service.
# Safe: reuses /opt/qdrant_storage (vectors preserved). Idempotent.
set -euo pipefail
cd /opt/leadgen

echo "=== Stop legacy standalone qdrant (if any) ==="
docker stop qdrant 2>/dev/null || true
docker update --restart=no qdrant 2>/dev/null || true

echo "=== Start compose qdrant on leadgen_net ==="
docker compose -f docker-compose.vps.yml up -d qdrant

echo "=== Fix .env QDRANT_URL (compose hardcodes too, but keep truth aligned) ==="
if grep -q '^QDRANT_URL=' .env 2>/dev/null; then
  sed -i 's|^QDRANT_URL=.*|QDRANT_URL=http://qdrant:6333|' .env
else
  echo 'QDRANT_URL=http://qdrant:6333' >> .env
fi

echo "=== Recreate app + workers ==="
docker compose -f docker-compose.vps.yml up -d --no-deps app
docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps worker worker-heavy

sleep 8
curl -sf http://127.0.0.1:6333/healthz && echo " host qdrant OK"
docker exec leadgen_app python -c "import os,urllib.request; u=os.environ['QDRANT_URL'].rstrip('/')+'/healthz'; print(urllib.request.urlopen(u,timeout=3).status)"
echo "DONE"
