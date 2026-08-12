import json
import sys
import urllib.request

url = "https://leadsgenai.in/health"
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        d = json.loads(r.read())
        print("health:", d.get("environment"), d.get("status", "ok"))
        print("version:", d.get("version", "?"))
except Exception as e:
    print("FAIL:", e)
    sys.exit(1)
