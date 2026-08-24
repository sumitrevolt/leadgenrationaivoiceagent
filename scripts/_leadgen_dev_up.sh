#!/usr/bin/env bash
# WSL-side local dev bring-up: Redis broker + gateway-only OmniRoute (Node 22).
# Called by scripts/start-leadgen-dev.ps1 (which strips CR + base64-pipes this in).
# Dev-only, loopback-only. No production touch. Idempotent.
set -uo pipefail
NODE_BIN=/root/.nvm/versions/node/v22.23.1/bin
export PATH="$NODE_BIN:$PATH"
export OMNIROUTE_MEMORY_MB=4096
OMNI_CMD="export PATH=$NODE_BIN:\$PATH; export OMNIROUTE_MEMORY_MB=4096; omniroute"
SESSION=leadgen-omni

echo "== Redis =="
redis-server --daemonize yes >/dev/null 2>&1 || true
sleep 1
printf 'redis ping: '; redis-cli ping 2>/dev/null || echo DOWN

echo "== OmniRoute (tmux $SESSION) =="
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already running"
  if ! tmux list-windows -t "$SESSION" 2>/dev/null | grep -q gateway; then
    tmux new-window -d -t "$SESSION" -n gateway
    tmux send-keys -t "$SESSION:gateway" "$OMNI_CMD" C-m
    echo "re-added gateway window"
  fi
else
  tmux new-session -d -s "$SESSION" -c "$HOME" -n gateway
  tmux send-keys -t "$SESSION:gateway" "$OMNI_CMD" C-m
  echo "tmux session started (gateway-only; no provider worktree access)"
fi

sleep 10
printf 'omniroute :20128 '; (ss -ltnp 2>/dev/null | grep -q ':20128' && echo UP) || echo "still starting"
printf 'omniroute doctor: '; omniroute doctor 2>/dev/null | grep -c '^\[' >/dev/null 2>&1 && omniroute doctor 2>/dev/null | grep -E 'Summary:' || echo "(run: omniroute doctor)"
echo "attach gateway: wsl -d Ubuntu-24.04 -- tmux attach -t $SESSION"
