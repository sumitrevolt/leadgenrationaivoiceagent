#!/usr/bin/env bash
set -euo pipefail

SESSION="${OMNI_TMUX_SESSION:-leadgen-omni}"
ROOT="${OMNI_PROJECT_ROOT:-$PWD}"
RESEARCH="${OMNI_RESEARCH_ROOT:-$ROOT}"
IMPLEMENT="${OMNI_IMPLEMENT_ROOT:-$ROOT}"
REVIEW="${OMNI_REVIEW_ROOT:-$ROOT}"

for dir in "$ROOT" "$RESEARCH" "$IMPLEMENT" "$REVIEW"; do
  [[ -d "$dir" ]] || { echo "Missing lane directory: $dir" >&2; exit 1; }
done

command -v tmux >/dev/null 2>&1 || { echo "Install tmux: sudo apt-get install -y tmux" >&2; exit 1; }
command -v omniroute >/dev/null 2>&1 || { echo "Install OmniRoute: npm install -g omniroute" >&2; exit 1; }

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session already exists: $SESSION"
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

echo "Started tmux session: $SESSION"
echo "Attach with: tmux attach -t $SESSION"
