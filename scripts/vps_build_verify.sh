#!/usr/bin/env bash
# Build the app image from the live-venv lock (Dockerfile.lock) and verify it
# imports cleanly INSIDE the container. No impact on the live systemd app.
set -uo pipefail
cd /opt/leadgen
COMPOSE="docker compose -f docker-compose.vps.yml"

echo "=== ensure lockfile present (from scripts/vps_freeze.sh) ==="
[ -f requirements.lock.txt ] || { echo "FATAL: requirements.lock.txt missing — run vps_freeze.sh"; exit 1; }
echo "lock lines: $(wc -l < requirements.lock.txt)"

echo "=== build app image (Dockerfile.lock, --no-deps) ==="
$COMPOSE build app

echo "=== verify import inside the freshly built image ==="
$COMPOSE run --rm -e RUN_IN_PROCESS_SCHEDULER=0 app python -c "import app.main; print('CONTAINER IMPORT OK — image is good')"

echo "BUILD-VERIFY DONE"
