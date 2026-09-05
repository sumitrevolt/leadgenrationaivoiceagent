import urllib.request
import sys

try:
    res = urllib.request.urlopen("http://72.61.245.204:3110/_liveness", timeout=10)
    if res.status not in (200, 204, 201):
        print(f"[ALERT] BUZZ RELAY: Liveness returned HTTP {res.status}!")
        sys.exit(1)
    print("[OK] BUZZ RELAY HEALTHY (HTTP 200)")
except Exception as e:
    print(f"[DOWN] BUZZ RELAY DOWN! Liveness probe failed: {e}")
    sys.exit(1)
