#!/usr/bin/env bash
# Emergency recovery after compose recreate race — then canonical redeploy.
# Scoped to the 5 app-image services ONLY. Never --remove-orphans.
set -uo pipefail
cd /opt/leadgen || exit 1
VER="$(git rev-parse --short HEAD)"
echo "=== RECOVER prod at HEAD=$VER ==="

_cleanup() {
  docker ps -a --format '{{.Names}} {{.Status}}' | while read -r _name _status; do
    case "$_name" in *_leadgen_*)
      if echo "$_status" | grep -qiE 'created|dead'; then
        echo "rm ghost $_name"
        docker rm -f "$_name" 2>/dev/null || true
      fi
      ;;
    esac
  done
  for _c in leadgen_app leadgen_worker leadgen_scheduler leadgen_worker_heavy leadgen_worker_video; do
    _st="$(docker inspect -f '{{.State.Status}}' "$_c" 2>/dev/null || echo missing)"
    if [ "$_st" != "running" ]; then
      echo "rm stale $_c (status=$_st)"
      docker rm -f "$_c" 2>/dev/null || true
    fi
  done
}

_cleanup
echo "=== REDEPLOY via deploy_vps.sh $VER ==="
: > /tmp/dep.log
setsid nohup bash scripts/deploy_vps.sh "$VER" > /tmp/dep.log 2>&1 < /dev/null &
echo "DEPLOY_PID=$!"
sleep 3
head -20 /tmp/dep.log
