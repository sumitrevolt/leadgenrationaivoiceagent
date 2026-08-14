"""Activate Gemini as primary brain on VPS. Run: python3 scripts/activate_gemini_primary.py"""

import re
import subprocess
import sys

ENV_FILE = "/opt/leadgen/.env"

# 1) Read .env
with open(ENV_FILE) as f:
    content = f.read()

# 2) Set GEMINI_PRIMARY=true
if re.search(r"^GEMINI_PRIMARY=", content, re.MULTILINE):
    content = re.sub(r"^GEMINI_PRIMARY=.*$", "GEMINI_PRIMARY=true", content, flags=re.MULTILINE)
    print("GEMINI_PRIMARY: updated to true")
else:
    content += "\nGEMINI_PRIMARY=true\n"
    print("GEMINI_PRIMARY: added as true")

with open(ENV_FILE, "w") as f:
    f.write(content)
print(".env: written")

# 3) Recreate app container to pick up new env
print("Recreating app container...")
r = subprocess.run(
    [
        "docker",
        "compose",
        "-f",
        "/opt/leadgen/docker-compose.vps.yml",
        "up",
        "-d",
        "--no-deps",
        "app",
    ],
    capture_output=True,
    text=True,
    cwd="/opt/leadgen",
)
out = (r.stdout + r.stderr).strip()
print(out[-300:] if len(out) > 300 else out)
print("APP_RECREATE_EXIT:", r.returncode)

# 4) Quick health check after 20s
import time

time.sleep(20)
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=10) as resp:
        import json

        d = json.loads(resp.read())
        print("HEALTH:", d.get("status"), d.get("environment"))
except Exception as e:
    print("HEALTH_CHECK_ERR:", e)

print("GEMINI_ACTIVATE_DONE")
