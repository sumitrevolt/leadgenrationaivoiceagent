import json
import subprocess
import sys

ssh = r"C:\PROGRA~1\Git\usr\bin\ssh.exe"
key = r"C:\Users\Ratanshila\.ssh\id_rsa"

# 1. Health check
r1 = subprocess.run(
    [
        ssh,
        "-i",
        key,
        "-o",
        "StrictHostKeyChecking=no",
        "root@72.61.245.204",
        "curl -sf http://localhost:8000/health",
    ],
    capture_output=True,
    text=True,
    timeout=20,
)
try:
    h = json.loads(r1.stdout)
    print(f"Health: {h.get('environment', '?')} | status: {h.get('status', '?')}")
except:
    print("Health raw:", r1.stdout[:200])

# 2. Admin summary — expects 401 (auth required = route is live)
r2 = subprocess.run(
    [
        ssh,
        "-i",
        key,
        "-o",
        "StrictHostKeyChecking=no",
        "root@72.61.245.204",
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/admin/system/summary",
    ],
    capture_output=True,
    text=True,
    timeout=20,
)
code = r2.stdout.strip().strip("'")
print(
    f"/api/admin/system/summary HTTP: {code} ({'OK - auth required (live)' if code in ('401', '403') else 'UNEXPECTED: ' + code})"
)

# 3. Campaign status — also auth-required
r3 = subprocess.run(
    [
        ssh,
        "-i",
        key,
        "-o",
        "StrictHostKeyChecking=no",
        "root@72.61.245.204",
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/admin/campaign/status",
    ],
    capture_output=True,
    text=True,
    timeout=20,
)
code3 = r3.stdout.strip().strip("'")
print(f"/api/admin/campaign/status HTTP: {code3} ({'OK' if code3 in ('401', '403') else code3})")

# 4. TELEPHONY_PROVIDER in .env
r4 = subprocess.run(
    [
        ssh,
        "-i",
        key,
        "-o",
        "StrictHostKeyChecking=no",
        "root@72.61.245.204",
        "grep TELEPHONY_PROVIDER /opt/leadgen/.env",
    ],
    capture_output=True,
    text=True,
    timeout=20,
)
print(f"VPS .env: {r4.stdout.strip() or 'NOT SET'}")
