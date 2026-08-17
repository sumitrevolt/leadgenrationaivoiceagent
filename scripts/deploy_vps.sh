#!/usr/bin/env bash
# deploy_vps.sh — THE canonical VPS deploy. Run ON the VPS from /opt/leadgen.
#
# WHY THIS EXISTS (2026-07-14, ADR-097): the deploy runbook was hand-typed, and
# two real production faults came straight out of that:
#   1. APP_VERSION forgotten -> prod ran an image whose provenance nobody could
#      establish. Compose now fails closed when APP_VERSION is absent.
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
# Every service runs the same app image. Only `app` builds it; miss one during
# recreation and version skew can still occur. DSH worker is a separately built
# hardened image but shares APP_VERSION provenance and must deploy in lockstep.
SERVICES="app worker scheduler worker-heavy worker-video"
DSH_SERVICES="dsh-worker"
ALL_ROLLOUT_SERVICES="$SERVICES $DSH_SERVICES"
DRY_RUN="${DRY_RUN:-0}"

cd "$REPO" || { echo "FATAL: $REPO not found"; exit 1; }

# ---------------------------------------------------- runtime-data guard
# CANONICAL NORMAL-RELEASE PARENT. This is the protected entry point for
# ordinary production releases; recovery, database-restore, bootstrap and
# config-preparation keep their own parents because their semantics differ.
#
# Must precede the `git pull` below and every Compose rollout further down:
# live invoices, consent, suppression, customer identity and 182 MB of DPDP
# call recordings still live inside this checkout, so a release that moves
# HEAD can carry tracked data files over them.
#
# The `|| exit 91` is load-bearing and is NOT a stylistic flourish. This script
# runs under `set -uo pipefail` with NO `-e`, so a FAILED `.` source does not
# abort it: if _runtime_data_guard.sh were renamed, deleted, or unreadable, the
# shell would print "No such file or directory", carry on, and reach the
# `git pull` below completely unguarded. A behavioural harness caught exactly
# that (tests/test_deploy_parent_behaviour.py) — the textual "guard line comes
# before git pull" test could not, because the line WAS there and still failed
# open. 91 = guard unavailable, distinct from 90 = guard ran and denied.
_script_dir="$(cd "$(dirname "$0")" && pwd)"
for _dep in _deploy_gate_container.sh _deploy_candidate.sh _runtime_data_guard.sh; do
  if [ ! -r "$_script_dir/$_dep" ]; then
    echo "FATAL: release helper not found or unreadable at: $_script_dir/$_dep"
    echo "       Refusing to deploy unguarded. Restore it, do not remove the call."
    exit 91
  fi
done
# shellcheck source=scripts/_deploy_gate_container.sh
. "$_script_dir/_deploy_gate_container.sh" || exit 91
# shellcheck source=scripts/_deploy_candidate.sh
. "$_script_dir/_deploy_candidate.sh" || exit 91

# ------------------------------------------------- isolated candidate release
# The live checkout is NOT touched until both gates have passed. `git fetch`
# updates the object database only; the release sha is then materialised in its
# own detached worktree, away from the production ledgers that still live in
# /opt/leadgen/data. This is what lets the runtime-data guard keep its original
# contract — it runs BEFORE the first destructive command on the live checkout —
# while the gates still read the code that is actually about to ship.
candidate_fetch "$REPO" || exit 2

if [ "${1:-}" != "" ]; then
  CANDIDATE_REF="$1"
else
  CANDIDATE_REF="origin/main"
fi
CANDIDATE_SHA="$(candidate_resolve "$REPO" "$CANDIDATE_REF")" || exit 2
VER="$(git -C "$REPO" rev-parse --short "$CANDIDATE_SHA")"

# Hard refusal: never allow a mutable/provenance-less version.
case "$(printf '%s' "$VER" | tr '[:upper:]' '[:lower:]')" in
  ""|latest|dev|1.0.0)
    echo "FATAL: refusing to deploy with APP_VERSION='$VER' — that is the"
    echo "       provenance-less tag that caused ADR-097. Pass a real git sha."
    exit 2
    ;;
esac

