#!/usr/bin/env bash
set +e
pgrep -f deploy_adr097.sh > /dev/null && echo "STILL RUNNING" || echo "ENDED"
echo "===RUN LOG==="
tail -34 /tmp/adr097_run.log 2>/dev/null || echo "(none)"
echo "===POLL097_DONE==="
