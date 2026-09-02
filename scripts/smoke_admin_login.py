"""Smoke: admin-login page not 429."""

import sys
import urllib.request

url = "https://leadsgenai.in/app/admin-login"
req = urllib.request.Request(url, headers={"User-Agent": "smoke/1"})
with urllib.request.urlopen(req, timeout=30) as r:
    body = r.read(500).decode("utf-8", errors="replace")
    print(f"status={r.status} len={len(body)}")
    print(body[:200])
    if r.status != 200:
        sys.exit(1)
    if "429" in body or "rate limit" in body.lower():
        print("FAIL: still rate limited")
        sys.exit(1)
    if "<html" not in body.lower() and "<!doctype" not in body.lower():
        print("WARN: not HTML?")
    print("OK")
