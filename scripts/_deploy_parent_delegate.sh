#!/usr/bin/env bash
# Shared delegation to the canonical release parent (deploy_vps.sh).
#
# THIS IS NOT A SECOND GUARD. Runtime-data enforcement lives in exactly one
# place — _runtime_data_guard.sh, sourced by deploy_vps.sh. Copying that logic
# into every wrapper would create N places to drift and N places to weaken.
# This helper only:
#
#   1. resolves the parent next to itself (no PATH lookup, no interpolation),
#   2. refuses to continue if the parent is missing or unreadable,
#   3. runs it and hands back its EXACT exit status.
#
# Exit-status contract inherited from the parent, preserved verbatim:
#     0  = release completed
#     90 = runtime-data guard ran and DENIED the deployment
#     91 = runtime-data guard (or now the parent itself) was unavailable
#
# Callers must treat any non-zero as terminal. A wrapper that falls back to its
# old git/compose chain after a denial would defeat the guard completely, which
# is the entire reason these wrappers were consolidated.

delegate_to_parent() {
  local ver="${1:-}"
  local here parent
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 91
  parent="$here/deploy_vps.sh"

  if [ ! -r "$parent" ]; then
    echo "FATAL: canonical release parent not found or unreadable: $parent"
    echo "       Refusing to deploy. Restore it — do not reinstate a local"
    echo "       git/compose chain in this wrapper."
    return 91
  fi

  # Structured invocation: the sha is a single argument, never concatenated
  # into a command string, so a malformed value cannot inject shell control.
  if [ -n "$ver" ]; then
    bash "$parent" "$ver"
  else
    bash "$parent"
  fi
}
