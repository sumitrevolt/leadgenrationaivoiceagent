"""Test GEMINI_API_KEY from VPS .env against Generative Language API."""

import json
import os
import urllib.error
import urllib.request

env_file = "/opt/leadgen/.env"
key = ""
with open(env_file) as f:
    for line in f:
        if line.startswith("GEMINI_API_KEY="):
            key = line.strip().split("=", 1)[1]
            break

print(f"Key length: {len(key)}, prefix: {key[:8] if key else 'NONE'}")

if not key:
    print("RESULT: NO_KEY")
    exit(1)

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={key}"
body = json.dumps({"contents": [{"parts": [{"text": "Reply with just: hello"}]}]}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    print(f"RESULT: OK — reply: {text[:80]}")
except urllib.error.HTTPError as e:
    body_err = e.read().decode()
    err_msg = json.loads(body_err).get("error", {}).get("message", body_err[:120])
    print(f"RESULT: HTTP_{e.code} — {err_msg}")
except Exception as e:
    print(f"RESULT: ERROR — {e}")
