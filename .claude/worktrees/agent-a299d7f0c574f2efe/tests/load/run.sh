#!/usr/bin/env bash
# =============================================================================
# run.sh — k6 runner via Docker (local k6 install NAHI chahiye).
# Default target = STAGING (:8001). Prod (leadsgenai.in) pe galti se load na
# ho isliye guard hai — prod test jaan-boojh ke karna ho to CONFIRM_PROD=1.
#
#   bash tests/load/run.sh smoke                      # staging smoke
#   MAX_VUS=80 SUSTAIN=5m bash tests/load/run.sh load # staging capacity test
#   BASE_URL=http://host.docker.internal:8000 bash tests/load/run.sh smoke
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="${1:-smoke}" # smoke | load

# Staging default (docker se host tak pohanchne ke liye host.docker.internal).
BASE_URL="${BASE_URL:-http://host.docker.internal:8001}"

case "$BASE_URL" in
*leadsgenai.in* | *72.61.245.204*)
  if [ "${CONFIRM_PROD:-0}" != "1" ]; then
    echo "REFUSING: BASE_URL prod ki taraf hai ($BASE_URL)."
    echo "Staging use kar, ya jaan-boojh ke: CONFIRM_PROD=1 BASE_URL=$BASE_URL bash $0 $SCRIPT"
    exit 2
  fi
  echo "WARNING: PROD pe load test chala raha hai ($BASE_URL)"
  ;;
esac

if [ ! -f "$HERE/${SCRIPT}.js" ]; then
  echo "no such script: $HERE/${SCRIPT}.js (use 'smoke' ya 'load')"
  exit 1
fi

echo "==> k6 ${SCRIPT} -> ${BASE_URL}"
docker run --rm -i \
  --add-host=host.docker.internal:host-gateway \
  -e BASE_URL="$BASE_URL" \
  -e VUS="${VUS:-}" -e MAX_VUS="${MAX_VUS:-}" \
  -e DURATION="${DURATION:-}" -e RAMP="${RAMP:-}" -e SUSTAIN="${SUSTAIN:-}" \
  -v "$HERE":/scripts \
  grafana/k6 run "/scripts/${SCRIPT}.js" \
  --summary-export="/scripts/last-${SCRIPT}-summary.json"

echo "==> summary saved: tests/load/last-${SCRIPT}-summary.json"
