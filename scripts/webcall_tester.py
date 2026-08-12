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

Note: canonical QA tester scripts/agent_tester.py hai; yeh ek lightweight variant.
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


async def collect_bot_msgs(ws, window_s: float = 8.0) -> tuple[list, float | None]:
    """window ke andar jitne bhi bot/info/error msgs aaye, sab collect karo
    (double-reply pakadne ke liye pura window sunte hain, pehla msg aate hi
    nahi rukte)."""
    msgs = []
    first_bot_latency = None
    started = time.monotonic()
    end = time.monotonic() + window_s
    while time.monotonic() < end:
        try:
            timeout = max(0.1, end - time.monotonic())
            raw = await asyncio.wait_for(ws.receive(), timeout)
        except asyncio.TimeoutError:
            break
        if raw.type != aiohttp.WSMsgType.TEXT:
            # close/error frame -> stop listening this window
            if raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break
            continue
        try:
            data = json.loads(raw.data)
        except Exception:
            continue
        if data.get("type") in ("bot", "info", "error"):
            if data.get("type") == "bot" and first_bot_latency is None:
                first_bot_latency = time.monotonic() - started
            msgs.append(data)
    return msgs, first_bot_latency


async def run() -> int:
    t0 = time.monotonic()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(URL, heartbeat=20) as ws:
                # initial greeting window
                await collect_bot_msgs(ws, window_s=10.0)
                for turn in TURNS:
                    await ws.send_json({"type": "user", "text": turn})
                    t_turn = time.monotonic()
                    msgs, first_bot_latency = await collect_bot_msgs(ws, window_s=8.0)
                    # Sentence-streamed replies use multiple bot frames for one
                    # spoken answer. Count only the first chunk as a logical reply;
                    # chunk_total remains available for protocol-level checks.
                    latency = (
                        first_bot_latency
                        if first_bot_latency is not None
                        else time.monotonic() - t_turn
                    )
                    bot = [
                        m
                        for m in msgs
                        if m.get("type") == "bot" and (m.get("chunk_index") in (None, 0))
                    ]

                    if len(bot) == 0:
                        flag("NO_REPLY", f"turn={turn!r} -> 0 bot msgs")
                    elif len(bot) > 1:
                        flag("DOUBLE_REPLY", f"turn={turn!r} -> {len(bot)} bot msgs")

                    text = " ".join(
                        (m.get("full_text") or m.get("text") or "") for m in bot
                    ).strip()
                    if bot and not any(m.get("audio_b64") for m in bot):
                        flag("NO_AUDIO", f"turn={turn!r} -> no audio_b64 (robotic fallback)")
                    if len(text.split()) > 35:
                        flag("TOO_LONG", f"turn={turn!r} -> {len(text.split())} words")
                    low = text.lower()
                    for b in BANNED:
                        if b in low:
                            flag("META_TALK", f"turn={turn!r} -> '{b}'")
                    if latency > 6.0:
                        flag("SLOW", f"turn={turn!r} -> {latency:.1f}s")

                    report["turns"].append(
                        {
                            "turn": turn,
                            "reply": text,
                            "n_bot": len(bot),
                            "latency_s": round(latency, 2),
                        }
                    )

                replies = [t["reply"] for t in report["turns"] if t["reply"]]
                if len(replies) != len(set(replies)):
                    flag("REPEAT", "same reply repeated across turns")
    except Exception as exc:  # connection/protocol error -> report, don't crash
        flag("CONNECT", f"{type(exc).__name__}: {exc}")

    report["issues"] = issues
    report["total_s"] = round(time.monotonic() - t0, 2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(run()))
    except KeyboardInterrupt:
        sys.exit(130)
