"""
Web-Call QA Tester Agent — khud baat karke bugs dhoondhta hai, report deta hai.

Run (VPS ya kahin se bhi):  python scripts/webcall_tester.py [wss_url]
Default URL: wss://leadsgenai.in/api/web-call/ws

CHECKS per turn:
  1. EXACTLY 1 bot message per user turn (double-reply = double awaaz root cause)
  2. audio_b64 present (natural Swara voice; None = robotic browser fallback)
  3. Reply chhota ho (<= ~30 words — telecaller brevity rule)
  4. Meta-talk banned words ("maine pehle poocha", "unclear hai", "maaf kijiye")
  5. Same reply repeat na ho (gawaar-loop guard)
  6. Latency per turn (<6s target free stack pe)
Exit code 0 = PASS, 1 = issues found. Report JSON bhi print hota hai.
"""
import asyncio
import json
import sys
import time

import aiohttp

URL = sys.argv[1] if len(sys.argv) > 1 else "wss://leadsgenai.in/api/web-call/ws"

TURNS = [
    "haan bolo",
    "bijli ka bill bahut zyada aata hai",
    "lekin solar to mehenga hota hai na",
    "theek hai sochenge, abhi nahi",
]
BANNED = ["maine pehle poocha", "pehle hi poocha", "unclear hai", "maaf kijiye, awaaz"]

issues: list = []
report: dict = {"url": URL, "turns": []}


def flag(kind: str, detail: str) -> None:
    issues.append({"kind": kind, "detail": detail})


async def collect_bot_msgs(ws, window_s: float = 8.0) -> list:
    """window ke andar jitne bhi bot/info/error msgs aaye, sab collect karo
    (double-reply pakadne ke liye pura window sunte hain, pehla msg aate hi
    nahi rukte)."""
    msgs = []
    end = time.monotonic() + window_s
    while time.monotonic() < end:
        try:
            timeout = max(0.1, end - time.monotonic())
            raw = await asyncio.wait_for(ws.receive(), timeout)
        except asyncio.TimeoutError:
            break
        if raw.type != aiohttp.WSMsgType.TE