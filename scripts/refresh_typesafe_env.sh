#!/bin/bash
# RETIRED 2026-09-20 — this script could not do the one job it existed for, and
# every way it tried to do it caused a different kind of damage.
#
#   1. SECRET EXPOSURE. It printed `prefix=${k[:14]}` of the live
#      TYPESAFE_API_KEY twice per run (old lines 10 and 20) straight to stdout —
#      into the terminal scrollback, into any captured log, and into anything
#      that wrapped the call. A prefix of a live credential is an exposure, not
#      a diagnostic. Credential state is reported only as
#      PRESENT / ABSENT / INVALID / ROTATION_REQUIRED; read-only inspection
#      lives in scripts/check_typesafe.sh, which prints a sha256 fingerprint.
#
#   2. IT NEVER TOUCHED THE APP. The whole purpose was to push a refreshed key
#      into the app process. `app` is served by a container whose env is fixed
#      at create time, and this script never recreated that container — it
#      rolled the worker and then `systemctl restart leadgen 2>/dev/null ||
#      true`, i.e. a unit that is `disabled` and fails every exec with
#      203/EXEC (measured on prod 2026-09-20: NRestarts=5583). Both the redirect
#      and the `|| true` swallowed the failure, so the operator saw "DONE" and
#      believed the key was live. Placebo, not a tool.
#
#   3. VERSION SKEW. `export APP_VERSION=404e5309` is a hardcoded tag that was
#      already stale when this was last edited. Running it today re-creates the
#      worker on a two-week-old image while the web tier stays wherever it is —
#      manufacturing exactly the app/worker skew that scripts/deploy_vps.sh
#      exists to refuse.
#
#   4. MASKED FAILURE. `... | tail -6` hides compose's exit status behind
#      tail's, the documented pipefail landmine in this repo.
#
# A correct env refresh is a release: it must pin the CURRENT sha, recreate the
# services that hold the env, and verify /health. That is deploy_vps.sh, which
# fails closed on all four points above. Nothing here is worth keeping.
set -uo pipefail

echo "REFUSED: scripts/refresh_typesafe_env.sh is RETIRED (2026-09-20)." >&2
echo "  It printed a live credential prefix, never recreated the process it" >&2
echo "  claimed to refresh, and pinned a stale APP_VERSION." >&2
echo "  Read-only TypeSafe state:  bash scripts/check_typesafe.sh" >&2
echo "  Canonical release path:    bash scripts/deploy_vps.sh" >&2
exit 1
