#!/usr/bin/env bash
# Runtime-data deploy guard — source this BEFORE any destructive Git/Compose command.
#
# Production mutable state currently lives inside the Git checkout, so
# `git reset --hard`, `git clean` and even a `git pull` that carries a tracked
# data file can destroy the live invoice ledger, consent ledger, suppression
# ledgers, customer registry, or 182 MB of DPDP call recordings.
#
# Usage (must be the first executable line of a destructive script):
#     . "$(dirname "$0")/_runtime_data_guard.sh"
#
# There is deliberately NO bypass variable and no `|| true`. If you need to
# deploy, migrate the stores — do not silence the guard.
#
# EXECUTION VEHICLE (2026-07-28)
# ------------------------------
# The decision below is unchanged; only the interpreter moved. The preflight
# imports the application, and those dependencies live in the app image, never
# on the VPS host — so the previous `${PYTHON_BIN:-python3}` invocation could
# only ever raise ModuleNotFoundError on production. It "denied" every deploy
# for a reason that had nothing to do with runtime-data safety, which is the
# fastest way to teach an operator that this guard is noise to be worked around.
#
# The caller must therefore export a candidate checkout and source the container
# runner before sourcing this file:
#
#     . "$(dirname "$0")/_deploy_gate_container.sh"
#     RUNTIME_DATA_GATE_CANDIDATE=<isolated worktree at the release sha>
#     RUNTIME_DATA_GATE_REPO=<live checkout, for .env + the REAL data/>
#     . "$(dirname "$0")/_runtime_data_guard.sh"
#
# If that vehicle is absent this guard DENIES. It does not fall back to the host
# interpreter: a fallback that always fails is indistinguishable from a real
# blocker, and the two must never be confused by whoever is reading the log.
set -euo pipefail

_guard_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_guard_repo="$(cd "${_guard_dir}/.." && pwd)"

_guard_candidate="${RUNTIME_DATA_GATE_CANDIDATE:-}"
_guard_live="${RUNTIME_DATA_GATE_REPO:-${_guard_repo}}"

if ! command -v gate_run >/dev/null 2>&1; then
  echo ""
  echo "FATAL: runtime-data preflight has no execution vehicle."
  echo "       Source scripts/_deploy_gate_container.sh and export"
  echo "       RUNTIME_DATA_GATE_CANDIDATE before sourcing this guard."
  echo "       Refusing to deploy: an unrun gate is not a passed gate."
  exit 90
fi

if [ -z "${_guard_candidate}" ] || [ ! -d "${_guard_candidate}" ]; then
  echo ""
  echo "FATAL: no candidate checkout for the runtime-data preflight."
  echo "       RUNTIME_DATA_GATE_CANDIDATE must point at an isolated worktree"
  echo "       checked out at the exact release sha."
  exit 90
fi

# Read-only report first. It always exits 0 and never decides anything; it is
# here so the blocker list is on the operator's screen BEFORE the refusal, not
# discovered afterwards in a runbook.
echo "=== runtime-data preflight (diagnose — read-only, decides nothing) ==="
if ! gate_run "${_guard_candidate}" "${_guard_live}" scripts/runtime_data_preflight.py diagnose; then
  # Explicitly non-fatal, and written as a branch rather than `|| true`:
  # this guard forbids `|| true` on principle, and a reader must be able to see
  # at a glance that ONLY the report is optional. The decision below is not.
  echo "WARN: diagnose report unavailable — the check-deploy decision still stands."
fi

echo "=== runtime-data preflight (check-deploy) ==="
if ! gate_run "${_guard_candidate}" "${_guard_live}" scripts/runtime_data_preflight.py check-deploy; then
  echo ""
  echo "FATAL: runtime-data preflight DENIED this deployment."
  echo "       Mutable production state is still inside the Git checkout, so the"
  echo "       destructive command that follows would destroy it."
  echo "       See the blocker list above and docs/runbooks/RUNTIME_DATA_CUTOVER.md"
  exit 90
fi
echo "=== preflight passed — destructive deployment permitted ==="
