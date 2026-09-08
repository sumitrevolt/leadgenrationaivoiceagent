"""Check GEMINI_API_KEY and set GEMINI_PRIMARY on VPS."""

import os
import re

env_file = "/opt/leadgen/.env"
with open(env_file) as f:
    content = f.read()

# Check GEMINI_API_KEY
gemini_key = ""
for line in content.splitlines():
    if line.startswith("GEMINI_API_KEY="):
        gemini_key = line.split("=", 1)[1].strip()
        break

print(f"GEMINI_API_KEY: {f'SET (len={len(gemini_key)})' if gemini_key else 'NOT_SET'}")

# Check current GEMINI_PRIMARY
gp_match = re.search(r"^GEMINI_PRIMARY=(.+)$", content, re.MULTILINE)
print(f"GEMINI_PRIMARY: {gp_match.group(1) if gp_match else 'NOT_SET'}")

# If key is set, enable GEMINI_PRIMARY=true
if gemini_key:
    if gp_match:
        content = re.sub(r"^GEMINI_PRIMARY=.*$", "GEMINI_PRIMARY=true", content, flags=re.MULTILINE)
        print("GEMINI_PRIMARY: updated to true")
    else:
        content += "\nGEMINI_PRIMARY=true\n"
        print("GEMINI_PRIMARY: added as true")
    with open(env_file, "w") as f:
        f.write(content)
    print(".env: written")
else:
    print(
        "SKIP: GEMINI_API_KEY not set — cannot enable Gemini as primary (will fail on every call)"
    )
    print("ACTION: Set GEMINI_API_KEY in VPS .env first, then re-run this script")
