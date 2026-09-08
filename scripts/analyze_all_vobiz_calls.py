import requests, json, os
from pathlib import Path

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

r = requests.get(f"{base}/Call/?limit=150", auth=(aid, tok), timeout=25)
if r.status_code == 200:
    data = r.json()
    objects = data.get("objects", [])
    print(f"Total objects returned: {len(objects)}")
    
    answered = [c for c in objects if c.get("bill_duration", 0) > 0 or c.get("hangup_cause") not in ("USER_BUSY", "CALL_REJECTED")]
    print(f"Total non-busy / answered: {len(answered)}")
    
    print("\n--- Last 10 calls ---")
    for c in objects[:10]:
        print(f"{c.get('created_at')} | {c.get('from_number')} -> {c.get('to_number')} | state: {c.get('call_state')} | cause: {c.get('hangup_cause')} | cause_name: {c.get('hangup_cause_name')} | dur: {c.get('bill_duration')}")

    print("\n--- Any calls with duration > 0 or answered in all history ---")
    for c in objects:
        dur = c.get("bill_duration", 0)
        cause = c.get("hangup_cause")
        if dur > 0 or cause not in ("USER_BUSY",):
            print(f"{c.get('created_at')} | {c.get('from_number')} -> {c.get('to_number')} | cause: {cause} | dur: {dur}")
