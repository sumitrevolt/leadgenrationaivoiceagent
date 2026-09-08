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

endpoints = [
    "/Number/",
    "/PhoneNumber/",
    "/IncomingCarrier/",
    "/Subaccount/",
    "/Application/",
]

for ep in endpoints:
    try:
        r = requests.get(f"{base}{ep}", auth=(aid, tok), timeout=15)
        print(f"{ep}: status {r.status_code}")
        if r.status_code == 200:
            print(f"  Data: {r.text[:300]}")
    except Exception as e:
        print(f"{ep}: error {e}")
