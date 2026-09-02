#!/usr/bin/env bash
# OmniRoute health guard — local dev tool only, no production impact.
# Detects duplicate/rogue processes bound to the OmniRoute dashboard port,
# reports single-process health, and (with --fix) kills extras and restarts
# cleanly via the tmux gateway window (never a second ad-hoc instance).
set -uo pipefail

PORT="${OMNI_HEALTHGUARD_PORT:-20128}"
SESSION="${OMNI_TMUX_SESSION:-leadgen-omni}"
NODE_BIN_DIR="${OMNI_NODE_BIN_DIR:-/root/.nvm/versions/node/v22.23.1/bin}"
if [[ -d "$NODE_BIN_DIR" ]]; then
  export PATH="$NODE_BIN_DIR:$PATH"
fi
OMNI_CMD="export PATH='$NODE_BIN_DIR':\$PATH; export OMNIROUTE_MEMORY_MB=4096; omniroute"
FIX=0
[[ "${1:-}" == "--fix" ]] && FIX=1
WINDOW_SECONDS="${OMNI_HEALTHGUARD_WINDOW_SECONDS:-300}"

echo "== OmniRoute health guard =="
PIDS=$(ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+' | sort -u)
COUNT=$(echo -n "$PIDS" | grep -c . || true)

if [[ -z "$PIDS" ]]; then
  echo "STATUS: DOWN — nothing listening on port $PORT."
  if [[ "$FIX" == "1" ]]; then
    echo "Restarting via tmux gateway window ($SESSION:gateway)..."
    tmux has-session -t "$SESSION" 2>/dev/null || { echo "No tmux session '$SESSION' — run scripts/omniroute-tmux.sh first."; exit 1; }
    tmux send-keys -t "$SESSION:gateway" "$OMNI_CMD" Enter
    sleep 8
  fi
elif [[ "$COUNT" -eq 1 ]]; then
  echo "STATUS: OK — single process on port $PORT (pid $PIDS)."
else
  echo "STATUS: DUPLICATE — $COUNT processes claim port $PORT: $PIDS"
  if [[ "$FIX" == "1" ]]; then
    echo "Killing all and restarting cleanly from tmux gateway window..."
    pkill -9 -f omniroute 2>/dev/null || true
    sleep 2
    tmux send-keys -t "$SESSION:gateway" "$OMNI_CMD" Enter
    sleep 8
  fi
fi

echo "-- WebSocket reconnect-storm check (last ${WINDOW_SECONDS}s) --"
LOG=/root/.omniroute/logs/application/app.log
if [[ -f "$LOG" ]]; then
  CUTOFF=$(date -u -d "-${WINDOW_SECONDS} seconds" +'%Y-%m-%dT%H:%M:%S')
  RECENT_CONNECTS=$(awk -v cutoff="$CUTOFF" '
    /"LiveWS".*Client connected/ {
      timestamp = substr($0, 15, 19)
      if (timestamp >= cutoff) count++
    }
    END { print count + 0 }
  ' "$LOG")
  ACTIVE_WS=$(ss -Htn state established '( sport = :20129 )' 2>/dev/null | wc -l)
  if [[ "$RECENT_CONNECTS" -gt 30 ]]; then
    echo "WARN: $RECENT_CONNECTS LiveWS connect events in ${WINDOW_SECONDS}s ($ACTIVE_WS active) — possible reconnect storm."
  else
    echo "OK: LiveWS connect churn normal ($RECENT_CONNECTS in ${WINDOW_SECONDS}s; $ACTIVE_WS active)."
  fi
else
  echo "(no app.log found yet at $LOG)"
fi

echo "-- Memory --"
ps -eo pid,rss,cmd 2>/dev/null | grep '[o]mniroute (v' | awk '{printf "pid %s: %.0f MB RSS\n", $1, $2/1024}'

echo "-- Version pin --"
INSTALLED=$(omniroute --version 2>/dev/null | tail -1)
echo "Installed: $INSTALLED (pinned target: 3.8.46 — do not auto-upgrade; 3.8.47 has a known ERR_MODULE_NOT_FOUND packaging bug)"
if [[ "$INSTALLED" != "3.8.46" ]]; then
  echo "WARN: version drifted from pinned 3.8.46!"
fi
