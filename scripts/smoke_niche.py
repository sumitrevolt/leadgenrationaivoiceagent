"""Quick smoke test for niche_db endpoints — run via SSH on VPS."""

import json
import sys
import urllib.request

base = "http://localhost:8000"

checks = [
    ("/health", None, lambda d: d.get("environment") == "production"),
    (
        "/api/niche/schema/home_loans",
        None,
        lambda d: d.get("ok") and len(d.get("schema", {}).get("pre_call_fields", [])) > 0,
    ),
    ("/api/niche/voice-niches", None, lambda d: d.get("ok") and d.get("total", 0) > 0),
]

all_ok = True
for path, _, check in checks:
    try:
        with urllib.request.urlopen(base + path, timeout=5) as r:
            d = json.loads(r.read())
        ok = check(d)
        print(f"{'OK' if ok else 'FAIL'} {path} -> {json.dumps(d)[:120]}")
        if not ok:
            all_ok = False
    except Exception as e:
        print(f"ERROR {path}: {e}")
        all_ok = False

sys.exit(0 if all_ok else 1)
