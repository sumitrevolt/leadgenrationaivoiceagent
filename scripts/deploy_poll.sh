#!/usr/bin/env bash
# deploy_poll.sh — read-only: tail the detached deploy run log
set +e
echo "===RUNNING?==="
pgrep -f deploy_adr095.sh > /dev/null && echo "deploy STILL RUNNING" || echo "deploy process ENDED"
echo "===RUN_LOG==="
tail -32 /tmp/adr095_run.log 2>/dev/null || echo "(no run log)"
echo "===POLL_DONE==="
