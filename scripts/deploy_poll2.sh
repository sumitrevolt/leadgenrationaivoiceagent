#!/usr/bin/env bash
set +e
echo "===RUNNING?==="
pgrep -f deploy_adr096.sh > /dev/null && echo "STILL RUNNING" || echo "ENDED"
echo "===RUN_LOG==="
tail -26 /tmp/adr096_run.log 2>/dev/null || echo "(none)"
echo "===POLL2_DONE==="
