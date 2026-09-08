#!/usr/bin/env python3
"""One-shot VPS deploy smoke for workflow parity ship (run via SSH on VPS).

CONSOLIDATED 2026-07-26. The release chain (`git fetch` + `git reset --hard
origin/main` + `compose build` + `compose up`) was joined into a single
`bash -lc` string and executed unguarded. `reset --hard` against this checkout
destroys live ledgers, so the chain is gone: the release is delegated to the
guarded canonical parent and only the read-only smoke checks remain.

No fallback. The parent's exit status is returned verbatim (90 = guard denied,
91 = guard/parent unavailable).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time
import urllib.request

PARENT = pathlib.Path(__file__).resolve().parent / "deploy_vps.sh"

EXIT_PARENT_UNAVAILABLE = 91


def _release() -> int:
    if not PARENT.is_file() or not os.access(PARENT, os.R_OK):
        print(f"FATAL: canonical release parent unavailable: {PARENT}")
        return EXIT_PARENT_UNAVAILABLE
    print("=== DEPLOY (delegated to guarded parent) ===")
    return subprocess.run(["bash", str(PARENT)], check=False).returncode  # noqa: S603


def main() -> int:
    rc = _release()
    if rc != 0:
        print(f"DEPLOY FAIL {rc} (90=guard denied, 91=guard unavailable)")
        return rc

    # ------------------------------------------------ read-only smoke checks
    print("=== WAIT 18s ===")
    time.sleep(18)
    ok = 0
    for i in range(2):
        try:
            # Literal loopback URL, no caller input. Host-side app port is 8000
            # (the container listens on 8080) — see the port trap in CLAUDE.md.
            with urllib.request.urlopen(  # nosec B310  # noqa: S310
                "http://127.0.0.1:8000/health", timeout=15
            ) as resp:
                body = json.loads(resp.read().decode())
                env = body.get("environment", body)
                print(f"health[{i + 1}]", resp.status, env)
                if resp.status == 200 and str(env).find("production") >= 0:
                    ok += 1
        except Exception as e:
            print(f"health[{i + 1}] ERR", e)
        time.sleep(3)

    print("=== CELERY QUEUE ===")
    subprocess.run(  # noqa: S603
        ["docker", "exec", "leadgen_redis", "redis-cli", "llen", "celery"],
        check=False,
    )
    return 0 if ok >= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
