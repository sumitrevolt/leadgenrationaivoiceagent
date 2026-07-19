#!/bin/bash
set -e
D=/usr/bin/docker
echo "=== CONTAINERS ==="
$D ps --format '{{.Names}} {{.Image}}' | grep leadgen | sort
echo "=== OMNIROUTE ==="
$D cp /tmp/_canary_omni_check.py leadgen_app:/tmp/_canary_omni_check.py
$D exec leadgen_app python /tmp/_canary_omni_check.py
echo "=== STRAY voice_agent ==="
$D ps --format '{{.Names}}' | grep voice_agent || echo none
echo DONE
