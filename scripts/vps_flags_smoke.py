#!/usr/bin/env python3
"""Check/set workflow flags on VPS .env + import smoke."""

from __future__ import annotations

import os
import re
import subprocess
import sys

ENV_PATH = "/opt/leadgen/.env"
WANT = {
    "CONTENT_APPROVAL_AUTO": "1",
}


def main() -> int:
    print("=== CURRENT FLAGS ===")
    if os.path.isfile(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8", errors="replace") as f:
            for line in f:
                if re.match(
                    r"^(CONTENT_APPROVAL_AUTO|CADENCE_ENGINE|JOURNEY_ENGINE|CUSTOMER_WEBHOOKS|SELF_IMPROVE_LOOP|AUTO_CALLBACK_INQUIRY)=",
                    line,
                ):
                    print(line.rstrip())
    else:
        print("NO .env")

    changed = False
    text = (
        open(ENV_PATH, encoding="utf-8", errors="replace").read()
        if os.path.isfile(ENV_PATH)
        else ""
    )
    for key, val in WANT.items():
        pat = re.compile(rf"^{re.escape(key)}=.*$", re.M)
        if pat.search(text):
            if f"{key}={val}" not in text:
                text = pat.sub(f"{key}={val}", text)
                changed = True
                print(f"UPDATED {key}={val}")
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += f"{key}={val}\n"
            changed = True
            print(f"ADDED {key}={val}")

    if changed:
        bak = ENV_PATH + ".bak_workflow_fix"
        subprocess.run(["cp", ENV_PATH, bak], check=True)
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print("=== RECREATE app worker scheduler ===")
        subprocess.run(
            [
                "bash",
                "-lc",
                "cd /opt/leadgen && docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps app worker scheduler",
            ],
            check=True,
        )
    else:
        print("FLAGS OK (no change)")

    print("=== IMPORT SMOKE ===")
    r = subprocess.run(
        [
            "docker",
            "exec",
            "leadgen_app",
            "python",
            "-c",
            "import app.platform.inquiry_hooks, app.platform.boot_grace, app.agents.process_engine; print('imports_ok')",
        ],
        capture_output=True,
        text=True,
    )
    print(r.stdout or r.stderr)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