echo "=== CANDIDATE $VER ($CANDIDATE_SHA) from $CANDIDATE_REF ==="
CANDIDATE_DIR="$(candidate_add "$REPO" "$CANDIDATE_SHA")" || exit 2
echo "CANDIDATE_DIR=$CANDIDATE_DIR"
echo "LIVE_SHA=$(git -C "$REPO" rev-parse --short HEAD) (unchanged until both gates pass)"

# ------------------------------------------------------- runtime-data guard
# Same decision, same blockers, same exit 90 — executed in the pinned image
# because the host cannot import the application. The guard reads the CANDIDATE
# source and the LIVE data (mounted read-only): a candidate's own empty `data/`
# would report a clean system that does not exist.
RUNTIME_DATA_GATE_CANDIDATE="$CANDIDATE_DIR"
RUNTIME_DATA_GATE_REPO="$REPO"
export RUNTIME_DATA_GATE_CANDIDATE RUNTIME_DATA_GATE_REPO
# shellcheck source=scripts/_runtime_data_guard.sh
. "$_script_dir/_runtime_data_guard.sh" || exit 91

# Proof that the calling-safety environment reaches the gate container at all.
# Booleans only — the token itself is never printed. Without this, a missing
# `.env` injection would surface as "VOICE_LAUNCH_KILL: UNSET" and get "fixed"
# by exporting it in the operator's shell, proving nothing about production.
echo "=== gate environment proof (booleans only, no values) ==="
gate_kill_env_proof "$CANDIDATE_DIR" "$REPO" || {
  echo "FATAL: could not prove the gate container environment. Refusing to deploy."
  exit 92
}

# ---------------------------------------------------------------- resolve sha
# 2026-07-16 hardening: pull-fail + SHA/HEAD mismatch used to silently rebuild
# whatever dirty tree was on disk while claiming a different APP_VERSION in the
# log header (dep3 incident). The sha is now resolved BEFORE anything runs, from
# the fetched object database, and the candidate worktree has already proven it
# is at exactly that commit — so there is no window in which the tag and the
# tree can disagree.
echo "=== DEPLOY $VER (services: $ALL_ROLLOUT_SERVICES) ==="
echo "CANDIDATE_SHA=$CANDIDATE_SHA"
if [ "$(git -C "$CANDIDATE_DIR" rev-parse HEAD)" != "$CANDIDATE_SHA" ]; then
  echo "FATAL: candidate tree drifted from $CANDIDATE_SHA — aborting before build."
  exit 2
fi

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
  echo "=== IMAGE RETENTION preview (lineage-aware; KEEP_IMAGES=${KEEP_IMAGES:-1}) ==="
  echo "  would protect: newly deployed tag + durable rollback (/var/lib/leadgen lineage state)"
  echo "  would refuse retention cleanup on skewed/missing/malformed tags or missing artifacts"
  echo "  same-SHA without durable present rollback = zero destructive cleanup"
  echo "  CreatedAt-newest alone cannot displace the lineage rollback tag"
  _KEEP="${KEEP_IMAGES:-1}"
  _IMG=ghcr.io/sumitrevolt/leadgenrationaivoiceagent
  echo "  planner keep_images=$_KEEP (floor expands to protected lineage size)"
  docker images "$_IMG" --format '  present {{.Tag}} created={{.CreatedAt}}' | head -20 || true
  echo "DRY_RUN=1 -> would build+up the above, verify /health == $VER, then run lineage retention. Exiting."
  exit 0
fi

# ----------------------------------------------------- build candidate image
# Built from the CANDIDATE worktree, tagged with the exact release sha. A build
# creates an image; it replaces no container and moves no HEAD, so production is
# still untouched at this point and a build failure costs nothing.
echo "=== BUILD candidate $VER (log: /tmp/deploy_build.log) ==="
: > /tmp/deploy_build.log
DSH_RUNTIME_IMAGE="${DSH_RUNTIME_IMAGE:-leadgen-dsh:47f94385}"
echo "=== BUILD hardened DSH runtime base $DSH_RUNTIME_IMAGE ===" >> /tmp/deploy_build.log
APP_VERSION="$VER" docker build \
  --file "$CANDIDATE_DIR/deploy/dsh/Dockerfile" \
  --tag "$DSH_RUNTIME_IMAGE" \
  "$CANDIDATE_DIR" >> /tmp/deploy_build.log 2>&1
