# Free Provider Chain

Voice/AI stack = FREE providers ONLY (user mandate — no paid STT/TTS/LLM ever).

Chain pattern (`app/voice_agent/free_ai.py`):

- Every provider is OPTIONAL — missing key/SDK = silent skip, next link takes over.
- Module is **import-safe and never raises**: zero keys → app still boots; `transcribe_audio()`/`chat()` return `("", "")` and the caller falls back.
- Lazy `AsyncOpenAI` client per provider, cached (None cached too). OpenAI-compatible providers differ only in `base_url` + key.
- Every provider call wrapped in `asyncio.wait_for(..., timeout=...)` — no unbounded awaits on the phone hot path.
- Success returns `(text, provider_name)` so callers can attribute/log the source.
- Deep-tail providers (NVIDIA ~5k LIFETIME credits) fire only when primaries are circuit-broken.
