import json
import urllib.request

BASE = "http://localhost:8000"
results = {}

for url, method, data in [
    ("/api/niche/schema/home_loans", "GET", None),
    ("/api/niche/voice-niches", "GET", None),
    (
        "/api/niche/queue-call",
        "POST",
        json.dumps({"client_id": "t", "niche": "home_loans"}).encode(),
    ),
]:
    try:
        req = urllib.request.Request(
            BASE + url, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            r = urllib.request.urlopen(req, timeout=5)
            code = r.status
            body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            code = e.code
            body = {}
        results[url] = code
        print(f"{method} {url} -> {code}")
        if code == 200 and "schema" in url:
            s = body.get("schema", {})
            print(
                f"  collect_during: {len(s.get('collect_during', []))}, script_context: {s.get('script_context', '')[:60]}"
            )
    except Exception as e:
        print(f"ERROR {url}: {e}")

print("ALL_DONE")
