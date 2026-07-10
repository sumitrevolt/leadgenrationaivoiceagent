#!/bin/bash
set -euo pipefail

SESSION="leadgen"
PROJ="/opt/leadgen"
DC="docker compose -f ${PROJ}/docker-compose.vps.yml"

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  echo "Session already running. Attach: tmux attach -t ${SESSION}"
  exit 0
fi

tmux kill-server 2>/dev/null || true
sleep 1

# Window 1: App logs
tmux new-session -d -s "${SESSION}" -n "app" -c "${PROJ}"
tmux send-keys "echo '=== App ===' && ${DC} logs -f --tail=60 app" Enter
tmux split-window -h
tmux send-keys "watch -n 5 '${DC} ps'" Enter

# Window 2: Worker logs + queue
tmux new-window -t "${SESSION}" -n "worker" -c "${PROJ}"
tmux send-keys "echo '=== Worker + Heavy ===' && ${DC} logs -f --tail=60 worker worker-heavy" Enter
tmux split-window -h
tmux send-keys "watch -n 8 'redis-cli llen celery 2>/dev/null; redis-cli llen dlq:failed_tasks 2>/dev/null'" Enter

# Window 3: Scheduler
tmux new-window -t "${SESSION}" -n "scheduler" -c "${PROJ}"
tmux send-keys "echo '=== Beat ===' && ${DC} logs -f --tail=50 scheduler" Enter

# Window 4: System (htop + caddy)
tmux new-window -t "${SESSION}" -n "sys" -c "${PROJ}"
tmux send-keys "htop -d 3" Enter
tmux split-window -h
tmux send-keys "journalctl -u caddy -f --no-pager" Enter
tmux split-window -v
tmux send-keys "watch -n 20 'df -h /; echo; free -m; echo; ps aux --sort=-%cpu | head -4'" Enter

# Window 5: Docker stats
tmux new-window -t "${SESSION}" -n "docker" -c "${PROJ}"
tmux send-keys "watch -n 3 'docker stats --no-stream'" Enter

# Window 6: Postgres
tmux new-window -t "${SESSION}" -n "db" -c "${PROJ}"
tmux send-keys 'watch -n 5 "docker exec leadgen_db psql -U leadgen -d leadgen_db -P pager=off -c \"SELECT pid, age(now(),query_start) as age, state, left(query,60) FROM pg_stat_activity WHERE state != '\''idle'\'' AND pid != pg_backend_pid() ORDER BY query_start;\""' Enter

tmux select-window -t "${SESSION}:app"
echo "OK - tmux session ready"
