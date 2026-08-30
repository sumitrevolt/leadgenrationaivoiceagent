import os
from pathlib import Path

env = {}
for p in ["/opt/leadgen/.env"]:
    if os.path.exists(p):
        for line in Path(p).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("\"'")

for k, v in env.items():
    if "VOBIZ" in k or "TELEPHONY" in k or "SIP" in k or "CALLER" in k or "TRUNK" in k:
        if "TOKEN" in k or "PASS" in k or "KEY" in k:
            masked = v[:3] + "..." + v[-3:] if len(v) > 6 else "***"
            print(f"{k} = {masked}")
        else:
            print(f"{k} = {v}")
