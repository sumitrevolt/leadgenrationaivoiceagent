"""Probe: why is the web-call responder falling back to echo?

Run on the VPS:  .venv/bin/python scripts/llm_probe.py
Prints which responder layer works and the exact exception if one fails.
"""

import asyncio
import traceback


async def main() -> None:
    print("=== 1) VoicePipeline ===")
    try:
        from app.voice_agent.pipeline import VoicePipeline

        p = VoicePipeline()
        method = None
        for n in ("respond", "process_text", "handle_text", "chat"):
            fn = getattr(p, n, None)
            if callable(fn):
                method = n
                break
        print("method found:", method)
        if method:
            try:
                r = getattr(p, method)("hello")
                if asyncio.iscoroutine(r):
                    r = await r
                print("PIPELINE RESULT:", str(r)[:300])
            except Exception:
                print("PIPELINE CALL FAILED:")
                traceback.print_exc()
    except Exception:
        print("PIPELINE BUILD FAILED:")
        traceback.print_exc()

    print("=== 2) LLM brain (fallback layer) ===")
    try:
        from app.api.web_call import _get_llm_brain

        brain = _get_llm_brain()
        print("brain:", type(brain).__name__ if brain else None)
        if brain:
            fn = getattr(brain, "generate_response", None)
            if callable(fn):
                try:
                    r = fn(
                        conversation_history=[{"role": "user", "content": "hello"}],
                        niche="solar",
                        client_name="Demo Co",
                        client_service="solar",
                    )
                    if asyncio.iscoroutine(r):
                        r = await r
                    print("BRAIN RESULT:", str(r)[:300])
                except Exception:
                    print("BRAIN CALL FAILED:")
                    traceback.print_exc()
    except Exception:
        print("BRAIN IMPORT FAILED:")
        traceback.print_exc()

    print("=== 3) Raw Gemini check ===")
    try:
        from app.config import settings

        print("DEFAULT_LLM:", settings.default_llm)
        print("GEMINI key set:", bool(settings.gemini_api_key))
        import google.generativeai as genai

        print("google-generativeai version:", getattr(genai, "__version__", "?"))
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.default_llm)
        resp = model.generate_content("Say OK")
        print("RAW GEMINI RESULT:", str(getattr(resp, "text", resp))[:200])
    except Exception:
        print("RAW GEMINI FAILED:")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
