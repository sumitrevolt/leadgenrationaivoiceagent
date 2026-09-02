#!/usr/bin/env bash
# Build app image from live-venv lock (Dockerfile.lock) + verify import INSIDE the
# container. Self-backgrounds so the ssh call returns immediately; writes a 1-word
# status to .build_verify_status (poll it). Verbose logs -> /tmp/build.log,/tmp/run.log.
# No impact on the live systemd app.
set -uo pipefail
cd /opt/leadgen

if [ "${BG:-}" != "1" ]; then
  echo "STARTING" > .build_verify_status
  BG=1 nohup bash "$0" >/tmp/bv.log 2>&1 &
  echo "started in background — poll: cat /opt/leadgen/.build_verify_status"
  exit 0
fi

COMPOSE="docker compose -f docker-compose.vps.yml"
echo "RUNNING" > .build_verify_status
[ -f requirements.lock.txt ] || { echo "NO_LOCK" > .build_verify_status; exit 1; }

if $COMPOSE build app >/tmp/build.log 2>&1; then
  if $COMPOSE run --rm -e RUN_IN_PROCESS_SCHEDULER=0 app python -c "import app.main" >/tmp/run.log 2>&1; then
    echo "OK" > .build_verify_status
  else
    echo "IMPORT_FAILED" > .build_verify_status
  fi
else
  echo "BUILD_FAILED" > .build_verify_status
fi
