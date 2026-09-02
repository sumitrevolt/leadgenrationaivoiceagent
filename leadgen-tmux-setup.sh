#!/usr/bin/env bash
# LeadGen full tmux cockpit (MSYS2). Windows se leadgen-tmux.bat double-click karo.
# Preflight: PowerShell -ExecutionPolicy Bypass -File .\leadgen-operator-doctor.ps1
SESSION="leadgen"
PROJECT_DIR="/c/Users/Ratanshila/Documents/leadgenrationaiagent"
PY=".venv/Scripts/python"

# PATH guard -- tmux (/usr/bin) + Windows git/node hamesha milen
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH:/c/Program Files/Git/cmd:/c/Program Files/nodejs"

# tmux guard (MSYS2 pacman)
if ! command -v tmux >/dev/null 2>&1; then
  echo ">> tmux missing in MSYS2."
  echo ">> Install once: C:\\msys64\\usr\\bin\\pacman.exe -Sy --noconfirm tmux"
  exit 1
fi

# ~/.tmux.conf likho (LeadGen config)
cat > "$HOME/.tmux.conf" << 'EOF'
unbind C-b
set-option -g prefix C-Space
set-option -g mouse on
set-option -g status-bg black
set-option -g status-fg white
set-option -g status-right "#[fg=green]LeadGen #[fg=white]%H:%M %d-%b"
set-option -g default-terminal "screen-256color"
set-option -g base-index 1
set-option -g pane-base-index 1
bind-key -n M-1 select-window -t 1
bind-key -n M-2 select-window -t 2
bind-key -n M-3 select-window -t 3
bind-key -n M-4 select-window -t 4
bind-key -n M-5 select-window -t 5
bind-key -n M-6 select-window -t 6
bind-key -n M-Left  select-pane -L
bind-key -n M-Right select-pane -R
bind-key -n M-Up    select-pane -U
bind-key -n M-Down  select-pane -D
bind-key -n M-S-Left  resize-pane -L 5
bind-key -n M-S-Right resize-pane -R 5
bind-key -n M-S-Up    resize-pane -U 5
bind-key -n M-S-Down  resize-pane -D 5
EOF

CD="cd '$PROJECT_DIR'"

tmux kill-session -t "$SESSION" 2>/dev/null
tmux new-session -d -s "$SESSION" -n architect -x 220 -y 50

# 1) ARCHITECT -- git dashboard (auto-run, read-only)
tmux send-keys -t "$SESSION:architect" "$CD && clear && echo '===== ARCHITECT :: git =====' && git status -sb && echo && echo '--- last 6 commits ---' && git log --oneline -6" Enter

# 2) BACKEND -- local FastAPI (command PRIMED; Enter dabao)
tmux new-window -t "$SESSION" -n backend
tmux send-keys -t "$SESSION:backend" "$CD && clear && echo '===== BACKEND :: local FastAPI =====' && echo 'Note: DB/Redis VPS pe -- local degraded ho sakta (live app: https://leadsgenai.in).' && echo && echo '>>>>> Enter dabao -- uvicorn --reload :8000 start >>>>>'" Enter
tmux send-keys -t "$SESSION:backend" "$PY -m uvicorn app.main:app --reload --port 8000"

# 3) AUTOMATION -- VPS worker logs (read-only SSH; PRIMED)
tmux new-window -t "$SESSION" -n automation
tmux send-keys -t "$SESSION:automation" "$CD && clear && echo '===== AUTOMATION :: VPS Celery worker logs (LIVE, read-only) =====' && echo '(Ctrl-C = stop | app/scheduler: bash leadgen-vps.sh logs app|scheduler)' && bash leadgen-vps.sh logs worker" Enter

# 4) TESTS -- pytest (PRIMED)
tmux new-window -t "$SESSION" -n tests
tmux send-keys -t "$SESSION:tests" "$CD && clear && echo '===== TESTS :: pytest (targeted -- full suite team_pulse pe HANG hota) =====' && echo 'FULL run: .venv/Scripts/python -m pytest tests/ -q -p no:cacheprovider' && echo && echo '>>>>> Enter dabao -- fast contract+api suite chalega >>>>>'" Enter
tmux send-keys -t "$SESSION:tests" "$PY -m pytest tests/test_billing_truth_2026.py tests/test_api.py -q -p no:cacheprovider"

# 5) VOICE -- agent scorecard (PRIMED)
tmux new-window -t "$SESSION" -n voice
tmux send-keys -t "$SESSION:voice" "$CD && clear && echo '===== VOICE :: agent scorecard =====' && echo '(free AI providers use karta -- network chahiye)' && echo && echo '>>>>> Enter dabao -- scripts/agent_tester.py chalega >>>>>'" Enter
tmux send-keys -t "$SESSION:voice" "$PY scripts/agent_tester.py"

# 6) MONITOR -- 2 panes: [L] VPS container status (auto)  [R] public /health watch (PRIMED)
tmux new-window -t "$SESSION" -n monitor
tmux send-keys -t "$SESSION:monitor" "$CD && clear && echo '===== MONITOR :: VPS containers =====' && bash leadgen-vps.sh ps" Enter
tmux split-window -h -t "$SESSION:monitor"
tmux send-keys -t "$SESSION:monitor.2" "$CD && clear && echo '===== public /health watch (Enter=live loop) =====' " Enter
tmux send-keys -t "$SESSION:monitor.2" "while true; do date '+%H:%M:%S'; curl -s -m5 https://leadsgenai.in/health; echo; sleep 60; done"
tmux select-pane -t "$SESSION:monitor.1"

tmux select-window -t "$SESSION:architect"

echo ">> LeadGen cockpit ready. Alt-1..6 = windows | Ctrl-Space d = detach"
if [ -n "$TMUX" ]; then
  tmux switch-client -t "$SESSION"
else
  tmux attach -t "$SESSION"
fi
