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
set -euo pipefail

_guard_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_guard_repo="$(cd "${_guard_dir}/.." && pwd)"
_guard_py="${PYTHON_BIN:-python3}"

echo "=== runtime-data preflight (check-deploy) ==="
if ! "${_guard_py}" "${_guard_dir}/runtime_data_preflight.py" check-deploy; then
  echo ""
  echo "FATAL: runtime-data preflight DENIED this deployment."
  echo "       Mutable production state is still inside the Git checkout, so the"
  echo "       destructive command that follows would destroy it."
  echo "       See the blocker list above and docs/runbooks/RUNTIME_DATA_CUTOVER.md"
  exit 90
fi
echo "=== preflight passed — destructive deployment permitted ==="
