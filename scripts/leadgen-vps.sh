#!/usr/bin/env bash
# LeadGen VPS helper (monitoring-first). MSYS2 se chalta hai.
# Usage: bash leadgen-vps.sh {ps|health|logs [app|worker|worker-heavy|scheduler|redis]|applogs|ssh}
SSH_BIN="C:/Program Files/Git/usr/bin/ssh.exe"
KEY="C:/Users/Ratanshila/.ssh/id_rsa"
VPS="root@72.61.245.204"
SSHOPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=12 -o ServerAliveInterval=30"

svps() { "$SSH_BIN" $SSHOPTS -i "$KEY" "$VPS" "$@"; }

case "${1:-help}" in
  ps)       svps "docker ps --format 'table {{.Names}}\t{{.Status}}'" ;;
  health)   svps "echo '[VPS internal /health]:'; curl -s -m 5 http://localhost:8000/health; echo" ;;
  logs)     svc="${2:-worker}"; [ "$svc" = "worker-heavy" ] && svc="worker_heavy"; svps "docker logs -f --tail=100 leadgen_${svc}" ;;
  applogs)  svps "docker logs -f --tail=100 leadgen_app" ;;
  ssh)      echo "Interactive SSH. For deploy use the guarded Hostinger runbook, not ad-hoc shell changes."; "$SSH_BIN" $SSHOPTS -i "$KEY" "$VPS" ;;
  *) echo 'Usage: bash leadgen-vps.sh {ps|health|logs [app|worker|worker-heavy|scheduler|redis]|applogs|ssh}' ;;
esac