DSH_BASE_BUILD_RC=$?
echo "DSH_BASE_BUILD_RC=$DSH_BASE_BUILD_RC" >> /tmp/deploy_build.log
if [ "$DSH_BASE_BUILD_RC" -ne 0 ]; then
  BUILD_RC="$DSH_BASE_BUILD_RC"
else
  APP_VERSION="$VER" DSH_RUNTIME_IMAGE="$DSH_RUNTIME_IMAGE" docker compose \
    --project-directory "$CANDIDATE_DIR" \
    -f "$CANDIDATE_DIR/$COMPOSE" \
    --profile dsh \
    build app $DSH_SERVICES >> /tmp/deploy_build.log 2>&1
  BUILD_RC=$?
fi
echo "BUILD_RC=$BUILD_RC"
if [ "$BUILD_RC" -ne 0 ]; then
  echo "FATAL: candidate build failed — NOTHING restarted, live checkout NOT moved. Tail:"
  tail -15 /tmp/deploy_build.log
  exit 1
fi

CANDIDATE_IMAGE="ghcr.io/sumitrevolt/leadgenrationaivoiceagent:$VER"
if ! docker image inspect "$CANDIDATE_IMAGE" >/dev/null 2>&1; then
  echo "FATAL: build reported success but $CANDIDATE_IMAGE does not exist."
  echo "       Refusing to continue on an image that cannot be proven."
  exit 1
fi

# ------------------------------------------------- canonical deployment gate
# Runs in the CANDIDATE image, so the dependencies, the code and the classifier
# are the ones about to serve traffic. One authority: the same checker CI runs,
# plus the deploy-only gates. A private voice-kill check in this script would be
# a second authority and a bypass waiting to happen, so the classification stays
# in prod_check.py. VOICE_LAUNCH_KILL is read there from the environment; it is
# never echoed.
echo "=== deployment gate: prod_check.py --deployment (candidate image) ==="
if ! gate_run_image "$CANDIDATE_IMAGE" "$CANDIDATE_DIR" "$REPO" scripts/prod_check.py --deployment; then
  echo "FATAL: deployment gate failed — refusing to deploy."
  echo "       The live checkout has NOT moved and no container was replaced."
  exit 1
fi

# ------------------------------------------------ live checkout, ff-only only
# Both gates have now passed against this exact sha. Only here does the live
# checkout — the one holding the production ledgers — move, and only forwards.
echo "=== live checkout: git pull --ff-only ==="
# Plain `git pull` on purpose: cwd is already $REPO, and the guard-ordering
# suite matches this exact destructive literal to prove the guard precedes it.
# A `-C "$REPO"` form would hide the release's one destructive command from the
# check whose entire job is to find it.
if ! git pull --ff-only; then
  echo "FATAL: git pull --ff-only failed — refusing to deploy stale/dirty HEAD."
  echo "       Resolve the pull (backup live data/*, no reset --hard), then retry."
  echo "       No container has been replaced."
  exit 2
fi
LIVE_SHA="$(git -C "$REPO" rev-parse HEAD)"
if [ "$LIVE_SHA" != "$CANDIDATE_SHA" ]; then
  echo "FATAL: live checkout is at $LIVE_SHA but the gated release is $CANDIDATE_SHA."
  echo "       Refusing to start containers on code that was never gated."
  exit 2
fi
echo "LIVE_SHA=$(git -C "$REPO" rev-parse --short HEAD) (gated)"

# ------------------------------------------------------------------------ up
echo "=== UP (all app-image services — prevents skew) ==="

# Compose recreate race (2026-07-16 prod-down): docker renames the old container
# to <hash>_leadgen_* before removing it; if the next step fails, canonical
# names stay Exited and ghosts stay Created → /health 000. Bounded cleanup+retry.

