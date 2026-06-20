#!/usr/bin/env python3
"""Windows-safe: SSH to VPS and queue catch-up staff jobs."""
from __future__ import annotations

import subprocess
import sys

SSH = [
    r"C:\PROGRA~1\Git\usr\bin\ssh.exe",
    "-i",
    r"C:\Users\Ratanshila\.ssh\id_rsa",
    "-o",
    "BatchMode=yes",
    "root@72.61.245.204",
]

PY = (
    "from app.tasks.staff_jobs import run_staff_job\n"
    "for j in ('qa','trainer','pipeline'):\n"
    "    r=run_staff_job.delay(j)\n"
    "    print(j, r.id)\n"
)


def main() -> int:
    cmd = SSH + ["docker", "exec", "-i", "leadgen_app", "python", "-"]
    r = subprocess.run(cmd, input=PY, text=True, capture_output=True, timeout=120)
    print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
