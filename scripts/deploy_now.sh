#!/usr/bin/env bash
# =============================================================================
# RETIRED 2026-09-15 -- DO NOT RUN. Superseded by the canonical release parent.
#
# It used to `docker compose build app` + `up -d --no-deps app`, then curl
# 127.0.0.1:8000/health. Under the current topology (the systemd unit `leadgen`
# owns :8000) that container can never bind the port, so the recreate fails
# while the old process keeps serving -- and the health check still returned
# 200. That is a FALSE SUCCESS: it claimed a deploy had happened when nothing
# had. It also never pinned APP_VERSION, so even in container mode it could
# have shipped a :latest image instead of an immutable SHA.
#
# Use the canonical release path instead:
#     bash scripts/deploy_vps.sh
# =============================================================================
set -uo pipefail
echo "REFUSED: scripts/deploy_now.sh is RETIRED (2026-09-15)." >&2
echo "" >&2
echo "It rebuilt an 'app' container that cannot bind :8000 (the systemd unit" >&2
echo "'leadgen' holds it), then reported HEALTH OK off the OLD process." >&2
echo "" >&2
echo "Use the canonical release path:  bash scripts/deploy_vps.sh" >&2
exit 1
