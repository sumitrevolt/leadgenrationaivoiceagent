#!/usr/bin/env bash
set +e
pgrep -f deploy_vps.sh > /dev/null && echo "STILL RUNNING" || echo "ENDED"
echo "===/tmp/dep.log==="
tail -40 /tmp/dep.log 2>/dev/null || echo "(none)"
echo "===POLL_DEP_DONE==="
