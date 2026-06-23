"""Run on VPS via ssh: python3 scripts/vps_build_deploy.py"""
import subprocess, sys

cmds = [
    "cd /opt/leadgen",
    "git fetch --all -q",
    "git reset --hard origin/main -q",
    "docker compose -f docker-compose.vps.yml build app",
    "docker compose -f docker-compose.vps.yml up -d --no-deps app",
    "echo BUILD_AND_UP_DONE",
]

for cmd in cmds:
    print(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, text=True)
    if r.returncode != 0 and cmd not in ("git fetch --all -q",):
        print(f"FAILED: {cmd}")
        sys.exit(1)

print("ALL DONE")
