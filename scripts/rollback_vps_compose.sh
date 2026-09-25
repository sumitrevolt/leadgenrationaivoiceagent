#!/usr/bin/env bash
# Roll back the Docker-served production cohort to one verified immutable tag.
# Run on the VPS from /opt/leadgen. This never moves the git checkout.
set -uo pipefail

REPO="${REPO:-/opt/leadgen}"
COMPOSE="${COMPOSE:-docker-compose.vps.yml}"
SERVICES="app worker scheduler worker-heavy worker-video dsh-worker"
TARGET_TAG="${1:-}"
SOURCE_TAG="${ROLLBACK_SOURCE_TAG:-}"
HEALTH_MAX_ATTEMPTS="${HEALTH_MAX_ATTEMPTS:-12}"
HEALTH_RETRY_SECONDS="${HEALTH_RETRY_SECONDS:-5}"

case "$TARGET_TAG" in
  ""|*[!0-9a-f]* )
    echo "FATAL: rollback tag must be a 7-40 character lowercase git SHA."
    exit 2
    ;;
esac
if [ "${#TARGET_TAG}" -lt 7 ] || [ "${#TARGET_TAG}" -gt 40 ]; then
  echo "FATAL: rollback tag must be a 7-40 character lowercase git SHA."
  exit 2
fi
if [ -n "$SOURCE_TAG" ]; then
  case "$SOURCE_TAG" in
    *[!0-9a-f]* ) echo "FATAL: recovery source tag must be a lowercase git SHA."; exit 2 ;;
  esac
  if [ "${#SOURCE_TAG}" -lt 7 ] || [ "${#SOURCE_TAG}" -gt 40 ] || [ "$SOURCE_TAG" = "$TARGET_TAG" ]; then
    echo "FATAL: recovery source tag must be a distinct 7-40 character git SHA."
    exit 2
  fi
fi
if [ "${ROLLBACK_DB_COMPATIBLE:-0}" != "1" ]; then
  echo "FATAL: set ROLLBACK_DB_COMPATIBLE=1 after migration compatibility review."
  exit 11
fi

cd "$REPO" || { echo "FATAL: $REPO not found"; exit 2; }
if systemctl is-active --quiet leadgen >/dev/null 2>&1; then
  echo "FATAL: systemd leadgen is active; this rollback is Compose-only."
  exit 10
fi
ENV_TAG_COUNT="$(grep -cE '^APP_VERSION=' "$REPO/.env" 2>/dev/null || true)"
ENV_TAG="$(grep -E '^APP_VERSION=' "$REPO/.env" 2>/dev/null | head -1 | cut -d= -f2 || true)"
if [ -n "$SOURCE_TAG" ]; then
  CURRENT_TAG="$SOURCE_TAG"
  if [ "$ENV_TAG_COUNT" != "1" ] || [ "$ENV_TAG" != "$SOURCE_TAG" ]; then
    echo "FATAL: recovery requires .env APP_VERSION to occur once and match source $SOURCE_TAG."
    exit 12
  fi
  CURRENT_IMAGE="$(docker inspect -f '{{.Config.Image}}' leadgen_app 2>/dev/null || true)"
  if [ -n "$CURRENT_IMAGE" ]; then
    _observed_tag="${CURRENT_IMAGE##*:}"
    if [ "$_observed_tag" != "$SOURCE_TAG" ] && [ "$_observed_tag" != "$TARGET_TAG" ]; then
      echo "FATAL: recovery observed unexpected app image '$CURRENT_IMAGE'."
      exit 12
    fi
  fi
else
  if [ "$(docker inspect -f '{{.State.Running}}' leadgen_app 2>/dev/null || true)" != "true" ]; then
    echo "FATAL: leadgen_app is not the running web app."
    exit 10
  fi
  CURRENT_IMAGE="$(docker inspect -f '{{.Config.Image}}' leadgen_app 2>/dev/null || true)"
  CURRENT_TAG="${CURRENT_IMAGE##*:}"
  case "$CURRENT_TAG" in
    ""|*[!0-9a-f]* ) echo "FATAL: current app image is not immutable: $CURRENT_IMAGE"; exit 2 ;;
  esac
  if [ "${#CURRENT_TAG}" -lt 7 ] || [ "${#CURRENT_TAG}" -gt 40 ]; then
    echo "FATAL: current app image tag has invalid SHA length: $CURRENT_IMAGE"
    exit 2
  fi
  if [ "$CURRENT_TAG" = "$TARGET_TAG" ]; then
    echo "FATAL: target already serves production; refusing a no-op rollback."
    exit 2
  fi
  if [ "$ENV_TAG_COUNT" != "1" ] || [ "$ENV_TAG" != "$CURRENT_TAG" ]; then
    echo "FATAL: .env APP_VERSION must occur once and match running tag $CURRENT_TAG."
    exit 12
  fi
