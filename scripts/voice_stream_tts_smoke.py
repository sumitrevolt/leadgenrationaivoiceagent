#!/usr/bin/env python3
"""Smoke USE_LLM_STREAM_TTS path — run locally or inside leadgen_app container.

  python scripts/voice_stream_tts_smoke.py
  python scripts/voice_stream_tts_smoke.py --ws --base http://127.0.0.1:8000

Exit 0 = safe to flip USE_LLM_STREAM_TTS=1 on VPS.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

# Bare script execution puts `scripts/` on sys.path, not the repository root.
# Add the root so the unit checks exercise the same app package as the live WS.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _unit_checks() -> list[str]:
    issues: list[str] = []
    try:
        from app.voice_agent.llm_stream_tts import pop_sentence, stream_tts_enabled

        s, rest = pop_sentence("Hi. Bye.")
        if s != "Hi." or "Bye" not in rest:
            issues.append(f"pop_sentence broken: {s!r} {rest!r}")
        if stream_tts_enabled() != (
            (os.getenv("USE_LLM_STREAM_TTS") or "").strip().lower() in ("1", "true", "yes", "on")
        ):
            issues.append("stream_tts_enabled mismatch")
    except Exception as e:
        issues.append(f"unit import: {e}")
    return issues


async def _brain_stream_check() -> list[str]:
    issues: list[str] = []
    try:
        from app.voice_agent.telecaller_brain import TelecallerBrain

        brain = TelecallerBrain(niche="general", client_name="Smoke Test")
        t0 = time.perf_counter()
        parts: list[str] = []
        async for sent in brain.reply_stream_sentences(
            [], "namaste, solar panel ke baare me batao"
        ):
            parts.append(sent)
            if len(parts) >= 2:
                break
        elapsed = time.perf_counter() - t0
        if not parts:
            issues.append("reply_stream_sentences returned empty (LLM down?)")
        elif elapsed > 45:
            issues.append(f"stream too slow: {elapsed:.1f}s for {len(parts)} sentence(s)")
        else:
            print(
                f"OK brain stream: {len(parts)} sentence(s) in {elapsed:.1f}s — {parts[0][:60]!r}…"
            )
    except Exception as e:
        issues.append(f"brain stream: {e}")
    return issues


async def _ws_check(base: str) -> list[str]:
    issues: list[str] = []
    try:
        import aiohttp
    except ImportError:
        return ["aiohttp missing for --ws"]

    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    url = f"{ws_base.rstrip('/')}/api/web-call/ws"
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, timeout=25) as ws:
            await ws.send_json({"type": "start", "niche": "solar", "flow": "qualify"})
            # drain opener
            for _ in range(8):
                msg = await asyncio.wait_for(ws.receive(), timeout=12)
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                d = json.loads(msg.data)
                if d.get("type") == "bot":
                    # Platform pitch sends exactly three ordered opener chunks;
                    # do not wait for another frame after the final chunk.
                    if not d.get("chunk_total") or d.get("chunk_index") == d.get("chunk_total") - 1:
                        break

            t0 = time.perf_counter()
            await ws.send_json({"type": "user", "text": "haan ji budget 50000", "niche": "solar"})
            first_bot = None
            for _ in range(15):
                msg = await asyncio.wait_for(ws.receive(), timeout=25)
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                d = json.loads(msg.data)
                if d.get("type") == "bot" and d.get("text"):
                    first_bot = d
                    break
            elapsed = time.perf_counter() - t0
            if not first_bot:
                issues.append("WS: no bot reply after user turn")
            else:
                stream_flag = first_bot.get("llm_stream")
                print(
                    f"OK WS first bot in {elapsed:.1f}s llm_stream={stream_flag} "
                    f"text={str(first_bot.get('text'))[:50]!r}…"
                )
    return issues


async def _async_main(ws: bool, base: str, skip_brain: bool) -> int:
    issues = _unit_checks()
    if not skip_brain:
        issues.extend(await _brain_stream_check())
    if ws:
        issues.extend(await _ws_check(base))

    if issues:
        print("FAIL:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("RESULT: PASS — USE_LLM_STREAM_TTS safe to enable")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ws", action="store_true", help="Also hit /api/web-call/ws")
    p.add_argument("--base", default=os.getenv("SMOKE_BASE", "http://127.0.0.1:8000"))
    p.add_argument("--skip-brain", action="store_true", help="Unit checks only (no LLM)")
    args = p.parse_args()
    return asyncio.run(_async_main(args.ws, args.base, args.skip_brain))


if __name__ == "__main__":
    raise SystemExit(main())
