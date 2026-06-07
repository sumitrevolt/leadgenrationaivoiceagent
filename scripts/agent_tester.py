"""
Automated voice-agent QA tester — bugs dhoondta hai, report deta hai.
Run on VPS: env PYTHONPATH=/opt/leadgen .venv/bin/python scripts/agent_tester.py

Web-call WS (/api/web-call/ws) ko scripted conversations se drive karta hai
(text mode — FREE, no phone, same TelecallerBrain). Har niche pe checks:
  - DOUBLE REPLY: ek user turn pe >1 'bot' message? (double-voice ka root)
  - EMPTY/ECHO: blank ya "[echo" ya "(no response)" reply
  - REPEAT: lagataar same reply 2x
  - TOO LONG: reply > 35 shabd (phone par bura)
  - META junk: "maine pehle poocha / unclear / maaf kijiye" banned phrases
  - LATENCY: reply aane me kitna time
Scorecard print karta + har issue ki line.
"""
import asyncio
import json
import time

import aiohttp

WS = "ws://127.0.0.1:8000/api/web-call/ws"

SCRIPTS = {
    "solar_residential": [
        "haan boliye", "bijli ka bill bahut zyada aata hai",
        "lekin solar mehenga hota hai na", "abhi nahi baad me sochenge",
    ],
    "real_estate": [
        "haan", "2 BHK dhund raha hoon", "budget thoda kam hai",
        "site visit kab ho sakta hai",
    ],
    "insurance": [
        "haan bolo", "health insurance chahiye", "premium kitna hoga",
        "abhi busy hoon",
    ],
}

BANNED = ["maine pehle", "pehle hi poocha", "unclear", "maaf kij", "[echo", "(no response)"]


async def run_niche(session, niche, turns, report):
    async with session.ws_connect(WS, timeout=30) as ws:
        await ws.send_json({"type": "start", "niche": niche, "flow": "qualify"})
        last_reply = ""
        # drain greeting (ready + first bot)
        await _collect_bots(ws, settle=3.0)
        for turn in turns:
            await ws.send_json({"type": "user", "text": turn, "niche": niche})
            t0 = time.time()
            # Realistic: wait up to 12s for the FIRST reply, then 2.5s settle to
            # catch any (buggy) second reply — matches phone's turn-based pacing.
            bots = await _collect_bots(ws, first_timeout=12.0, settle=2.5)
            dt = time.time() - t0
            n = len(bots)
            reply = (bots[0] if bots else "").strip()
            # CHECKS
            if n == 0:
                report.append(f"[{niche}] NO REPLY for: {turn!r}")
            if n > 1:
                report.append(f"[{niche}] DOUBLE REPLY ({n}) for {turn!r}: {bots}")
            if reply and not reply.strip():
                report.append(f"[{niche}] EMPTY reply for {turn!r}")
            low = reply.lower()
            for b in BANNED:
                if b in low:
                    report.append(f"[{niche}] BANNED phrase '{b}' in: {reply!r}")
            if reply and reply == last_reply:
                report.append(f"[{niche}] REPEAT reply: {reply!r}")
            if len(reply.split()) > 35:
                report.append(f"[{niche}] TOO LONG ({len(reply.split())}w): {reply!r}")
            if dt > 9:
                report.append(f"[{niche}] SLOW {dt:.1f}s for {turn!r}")
            last_reply = reply
            print(f"  [{niche}] U: {turn}\n           B({n}, {dt:.1f}s): {reply[:90]}")


async def _collect_bots(ws, first_timeout=12.0, settle=2.5):
    """Wait up to first_timeout for the FIRST bot msg, then settle for extras."""
    bots = []
    while True:
        timeout = first_timeout if not bots else settle
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
        except asyncio.TimeoutError:
            break
        if msg.type != aiohttp.WSMsgType.TEXT:
            break
        try:
            d = json.loads(msg.data)
        except Exception:
            continue
        if d.get("type") == "bot":
            bots.append((d.get("text") or "").strip())
    return bots


async def main():
    report = []
    async with aiohttp.ClientSession() as s:
        for niche, turns in SCRIPTS.items():
            print(f"\n=== TEST: {niche} ===")
            try:
                await run_niche(s, niche, turns, report)
            except Exception as e:
                report.append(f"[{niche}] TEST CRASHED: {e}")
    print("\n" + "=" * 50)
    if report:
        print(f"❌ {len(report)} ISSUE(S) FOUND:")
        for r in report:
            print("  -", r)
    else:
        print("✅ NO ISSUES — all niches clean (no double/empty/repeat/long/slow/meta)")


if __name__ == "__main__":
    asyncio.run(main())
