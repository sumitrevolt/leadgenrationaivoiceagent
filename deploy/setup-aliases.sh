#!/bin/bash
set -euo pipefail

# Install tmux config
cp /opt/leadgen/tmux.conf /root/.tmux.conf

# Add bash_aliases
cat > /root/.bash_aliases << 'EOF'
# ── LeadGen AI docker-ops aliases ──
alias lga='tmux attach -t leadgen || tmux new -s leadgen'
alias lgdc='cd /opt/leadgen && docker compose -f docker-compose.vps.yml'
alias lglog='lgdc logs -f --tail=100'
alias lgapp='lglog app'
alias lgwork='lglog worker worker-heavy'
alias lgsched='lglog scheduler'
alias lgrestart='lgdc restart'
alias lgstat='lgdc ps'
alias lgdisk='df -h / && free -m'
alias lgdocker='docker stats --no-stream'
alias lghealth='curl -sS localhost:8000/health'
alias lgredeploy='cd /opt/leadgen && git pull && lgdc up -d --no-deps app && sleep 16 && curl -sSf localhost:8000/health'
EOF

grep -q 'bash_aliases' /root/.bashrc 2>/dev/null || echo '[ -f ~/.bash_aliases ] && . ~/.bash_aliases' >> /root/.bashrc

# Auto-attach to tmux on SSH (unless already in tmux or SSH-ing a command)
grep -q 'tmux attach' /root/.bashrc 2>/dev/null || cat >> /root/.bashrc << 'EOF'

# Auto-attach tmux on SSH login
if [ -z "$TMUX" ] && [ "$SSH_TTY" != "" ] && [ "$TERM" != "dumb" ]; then
  tmux attach -t leadgen 2>/dev/null || tmux new -s leadgen
fi
EOF

echo "✅ .tmux.conf + aliases + auto-attach configured"
