"""One-shot VPS deploy: cherry-pick boot-grace fix + rebuild worker/app + catch-up jobs."""

import subprocess
import sys

SSH = [
    r"C:\PROGRA~1\Git\usr\bin\ssh.exe",
    "-i",
    r"C:\Users\Ratanshila\.ssh\id_rsa",
    "-o",
    "StrictHostKeyChecking=no",
    "root@72.61.245.204",
]

COMMIT = "52a27c4"
REMOTE = f"""
set -e
cd /opt/leadgen
git fetch origin
git checkout main
git pull origin main || true
if ! git merge-base --is-ancestor {COMMIT} HEAD 2>/dev/null; then
  git cherry-pick {COMMIT} || {{ git cherry-pick --abort; exit 1; }}
fi
docker compose -f docker-compose.vps.yml build app
docker compose -f docker-compose.vps.yml up -d --no-deps app
docker compose -f docker-compose.vps.yml --profile celery up -d worker scheduler
sleep 14
curl -sf http://127.0.0.1:8000/health | head -c 200
echo
for j in qa trainer pipeline; do
  docker exec leadgen_worker celery -A app.worker call app.tasks.staff_jobs.run_staff_job --args='["'"$j"'"]' || true
done
echo DONE
"""

r = subprocess.run(SSH + [REMOTE], capture_output=True, text=True, timeout=600)
print(r.stdout)
if r.stderr:
    print(r.stderr, file=sys.stderr)
sys.exit(r.returncode)
