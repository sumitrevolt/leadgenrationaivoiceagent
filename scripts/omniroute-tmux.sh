#!/usr/bin/env bash
set -euo pipefail

SESSION="${OMNI_TMUX_SESSION:-leadgen-omni}"
ROOT="${OMNI_PROJECT_ROOT:-$PWD}"
RESEARCH="${OMNI_RESEARCH_ROOT:-$ROOT}"
IMPLEMENT="${OMNI_IMPLEMENT_ROOT:-$ROOT}"
REVIEW="${OMNI_REVIEW_ROOT:-$ROOT}"
NODE_BIN_DIR="${OMNI_NODE_BIN_DIR:-/root/.nvm/versions/node/v22.23.1/bin}"

# Prefer the verified Node 22 LTS in WSL so OmniRoute uses the matching
# better-sqlite3 native ABI even when nvm is not loaded by the login shell.
if [[ -d "$NODE_BIN_DIR" ]]; then
  export PATH="$NODE_BIN_DIR:$PATH"
fi
OMNI_CMD="export PATH='$NODE_BIN_DIR':\$PATH; export OMNIROUTE_MEMORY_MB=2048; omniroute"

for dir in "$ROOT" "$RESEARCH" "$IMPLEMENT" "$REVIEW"; do
  [[ -d "$dir" ]] || { echo "Missing lane directory: $dir" >&2; exit 1; }
done

command -v tmux >/dev/null 2>&1 || { echo "Install tmux: sudo apt-get install -y tmux" >&2; exit 1; }
command -v omniroute >/dev/null 2>&1 || { echo "Install OmniRoute: npm install -g omniroute" >&2; exit 1; }

if tmux has-session -t "$SESSION" 2>/dev/null; then
  if ! tmux has-session -t "$SESSION:gateway" 2>/dev/null; then
    tmux new-window -d -t "$SESSION" -n gateway
    tmux send-keys -t "$SESSION:gateway" "$OMNI_CMD" C-m
    echo "Added missing gateway window to existing session: $SESSION"
  else
    echo "Session already exists: $SESSION"
  fi
  echo "Attach with: tmux attach -t $SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" -c "$ROOT" -n leadgen
tmux send-keys -t "$SESSION:leadgen.0" "echo 'Research/context lane — read-only by convention'; cd '$RESEARCH'; bash" C-m
tmux split-window -h -t "$SESSION:leadgen" -c "$IMPLEMENT"
tmux send-keys -t "$SESSION:leadgen.1" "echo 'Implementation lane — owns the patch'; bash" C-m
tmux split-window -v -t "$SESSION:leadgen.1" -c "$REVIEW"
tmux send-keys -t "$SESSION:leadgen.2" "echo 'Tests/review lane — verify, do not edit implementation files'; bash" C-m
tmux select-pane -t "$SESSION:leadgen.0"
tmux new-window -d -t "$SESSION" -n gateway
tmux send-keys -t "$SESSION:gateway" "$OMNI_CMD" C-m

echo "Started tmux session: $SESSION"
echo "Attach with: tmux attach -t $SESSION"
