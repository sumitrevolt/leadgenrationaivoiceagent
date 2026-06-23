"""test_nvidia_key.py — real-API smoke for the NVIDIA NIM provider.

Confirms the wired NVIDIA NIM entry can reach integrate.api.nvidia.com and return
a completion. Reads NVIDIA_API_KEY from env/.env (via app.config settings).

Usage:
    NVIDIA_API_KEY=nvapi-... python scripts/test_nvidia_key.py
    # or with the key already in .env:
    python scripts/test_nvidia_key.py
"""

import asyncio
import sys


async def main() -> int:
    from app.voice_agent import free_ai

    model = free_ai._NVIDIA_LLM_MODEL
    has_key = free_ai._has_key("nvidia")
    print(f"[nvidia] model={model}  key_present={has_key}")
    if not has_key:
        print("[nvidia] NO KEY — set NVIDIA_API_KEY in env or .env. (provider is inert)")
        return 2

    text, provider = await free_ai.chat_provider(
        "nvidia",
        model,
        "You are a test harness. Reply with exactly: OK",
        [{"role": "user", "content": "Say OK"}],
        max_tokens=16,
        temperature=0.0,
        timeout_s=20.0,
    )
    print(f"[nvidia] provider={provider!r}  reply={text!r}")
    if text:
        print("[nvidia] SMOKE PASS ✅ (real 200 from integrate.api.nvidia.com)")
        return 0
    print("[nvidia] SMOKE FAIL ❌ (empty reply — check key/credits/model id)")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
