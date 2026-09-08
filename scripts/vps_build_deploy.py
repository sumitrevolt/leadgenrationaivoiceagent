"""Run on VPS via ssh: python3 scripts/vps_build_deploy.py

CONSOLIDATED 2026-07-26. This used to execute its own release chain:

    cd /opt/leadgen
    git fetch --all -q
    git reset --hard origin/main -q      <-- destroys uncommitted live data
    docker compose ... build app
    docker compose ... up -d --no-deps app

Two things were wrong with it, beyond being unguarded:

1. `git reset --hard` against a checkout that still holds the live invoice,
   consent and suppression ledgers plus 182 MB of DPDP call recordings.
2. Each command ran in its OWN `shell=True` subprocess, so `cd /opt/leadgen`
   had no effect on the commands after it — the reset ran against whatever
   the current working directory happened to be.

It now delegates to the guarded canonical parent, with no shell and no
fallback. Exit status is the parent's, verbatim: 90 = guard denied,
91 = guard/parent unavailable.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

PARENT = pathlib.Path(__file__).resolve().parent / "deploy_vps.sh"

EXIT_PARENT_UNAVAILABLE = 91


def main() -> int:
    if not PARENT.is_file() or not os.access(PARENT, os.R_OK):
        print(f"FATAL: canonical release parent unavailable: {PARENT}", file=sys.stderr)
        print("Refusing to deploy. Do not reinstate a local git/compose chain.", file=sys.stderr)
        return EXIT_PARENT_UNAVAILABLE

    print(f"$ bash {PARENT}")
    # Structured args, shell=False: nothing is interpolated into a command
    # string, so no value can inject shell control characters.
    r = subprocess.run(["bash", str(PARENT)], check=False)  # noqa: S603
    if r.returncode != 0:
        print(f"PARENT_RC={r.returncode} (90=guard denied, 91=guard unavailable)")
        return r.returncode

    print("ALL DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