fi

_set_env_tag() {
  local tag="$1"
  sed -i "s/^APP_VERSION=.*/APP_VERSION=$tag/" "$REPO/.env"
  [ "$(grep -E '^APP_VERSION=' "$REPO/.env" | head -1 | cut -d= -f2 || true)" = "$tag" ]
}

_compose_up() {
  local tag="$1"
  # shellcheck disable=SC2086
  APP_VERSION="$tag" docker compose -f "$COMPOSE" --profile celery --profile dsh \
    up -d --no-deps $SERVICES
}

_health_matches() {
  local tag="$1"
  local attempt=1
  local body=""
  local observed=""
  while [ "$attempt" -le "$HEALTH_MAX_ATTEMPTS" ]; do
    body="$(curl -s -m 10 127.0.0.1:8000/health || true)"
    observed="$(printf '%s' "$body" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p')"
    [ "$observed" = "$tag" ] && return 0
    [ "$attempt" -lt "$HEALTH_MAX_ATTEMPTS" ] && sleep "$HEALTH_RETRY_SECONDS"
    attempt=$((attempt + 1))
  done
  echo "FATAL: health version '${observed:-missing}' != '$tag'."
  return 1
}

_cohort_matches() {
  local tag="$1"
  local service=""
  local cid=""
  local running=""
  local image=""
  for service in $SERVICES; do
    cid="$(APP_VERSION="$tag" docker compose -f "$COMPOSE" --profile celery \
      --profile dsh ps -q "$service" 2>/dev/null | head -1)"
    [ -n "$cid" ] || { echo "FATAL: cannot resolve rollback service $service."; return 1; }
    running="$(docker inspect -f '{{.State.Running}}' "$cid" 2>/dev/null || true)"
    image="$(docker inspect -f '{{.Config.Image}}' "$cid" 2>/dev/null || true)"
    [ "$running" = "true" ] || { echo "FATAL: rollback service $service is not running."; return 1; }
    [ "${image##*:}" = "$tag" ] || {
      echo "FATAL: rollback service $service image '$image' does not match '$tag'."
      return 1
    }
  done
}

_restore_previous() {
  echo "ROLLBACK FAILED: restoring previous cohort $CURRENT_TAG"
  _set_env_tag "$CURRENT_TAG" || return 1
  _compose_up "$CURRENT_TAG" || return 1
  _health_matches "$CURRENT_TAG" && _cohort_matches "$CURRENT_TAG"
}

echo "=== ROLLBACK PREFLIGHT current=$CURRENT_TAG target=$TARGET_TAG ==="
for image in $(APP_VERSION="$TARGET_TAG" docker compose -f "$COMPOSE" \
  --profile celery --profile dsh config --images); do
  docker image inspect "$image" >/dev/null 2>&1 || {
    echo "FATAL: required rollback image is missing: $image"
    exit 12
  }
done

_set_env_tag "$TARGET_TAG" || { echo "FATAL: could not pin APP_VERSION."; exit 12; }
if ! _compose_up "$TARGET_TAG" || ! _health_matches "$TARGET_TAG" || ! _cohort_matches "$TARGET_TAG"; then
  if [ -n "$SOURCE_TAG" ]; then
    echo "FATAL: deploy recovery target failed verification; operator recovery required."
    exit 21
  fi
  _restore_previous || {
    echo "FATAL: rollback and automatic restore both failed; operator recovery required."
    exit 21
  }
  echo "FATAL: rollback target failed verification; previous cohort restored."
  exit 20
fi

echo "ROLLBACK VERIFIED: production serves $TARGET_TAG"
