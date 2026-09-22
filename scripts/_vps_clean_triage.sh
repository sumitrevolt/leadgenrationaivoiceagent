#!/bin/bash
# ONE clean, cheap diagnostic. Avoids `top -bn2` (double scan) and `docker`
# (daemon may be I/O-locked). Uses single `ps` + /proc only.
set -uo pipefail
cd /opt/leadgen
echo "=== $(date -u) ==="
awk '{print "LOAD: 1min="$1" 5min="$2" 15min="$3}' /proc/loadavg
echo "TASKS: $(wc -l < /proc/loadavg >/dev/null 2>&1; cat /proc/stat | awk '/^procs/ {print "procs_running="$3" procs_blocked="$4}')"
echo
echo "=== my prune truly dead? (exact PIDs) ==="
ps -eo pid,etime,stat,cmd | grep -E 'builder prune|buildx prune|_vps_prune_safe' | grep -v grep || echo "  none running (good)"
echo
echo "=== until=24h pre-existing retention loop (leave alone, just confirm) ==="
ps -eo pid,etime,cmd | grep 'until=24h' | grep -v grep | head
echo
echo "=== TOP 18 by CPU (single ps, full cmd) ==="
ps -eo pid,ppid,pcpu,pmem,etime,stat,comm,args --sort=-pcpu | head -19
echo
echo "=== how many are in D-state (uninterruptible I/O) vs R (running) ==="
echo "  R=$(ps -eo stat | grep -c '^R')  D=$(ps -eo stat | grep -c '^D')  Z=$(ps -eo stat | grep -c '^Z')"
echo "CHEAP_TRIAGE_DONE"
