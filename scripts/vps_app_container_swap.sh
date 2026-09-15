#!/usr/bin/env bash
# =============================================================================
# RETIRED 2026-09-15 -- DO NOT RUN. This script reversed the serving topology.
#
# It used to: `systemctl stop leadgen` -> `docker compose up -d app` ->
# `systemctl disable leadgen`. That is the OPPOSITE of the owner decision of
# 2026-09-15: the systemd unit `leadgen` IS the authoritative server for
# 127.0.0.1:8000, with EnvironmentFile=/opt/leadgen/.env.
#
# Why running it is actively harmful:
#   * `systemctl disable leadgen` stops the unit coming back after a reboot, so
#     a crash or reboot silently drops production onto a container that
#     docker-compose.vps.yml publishes as 127.0.0.1:8000:8080 -- the very port
#     the unit owns. Whichever side loses the race, :8000 ends up serving an
#     image whose tag nobody pinned.
#   * scripts/deploy_vps.sh now uses `systemctl restart leadgen` as its app
#     rollout step. With the unit disabled and the port held by a container,
#     that restart fails, so every later deploy exits 10.
#
# The app is NOT a container. Use the canonical release path instead:
#     bash scripts/deploy_vps.sh
# =============================================================================
set -uo pipefail
echo "REFUSED: scripts/vps_app_container_swap.sh is RETIRED (2026-09-15)." >&2
echo "" >&2
echo "It would flip production from the authoritative systemd unit 'leadgen'" >&2
echo "back onto a Docker container on the same 127.0.0.1:8000, and would run" >&2
echo "'systemctl disable leadgen', which breaks every later deploy." >&2
echo "" >&2
echo "Use the canonical release path:  bash scripts/deploy_vps.sh" >&2
exit 1
