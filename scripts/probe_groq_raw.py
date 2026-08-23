"""Raw Groq probe — run inside leadgen_app container.

Checks whether the Groq API actually returns content for gpt-oss-20b, and
times it. Prints 1 line of evidence.
"""

import asyncio
import sys
import time

sys.path.insert(0, "/app")

from app.voice_agent import free_ai  # noqa: E402


async def main() -> None:
    client = free_ai._client("groq")
    if client is None:
        print("RAW_GROQ: no client (key missing)")
        return
    t0 = time.time()
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[{"role": "user", "content": "Reply with exactly: GROQ_OK"}],
                max_tokens=10,
            ),
            timeout=15,
        )
        txt = (resp.choices[0].message.content or "").strip()
        print(f"RAW_GROQ ms={int((time.time() - t0) * 1000)} text={txt[:40]!r}")
    except Exception as e:
        print(f"RAW_GROQ ms={int((time.time() - t0) * 1000)} ERR {type(e).__name__} {str(e)[:80]}")


asyncio.run(main())
