import asyncio
import os
import json

os.environ['OMNIROUTE_ENABLED'] = '1'
os.environ['OMNIROUTE_AGENTS'] = '1'

API_KEY = os.getenv('OMNIROUTE_API_KEY')
BASE_URL = 'http://127.0.0.1:20128'

import httpx

# 42 FLAGSHIP MODELS - ONE PER PROVIDER
FLAGSHIP_MODELS = [
    # Chinese Providers (21)
    ("siliconflow", "siliconflow/deepseek-ai/DeepSeek-V4-Pro", "Chinese Flagship"),
    ("volcengine", "volcengine/doubao-seed-2.0-pro", "Chinese Flagship"),
    ("zai", "zai/glm-5.2", "Chinese Flagship"),
    ("meituan", "meituan/longcat-2.0", "Chinese Flagship"),
    ("alibaba", "alibaba/qwen3.7-max", "Chinese Flagship"),
    ("baidu", "baidu/ernie-5.1", "Chinese Flagship"),
    ("tencent", "tencent/hunyuan-hy3", "Chinese Flagship"),
    ("minimax", "minimax/minimax-m3", "Chinese Flagship"),
    ("kimi", "kimi/kimi-k3", "Chinese Flagship"),
    ("deepseek", "deepseek/deepseek-v4-flash", "Chinese Flagship"),
    ("iflytek", "iflytek/spark-x2", "Chinese Flagship"),
    ("streamlake", "streamlake/kat-coder-air-v2.5", "Chinese Flagship"),
    ("telecom", "telecom/telechat3", "Chinese Flagship"),
    ("sensetime", "sensetime/sensenova-6.7-flash", "Chinese Flagship"),
    ("dmxapi", "dmxapi/deepseek-v4", "Chinese Flagship"),
    ("lingyi", "lingyi/yi-lightning", "Chinese Flagship"),
    ("chinamobile", "chinamobile/moma-300b", "Chinese Flagship"),
    ("dataeye", "dataeye/aggregator", "Chinese Flagship"),
    ("kunlun", "kunlun/matrix-3.5", "Chinese Flagship"),
    ("360ai", "360ai/360-ai-4.0", "Chinese Flagship"),
    ("ppio", "ppio/deepseek-v4-flash", "Chinese Flagship"),
    
    # International Providers (21)
    ("gemini", "gemini/gemini-3.5-flash", "International Flagship"),
    ("groq", "groq/llama-3.3-70b-versatile", "International Flagship"),
    ("openrouter", "openrouter/openrouter/auto", "International Flagship"),
    ("cloudflare", "cfr/@cf/meta/llama-3.3-70b-instruct-fp8-fast", "International Flagship"),
    ("github", "github/gpt-4o", "International Flagship"),
    ("nvidia", "nvidia/nvidia/nemotron-3-super-120b-a12b", "International Flagship"),
    ("cerebras", "cerebras/llama-3.3-70b", "International Flagship"),
    ("mistral", "mistral/mistral-large-latest", "International Flagship"),
    ("cohere", "cohere/command-r-plus", "International Flagship"),
    ("huggingface", "huggingface/Qwen/Qwen3.5-122B", "International Flagship"),
    ("together", "together/llama-3.3-70b", "International Flagship"),
    ("llm7", "llm7/deepseek-v4-flash", "International Flagship"),
    ("ollama-cloud", "ollama-cloud/llama-3.3-70b", "International Flagship"),
    ("aws", "aws/claude-sonnet-4", "International Flagship"),
    ("anyscale", "anyscale/llama-3.1-405b", "International Flagship"),
    ("ncompass", "ncompass/various", "International Flagship"),
    ("digitalocean", "digitalocean/genai", "International Flagship"),
    ("fireworks", "fireworks/llama-3.3-70b", "International Flagship"),
    ("octoai", "octoai/various", "International Flagship"),
    ("unify", "unify/various", "International Flagship"),
    ("deepinfra", "deepinfra/various", "International Flagship"),
]

results = {}

async def main():
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    working = []
    not_working = []
    
    for provider, model, category in FLAGSHIP_MODELS:
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
                    working.append((provider, model, category, resolved))
                    print(f"OK {category} {provider} {model} -> {resolved}")
                else:
                    error = response.text[:80]
                    not_working.append((provider, model, status, error))
                    print(f"FAIL {category} {provider} {model} {status}: {error[:50]}")
                    
        except httpx.TimeoutException:
            not_working.append((provider, model, "TIMEOUT", ""))
            print(f"TIMEOUT {category} {provider} {model}")
        except Exception as e:
            not_working.append((provider, model, "ERROR", str(e)))
            print(f"ERROR {category} {provider} {model} {type(e).__name__}")
    
    print(f"RESULTS")
    print(f"Working: {len(working)}")
    print(f"Not working: {len(not_working)}")
    
    chinese_working = [w for w in working if w[2] == "Chinese Flagship"]
    intl_working = [w for w in working if w[2] == "International Flagship"]
    
    print(f"Chinese working: {len(chinese_working)}")
    for p, m, c, r in chinese_working:
        print(f"  {p} {m}")
    
    print(f"International working: {len(intl_working)}")
    for p, m, c, r in intl_working:
        print(f"  {p} {m}")

asyncio.run(main())
