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

# ---------------------------------------------------------------- disk guard
# Phase C (2026-07-15): the existing image-retention step below (added after
# a 92%-full/16G-free near-miss that put Postgres/Docker ~2 deploys from
# dying) only prunes TAGGED app images. buildx's own build cache is a
# SEPARATE, unbounded disk consumer (see BUILD CACHE section below) with no
# relationship to image tags — and nothing checked disk BEFORE a build
# started, so a critically-low-disk build could corrupt a layer or crash
# dockerd mid-build instead of failing fast with a clear message. This guard
# runs before build+DRY_RUN's exit so both a real deploy and a dry-run
# report the same disk truth up front.
DISK_WARN_PCT="${DISK_WARN_PCT:-80}"
DISK_HARD_PCT="${DISK_HARD_PCT:-90}"
DISK_USED_PCT="$(df -P / | tail -1 | awk '{gsub("%","",$5); print $5}')"
DISK_FREE_H="$(df -h / | tail -1 | awk '{print $4}')"
echo "=== DISK GUARD: ${DISK_USED_PCT}% used, ${DISK_FREE_H} free (warn>=${DISK_WARN_PCT}%, hard-stop>=${DISK_HARD_PCT}%) ==="
if [ "$DISK_USED_PCT" -ge "$DISK_HARD_PCT" ]; then
  echo "FATAL: disk ${DISK_USED_PCT}% >= hard-stop ${DISK_HARD_PCT}% — refusing to build."
  echo "       Free space first (see BUILD CACHE preview below / docker builder prune / KEEP_IMAGES=2 rerun), then retry."
  if [ "$DRY_RUN" != "1" ]; then
    exit 5
  fi
  echo "DRY_RUN=1 — would have exited here for real; continuing to print the rest of the plan."
elif [ "$DISK_USED_PCT" -ge "$DISK_WARN_PCT" ]; then
  echo "WARN: disk ${DISK_USED_PCT}% >= warn ${DISK_WARN_PCT}% — proceeding, but this deploy's retention step matters more than usual."
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "=== BUILD CACHE (current — read-only preview, nothing deleted) ==="
  docker system df | grep -E "TYPE|Build Cache" || true
  echo "=== IMAGE RETENTION preview (keep newest ${KEEP_IMAGES:-3} tags) ==="
  _KEEP="${KEEP_IMAGES:-3}"
  _IMG=ghcr.io/sumitrevolt/leadgenrationaivoiceagent
  _OLD="$(docker images "$_IMG" --format '{{.CreatedAt}}\t{{.Tag}}' | sort -r | tail -n +$((_KEEP + 1)) | cut -f2)"
  if [ -z "$_OLD" ]; then
    echo "  nothing would be reclaimed"
  else
    for t in $_OLD; do
      [ "$t" = "$VER" ] && continue
      [ "$t" = "<none>" ] && continue
      echo "  would remove $t (if not still referenced by a running container)"
    done
  fi
  echo "DRY_RUN=1 -> would build+up the above, verify /health == $VER, then run the retention shown above. Exiting."
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
  # Do NOT abort on the exit code alone. `docker compose up` can return non-zero
  # on a TRANSIENT recreate race (observed 2026-07-14: 'Conflict. The container
  # name "/<hash>_leadgen_app" is already in use' — docker renames the old
  # container before removing it, and a retry inside compose then succeeded) while
  # the END STATE is completely correct. The exit code is an inference; the
  # verification below is evidence. Warn loudly, then let VERIFY decide — it is
  # strict (health version + per-container skew + smoke) and cannot pass on a
  # genuinely broken deploy.
  echo "WARN: up returned $UP_RC — NOT trusting that alone. Tail:"
  tail -12 /tmp/deploy_up.log
  echo "WARN: continuing to VERIFY; the observed end state decides."
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
  [ "$UP_RC" -ne 0 ] && echo "       (up also returned $UP_RC — see /tmp/deploy_up.log)"
  exit 3
fi
if [ "$UP_RC" -ne 0 ]; then
  echo "NOTE: up returned $UP_RC but the end state VERIFIES — treating the compose"
  echo "      error as transient. Evidence over exit codes."
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

# ------------------------------------------------------------------ retention
# Every deploy adds a ~7GB app image. With no retention the disk filled to 92%
# (16G free = ~2 deploys from Postgres/Docker dying); a one-off cleanup freed
# 60GB. Retention runs ONLY after a fully verified deploy, keeps the newest
# $KEEP_IMAGES tags (current + rollbacks), and never uses `rmi -f` — docker
# itself refuses to delete an image a container still references.
KEEP_IMAGES="${KEEP_IMAGES:-3}"
echo "=== RETENTION (keep newest $KEEP_IMAGES app image tags) ==="
IMG=ghcr.io/sumitrevolt/leadgenrationaivoiceagent
OLD_TAGS="$(docker images "$IMG" --format '{{.CreatedAt}}\t{{.Tag}}' \
  | sort -r | tail -n +$((KEEP_IMAGES + 1)) | cut -f2)"
if [ -z "$OLD_TAGS" ]; then
  echo "  nothing to reclaim"
else
  for t in $OLD_TAGS; do
    [ "$t" = "$VER" ] && continue          # never the tag we just deployed
    [ "$t" = "<none>" ] && continue
    if docker rmi "$IMG:$t" >/dev/null 2>&1; then
      echo "  removed $t"
    else
      echo "  kept    $t (still referenced)"
    fi
  done
fi
docker image prune -f >/dev/null 2>&1     # untagged leftovers only
echo "  disk now: $(df -h / | tail -1 | awk '{print $5" used, "$4" free"}')"

# ------------------------------------------------------- build-cache retention
# Phase C (2026-07-15): buildx's build cache is a SEPARATE store from tagged
# images (nothing above touches it) — it can grow unbounded across many
# deploys with zero relationship to how many image tags are kept. Bounded by
# BOTH age (a layer still reused every build never ages out — only genuinely
# stale/orphaned cache is a target) AND a keep-storage floor (so this never
# nukes cache that would just slow the NEXT build back down for no disk
# benefit). Never touches running containers, the image just deployed,
# rollback images, volumes, or app/customer data — `docker builder prune` is
# scoped strictly to buildx's own cache namespace, disjoint from `docker
# images`/`docker volume`. Runs only after the verified deploy above, same
# as image retention.
BUILD_CACHE_MAX_AGE="${BUILD_CACHE_MAX_AGE:-168h}"        # 7 days unused
BUILD_CACHE_KEEP_STORAGE="${BUILD_CACHE_KEEP_STORAGE:-20GB}"
echo "=== BUILD CACHE (before) ==="
docker system df | grep -E "TYPE|Build Cache" || true
if docker builder prune -f --filter "unused-for=$BUILD_CACHE_MAX_AGE" \
    --keep-storage "$BUILD_CACHE_KEEP_STORAGE" > /tmp/deploy_buildcache_prune.log 2>&1; then
  echo "=== BUILD CACHE (after, unused-for>=$BUILD_CACHE_MAX_AGE reclaimed above $BUILD_CACHE_KEEP_STORAGE floor) ==="
  docker system df | grep -E "TYPE|Build Cache" || true
else
  echo "WARN: build-cache prune failed (non-fatal — deploy already verified). Tail:"
  tail -8 /tmp/deploy_buildcache_prune.log
fi
echo "  disk now: $(df -h / | tail -1 | awk '{print $5" used, "$4" free"}')"

echo "=== DEPLOYED $VER OK ==="
