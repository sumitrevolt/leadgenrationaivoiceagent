#!/bin/bash
# MINIMAL final check: load + git tip + compose line + bounded local /health.
set -uo pipefail
cd /opt/leadgen
awk '{print "LOAD: 1min="$1" 5min="$2" 15min="$3}' /proc/loadavg
echo "GIT-TIP: $(git log --oneline -1 | cut -c1-50)"
echo "COMPOSE-L59: $(sed -n '59p' docker-compose.vps.yml)"
echo -n "HEALTH: "
OUT="$(timeout 8 curl -s http://127.0.0.1:8000/health)"
echo "${OUT:-<empty>} " | grep -oE '"version":"[^"]*"|"uptime":"[^"]*"' | tr '\n' ' '
echo
echo "FINAL_VPS_STATE_DONE"
