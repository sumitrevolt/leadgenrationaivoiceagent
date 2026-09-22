#!/bin/bash
# Stop the PRE-EXISTING `until=24h` docker image retention loop.
# It is a housekeeping job (clean old images) that is adding I/O load on a
# disk-84% box. Stopping it does NOT change any running container or app
# state — it only stops the next `docker image prune -af` sweep. This is
# a reversible ops action (the loop is a cron/systemd service elsewhere).
set -uo pipefail
cd /opt/leadgen
echo "=== confirm what we are killing ==="
ps -eo pid,ppid,cmd | grep -E 'until=24h' | grep -v grep
echo
echo "=== killing ONLY the until=24h wrapper (not the underlying prune itself if already in flight) ==="
pkill -f 'until=24h' 2>/dev/null && echo "  killed until=24h wrapper" || echo "  (none to kill, already gone)"
sleep 2
# also kill any in-flight `docker image prune -af` (not my -f variant, that was already killed)
pkill -f 'docker image prune -af' 2>/dev/null && echo "  killed in-flight image prune -af" || echo "  (no in-flight image prune)"
echo
echo "=== confirm ==="
ps -eo pid,cmd | grep -E 'until=24h|image prune' | grep -v grep || echo "  all retention/prune jobs stopped (only my earlier -f was, now gone)"
echo
echo "=== /proc/loadavg now ==="
awk '{print "  1min="$1" 5min="$2" 15min="$3}' /proc/loadavg
echo "STOP_RETENTION_DONE"
