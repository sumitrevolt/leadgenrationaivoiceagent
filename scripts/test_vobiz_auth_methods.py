import os
from pathlib import Path

import requests

# Load .env
env = {}
for p in ["/opt/leadgen/.env", ".env"]:
    if os.path.exists(p):
        for line in Path(p).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("\"'")
        break

aid = env.get("VOBIZ_AUTH_ID")
tok = env.get("VOBIZ_AUTH_TOKEN")
base = f"https://api.vobiz.ai/api/v1/Account/{aid}"

print(f"AID: {aid}")

# Test 1: Basic Auth
try:
    r1 = requests.get(f"{base}/", auth=(aid, tok), timeout=10)
    print(f"Basic Auth status: {r1.status_code}, response: {r1.text[:200]}")
except Exception as e:
    print(f"Basic Auth error: {e}")

# Test 2: X-Auth-ID headers
try:
    h2 = {"X-Auth-ID": aid, "X-Auth-Token": tok, "Content-Type": "application/json"}
    r2 = requests.get(f"{base}/", headers=h2, timeout=10)
    print(f"Headers Auth status: {r2.status_code}, response: {r2.text[:200]}")
except Exception as e:
    print(f"Headers Auth error: {e}")

# Test 3: Calls list with Basic Auth
try:
    r3 = requests.get(f"{base}/Call/?limit=5", auth=(aid, tok), timeout=10)
    print(f"Calls (Basic Auth) status: {r3.status_code}")
    if r3.status_code == 200:
        data = r3.json()
        print(f"Total calls: {data.get('meta', {}).get('total_count')}")
        for c in data.get("objects", []):
            print(
                f"  {c.get('created_at')} | {c.get('from_number')} -> {c.get('to_number')} | state: {c.get('call_state')} | cause: {c.get('hangup_cause')} | bill_dur: {c.get('bill_duration')}"
            )
except Exception as e:
    print(f"Calls error: {e}")
