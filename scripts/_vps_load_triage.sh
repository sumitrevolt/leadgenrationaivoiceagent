#!/bin/bash
# FINAL bounded triage: external public truth + VPS load + heaviest CPU consumers.
# Two bounded probes only (no repeated hammering of the loaded box).
set -uo pipefail
cd /opt/leadgen
echo "=== VPS LOAD (instant /proc, no ps overhead) ==="
awk '{print "  1min="$1" 5min="$2 15min="$3}' /proc/loadavg
echo
echo "=== heaviest CPU (single top batch, 3s sample) ==="
top -bn2 -d3 | awk '/^%Cpu/ && NR==0{next} /^ %Cpu/ {last=$0} /^ *[0-9]+ root/ && last{print} END{}' | grep -E 'root|nobody' | head -8
echo
echo "=== pre-existing retention loop + my killed prune confirm ==="
echo "  my-prune-running: $(ps -eo cmd | grep -c -E 'builder prune -f|_vps_prune_safe' || echo 0) (0 = killed)"
echo "  until=24h loop:   $(ps -eo cmd | grep -c 'until=24h' || echo 0) (pre-existing, leave alone)"
echo
echo "=== app serving? (bounded 8s) ==="
OUT="$(timeout 8 curl -s http://127.0.0.1:8000/health)"
echo "  ${OUT:-<empty>} " | grep -oE '"version":"[^"]*"|"status":"[^"]*"|"uptime":"[^"]*"' | tr '\n' ' '
echo
echo "FINAL_TRIAGE_DONE"
