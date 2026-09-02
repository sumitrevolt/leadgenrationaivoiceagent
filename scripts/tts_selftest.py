"""EdgeTTS selftest — synth a Hindi line, report audio bytes (run on VPS)."""

import asyncio

import edge_tts

print("edge-tts", edge_tts.__version__)


async def t() -> None:
    c = edge_tts.Communicate("Namaste, yeh ek test hai.", "hi-IN-SwaraNeural")
    n = 0
    async for ch in c.stream():
        if ch.get("type") == "audio":
            n += len(ch.get("data") or b"")
    print("AUDIO_BYTES:", n)


asyncio.run(t())
