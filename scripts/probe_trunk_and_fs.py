import os
import subprocess
from pathlib import Path

import requests

env = {}
for p in ["/opt/leadgen/.env"]:
    if os.path.exists(p):
        for line in Path(p).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("\"'")

aid = env.get("VOBIZ_AUTH_ID")
tok = env.get("VOBIZ_AUTH_TOKEN")
base = f"https://api.vobiz.ai/api/v1/Account/{aid}"

# 1. Test Trunk endpoints on Vobiz API
trunk_endpoints = [
    "/Trunk/",
    f"/Trunk/{env.get('VOBIZ_TRUNK_ID')}/",
    "/SIPTrunk/",
    "/Endpoint/",
    "/Carrier/",
    "/Account/",
]

for ep in trunk_endpoints:
    try:
        r = requests.get(f"{base}{ep}", auth=(aid, tok), timeout=10)
        print(f"Vobiz API {ep}: status {r.status_code}, response: {r.text[:250]}")
    except Exception as e:
        print(f"Vobiz API {ep} error: {e}")

# 2. Check FreeSWITCH status
try:
    cmd = "docker exec leadgen-freeswitch fs_cli -x 'sofia status'"
    out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
    print("\n=== FreeSWITCH Sofia Status ===")
    print(out)
except Exception as e:
    print("\nFreeSWITCH error:", e)

# 3. Check FreeSWITCH gateways
try:
    cmd = "docker exec leadgen-freeswitch fs_cli -x 'sofia status gateway'"
    out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
    print("\n=== FreeSWITCH Sofia Gateways ===")
    print(out)
except Exception as e:
    print("\nFreeSWITCH gateway error:", e)