# Resolve app-image containers by COMPOSE SERVICE name (not bare container_name).
# Project-prefixed / hashed compose names used to false-FATAL the skew check when
# hardcoding leadgen_app etc. even though /health SHA + image tags matched.
_legacy_name_for_service() {
  case "$1" in
    app) echo leadgen_app ;;
    worker) echo leadgen_worker ;;
    scheduler) echo leadgen_scheduler ;;
    worker-heavy) echo leadgen_worker_heavy ;;
    worker-video) echo leadgen_worker_video ;;
    dsh-worker) echo leadgen_dsh_worker ;;
    *) echo "" ;;
  esac
}

# Prints a container id/name for a compose service; returns 1 if unresolved.
# Order: compose ps -> com.docker.compose.service label (+ optional image :$VER)
#      -> legacy container_name from docker-compose.vps.yml.
_resolve_compose_container() {
  local svc="$1"
  local cid=""
  local legacy=""
  local id=""
  local img=""

  # 1) docker compose ps (honors project name / this COMPOSE file)
  cid="$(docker compose -f "$COMPOSE" --profile celery --profile dsh ps -q "$svc" 2>/dev/null | awk 'NF { print; exit }')"
  if [ -n "$cid" ]; then
    printf '%s\n' "$cid"
    return 0
  fi

  # 2) Compose service label (project-prefixed names still carry this label)
  while IFS= read -r id; do
    [ -z "$id" ] && continue
    if [ -n "${VER:-}" ]; then
      img="$(docker inspect -f '{{.Config.Image}}' "$id" 2>/dev/null || true)"
      case "$img" in
        *:"$VER")
          printf '%s\n' "$id"
          return 0
          ;;
      esac
    fi
    printf '%s\n' "$id"
    return 0
  done <<EOF
$(docker ps -aq --filter "label=com.docker.compose.service=${svc}" 2>/dev/null)
EOF

  # 3) Legacy bare container_name (compose file still sets these on prod today)
  legacy="$(_legacy_name_for_service "$svc")"
  if [ -n "$legacy" ] && docker inspect "$legacy" >/dev/null 2>&1; then
    printf '%s\n' "$legacy"
    return 0
  fi

  return 1
}

_compose_up() {
  # shellcheck disable=SC2086
  APP_VERSION="$VER" docker compose -f "$COMPOSE" --profile celery --profile dsh \
    up -d --no-deps $ALL_ROLLOUT_SERVICES
}

_cleanup_recreate_ghosts() {
  echo "=== UP CLEANUP: remove Created *_leadgen_* ghosts + exited app-image containers ==="
  docker ps -a --format '{{.Names}} {{.Status}}' | while read -r _name _status; do
    case "$_name" in *_leadgen_*)
      if echo "$_status" | grep -qiE 'created|dead'; then
        echo "  rm ghost $_name ($_status)"
        docker rm -f "$_name" 2>/dev/null || true
      fi
      ;;
    esac
  done
  # Resolve via compose service names (same as skew check) — bare leadgen_* alone
  # misses project-prefixed containers after a failed recreate.
  for _svc in $ALL_ROLLOUT_SERVICES; do
    _c="$(_resolve_compose_container "$_svc" || true)"
    [ -z "$_c" ] && _c="$(_legacy_name_for_service "$_svc")"
    [ -z "$_c" ] && continue
    _st="$(docker inspect -f '{{.State.Status}}' "$_c" 2>/dev/null || echo missing)"
    if [ "$_st" = "exited" ] || [ "$_st" = "created" ] || [ "$_st" = "dead" ]; then
      echo "  rm stale $_svc ($_c status=$_st)"
      docker rm -f "$_c" 2>/dev/null || true
    fi
  done
}

# Capture consistent running production tag BEFORE replace (lineage retention).
# Durable state survives same-SHA redeploy (PREV==VER); CreatedAt is never lineage.
PREV_PROD_TAG=""
RUNNING_JSON=""
ROLLBACK_TAG=""
LINEAGE_STATE="${LINEAGE_STATE:-/var/lib/leadgen/deploy_rollback_lineage.json}"
echo "=== PRE-DEPLOY production tag capture (lineage) ==="
echo "LINEAGE_STATE=$LINEAGE_STATE"
_running_pairs=""
for _svc in $SERVICES; do
  _c="$(_resolve_compose_container "$_svc")" || {
    echo "FATAL: cannot resolve running service '$_svc' before UP — refusing deploy."
    exit 2
  }
  _img="$(docker inspect -f '{{.Config.Image}}' "$_c" 2>/dev/null || true)"
  _tag="${_img##*:}"
  if [ -z "$_tag" ] || [ "$_tag" = "$_img" ]; then
    echo "FATAL: service '$_svc' has unparseable image '$_img' — refusing deploy."
    exit 2
  fi
  echo "  pre-deploy $_svc -> $_tag"
  _running_pairs="${_running_pairs}${_svc}=${_tag}"$'\n'
