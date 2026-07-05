#!/usr/bin/env bash
# SSH-quoting-safe background runner (CLAUDE.md gotcha: & > ssh-cmd me todte)
nohup bash /opt/leadgen/scripts/vps_deploy_selfimprove.sh >/tmp/deploy_si.log 2>&1 &
echo "BG_STARTED $!"
