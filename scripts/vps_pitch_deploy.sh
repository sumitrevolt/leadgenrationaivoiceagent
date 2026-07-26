#!/bin/bash
set -e
cd /opt/leadgen
# GUARD FIRST — see _runtime_data_guard.sh. `reset --hard` destroys live state.
. "$(dirname "$0")/_runtime_data_guard.sh"
git fetch --all -q
git reset --hard origin/main -q
echo "COMMIT: $(git log --oneline -1)"
docker compose -f docker-compose.vps.yml build app
docker compose -f docker-compose.vps.yml up -d --no-deps app
sleep 18
curl -sf http://127.0.0.1:8000/health
echo
docker exec leadgen_app python -c "from app.voice_agent.universal_pitch import UNIVERSAL_AGENT_INTRO; print(UNIVERSAL_AGENT_INTRO)"
