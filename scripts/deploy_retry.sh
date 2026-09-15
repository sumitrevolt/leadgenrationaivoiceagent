#!/usr/bin/env bash
# deploy_retry.sh — network-resilient wrapper for deploy_vps.sh
#
# WHY THIS EXISTS (2026-09-15 owner order):
#   The SSH tunnel to the VPS is flaky. A dropped mid-flight SIGHUP has
#   historically killed the build (CLAUDE.md landmine). This wrapper:
#     1. Detects network-layer failures (curl exit 28/35/56, scp timeout,
#        ssh "Connection reset/broken pipe", docker registry pull timeout).
#     2. Waits BACKOFF_SECS (default 60) and retries up to MAX_ATTEMPTS.
#     3. NEVER retries a deploy_vps.sh FATAL (the script's own fail-closed
#        gates — /health/ready=200, route count, per-service skew, runtime-data
#        guard — are the correctness authority; a FATAL exit means the deploy
#        is genuinely wrong, not a network blip).
#     4. Logs every attempt to /tmp/deploy_retry.log with timestamps.
#
# Usage on the VPS:
#   # normal deploy with retry:
#   bash scripts/deploy_retry.sh <git-sha>
#
#   # dry-run (prints the plan, changes nothing):
#   DRY_RUN=1 bash scripts/deploy_retry.sh <git-sha>
#
#   # override backoff / attempts:
#   MAX_ATTEMPTS=8 BACKOFF_SECS=90 bash scripts/deploy_retry.sh <sha>
#
# What it does NOT do:
#   - It does NOT call deploy_vps.sh with a different SHA on each retry
#     (idempotency: same SHA, same gates, safe to re-run).
#   - It does NOT bypass any deploy_vps.sh fail-closed gate.
#   - It does NOT run `git pull` or `docker` commands directly.

set -uo pipefail

MAX_ATTEMPTS="${MAX_ATTEMPTS:-5}"
BACKOFF_SECS="${BACKOFF_SECS:-60}"
LOG="/tmp/deploy_retry.log"
CANDIDATE_SHA="${1:?Usage: bash scripts/deploy_retry.sh <git-sha> [DRY_RUN=0|1]}"

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$LOG"; }

# deploy_vps.sh exit codes we recognise:
#   0  = success
#   1  = generic FATAL (gate failed, bad SHA, etc.)
#   2  = usage error
#   4  = version-skill FATAL (drift detected, lineage poisoned)
#   92 = (parallel-agent pin) gate proof failure
#   91 = (parallel-agent pin) env proof failure
# Anything that is NOT 0 is treated as "not a network failure" unless we
# explicitly detect a network-layer error in the log tail.

is_network_failure() {
  # Check the last 200 lines of the deploy log for network-layer errors.
  # deploy_vps.sh writes its build log to /tmp/dep.log (per CLAUDE.md runbook).
  local tail
  tail=$(tail -200 /tmp/dep.log 2>/dev/null)
  echo "$tail" | grep -qE 'Connection reset|Connection timed out|broken pipe|curl: \(2[0-9]\)|curl: \(3[0-9]\)|curl: \(5[0-9]\)|ECONNREFUSED|ECONNRESET|ETIMEDOUT|EOF while writing|network is unreachable|Temporary failure in name resolution' && return 0
  # Also check the retry log itself (in case the SSH session itself dropped)
  return 1
}

attempts=0
while [ "$attempts" -lt "$MAX_ATTEMPTS" ]; do
  attempts=$((attempts + 1))
  log "=== attempt $attempts / $MAX_ATTEMPTS  sha=$CANDIDATE_SHA  dry_run=${DRY_RUN:-0} ==="

  # Run deploy_vps.sh; capture exit code but do NOT let set -e kill this wrapper.
  set +e
  DRY_RUN="${DRY_RUN:-0}" APP_VERSION="$CANDIDATE_SHA" bash scripts/deploy_vps.sh "$CANDIDATE_SHA"
  rc=$?
  set -e

  if [ "$rc" -eq 0 ]; then
    log "SUCCESS on attempt $attempts — deploy $CANDIDATE_SHA complete."
    exit 0
  fi

  log "deploy_vps.sh exited rc=$rc on attempt $attempts."

  # Is this a network-layer failure we should retry?
  if is_network_failure; then
    log "Network-layer error detected. Backing off ${BACKOFF_SECS}s before retry."
    sleep "$BACKOFF_SECS"
    continue
  fi

  # Not a network failure — a genuine deploy FATAL. Do NOT retry.
  log "FATAL (rc=$rc, not a network error). deploy_vps.sh fail-closed gate tripped."
  log "Inspect /tmp/dep.log and /tmp/deploy_retry.log before retrying manually."
  log "Do NOT blindly re-run — the deploy gate is blocking for a reason."
  exit "$rc"
done

log "Exhausted MAX_ATTEMPTS=$MAX_ATTEMPTS retries. Giving up."
exit 1
