"""Test Gemini key with paid-tier models to find what works."""

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

if not key:
    print("NO_KEY")
    exit(1)

models = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite-preview-06-17",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

for model in models:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    )
    body = json.dumps({"contents": [{"parts": [{"text": "hi"}]}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "?")
        )
        print(f"OK: {model} -> {text[:60]}")
        break
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode()).get("error", {}).get("message", "?")[:80]
        print(f"FAIL {e.code}: {model} -> {err}")
    except Exception as e:
        print(f"ERR: {model} -> {e}")
