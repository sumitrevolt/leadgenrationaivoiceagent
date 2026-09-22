#!/bin/bash
# Safe load-relief: stop the pre-existing `until=24h` docker image-retention loop
# that is hammering I/O on a disk-84% box. Reversible (re-enable timer after).
set -uo pipefail
echo "=== how is the until=24h loop scheduled? (find the timer/cron source) ==="
# check systemd timers
systemctl list-timers --all 2>/dev/null | grep -iE 'prune|retain|until' || echo "  no matching systemd timer by name"
echo
# check cron
crontab -l 2>/dev/null | grep -iE 'prune|until=24h' || echo "  no matching root crontab line"
ls /etc/cron.d/ 2>/dev/null
grep -rl "until=24h" /etc/cron.d/ /etc/cron* 2>/dev/null || echo "  no cron file with until=24h"
echo
echo "=== the live loop process ==="
ps -eo pid,ppid,cmd | grep 'until=24h' | grep -v grep
echo "RETENTION_SOURCE_DONE"
