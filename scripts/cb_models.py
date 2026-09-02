"""List valid Cerebras model ids + show deployed model string (run on VPS)."""

import sys
from pathlib import Path

import requests

env = {}
for line in Path("/opt/leadgen/.env").read_text(errors="ignore").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

key = env.get("CEREBRAS_API_KEY", "")
r = requests.get(
    "https://api.cerebras.ai/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=15
)
print("STATUS", r.status_code)
try:
    for m in r.json().get("data", []):
        print("MODEL:", m.get("id"))
except Exception as e:
    print("ERR", e, r.text[:200])

import app.voice_agent.free_ai as f  # noqa

print("DEPLOYED _CEREBRAS_LLM_MODEL:", f._CEREBRAS_LLM_MODEL)
