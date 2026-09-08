"""VPS deploy: pull + build app + recreate + health + pay-info smoke."""

import json
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
REMOTE = r"""
set -e
cd /opt/leadgen
git fetch origin
git checkout main
git pull origin main
echo "HEAD: $(git log -1 --oneline)"
docker compose -f docker-compose.vps.yml build app
docker compose -f docker-compose.vps.yml up -d --no-deps app
sleep 16
echo "--- health ---"
curl -sf http://127.0.0.1:8000/health
echo
echo "--- pay-info ---"
curl -sf http://127.0.0.1:8000/api/public/pay-info | python3 -c "import sys,json;d=json.load(sys.stdin);print('enabled',d.get('enabled'),'vpa_set',bool(d.get('vpa')))"
echo
echo "--- activation summary ---"
curl -sf http://127.0.0.1:8000/api/activation/summary | python3 -c "import sys,json;d=json.load(sys.stdin);print('paid_ready',d.get('ready_for_first_paid_customer'),'blockers',d.get('blocker_count'))"
echo DONE
"""

r = subprocess.run(SSH + [REMOTE], capture_output=True, text=True, timeout=900000)
print(r.stdout)
if r.stderr:
    print(r.stderr, file=sys.stderr)
sys.exit(r.returncode)
