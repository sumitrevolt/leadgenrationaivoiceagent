"""One-shot: set UPI_VPA on VPS + verify pay-info.

Usage:
    python scripts/vps_set_upi_smoke.py YOURVPA@bank
"""

import json
import subprocess
import sys

VPA = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
if not VPA or "@" not in VPA:
    print("usage: python scripts/vps_set_upi_smoke.py YOURVPA@bank", file=sys.stderr)
    sys.exit(2)
SSH = [
    r"C:\PROGRA~1\Git\usr\bin\ssh.exe",
    "-i",
    r"C:\Users\Ratanshila\.ssh\id_rsa",
    "-o",
    "StrictHostKeyChecking=no",
    "root@72.61.245.204",
]
REMOTE = f"""
set -e
cd /opt/leadgen
bash scripts/set_kv.sh UPI_VPA {VPA}
curl -sf http://127.0.0.1:8000/api/public/pay-info
"""

r = subprocess.run(SSH + [REMOTE], capture_output=True, text=True, timeout=120)
print(r.stdout)
if r.stderr:
    print(r.stderr, file=sys.stderr)
if r.returncode != 0:
    sys.exit(r.returncode)
try:
    lines = [ln for ln in r.stdout.strip().splitlines() if ln.startswith("{")]
    if lines:
        d = json.loads(lines[-1])
        print("VERIFY enabled=", d.get("enabled"), "vpa_ok=", d.get("vpa") == VPA)
except Exception as e:
    print("verify parse skip:", e)
