#!/usr/bin/env bash
set +e
echo "===SWEEP WATCH LOG==="
cat /tmp/sweep_watch.log 2>/dev/null || echo "(no watch log)"
echo "===NOW==="
date -u +%H:%M:%S
echo "===READ_WATCH_DONE==="
