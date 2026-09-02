#!/usr/bin/env bash
# Container execution vehicle for the deployment gates.
#
# WHY THIS FILE EXISTS
# ---------------------
# Both release gates import the application (pydantic, fastapi). Those
# dependencies live in the app IMAGE and have never existed on the VPS host, so
# on production `python3 scripts/prod_check.py --deployment` returns
# ModuleNotFoundError and `runtime_data_preflight.py check-deploy` cannot even
# reach its own manifest. A gate that can only ever fail closed is not a gate —
# it is an outage waiting for the first operator who decides to skip it. That is
# exactly the shape that turns a safety control into a bypass.
#
# WHAT THIS FILE DOES NOT CHANGE
# ------------------------------
# Nothing about the DECISION. `runtime_data_preflight.py` and `prod_check.py`
# keep every blocker, every threshold and every refusal, unchanged. Only the
# interpreter moves — from a host python that cannot import the app, into the
# image that already ships those exact dependencies.
#
# The container is deliberately hostile to accidents:
#
#   --read-only        the gate cannot write anywhere but its own tmpfs
#   --network none     a gate must not reach a provider, a queue or the API;
#                      a "preflight" that can place a call is not a preflight
#   candidate :ro      the source UNDER TEST cannot be edited by the gate
#   prod data :ro      the gate sees the REAL ledgers — a candidate worktree's
#                      empty `data/` would report a clean system that does not
#                      exist — and it cannot touch them
#   --env-file .env    the same environment production runs with. Values are
#                      never echoed; only names, booleans and counts are printed
#
# Image provenance: the image is pinned to the RUNNING production container's
# image ID (a sha256 digest), never to a tag, and never to `latest`. ADR-097
# exists because `:latest` silently decided what production was running.

# Resolve the pinned gate image as an immutable ID, not a moving tag.
# Prints the id on stdout; returns non-zero (and prints nothing) if it cannot be
# proven, because guessing here would run the gate against unknown code.
gate_pinned_image() {
  local ref="${1:-leadgen_app}"
  local id=""
  id="$(docker inspect -f '{{.Image}}' "$ref" 2>/dev/null || true)"
  case "$id" in
    sha256:*) ;;
    *)
      echo "FATAL: cannot resolve a pinned image id from container '$ref'." >&2
      echo "       Refusing to run a gate against an unproven image." >&2
      return 1
      ;;
  esac
  printf '%s\n' "$id"
}

# Human-readable tag of the same container, for the log line only. A tag is
# never used to RUN anything here.
gate_image_tag() {
  docker inspect -f '{{.Config.Image}}' "${1:-leadgen_app}" 2>/dev/null || true
}

# gate_run_image <image> <candidate_dir> <repo_root> <python args...>
#
# Runs one gate inside an EXPLICIT image against the candidate source, with the
# live production data mounted read-only at the same relative path the gate
# expects (`<repo>/data`). The bootstrap gate uses the pinned production image
# (the candidate image does not exist yet); the full readiness gate uses the
# candidate image, so it validates what will actually run.
gate_run_image() {
  local image="$1"
  local candidate="$2"
  local repo="$3"
  shift 3

  if [ -z "$image" ]; then
    echo "FATAL: no gate image supplied." >&2
    return 92
  fi
  case "$image" in
    *:latest|latest)
      echo "FATAL: refusing to run a gate against ':latest' (ADR-097)." >&2
      return 92
      ;;
  esac
  if [ ! -d "$candidate" ]; then
    echo "FATAL: candidate directory does not exist: $candidate" >&2
    return 92
  fi
  if [ ! -r "$repo/.env" ]; then
    echo "FATAL: $repo/.env is not readable — the gate would run with an" >&2
    echo "       environment production does not have, and could pass falsely." >&2
    return 92
  fi

  # External runtime root (cutover). `.env` tells the app where the marker lives
  # INSIDE the container (`LEADGEN_RUNTIME_DATA_DIR`); the matching host path
  # (`LEADGEN_RUNTIME_DATA_HOST_DIR`) must be bind-mounted or check-deploy will
  # report MARKER_ABSENT / EXTERNAL_ROOT_UNVERIFIED even after a valid host
  # activate — which is exactly the false DENY that blocked the first
  # post-cutover canonical deploy (2026-07-29).
  local host_runtime app_runtime
  host_runtime="${LEADGEN_RUNTIME_DATA_HOST_DIR:-}"
  app_runtime="${LEADGEN_RUNTIME_DATA_DIR:-}"
  if [ -z "$host_runtime" ]; then
    host_runtime="$(grep -E '^LEADGEN_RUNTIME_DATA_HOST_DIR=' "$repo/.env" | head -n1 | cut -d= -f2- | tr -d '\r' || true)"
  fi
  if [ -z "$app_runtime" ]; then
    app_runtime="$(grep -E '^LEADGEN_RUNTIME_DATA_DIR=' "$repo/.env" | head -n1 | cut -d= -f2- | tr -d '\r' || true)"
  fi
  local -a runtime_mount=()
  if [ -n "$host_runtime" ] && [ -n "$app_runtime" ]; then
    if [ ! -d "$host_runtime" ]; then
      echo "FATAL: LEADGEN_RUNTIME_DATA_HOST_DIR='$host_runtime' is not a directory." >&2
      echo "       Refusing to run the gate against a missing external root." >&2
      return 92
    fi
    runtime_mount=(-v "$host_runtime:$app_runtime:ro")
  fi

  docker run --rm \
    --read-only \
    --tmpfs /tmp \
    --network none \
    --env-file "$repo/.env" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e PYTHONPATH=/repo \
    -v "$candidate:/repo:ro" \
    -v "$repo/data:/repo/data:ro" \
    "${runtime_mount[@]}" \
    -w /repo \
    "$image" \
    python "$@"
}

# gate_run <candidate_dir> <repo_root> <python args...> — pinned production image.
gate_run() {
  local candidate="$1"
  local repo="$2"
  shift 2
  local image=""
  image="$(gate_pinned_image)" || return 92
  gate_run_image "$image" "$candidate" "$repo" "$@"
}

# Non-secret proof that the calling-safety environment actually reaches the
# gate container. Prints booleans only — never the token, never any value.
#
# This exists because the deployment gate reads VOICE_LAUNCH_KILL from the
# ENVIRONMENT: if `.env` were not injected, `prod_check --deployment` would
# report UNSET and the operator would "fix" it by exporting the variable in
# their shell, proving nothing about what production will actually run with.
gate_kill_env_proof() {
  local candidate="$1"
  local repo="$2"
  gate_run "$candidate" "$repo" -c '
import os
v = os.environ.get("VOICE_LAUNCH_KILL")
true_tokens = {"1", "true", "yes", "on", "true_token"}
print("VOICE_LAUNCH_KILL_PRESENT=" + ("1" if v is not None else "0"))
print("VOICE_LAUNCH_KILL_IS_TRUE_TOKEN=" + ("1" if (v or "").strip().lower() in true_tokens else "0"))
print("PLATFORM_DIAL_DAILY=" + (os.environ.get("PLATFORM_DIAL_DAILY") or "<unset>"))
'
}
