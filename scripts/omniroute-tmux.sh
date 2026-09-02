#!/usr/bin/env bash
set -euo pipefail

SESSION="${OMNI_TMUX_SESSION:-leadgen-omni}"
NODE_BIN_DIR="${OMNI_NODE_BIN_DIR:-/root/.nvm/versions/node/v22.23.1/bin}"

# Prefer the verified Node 22 LTS so better-sqlite3 uses the matching ABI.
if [[ -d "$NODE_BIN_DIR" ]]; then
  export PATH="$NODE_BIN_DIR:$PATH"
fi
OMNI_CMD="export PATH='$NODE_BIN_DIR':\$PATH; export OMNIROUTE_MEMORY_MB=4096; omniroute"

command -v tmux >/dev/null 2>&1 || { echo "Install tmux: sudo apt-get install -y tmux" >&2; exit 1; }
command -v omniroute >/dev/null 2>&1 || { echo "Install OmniRoute: npm install -g omniroute" >&2; exit 1; }

if tmux has-session -t "$SESSION" 2>/dev/null; then
  if ! tmux has-session -t "$SESSION:gateway" 2>/dev/null; then
    tmux new-window -d -t "$SESSION" -n gateway
    tmux send-keys -t "$SESSION:gateway" "$OMNI_CMD" C-m
    echo "Added missing gateway window to existing session: $SESSION"
  else
    echo "Gateway session already exists: $SESSION"
  fi
  echo "Attach with: tmux attach -t $SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" -c "$HOME" -n gateway
tmux send-keys -t "$SESSION:gateway" "$OMNI_CMD" C-m

echo "Started gateway-only tmux session: $SESSION"
echo "Claude/ChatGPT own worktrees separately; providers receive sanitized text only."
echo "Attach with: tmux attach -t $SESSION"
