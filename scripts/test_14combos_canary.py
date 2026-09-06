import urllib.request
import json
import os

OMNI_URL = "http://127.0.0.1:20128/v1/chat/completions"

# Test Combos
test_combos = [
    ("leadsgen combo 1", "admin@leadsgenai.in", "sk-451bbb616f5d6318-3774cf-66f99aef"),
    ("leadsgen combo 6", "sumit20016@gmail.com", "sk-451bbb616f5d6318-3f3851-51532253"),
    ("leadsgen combo 13", "CLI Auto-Key", "sk-1946b7774f91a2d1-c4f051-14cee779"),
]

print("=== Running Canary Inference Test Across 14-Combo x 42-Provider Setup ===")

for combo_name, email, api_key in test_combos:
    print(f"\nTesting '{combo_name}' (Dedicated: {email})...")
    req_body = {
        "model": combo_name,
        "messages": [
            {"role": "user", "content": "Respond with single word: OK"}
        ],
        "max_tokens": 10,
        "temperature": 0.1
    }
    data = json.dumps(req_body).encode("utf-8")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    req = urllib.request.Request(OMNI_URL, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body)
            msg = parsed["choices"][0]["message"]["content"].strip()
            print(f"  [SUCCESS 200] Model: {parsed.get('model')} | Content: {msg[:40]}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        print(f"  [FAIL HTTP {e.code}]: {err_body[:200]}")
    except Exception as e:
        print(f"  [ERROR]: {e}")

print("\n=== Canary Test Complete ===")