done
RUNNING_JSON="$(printf '%s' "$_running_pairs" | python3 -c '
import json, sys
out = {}
for line in sys.stdin:
    line = line.strip()
    if not line or "=" not in line:
        continue
    k, v = line.split("=", 1)
    out[k] = v
print(json.dumps(out, sort_keys=True))
')"
PREV_PROD_TAG="$(python3 "$_script_dir/deploy_image_retention.py" \
  --assert-running-only \
  --running-json "$RUNNING_JSON")" || {
  echo "FATAL: inconsistent/missing/malformed pre-deploy app-image tags — refusing deploy."
  echo "       RUNNING_JSON=$RUNNING_JSON"
  exit 2
}
echo "PREV_PROD_TAG=$PREV_PROD_TAG"
echo "RUNNING_JSON=$RUNNING_JSON"

_compose_up > /tmp/deploy_up.log 2>&1
UP_RC=$?
echo "UP_RC=$UP_RC"
if [ "$UP_RC" -ne 0 ]; then
  echo "WARN: up returned $UP_RC — NOT trusting that alone. Tail:"
  tail -12 /tmp/deploy_up.log
  if grep -qiE 'Conflict|already in use|Error while Stopping' /tmp/deploy_up.log; then
    echo "WARN: compose recreate conflict detected — bounded cleanup + one retry"
    _cleanup_recreate_ghosts
    _compose_up >> /tmp/deploy_up.log 2>&1
    UP_RC=$?
    echo "UP_RETRY_RC=$UP_RC"
    if [ "$UP_RC" -ne 0 ]; then
      echo "WARN: up retry returned $UP_RC. Tail:"
      tail -12 /tmp/deploy_up.log
    fi
  fi
  echo "WARN: continuing to VERIFY; the observed end state decides."
fi

sleep 22

# -------------------------------------------------------------------- verify
echo "=== VERIFY /health (host port 8000; in-network the app listens on 8080) ==="
HEALTH_MAX_ATTEMPTS="${HEALTH_MAX_ATTEMPTS:-12}"
HEALTH_RETRY_SECONDS="${HEALTH_RETRY_SECONDS:-5}"
case "$HEALTH_MAX_ATTEMPTS" in
  ''|*[!0-9]*) HEALTH_MAX_ATTEMPTS=12 ;;
esac
case "$HEALTH_RETRY_SECONDS" in
  ''|*[!0-9]*) HEALTH_RETRY_SECONDS=5 ;;
esac
# Keep operator overrides bounded: enough for a slow model/import cold start,
# never an unbounded deploy hang.
[ "$HEALTH_MAX_ATTEMPTS" -lt 1 ] && HEALTH_MAX_ATTEMPTS=1
[ "$HEALTH_MAX_ATTEMPTS" -gt 24 ] && HEALTH_MAX_ATTEMPTS=24
[ "$HEALTH_RETRY_SECONDS" -gt 15 ] && HEALTH_RETRY_SECONDS=15

HEALTH=""
LIVE_VER=""
HEALTH_ATTEMPT=1
while [ "$HEALTH_ATTEMPT" -le "$HEALTH_MAX_ATTEMPTS" ]; do
  HEALTH="$(curl -s -m 10 127.0.0.1:8000/health || true)"
  LIVE_VER="$(printf '%s' "$HEALTH" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p')"
  printf '  attempt %s/%s: version=%s\n' \
    "$HEALTH_ATTEMPT" "$HEALTH_MAX_ATTEMPTS" "${LIVE_VER:-<not-ready>}"
  if [ "$LIVE_VER" = "$VER" ]; then
    break
  fi
  [ "$HEALTH_ATTEMPT" -lt "$HEALTH_MAX_ATTEMPTS" ] && sleep "$HEALTH_RETRY_SECONDS"
  HEALTH_ATTEMPT=$((HEALTH_ATTEMPT + 1))
