#!/usr/bin/env bash
# deploy_vps.sh — THE canonical VPS deploy. Run ON the VPS from /opt/leadgen.
#
# WHY THIS EXISTS (2026-07-14, ADR-097): the deploy runbook was hand-typed, and
# two real production faults came straight out of that:
#   1. APP_VERSION forgotten -> compose falls back to `${APP_VERSION:-latest}` ->
#      prod runs an image whose provenance nobody can establish (/health says
#      "latest"), indistinguishable from running stale code.
#   2. Only `app worker scheduler` recreated -> worker_heavy/worker_video were
#      left on an older `:latest` for DAYS = live version skew across containers
#      that share one image tag.
# The ADR-097 startup guard catches (1) at RUNTIME. This script prevents both at
# DEPLOY time, which is cheaper. Use this instead of typing docker commands.
#
# Usage:  bash scripts/deploy_vps.sh            # deploy current HEAD
#         bash scripts/deploy_vps.sh <git-sha>  # deploy an explicit sha
#         DRY_RUN=1 bash scripts/deploy_vps.sh  # print the plan, change nothing
#
# Landmines encoded here (do not "simplify" them away):
#   - `set -o pipefail`: a piped build (`| tail`) otherwise MASKS a non-zero exit.
#   - build log -> /tmp: verbose build output over the SSH tunnel kills the session.
#   - `worker-heavy`/`worker-video` use HYPHENS as compose service names; a wrong
#     name aborts the whole `up`.
#   - run detached (setsid nohup) from the caller so a dropped tunnel cannot
#     SIGHUP-kill the build mid-flight.
set -uo pipefail

REPO=/opt/leadgen
COMPOSE=docker-compose.vps.yml
# Every service built from the app image. Miss one -> version skew.
SERVICES="app worker scheduler worker-heavy worker-video"
DRY_RUN="${DRY_RUN:-0}"

cd "$REPO" || { echo "FATAL: $REPO not found"; exit 1; }

# ---------------------------------------------------------------- resolve sha
if [ "${1:-}" != "" ]; then
  VER="$1"
else
  git pull --ff-only 2>&1 | tail -2
  VER="$(git rev-parse --short HEAD)"
fi

# Hard refusal: never let the compose `:-latest` fallback decide for us.
case "$(printf '%s' "$VER" | tr '[:upper:]' '[:lower:]')" in
  ""|latest|dev|1.0.0)
    echo "FATAL: refusing to deploy with APP_VERSION='$VER' — that is the"
    echo "       provenance-less tag that caused ADR-097. Pass a real git sha."
    exit 2
    ;;
esac
echo "=== DEPLOY $VER (services: $SERVICES) ==="
echo "REPO_SHA=$(git rev-parse --short HEAD)"

if [ "$DRY_RUN" = "1" ]; then
  echo "DRY_RUN=1 -> would build+up the above and verify /health == $VER. Exiting."
  exit 0
fi

# --------------------------------------------------------------------- build
echo "=== BUILD (log: /tmp/deploy_build.log) ==="
APP_VERSION="$VER" docker compose -f "$COMPOSE" build app > /tmp/deploy_build.log 2>&1
BUILD_RC=$?
echo "BUILD_RC=$BUILD_RC"
if [ "$BUILD_RC" -ne 0 ]; then
  echo "FATAL: build failed — NOTHING restarted (prod untouched). Tail:"
  tail -15 /tmp/deploy_build.log
  exit 1
fi

# ------------------------------------------------------------------------ up
echo "=== UP (all app-image services — prevents skew) ==="
# shellcheck disable=SC2086
APP_VERSION="$VER" docker compose -f "$COMPOSE" --profile celery \
  up -d --no-deps $SERVICES > /tmp/deploy_up.log 2>&1
UP_RC=$?
echo "UP_RC=$UP_RC"
if [ "$UP_RC" -ne 0 ]; then
  echo "FATAL: up failed. Tail:"; tail -15 /tmp/deploy_up.log; exit 1
fi

sleep 22

# -------------------------------------------------------------------- verify
echo "=== VERIFY /health (host port 8000; in-network the app listens on 8080) ==="
HEALTH="$(curl -s -m 10 127.0.0.1:8000/health)"
echo "$HEALTH"
LIVE_VER="$(printf '%s' "$HEALTH" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p')"
if [ "$LIVE_VER" != "$VER" ]; then
  echo "FATAL: /health version='$LIVE_VER' != deployed '$VER' — prod did NOT pick"
  echo "       up this build. Do NOT report this deploy as successful."
  exit 3
fi

echo "=== SKEW CHECK — every container must report the same sha ==="
SKEW=0
for c in leadgen_app leadgen_worker leadgen_scheduler leadgen_worker_heavy leadgen_worker_video; do
  cv="$(docker exec "$c" printenv APP_VERSION 2>/dev/null)"
  printf '%-24s APP_VERSION=%s\n' "$c" "${cv:-<unset>}"
  [ "$cv" = "$VER" ] || SKEW=1
done
if [ "$SKEW" -ne 0 ]; then
  echo "FATAL: version skew — at least one container is not on $VER."
  exit 4
fi

echo "=== SMOKE (revenue + auth critical paths) ==="
for p in /health /api/voice/niches /api/billing/plans /api/public/pay-info; do
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 15 "https://leadsgenai.in$p")"
  printf '%-24s -> %s\n' "$p" "$code"
  [ "$code" = "200" ] || echo "   WARN: expected 200"
done

echo "=== QUEUES / DLQ ==="
docker exec leadgen_redis redis-cli llen celery
docker exec leadgen_redis redis-cli llen dlq:failed_tasks

echo "=== DEPLOYED $VER OK ==="
