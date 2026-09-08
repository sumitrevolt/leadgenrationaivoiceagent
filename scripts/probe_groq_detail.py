"""Groq raw detail probe — inspect the full response object + finish_reason.

gpt-oss models are REASONING models: they spend tokens in `reasoning` and can
return empty content when max_tokens is too low. This prints the evidence.
"""

import asyncio
import sys
import time

sys.path.insert(0, "/app")

from app.voice_agent import free_ai  # noqa: E402


async def main() -> None:
    client = free_ai._client("groq")
    if client is None:
        print("GROQ_DETAIL: no client")
        return

    # Test 1: gpt-oss-20b with tiny max_tokens (current prod config behaviour)
    t0 = time.time()
    r1 = await asyncio.wait_for(
        client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": "Reply with exactly: GROQ_OK"}],
            max_tokens=10,
        ),
        timeout=20,
    )
    c1 = r1.choices[0]
    print(
        f"T1_oss20b_tok10 ms={int((time.time() - t0) * 1000)} "
        f"finish={c1.finish_reason!r} content={(c1.message.content or '')[:30]!r} "
        f"reasoning={getattr(c1.message, 'reasoning', None) and str(c1.message.reasoning)[:40]!r}"
    )

    # Test 2: same model with generous max_tokens
    t1 = time.time()
    r2 = await asyncio.wait_for(
        client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": "Reply with exactly: GROQ_OK"}],
            max_tokens=512,
        ),
        timeout=25,
    )
    c2 = r2.choices[0]
    print(
        f"T2_oss20b_tok512 ms={int((time.time() - t1) * 1000)} "
        f"finish={c2.finish_reason!r} content={(c2.message.content or '')[:30]!r}"
    )

    # Test 3: llama-4 scout (non-reasoning fallback model)
    t2 = time.time()
    try:
        r3 = await asyncio.wait_for(
            client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{"role": "user", "content": "Reply with exactly: GROQ_OK"}],
                max_tokens=10,
            ),
            timeout=20,
        )
        c3 = r3.choices[0]
        print(
            f"T3_scout_tok10 ms={int((time.time() - t2) * 1000)} "
            f"finish={c3.finish_reason!r} content={(c3.message.content or '')[:30]!r}"
        )
    except Exception as e:
        print(f"T3_scout ERR {type(e).__name__} {str(e)[:80]}")


asyncio.run(main())
