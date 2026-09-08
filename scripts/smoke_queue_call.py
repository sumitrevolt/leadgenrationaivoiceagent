"""Quick smoke: verify /api/niche/queue-call endpoint is wired (401 = auth guard working)."""

import json
import sys
import urllib.request

BASE = "http://localhost:8000"

tests = [
    ("GET  /api/niche/schema/home_loans", f"{BASE}/api/niche/schema/home_loans", "GET", None),
    ("GET  /api/niche/voice-niches", f"{BASE}/api/niche/voice-niches", "GET", None),
    (
        "POST /api/niche/queue-call (no auth → 401/422)",
        f"{BASE}/api/niche/queue-call",
        "POST",
        json.dumps({"client_id": "test", "niche": "home_loans"}).encode(),
    ),
]

all_ok = True
for label, url, method, data in tests:
    try:
        req = urllib.request.Request(
            url, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            body = json.loads(resp.read())
            code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
            body = {}
        print(f"[{'OK' if code in (200, 401, 422) else 'FAIL'}] {label} → HTTP {code}")
        if method == "GET" and code == 200:
            if "ok" in body and not body.get("ok"):
                print(f"     WARNING: ok=False — {body.get('error')}")
    except Exception as e:
        print(f"[FAIL] {label} → {e}")
        all_ok = False

# Also check TelecallerBrain niche schema injection via logs
try:
    import subprocess

    logs = subprocess.check_output(
        ["docker", "logs", "leadgen_app", "--tail", "50"], stderr=subprocess.STDOUT, text=True
    )
    if "niche_database schema loaded" in logs or "niche_db" in logs.lower():
        print("[OK] niche_database schema injection: log evidence found")
    else:
        print("[INFO] niche_database schema injection: no log yet (first call will trigger)")
except Exception as e:
    print(f"[INFO] docker logs check: {e}")

print("SMOKE DONE")
