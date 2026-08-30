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

for call_uuid in ["9f3e1d73-ff47-4f9d-9eda-98e96bc4a5dc", "e1a3e96b-541b-4562-81ee-6efca7307858", "7b6465d1-f0f2-4028-90a2-d2fade749398"]:
    print(f"\n=== Call detail for {call_uuid} ===")
    r = requests.get(f"{base}/Call/{call_uuid}/", auth=(aid, tok), timeout=15)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        for k, v in sorted(d.items()):
            if v not in (None, "", [], {}):
                print(f"  {k}: {v}")
