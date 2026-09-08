import asyncio
import os
import json

os.environ['OMNIROUTE_ENABLED'] = '1'
os.environ['OMNIROUTE_AGENTS'] = '1'

API_KEY = os.getenv('OMNIROUTE_API_KEY')
BASE_URL = 'http://127.0.0.1:20128'

import httpx

# 42 FLAGSHIP MODELS - ONE PER PROVIDER (DEDUPLICATED)
FLAGSHIP_MODELS = [
    # Chinese Providers (15)
    {"provider": "siliconflow", "model": "siliconflow/deepseek-ai/DeepSeek-V4-Pro", "name": "DeepSeek-V4-Pro"},
    {"provider": "zai", "model": "zai/glm-5.2", "name": "GLM-5.2"},
    {"provider": "minimax", "model": "minimax/minimax-m3", "name": "MiniMax-M3"},
    {"provider": "kimi", "model": "kimi/kimi-k3", "name": "Kimi-K3"},
    {"provider": "deepseek", "model": "deepseek/deepseek-v4-flash", "name": "DeepSeek-V4-Flash"},
    {"provider": "iflytek", "model": "iflytek/spark-x2", "name": "Spark-X2"},
    {"provider": "streamlake", "model": "streamlake/kat-coder-air-v2.5", "name": "KAT-Coder-Air-V2.5"},
    {"provider": "telecom", "model": "telecom/telechat3", "name": "TeleChat3"},
    {"provider": "sensetime", "model": "sensetime/sensenova-6.7-flash", "name": "SenseNova-6.7-Flash"},
    {"provider": "meituan", "model": "meituan/longcat-2.0", "name": "LongCat-2.0"},
    {"provider": "alibaba", "model": "alibaba/qwen3.7-max", "name": "Qwen3.7-Max"},
    {"provider": "baidu", "model": "baidu/ernie-5.1", "name": "ERNIE-5.1"},
    {"provider": "tencent", "model": "tencent/hunyuan-hy3", "name": "Hunyuan-Hy3"},
    {"provider": "lingyi", "model": "lingyi/yi-lightning", "name": "Yi-Lightning"},
    {"provider": "chinamobile", "model": "chinamobile/moma-300b", "name": "MoMA-300B"},
    
    # International Providers (27)
    {"provider": "gemini", "model": "gemini/gemini-3.5-flash", "name": "Gemini-3.5-Flash"},
    {"provider": "groq", "model": "groq/openai/gpt-oss-120b", "name": "GPT-OSS-120B"},
    {"provider": "openrouter", "model": "openrouter/openrouter/auto", "name": "Auto-Router"},
    {"provider": "github", "model": "github/gpt-4o", "name": "GPT-4o"},
    {"provider": "nvidia", "model": "nvidia/nvidia/nemotron-3-super-120b-a12b", "name": "Nemotron-3-Super-120B"},
    {"provider": "cerebras", "model": "cerebras/llama-3.3-70b", "name": "Llama-3.3-70B-Cerebras"},
    {"provider": "mistral", "model": "mistral/mistral-large-latest", "name": "Mistral-Large-3"},
    {"provider": "cohere", "model": "cohere/command-r-plus", "name": "Command-R+"},
    {"provider": "huggingface", "model": "huggingface/Qwen/Qwen3.5-122B", "name": "Qwen-3.5-122B"},
    {"provider": "llm7", "model": "llm7/deepseek-v4-flash", "name": "DeepSeek-V4-Flash-LLM7"},
    {"provider": "ollama-cloud", "model": "ollama-cloud/llama-3.3-70b", "name": "Llama-3.3-70B-Ollama"},
    {"provider": "nous", "model": "nous/hermes-4", "name": "Hermes-4"},
    {"provider": "hetzner", "model": "hetzner/qwen3.6-35b-a3b", "name": "Qwen3.6-35B-A3B"},
    {"provider": "pollinations", "model": "pollinations/claude-sonnet-5", "name": "Claude-Sonnet-5-Pollinations"},
    {"provider": "modelscope", "model": "modelscope/qwen-3.5-122b", "name": "Qwen-3.5-122B-ModelScope"},
    {"provider": "aionlabs", "model": "aionlabs/llama-3.3-70b", "name": "Llama-3.3-70B-Aion"},
    {"provider": "inference", "model": "inference/deepseek-r1", "name": "DeepSeek-R1-Inference"},
    {"provider": "requesty", "model": "requesty/llama-3.3-70b", "name": "Llama-3.3-70B-Requesty"},
    {"provider": "venice", "model": "venice/llama-3.1-405b", "name": "Llama-3.1-405B-Venice"},
    {"provider": "together", "model": "together/llama-3.3-70b", "name": "Llama-3.3-70B-Together"},
    {"provider": "fireworks", "model": "fireworks/llama-3.3-70b", "name": "Llama-3.3-70B-Fireworks"},
    {"provider": "sambanova", "model": "sambanova/llama-3.3-70b", "name": "Llama-3.3-70B-SambaNova"},
    {"provider": "hyperbolic", "model": "hyperbolic/llama-3.3-70b", "name": "Llama-3.3-70B-Hyperbolic"},
    {"provider": "novita", "model": "novita/llama-3.3-70b", "name": "Llama-3.3-70B-Novita"},
    {"provider": "scaleway", "model": "scaleway/llama-3.3-70b", "name": "Llama-3.3-70B-Scaleway"},
    {"provider": "friendli", "model": "friendli/llama-3.3-70b", "name": "Llama-3.3-70B-Friendli"},
    {"provider": "deepinfra", "model": "deepinfra/llama-3.3-70b", "name": "Llama-3.3-70B-DeepInfra"},
]

COMBOS = [
    "leadgen-coding-primary",
    "leadgen-coding-fast",
    "leadgen-agent-ops",
    "leadgen-governor-review",
    "leadgen-repo-analysis",
    "leadgen-test-generation",
    "leadgen-prospect-enrich",
    "leadgen-outreach-email",
    "leadgen-marketing-content",
    "leadgen-seo-keyword",
    "leadgen-swara-live",
    "leadgen-free-first",
]

async def main():
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    # Get existing combos
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{BASE_URL}/api/combos", headers=headers)
        combos_data = resp.json().get('combos', [])
        
        # Create a map of combo name to id
        combo_map = {c['name']: c['id'] for c in combos_data}
        
        print(f"Found {len(combos_data)} combos")
        
        # Update each combo
        for combo_name in COMBOS:
            if combo_name not in combo_map:
                print(f"  Combo '{combo_name}' not found, skipping")
                continue
            
            combo_id = combo_map[combo_name]
            
            # Build models array
            models = []
            for i, m in enumerate(FLAGSHIP_MODELS):
                models.append({
                    "id": f"{combo_name}-model-{i+1}-{m['provider']}",
                    "kind": "model",
                    "model": m['model'],
                    "providerId": m['provider'],
                    "weight": 0,
                    "label": m['name']
                })
            
            # Update combo
            update_data = {
                "models": models,
                "strategy": "priority",
                "config": {
                    "maxRetries": 2,
                    "retryDelayMs": 1000,
                    "handoffThreshold": 0.85,
                    "trackMetrics": True
                }
            }
            
            resp = await client.put(
                f"{BASE_URL}/api/combos/{combo_id}",
                headers=headers,
                json=update_data
            )
            
            if resp.status_code == 200:
                print(f"  ✅ {combo_name}: {len(models)} models updated")
            else:
                print(f"  ❌ {combo_name}: {resp.status_code} - {resp.text[:100]}")
        
        print("\n✅ All combos updated with 42 flagship models!")

asyncio.run(main())
