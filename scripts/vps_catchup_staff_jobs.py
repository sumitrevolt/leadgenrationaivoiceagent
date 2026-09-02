#!/usr/bin/env python3
"""Queue catch-up staff jobs (qa, trainer, pipeline) on VPS.

Windows: SSH → docker exec leadgen_app
Linux/VPS: docker exec leadgen_app directly (no Windows ssh path).
"""

from __future__ import annotations

import platform
import subprocess
import sys

PY = (
    "from app.tasks.staff_jobs import run_staff_job\n"
    "for j in ('qa','trainer','pipeline'):\n"
    "    r=run_staff_job.delay(j)\n"
    "    print(j, r.id)\n"
)

SSH = [
    r"C:\PROGRA~1\Git\usr\bin\ssh.exe",
    "-i",
    r"C:\Users\Ratanshila\.ssh\id_rsa",
    "-o",
    "BatchMode=yes",
    "root@72.61.245.204",
]


def _run_docker_exec() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "exec", "-i", "leadgen_app", "python", "-"],
        input=PY,
        text=True,
        capture_output=True,
        timeout=120,
    )


def main() -> int:
    on_vps = platform.system() == "Linux" and __import__("os").path.isdir("/opt/leadgen")
    if on_vps:
        cmd = _run_docker_exec()
    else:
        cmd = subprocess.run(
            SSH + ["docker", "exec", "-i", "leadgen_app", "python", "-"],
            input=PY,
            text=True,
            capture_output=True,
            timeout=120,
        )
    print(cmd.stdout)
    if cmd.stderr:
        print(cmd.stderr, file=sys.stderr)
    return cmd.returncode


if __name__ == "__main__":
    raise SystemExit(main())
