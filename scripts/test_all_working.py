import asyncio
import os
import json

os.environ['OMNIROUTE_ENABLED'] = '1'
os.environ['OMNIROUTE_AGENTS'] = '1'

API_KEY = os.getenv('OMNIROUTE_API_KEY')
BASE_URL = 'http://127.0.0.1:20128'

import httpx

# ALL working models from both tests
ALL_WORKING = [
    # Free
    ("github", "github/claude-sonnet-5", "FREE_TIER"),
    ("pollinations", "pollinations/claude-sonnet-5", "FREE_ENDPOINT"),
    ("opencode", "opencode/big-pickle", "FREE_ENDPOINT"),
    ("groq", "groq/openai/gpt-oss-120b", "FREE_PLAN"),
    ("groq", "groq/openai/gpt-oss-20b", "FREE_PLAN"),
    ("gemini", "gemini/gemini-3.5-flash-lite", "FREE_TIER"),
    ("gemini", "gemini/gemini-3.1-flash-lite", "FREE_TIER"),
    ("gemini", "gemini/gemini-3.6-flash", "FREE_TIER"),
    ("gemini", "gemini/gemini-3.1-pro-preview", "FREE_TIER"),
    # Paid
    ("antigravity", "antigravity/gemini-2.5-flash", "PAID"),
    ("antigravity", "antigravity/gemini-3.1-pro-high", "PAID"),
    ("antigravity", "antigravity/claude-opus-4-6-thinking", "PAID"),
    ("antigravity", "antigravity/claude-sonnet-5", "PAID"),
    ("agy", "agy/gemini-3.1-pro-high", "PAID"),
    ("agy", "agy/claude-opus-4-6-thinking", "PAID"),
    ("kiro", "kiro/claude-sonnet-5", "PAID"),
    ("kiro", "kiro/glm-5", "PAID"),
    ("kiro", "kiro/claude-haiku-4.5", "PAID"),
    ("zai", "zai/glm-4.7-flash", "PAID"),
    ("zai", "zai/glm-5", "PAID"),
    ("nvidia", "nvidia/nvidia/nemotron-3-super-120b-a12b", "PAID"),
    ("nvidia", "nvidia/openai/gpt-oss-120b", "PAID"),
]

results = {}

async def main():
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    working = []
    
    for provider, model, cost in ALL_WORKING:
        payload = {
            "model": model,
            "input": [{"role": "user", "content": "OK"}],
            "max_output_tokens": 8,
            "temperature": 0.0
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(f"{BASE_URL}/v1/responses", headers=headers, json=payload)
                
                status = response.status_code
                if status == 200:
                    body = response.json()
                    resolved = body.get('model', '')
                    working.append((provider, model, cost, resolved))
                    print(f"OK {cost} {provider} {model} -> {resolved}")
                else:
                    print(f"FAIL {cost} {provider} {model} {status}")
                    
        except httpx.TimeoutException:
            print(f"TIMEOUT {cost} {provider} {model}")
        except Exception as e:
            print(f"ERROR {cost} {provider} {model} {type(e).__name__}")
    
    print(f"TOTAL WORKING: {len(working)}")
    
    free = [w for w in working if w[2] in ('FREE_TIER', 'FREE_ENDPOINT', 'FREE_PLAN')]
    paid = [w for w in working if w[2] == 'PAID']
    
    print(f"FREE: {len(free)}")
    for p, m, c, r in free:
        print(f"  {c} {p} {m}")
    
    print(f"PAID: {len(paid)}")
    for p, m, c, r in paid:
        print(f"  {c} {p} {m}")

asyncio.run(main())
