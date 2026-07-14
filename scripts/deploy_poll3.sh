#!/usr/bin/env bash
set +e
echo "===RUNNING?==="
pgrep -f deploy_adr096.sh > /dev/null && echo "STILL RUNNING" || echo "ENDED"
echo "===BUILD_LOG_TAIL==="
tail -6 /tmp/adr096_build.log 2>/dev/null || echo "(no build log)"
echo "===RUN_LOG_TAIL==="
tail -22 /tmp/adr096_run.log 2>/dev/null
echo "===HEALTH==="
curl -s -m 10 127.0.0.1:8000/health; echo
echo "===POLL3_DONE==="
