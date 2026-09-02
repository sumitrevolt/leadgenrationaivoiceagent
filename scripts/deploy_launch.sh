#!/usr/bin/env bash
# deploy_launch.sh — start deploy_adr095.sh DETACHED so a dropped SSH tunnel
# (known flaky link) cannot SIGHUP-kill the docker build mid-flight.
set +e
sed -i 's/\r$//' /tmp/deploy_adr095.sh 2>/dev/null
chmod +x /tmp/deploy_adr095.sh
rm -f /tmp/adr095_run.log /tmp/adr095_up.log
setsid nohup bash /tmp/deploy_adr095.sh > /tmp/adr095_run.log 2>&1 < /dev/null &
echo "DETACHED_PID=$!"
sleep 2
echo "LAUNCHED - poll /tmp/adr095_run.log"
