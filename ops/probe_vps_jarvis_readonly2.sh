#!/usr/bin/env bash
# Read-only inspection of the stray host-level jarvis poller on VPS
set -u
echo "=== full cmdline + start of PID (stray poller) ==="
ps -o pid,ppid,lstart,etime,args -C python 2>/dev/null | grep -E 'run_telegram_jarvis' | grep -v grep
echo
echo "=== systemd units that could launch it ==="
systemctl list-units --type=service 2>/dev/null | grep -iE 'telegram|jarvis' || echo "(no systemd unit matches)"
echo
echo "=== deploy_vps.sh SERVICES list (telegram-jarvis included?) ==="
grep -nE 'SERVICES=' /opt/leadgen/scripts/deploy_vps.sh 2>/dev/null | head -c 400
echo
echo "=== telegram-jarvis in compose? ==="
grep -nE 'telegram-jarvis|leadgen_telegram_jarvis' /opt/leadgen/docker-compose.vps.yml 2>/dev/null | head -5
