#!/bin/bash
# Idempotent: ensure tmux session "leadgen-omni" + window "gateway" exist and running omniroute.
# Does not touch other windows/panes (coding lanes) in the same session.
NODE_BIN_DIR="${OMNI_NODE_BIN_DIR:-/root/.nvm/versions/node/v22.23.1/bin}"
if [ -d "$NODE_BIN_DIR" ]; then
  export PATH="$NODE_BIN_DIR:$PATH"
fi
OMNI_CMD="export PATH='$NODE_BIN_DIR':\$PATH; export OMNIROUTE_MEMORY_MB=2048; omniroute"
tmux has-session -t leadgen-omni 2>/dev/null
if [ $? -ne 0 ]; then
  tmux new-session -d -s leadgen-omni -n gateway
fi
tmux list-windows -t leadgen-omni -F '#W' | grep -qx gateway
if [ $? -ne 0 ]; then
  tmux new-window -t leadgen-omni -n gateway
fi
tmux send-keys -t leadgen-omni:gateway C-c 2>/dev/null
sleep 1
tmux send-keys -t leadgen-omni:gateway "$OMNI_CMD" Enter
echo 'restart signal sent'
