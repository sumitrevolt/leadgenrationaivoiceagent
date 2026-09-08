import asyncio
import os
import json

os.environ['OMNIROUTE_ENABLED'] = '1'
os.environ['OMNIROUTE_AGENTS'] = '1'

API_KEY = os.getenv('OMNIROUTE_API_KEY')
BASE_URL = 'http://127.0.0.1:20128'

import httpx

FREE_MODELS = [
    ("github", "github/claude-sonnet-5"),
    ("github", "github/gpt-5.5"),
    ("github", "github/gpt-5.4"),
    ("github", "github/claude-opus-4.8"),
    ("pollinations", "pollinations/claude-sonnet-5"),
    ("opencode", "opencode/big-pickle"),
    ("opencode", "opencode/deepseek-v4-flash-free"),
    ("openai-compatible-chat-afc47780-f6b2-45d5-8b2b-df426cf305a7", "cfr/@cf/meta/llama-3.3-70b-instruct-fp8-fast"),
    ("openai-compatible-chat-afc47780-f6b2-45d5-8b2b-df426cf305a7", "cfr/@cf/meta/llama-4-scout-17b-16e-instruct"),
    ("groq", "groq/openai/gpt-oss-120b"),
    ("groq", "groq/openai/gpt-oss-20b"),
    ("groq", "groq/compound"),
    ("groq", "groq/compound-mini"),
    ("groq", "groq/llama-3.3-70b-versatile"),
    ("groq", "groq/llama-3.1-8b-instant"),
    ("nvidia", "nvidia/nvidia/nemotron-3-super-120b-a12b"),
    ("nvidia", "nvidia/meta/llama-3.3-70b-instruct"),
    ("nvidia", "nvidia/z-ai/glm-5.2"),
    ("nvidia", "nvidia/nvidia/nemotron-3.5-lightning-30b-a3b"),
    ("nvidia", "nvidia/deepseek-ai/deepseek-v4-flash"),
    ("nvidia", "nvidia/deepseek-ai/deepseek-v4-pro"),
    ("nvidia", "nvidia/moonshotai/kimi-k3"),
    ("nvidia", "nvidia/qwen/qwen3.8-2.4t-a95b"),
    ("nvidia", "nvidia/qwen/qwen3-coder-next"),
    ("nvidia", "nvidia/qwen/qwen3.5-72b"),
    ("nvidia", "nvidia/mistralai/mistral-large-latest"),
    ("nvidia", "nvidia/meta/llama-3.1-405b-instruct"),
    ("nvidia", "nvidia/meta/llama-3.1-70b-instruct"),
    ("nvidia", "nvidia/meta/llama-3.1-8b-instruct"),
    ("nvidia", "nvidia/nvidia/llama-3.1-nemotron-70b-instruct"),
    ("nvidia", "nvidia/nvidia/nemotron-4-mini-hf"),
    ("nvidia", "nvidia/google/gemma-2-27b-it"),
    ("nvidia", "nvidia/google/gemma-2-9b-it"),
    ("nvidia", "nvidia/google/gemma-2-2b-it"),
    ("nvidia", "nvidia/google/codegemma-7b"),
    ("nvidia", "nvidia/mistralai/mistral-7b-instruct-v0.3"),
    ("nvidia", "nvidia/mistralai/mixtral-8x7b-instruct-v0.1"),
    ("nvidia", "nvidia/mistralai/mixtral-8x22b-instruct-v0.1"),
    ("nvidia", "nvidia/databricks/dbrx-instruct"),
    ("nvidia", "nvidia/google/gemini-2.5-flash"),
    ("nvidia", "nvidia/google/gemini-3.1-pro-high"),
    ("nvidia", "nvidia/anthropic/claude-sonnet-5"),
    ("nvidia", "nvidia/anthropic/claude-opus-4-6-thinking"),
    ("nvidia", "nvidia/openai/gpt-oss-120b"),
    ("nvidia", "nvidia/openai/gpt-5.5"),
    ("nvidia", "nvidia/minimaxai/minimax-m3"),
    ("nvidia", "nvidia/qwen/qwen3.5-2.4t-a95b"),
    ("openrouter", "openrouter/meta-llama/llama-3.3-70b-instruct:free"),
    ("openrouter", "openrouter/deepseek/deepseek-v4-pro-0813:free"),
    ("openrouter", "openrouter/deepseek/deepseek-v4-flash-0731:free"),
    ("openrouter", "openrouter/nvidia/nemotron-3.5-lightning:free"),
    ("openrouter", "openrouter/minimaxai/minimax-m2.7:free"),
    ("openrouter", "openrouter/qwen/qwen3.5-72b:free"),
    ("openrouter", "openrouter/qwen/qwen3-coder-next:free"),
    ("openrouter", "openrouter/anthropic/claude-sonnet-5:free"),
    ("openrouter", "openrouter/openai/gpt-5.4:free"),
    ("openrouter", "openrouter/google/gemini-3.5-flash:free"),
    ("openrouter", "openrouter/google/gemini-3.1-pro-high:free"),
    ("gemini", "gemini/gemini-flash-latest"),
    ("gemini", "gemini/gemini-3.5-flash"),
    ("gemini", "gemini/gemini-3.5-flash-lite"),
    ("gemini", "gemini/gemini-3.1-flash-lite"),
    ("gemini", "gemini/gemini-3.6-flash"),
    ("gemini", "gemini/gemini-3.1-pro-preview"),
    ("zai", "zai/glm-4.7-flash"),
    ("zai", "zai/glm-4.7-flash-high"),
    ("zai", "zai/glm-5"),
    ("zai", "zai/glm-5-high"),
    ("kiro", "kiro/claude-sonnet-5"),
    ("kiro", "kiro/glm-5"),
    ("kiro", "kiro/claude-haiku-4.5"),
    ("amazon-q", "amazon-q/anthropic/claude-sonnet-5"),
    ("amazon-q", "amazon-q/meta/llama-3.3-70b-instruct"),
    ("deepseek", "deepseek/deepseek-v4-flash"),
    ("deepseek", "deepseek/deepseek-v4-pro"),
    ("claude", "claude/claude-sonnet-5"),
    ("claude", "claude/claude-opus-4-6-thinking"),
    ("mistral", "mistral/mistral-small-latest"),
    ("mistral", "mistral/mistral-large-latest"),
    ("mistral", "mistral/mistral-code-latest"),
    ("cohere", "cohere/command-a-03-2025"),
    ("cohere", "cohere/c4ai-aya-expanse-32b"),
    ("huggingface", "huggingface/Qwen/Qwen3.8-2.4T-A95B"),
    ("huggingface", "huggingface/deepseek-ai/DeepSeek-V4-Flash"),
    ("huggingface", "huggingface/deepseek-ai/DeepSeek-V4-Pro"),
    ("huggingface", "huggingface/moonshotai/Kimi-K3"),
    ("huggingface", "huggingface/moonshotai/Kimi-K2.7-Code"),
    ("huggingface", "huggingface/Qwen/Qwen3-Coder-Next"),
    ("huggingface", "huggingface/MiniMaxAI/MiniMax-M3"),
    ("huggingface", "huggingface/zai-org/GLM-5.2"),
    ("huggingface", "huggingface/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16"),
    ("ollama-cloud", "ollama-cloud/minimax-m3"),
    ("ollama-cloud", "ollama-cloud/nemotron-3-ultra"),
    ("sambanova", "sambanova/Meta-Llama-3.3-70B-Instruct"),
    ("api-airforce", "api-airforce/mistral-large-latest"),
    ("bazaarlink", "bazaarlink/auto:free"),
]

