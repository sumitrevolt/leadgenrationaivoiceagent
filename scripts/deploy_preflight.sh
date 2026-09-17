#!/usr/bin/env bash
# deploy_preflight.sh — pre-deploy gate for LeadGen AI (M6 T05).
#
# WHY THIS EXISTS
# ---------------
# Prod app = systemd unit `leadgen` serving 127.0.0.1:8000. There is NO `leadgen_app`
# container. `docker compose up -d ... app` is a GUARANTEED FALSE SUCCESS (port 8000
# is already bound by the unit, so recreate fails while the old process keeps serving
# and `/health` still returns 200). tests/test_no_app_container_drift.py pins this.
#
# This preflight REFUSES the false-success path and checks the real preconditions
# before `scripts/deploy_vps.sh` runs. Exit non-zero on any failure.
#
# Usage:  bash scripts/deploy_preflight.sh [APP_VERSION]
# Evidence label: CODE-PRESENT.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

APP_VERSION="${1:-${APP_VERSION:-}}"
FAIL=0

fail() { echo "❌ PREFLIGHT FAIL: $*" >&2; FAIL=1; }
ok()   { echo "✅ $*"; }

echo "== LeadGen deploy preflight =="

# 1) APP_VERSION must be a SHA, never 'latest' / empty.
if [[ -z "$APP_VERSION" ]]; then
  fail "APP_VERSION is empty (must be the deployed git SHA)"
elif [[ "$APP_VERSION" == "latest" ]]; then
  fail "APP_VERSION=latest is forbidden (images must be pinned to a SHA)"
else
  ok "APP_VERSION=$APP_VERSION"
fi

# 2) Refuse the guaranteed-false-success path: any 'up -d ... app' in deploy scripts.
#    Skip comments, the legacy archive, and retired stubs that only QUOTE the old
#    command in a comment/docstring (their behaviour is pinned by the drift test).
FALSE_SUCCESS_HITS="$(grep -RnE 'docker[[:space:]]+compose[[:space:]]+up[[:space:]]+-d[^\n]*\bapp\b' scripts/ 2>/dev/null \
  | grep -vE ':[[:space:]]*#' \
  | grep -v '^scripts/legacy/' \
  | grep -v 'scripts/deploy_preflight.sh' \
  | grep -v 'RETIRED' || true)"
if [[ -n "$FALSE_SUCCESS_HITS" ]]; then
  echo "$FALSE_SUCCESS_HITS" >&2
  fail "found 'docker compose up -d ... app' in scripts/ (false-success path)"
else
  ok "no live 'docker compose up -d ... app' in scripts/"
fi

# 3) The real app deploy step must be the systemd unit restart, present in deploy_vps.sh.
if [[ -f scripts/deploy_vps.sh ]] && grep -qE 'systemctl[[:space:]]+restart[[:space:]]+leadgen' scripts/deploy_vps.sh; then
  ok "deploy_vps.sh restarts systemd unit 'leadgen'"
else
  fail "deploy_vps.sh does not contain 'systemctl restart leadgen'"
fi

# 4) Single deploy authority present.
if [[ -f scripts/deploy_vps.sh ]]; then
  ok "deploy authority present: scripts/deploy_vps.sh"
else
  fail "scripts/deploy_vps.sh missing (single deploy authority)"
fi

# 5) Log rotation configured (belt + suspenders).
if [[ -f deploy/logrotate/leadgen ]]; then
  ok "logrotate policy present: deploy/logrotate/leadgen"
else
  fail "deploy/logrotate/leadgen missing (log rotation gap)"
fi

echo "== preflight done =="
if [[ "$FAIL" -ne 0 ]]; then
  echo "Preflight FAILED — deploy aborted." >&2
  exit 1
fi
echo "Preflight OK — proceed with scripts/deploy_vps.sh $APP_VERSION"
exit 0
