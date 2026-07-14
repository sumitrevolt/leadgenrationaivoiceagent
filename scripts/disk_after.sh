#!/usr/bin/env bash
set +e
echo "===DISK NOW==="
df -h / | tail -1
echo "===DOCKER DF==="
docker system df
echo "===APP IMAGE TAGS REMAINING==="
docker images ghcr.io/sumitrevolt/leadgenrationaivoiceagent --format '{{.Tag}}|{{.Size}}|{{.CreatedSince}}'
echo "===HEALTH==="
curl -s -m 10 127.0.0.1:8000/health; echo
echo "===CONTAINERS==="
docker ps --filter name=leadgen_app --filter name=leadgen_worker --filter name=leadgen_scheduler --format '{{.Names}}|{{.Status}}'
echo "===AFTER_DONE==="
