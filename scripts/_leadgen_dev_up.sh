#!/usr/bin/env bash
# WSL-side local dev bring-up: Redis broker + OmniRoute gateway/lanes (Node 24).
# Called by scripts/start-leadgen-dev.ps1 (which strips CR + base64-pipes this in).
# Dev-only, loopback-only. No production touch. Idempotent.
set -uo pipefail
NODE_BIN=/root/.nvm/versions/node/v24.18.0/bin
export PATH="$NODE_BIN:$PATH"
SESSION=leadgen-omni
WT=/root/src/leadgenrationaiagent-worktrees

echo "== Redis =="
redis-server --daemonize yes >/dev/null 2>&1 || true
sleep 1
printf 'redis ping: '; redis-cli ping 2>/dev/null || echo DOWN

echo "== OmniRoute (tmux $SESSION) =="
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already running"
  if ! tmux list-windows -t "$SESSION" 2>/dev/null | grep -q gateway; then
    tmux new-window -d -t "$SESSION" -n gateway
    tmux send-keys -t "$SESSION:gateway" "export PATH=$NODE_BIN:\$PATH; omniroute" C-m
    echo "re-added gateway window"
  fi
else
  tmux new-session -d -s "$SESSION" -c "$WT/implement" -n leadgen
  tmux send-keys -t "$SESSION:leadgen.0" "cd $WT/research; echo research-lane (read-only)" C-m
  tmux split-window -h -t "$SESSION:leadgen" -c "$WT/implement"
  tmux send-keys -t "$SESSION:leadgen.1" "echo implement-lane (owns patch)" C-m
  tmux split-window -v -t "$SESSION:leadgen.1" -c "$WT/review"
  tmux send-keys -t "$SESSION:leadgen.2" "echo review-lane (verify only)" C-m
  tmux select-pane -t "$SESSION:leadgen.0"
  tmux new-window -d -t "$SESSION" -n gateway
  tmux send-keys -t "$SESSION:gateway" "export PATH=$NODE_BIN:\$PATH; omniroute" C-m
  echo "tmux session started (gateway + 3 lanes)"
fi

sleep 10
printf 'omniroute :20128 '; (ss -ltnp 2>/dev/null | grep -q ':20128' && echo UP) || echo "still starting"
printf 'omniroute doctor: '; omniroute doctor 2>/dev/null | grep -c '^\[' >/dev/null 2>&1 && omniroute doctor 2>/dev/null | grep -E 'Summary:' || echo "(run: omniroute doctor)"
echo "attach lanes: wsl -d Ubuntu-24.04 -- tmux attach -t $SESSION"