done
echo "$HEALTH"
if [ "$LIVE_VER" != "$VER" ]; then
  echo "FATAL: /health did not report $VER after $HEALTH_MAX_ATTEMPTS attempts."
  echo "FATAL: /health version='$LIVE_VER' != deployed '$VER' — prod did NOT pick"
  echo "       up this build. Do NOT report this deploy as successful."
  [ "$UP_RC" -ne 0 ] && echo "       (up also returned $UP_RC — see /tmp/deploy_up.log)"
  exit 3
fi
if [ "$UP_RC" -ne 0 ]; then
  echo "NOTE: up returned $UP_RC but the end state VERIFIES — treating the compose"
  echo "      error as transient. Evidence over exit codes."
fi

echo "=== SKEW CHECK — every app-image service must report the same sha ==="
SKEW=0
for svc in $ALL_ROLLOUT_SERVICES; do
  c="$(_resolve_compose_container "$svc" || true)"
  if [ -z "$c" ]; then
    printf '%-16s resolve=MISSING APP_VERSION=<missing>\n' "$svc"
    SKEW=1
    continue
  fi
  cv="$(docker exec "$c" printenv APP_VERSION 2>/dev/null)"
  img="$(docker inspect -f '{{.Config.Image}}' "$c" 2>/dev/null || true)"
  printf '%-16s container=%s APP_VERSION=%s image=%s\n' \
    "$svc" "$c" "${cv:-<unset>}" "${img:-?}"
  if [ "$cv" != "$VER" ]; then
    SKEW=1
  fi
  # Fail-closed on image tag skew too (Config.Image must end with :$VER when set)
  case "$img" in
    *:"$VER"|'') ;;
    *)
      echo "  WARN: image tag for $svc does not end with :$VER (image=$img)"
      SKEW=1
      ;;
  esac
done
if [ "$SKEW" -ne 0 ]; then
  echo "FATAL: version skew — at least one app-image service is not on $VER."
  exit 4
fi

echo "=== SMOKE (revenue + auth critical paths) ==="
for p in /health / /audit /site-audit /demo /pricing /start /app/inbox /api/public/audit/questions /api/voice/niches /api/billing/plans /api/public/pay-info; do
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 15 "https://leadsgenai.in$p")"
  printf '%-24s -> %s\n' "$p" "$code"
  [ "$code" = "200" ] || echo "   WARN: expected 200"
done

echo "=== QUEUES / DLQ ==="
docker exec leadgen_redis redis-cli llen celery
docker exec leadgen_redis redis-cli llen dlq:failed_tasks

# ------------------------------------------------------------------ retention
# Every deploy adds a ~7GB app image. Retention runs ONLY after a fully verified
# deploy. Policy is deployment-LINEAGE aware (not CreatedAt newest-N alone):
# protect exact new tag + durable immediate rollback tag. Same-SHA redeploy
# (PREV_PROD_TAG==VER) reads rollback from LINEAGE_STATE — missing state or
# missing inventory artifacts fail-close with TRUE zero destructive cleanup
# (no rmi, no image prune, no build-cache prune). Lineage state lives OUTSIDE
# the git checkout and is written ONLY after exact-SHA /health verification.
# Never uses `rmi -f`.
KEEP_IMAGES="${KEEP_IMAGES:-1}"
echo "=== RETENTION (lineage-aware; keep>=protected; KEEP_IMAGES=$KEEP_IMAGES) ==="
IMG=ghcr.io/sumitrevolt/leadgenrationaivoiceagent
if [ -z "${PREV_PROD_TAG:-}" ] || [ -z "${RUNNING_JSON:-}" ]; then
  echo "FATAL: PREV_PROD_TAG/RUNNING_JSON unset — refusing retention without lineage capture."
  exit 2
fi
_IMAGES_JSON="$(docker images "$IMG" --format '{"tag":"{{.Tag}}","created_at":"{{.CreatedAt}}"}' \
  | python3 -c 'import sys,json; print(json.dumps([json.loads(l) for l in sys.stdin if l.strip()]))')"
