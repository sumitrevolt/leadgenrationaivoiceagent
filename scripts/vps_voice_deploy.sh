#!/bin/bash
set -e
docker cp /tmp/voice_deploy/web_call.py leadgen_app:/app/app/api/web_call.py
docker cp /tmp/voice_deploy/telecaller_brain.py leadgen_app:/app/app/voice_agent/telecaller_brain.py
docker cp /tmp/voice_deploy/platform_pitch.py leadgen_app:/app/app/voice_agent/platform_pitch.py
docker cp /tmp/voice_deploy/web_call_tune_loop.py leadgen_app:/app/scripts/web_call_tune_loop.py
cd /opt/leadgen
docker compose -f docker-compose.vps.yml restart app
sleep 16
curl -sf http://127.0.0.1:8000/health | head -c 200
echo
