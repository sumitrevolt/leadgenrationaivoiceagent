#!/bin/bash
# Diagnose DSH worker crash loop
echo "=== restart count + last exit ==="
docker inspect leadgen_dsh_worker --format 'RestartCount={{.RestartCount}} State={{.State.Status}} OOM={{.State.OOMKilled}} ExitCode={{.State.ExitCode}}' 2>&1
echo "=== last 40 log lines ==="
docker logs leadgen_dsh_worker --tail 40 2>&1
echo "=== config flags ==="
docker exec leadgen_app python -c '
import os
for v in ["DSH_RUNTIME_ENABLED","DSH_SHADOW_ENABLED","DSH_ALLOWED_CLUSTERS"]:
    print(v, "=", os.getenv(v, "(unset)"))
' 2>&1
echo "DONE"
