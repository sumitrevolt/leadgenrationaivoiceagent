#!/usr/bin/env bash
set +e
pgrep -f deploy_all.sh > /dev/null && echo "STILL RUNNING" || echo "ENDED"
echo "===RUN LOG==="
tail -36 /tmp/all_run.log 2>/dev/null || echo "(none)"
echo "===POLL_ALL_DONE==="
