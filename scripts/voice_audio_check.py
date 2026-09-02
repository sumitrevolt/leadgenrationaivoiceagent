"""Voice AUDIO-path diagnostic — kyun agent 'reply nahi deta' real call me.
Brain (text) theek ho sakta hai par AUDIO toot-ta hai: STT (sunna) ya TTS (bolna).
Run: docker cp scripts/voice_audio_check.py leadgen_app:/tmp/ && docker exec leadgen_app python /tmp/voice_audio_check.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _sec(t):
    print("\n=== " + t + " ===")


print("VOICE AUDIO CHECK")

# 1. STT key (agent 'sunne' ke liye Groq whisper chahiye)
_sec("1. STT (sunna) — GROQ key + provider")
g = os.environ.get("GROQ_API_KEY", "")
print(
    f"  GROQ_API_KEY: {'SET (len ' + str(len(g)) + ')' if g else 'MISSING ❌ — STT fail -> agent sun nahi payega'}"
)
for k in ("GEMINI_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY"):
    print(f"  {k}: {'set' if os.environ.get(k) else 'missing'}")

# 2. transcribe_audio function reachable?
_sec("2. STT function (free_ai.transcribe_audio)")
try:
    from app.voice_agent import free_ai

    print(f"  transcribe_audio present: {hasattr(free_ai, 'transcribe_audio')}")
except Exception as e:
    print(f"  [ERR] {e}")

# 3. TTS (agent 'bolne' ke liye EdgeTTS) — REAL synth test
_sec("3. TTS (bolna) — EdgeTTS synth test")
try:
    import edge_tts  # type: ignore

    print(f"  edge-tts version: {getattr(edge_tts, '__version__', '?')}")
except Exception as e:
    print(f"  edge-tts import FAIL ❌: {e}")


async def _tts_test():
    try:
        import edge_tts

        out = b""
        comm = edge_tts.Communicate("Namaste, main Swara bol rahi hoon.", "hi-IN-SwaraNeural")
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                out += chunk.get("data", b"")
        return len(out)
    except Exception as e:
        return f"FAIL: {e}"


try:
    n = asyncio.run(_tts_test())
    if isinstance(n, int) and n > 1000:
        print(f"  ✅ EdgeTTS synth OK — {n} bytes audio (agent bol sakta hai)")
    else:
        print(f"  ❌ EdgeTTS synth problem: {n} (agent ki reply audio nahi banegi -> silence)")
except Exception as e:
    print(f"  [ERR] {e}")

# 4. web_call _edge_tts_mp3_b64 (jo actually call me use hota)
_sec("4. web_call TTS wrapper (_edge_tts_mp3_b64)")


async def _wrap_test():
    try:
        from app.api.web_call import _edge_tts_mp3_b64

        b = await _edge_tts_mp3_b64("Bijli ka bill kitna aata hai?")
        return len(b) if b else 0
    except Exception as e:
        return f"FAIL: {e}"


try:
    r = asyncio.run(_wrap_test())
    print(
        f"  _edge_tts_mp3_b64 -> {('OK ' + str(r) + ' b64-chars') if isinstance(r, int) and r > 1000 else ('PROBLEM: ' + str(r))}"
    )
except Exception as e:
    print(f"  [ERR] {e}")

# 5. End-to-end brain reply (text) — confirm brain bolne-layak reply deta
_sec("5. Brain reply (text) — sanity")


async def _brain_test():
    try:
        from app.voice_agent.telecaller_brain import TelecallerBrain

        b = TelecallerBrain(niche="solar_residential", client_name="Test Solar")
        r = await b.reply(
            [{"role": "assistant", "content": "Namaste"}], "bijli ka bill bahut zyada aata hai"
        )
        return r
    except Exception as e:
        return f"FAIL: {e}"


try:
    r = asyncio.run(_brain_test())
    print(f"  reply: {str(r)[:90]!r}")
    print(
        f"  -> brain {'OK (reply deta hai)' if r and not str(r).startswith('FAIL') else 'PROBLEM'}"
    )
except Exception as e:
    print(f"  [ERR] {e}")

print("\n=== DONE ===")
