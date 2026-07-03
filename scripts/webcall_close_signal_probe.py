"""Manual verification for the landing-page voice-onboarding close_signal WS
event (docs/superpowers/plans/2026-07-03-landing-page-voice-onboarding.md).

Drives a scripted web-call conversation through both close-signal turns and
prints every WS message so you can confirm a close_signal event arrives.
Run locally with WEBCALL_INLINE_SIGNUP=1 and CLOSE_DETECT=1 set on the
server process (see uvicorn env), server already running on :8000.

Usage: python scripts/webcall_close_signal_probe.py
"""

import asyncio
import json

import aiohttp


def _is_last_bot_chunk(msg: dict) -> bool:
    if msg.get("type") != "bot":
        return False
    chunk_total = msg.get("chunk_total")
    chunk_index = msg.get("chunk_index")
    if not chunk_total or chunk_index is None:
        return True
    return chunk_index >= chunk_total - 1


async def _drain_turn(ws, label: str, max_messages: int = 12) -> bool:
    """Read messages until the bot's final chunk for this turn, then peek for
    ONE more message with a short timeout (close_signal is sent AFTER the
    sentence chunks finish, so it arrives just after the last "bot" chunk --
    breaking immediately on the last chunk misses it). Returns True if a
    close_signal event was seen along the way."""
    saw_close_signal = False
    for _ in range(max_messages):
        msg = json.loads((await asyncio.wait_for(ws.receive(), 30)).data)
        mtype = msg.get("type")
        if mtype == "bot":
            print(f"{label}: bot", (msg.get("text") or "")[:100])
        elif mtype == "close_signal":
            print(f"{label}: CLOSE_SIGNAL", msg)
            saw_close_signal = True
        else:
            print(f"{label}: {mtype}")
        if _is_last_bot_chunk(msg):
            try:
                trailing = json.loads((await asyncio.wait_for(ws.receive(), 3)).data)
                print(f"{label}: trailing", trailing.get("type"))
                if trailing.get("type") == "close_signal":
                    saw_close_signal = True
            except asyncio.TimeoutError:
                pass
            break
    return saw_close_signal


async def probe() -> None:
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect("http://127.0.0.1:8000/api/web-call/ws", timeout=30) as ws:
            print("ready:", (await ws.receive()).data[:120])
            await ws.send_json({"type": "start", "niche": "ai_marketing", "flow": "qualify"})
            await _drain_turn(ws, "opener")

            await ws.send_json({"type": "user", "text": "trial start karwa do"})
            saw_1 = await _drain_turn(ws, "turn1")

            await ws.send_json({"type": "user", "text": "9876543210"})
            saw_2 = await _drain_turn(ws, "turn2")

            print("SAW close_signal:", saw_1 or saw_2)


if __name__ == "__main__":
    asyncio.run(probe())
