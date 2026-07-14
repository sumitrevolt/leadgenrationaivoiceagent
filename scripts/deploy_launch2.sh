#!/usr/bin/env bash
# deploy_launch2.sh — start deploy_adr096.sh detached (survives SSH tunnel drop)
set +e
sed -i 's/\r$//' /tmp/deploy_adr096.sh 2>/dev/null
chmod +x /tmp/deploy_adr096.sh
rm -f /tmp/adr096_run.log
setsid nohup bash /tmp/deploy_adr096.sh > /tmp/adr096_run.log 2>&1 < /dev/null &
echo "DETACHED_PID=$!"
sleep 2
echo "LAUNCHED - poll /tmp/adr096_run.log"
