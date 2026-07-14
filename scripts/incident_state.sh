#!/usr/bin/env bash
# incident_state.sh — READ-ONLY: what is actually live after the failed `up`?
set +e
echo "===IS THE SITE UP? (public)==="
curl -s -o /dev/null -w 'https://leadsgenai.in/health -> %{http_code}\n' -m 15 https://leadsgenai.in/health
echo "===LOCAL HEALTH==="
curl -s -m 10 127.0.0.1:8000/health; echo
echo "===ALL leadgen_app* CONTAINERS (incl. stopped/renamed leftovers)==="
docker ps -a --filter 'name=leadgen_app' --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'
echo "===CORE CONTAINERS==="
docker ps -a --filter 'name=leadgen_worker' --filter 'name=leadgen_scheduler' --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'
echo "===CONFLICTING NAME==="
docker ps -a --format '{{.ID}}|{{.Names}}|{{.Status}}' | grep -i '0b2ef7814c97\|4199b3ecc7fc' || echo "(not found by that name)"
echo "===INCIDENT_STATE_DONE==="