results = {}

async def main():
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    working = []
    not_working = []
    
    for provider, model in FREE_MODELS:
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
                    working.append((provider, model, resolved))
                    print(f"OK {provider} {model} -> {resolved}")
                else:
                    error = response.text[:80]
                    not_working.append((provider, model, status, error))
                    print(f"FAIL {provider} {model} {status}: {error[:50]}")
                    
        except httpx.TimeoutException:
            not_working.append((provider, model, "TIMEOUT", ""))
            print(f"TIMEOUT {provider} {model}")
        except Exception as e:
            not_working.append((provider, model, "ERROR", str(e)))
            print(f"ERROR {provider} {model} {type(e).__name__}")
    
    print(f"RESULTS")
    print(f"Working: {len(working)}")
    print(f"Not working: {len(not_working)}")
    
    free_providers = ['github', 'opencode', 'pollinations', 'openai-compatible-chat-afc47780-f6b2-45d5-8b2b-df426cf305a7', 'bazaarlink', 'groq', 'gemini', 'huggingface', 'openrouter']
    
    free_working = [(p, m, r) for p, m, r in working if p in free_providers]
    paid_working = [(p, m, r) for p, m, r in working if p not in free_providers]
    
    print(f"Free working: {len(free_working)}")
    for p, m, r in free_working:
        print(f"FREE {p} {m}")
    
    print(f"Paid working: {len(paid_working)}")
    for p, m, r in paid_working:
        print(f"PAID {p} {m}")

asyncio.run(main())
