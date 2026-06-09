#!/usr/bin/env bash
# Build the app image from the live-venv lock (Dockerfile.lock) and verify it
# imports cleanly INSIDE the container. Verbose build -> /tmp/build.log so the
# console stays small. No impact on the live systemd app.
set -uo pipefail
cd /opt/leadgen
COMPOSE="docker compose -f docker-compose.vps.yml"

[ -f requirements.lock.txt ] || { echo "FATAL: requirements.lock.txt missing — run vps_freeze.sh"; exit 1; }
echo "lock lines: $(wc -l < requirements.lock.txt)"

echo "building app image (log -> /tmp/build.log; may take a few min)..."
if $COMPOSE build app >/tmp/build.log 2>&1; then
  echo "BUILD OK"
  grep -iE "naming to|exporting|writing image" /tmp/build.log | tail -1 || true
else
  echo "BUILD FAILED — last 25 log lines:"; tail -25 /tmp/build.log; exit 1
fi

echo "verifying import inside the image..."
if $COMPOSE run --rm -e RUN_IN_PROCESS_SCHEDULER=0 app python -c "import app.main; print('CONTAINER IMPORT OK - image is good')" 2>/tmp/run.log; then
  echo "BUILD-VERIFY DONE"
else
  echo "IMPORT FAILED — last 25 lines:"; tail -25 /tmp/run.log; exit 1
fi
