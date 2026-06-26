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
import os
import sys
import time

import aiohttp

# Windows cp1252 console can't encode emojis (❌/✅/⏱) used below — force UTF-8
# so the scorecard prints instead of crashing mid-print. No-op on Linux/Mac.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - older python
    pass

try:  # D-13 conversation QA judges (pushy-after-softno / talk-listen / permission / literal)
    from app.voice_agent import qa_checks as _qc
except Exception:  # pragma: no cover - script may run before path set
    _qc = None

try:  # objective latency distribution (voice_metrics — pure stdlib, import-safe)
    from app.voice_agent import voice_metrics as _vm
except Exception:  # pragma: no cover
    _vm = None

# Host/local default. IN-CONTAINER the app listens on :8080 (compose maps host
# 127.0.0.1:8000 -> container 8080), so run inside the container with:
#   AGENT_TESTER_WS=ws://127.0.0.1:8080/api/web-call/ws python scripts/agent_tester.py
WS = os.environ.get("AGENT_TESTER_WS") or "ws://127.0.0.1:8000/api/web-call/ws"

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
    "ai_marketing": [
        "haan", "khud post dalte hain", "Google pe dikhta hai kya",
        "trial kaise milega",
    ],
}

BANNED = ["maine pehle", "pehle hi poocha", "unclear", "maaf kij", "[echo", "(no response)"]


async def run_niche(session, niche, turns, report, latencies=None):
    transcript: list[dict] = []  # role-tagged turns for D-13 conversation checks
    async with session.ws_connect(WS, timeout=aiohttp.ClientWSTimeout(ws_close=60)) as ws:
        # Server sends {"type":"ready"} before the client sends anything.
        # Must drain this message BEFORE sending "start" — otherwise aiohttp
        # treats the unread buffer as an error and marks the transport "closing".
        try:
            ready_msg = await asyncio.wait_for(ws.receive(), timeout=15.0)
            if ready_msg.type != aiohttp.WSMsgType.TEXT:
                report.append(f"[{niche}] NO READY (got type={ready_msg.type})")
                return
        except asyncio.TimeoutError:
            report.append(f"[{niche}] TIMEOUT waiting for ready")
            return
        await ws.send_json({"type": "start", "niche": niche, "flow": "qualify"})
        last_reply = ""
        # drain greeting (ready + first bot) — keep it as the opener turn so the
        # permission/missing-permission check sees the opener.
        greeting, ws_closed = await _collect_bots(ws, settle=3.0)
        if ws_closed:
            report.append(f"[{niche}] SERVER CLOSED after start (no greeting sent)")
            return
        if greeting:
            transcript.append({"role": "assistant", "content": (greeting[0] or "").strip()})
        for turn in turns:
            await ws.send_json({"type": "user", "text": turn, "niche": niche})
            transcript.append({"role": "user", "content": turn})
            t0 = time.time()
            # Realistic: wait up to 12s for the FIRST reply, then 2.5s settle to
            # catch any (buggy) second reply — matches phone's turn-based pacing.
            bots, ws_closed = await _collect_bots(ws, first_timeout=12.0, settle=2.5)
            if ws_closed:
                report.append(f"[{niche}] SERVER CLOSED mid-turn for: {turn!r}")
                break
            dt = time.time() - t0
            n = len(bots)
            if latencies is not None and n > 0:
                latencies.append(dt * 1000.0)  # ms, for P50/P95/P99 distribution
            reply = (bots[0] if bots else "").strip()
            if reply:
                transcript.append({"role": "assistant", "content": reply})
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
        # Conversation-level D-13 checks over the whole transcript (pushy-after-
        # softno / talk-listen-ratio / missing-permission / literal-translation).
        if _qc is not None:
            for finding in _qc.run_all(transcript):
                report.append(f"[{niche}] {finding}")


async def _collect_bots(ws, first_timeout=12.0, settle=2.5):
    """Wait up to first_timeout for the FIRST bot msg, then settle for extras.
    Returns (bots_list, ws_closed) — ws_closed=True means server closed the WS."""
    bots = []
    while True:
        timeout = first_timeout if not bots else settle
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
        except asyncio.TimeoutError:
            break
        if msg.type == aiohttp.WSMsgType.ERROR or msg.type == aiohttp.WSMsgType.CLOSED:
            return bots, True  # server closed abnormally
        if msg.type != aiohttp.WSMsgType.TEXT:
            break
        try:
            d = json.loads(msg.data)
        except Exception:
            continue
        if d.get("type") == "bot":
            # Sentence-split STREAMING: ek reply N chunks me aata (chunk_total>1) —
            # ise EK reply gino (warna false "DOUBLE REPLY"). First chunk pe full_text.
            ct = d.get("chunk_total")
            if ct and ct > 1:
                if d.get("chunk_index", 0) == 0:
                    bots.append((d.get("full_text") or d.get("text") or "").strip())
                # baaki chunks same reply ke — skip
            else:
                bots.append((d.get("text") or "").strip())
    return bots, False


async def main():
    report = []
    latencies: list[float] = []
    async with aiohttp.ClientSession() as s:
        for niche, turns in SCRIPTS.items():
            print(f"\n=== TEST: {niche} ===")
            try:
                await run_niche(s, niche, turns, report, latencies)
            except Exception as e:
                report.append(f"[{niche}] TEST CRASHED: {e}")
    print("\n" + "=" * 50)
    # Objective latency distribution (P50/P95/P99) — "distribution, not average" (ph06/17)
    if _vm is not None and latencies:
        lat = _vm.latency_summary(latencies)
        print(
            f"⏱  LATENCY ms  n={lat['n']}  p50={lat['p50']}  p95={lat['p95']}  "
            f"p99={lat['p99']}  mean={lat['mean']}  max={lat['max']}"
        )
    if report:
        print(f"❌ {len(report)} ISSUE(S) FOUND:")
        for r in report:
            print("  -", r)
    else:
        print("✅ NO ISSUES — all niches clean (no double/empty/repeat/long/slow/meta)")


if __name__ == "__main__":
    asyncio.run(main())