_PLAN_RC=0
_PLAN_OUT="$(python3 "$_script_dir/deploy_image_retention.py" \
  --current "$VER" \
  --previous "$PREV_PROD_TAG" \
  --keep-images "$KEEP_IMAGES" \
  --images-json "$_IMAGES_JSON" \
  --running-json "$RUNNING_JSON" \
  --require-running-json \
  --lineage-state "$LINEAGE_STATE" \
  --write-lineage "$LINEAGE_STATE")" || _PLAN_RC=$?
_CLEANUP_OK=0
if [ "$_PLAN_RC" -ne 0 ]; then
  echo "WARN: lineage retention planner refused (rc=$_PLAN_RC) — zero destructive cleanup executed."
  echo "       No docker rmi / image prune / build-cache prune on this path."
  echo "       LINEAGE_STATE=$LINEAGE_STATE was NOT overwritten."
else
  echo "$_PLAN_OUT"
  ROLLBACK_TAG="$(printf '%s\n' "$_PLAN_OUT" | sed -n 's/^ROLLBACK_TAG=//p' | head -1)"
  if [ -z "$ROLLBACK_TAG" ]; then
    echo "WARN: planner omitted ROLLBACK_TAG — zero destructive cleanup executed."
  else
    echo "ROLLBACK_TAG=$ROLLBACK_TAG"
    _REMOVED_ANY=0
    while IFS= read -r _line; do
      case "$_line" in
        REMOVE=)
          ;;
        REMOVE=*)
          t="${_line#REMOVE=}"
          [ -z "$t" ] && continue
          [ "$t" = "$VER" ] && continue
          [ "$t" = "$PREV_PROD_TAG" ] && continue
          [ "$t" = "$ROLLBACK_TAG" ] && continue
          [ "$t" = "<none>" ] && continue
          [ "$t" = "latest" ] && continue
          if docker rmi "$IMG:$t" >/dev/null 2>&1; then
            echo "  removed $t"
            _REMOVED_ANY=1
          else
            echo "  kept    $t (still referenced or missing)"
          fi
          ;;
      esac
    done <<EOF
$_PLAN_OUT
EOF
    if [ "$_REMOVED_ANY" -eq 0 ]; then
      echo "  nothing to reclaim (or only protected lineage tags present)"
    fi
    docker image prune -f >/dev/null 2>&1     # untagged leftovers only (success path)
    _CLEANUP_OK=1
  fi
fi
echo "  disk now: $(df -h / | tail -1 | awk '{print $5" used, "$4" free"}')"

# ------------------------------------------------------- build-cache retention
# Only after a successful validated retention plan. Planner refusal / malformed
# output skips build-cache prune entirely (true zero destructive cleanup).
BUILD_CACHE_MAX_AGE="${BUILD_CACHE_MAX_AGE:-168h}"        # 7 days unused
BUILD_CACHE_KEEP_STORAGE="${BUILD_CACHE_KEEP_STORAGE:-20GB}"
if [ "$_CLEANUP_OK" -eq 1 ]; then
  echo "=== BUILD CACHE (before) ==="
  docker system df | grep -E "TYPE|Build Cache" || true
  if docker builder prune -f --filter "unused-for=$BUILD_CACHE_MAX_AGE" \
      > /tmp/deploy_buildcache_prune.log 2>&1 \
      && docker builder prune -f --max-used-space "$BUILD_CACHE_KEEP_STORAGE" \
      >> /tmp/deploy_buildcache_prune.log 2>&1; then
    echo "=== BUILD CACHE (after, unused-for>=$BUILD_CACHE_MAX_AGE reclaimed, capped at $BUILD_CACHE_KEEP_STORAGE) ==="
    docker system df | grep -E "TYPE|Build Cache" || true
  else
    echo "WARN: build-cache prune failed (non-fatal — deploy already verified). Tail:"
    tail -8 /tmp/deploy_buildcache_prune.log
  fi
  echo "  disk now: $(df -h / | tail -1 | awk '{print $5" used, "$4" free"}')"
else
  echo "=== BUILD CACHE skipped — zero destructive cleanup executed (retention refuse) ==="
fi

echo "=== DEPLOYED $VER OK ==="
