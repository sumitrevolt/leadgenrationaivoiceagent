#!/usr/bin/env python3
"""Web-call tune loop — /app/test-call WS pe scripted personas, score, report.

FREE (no phone). Same TelecallerBrain + platform_pitch as live test-call page.

  python scripts/web_call_tune_loop.py
  AGENT_TESTER_WS=wss://leadsgenai.in/api/web-call/ws python scripts/web_call_tune_loop.py
  python scripts/web_call_tune_loop.py --rounds 3 --niche ai_marketing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

# Windows console — ₹/Devanagari print crash avoid
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import aiohttp

WS = os.environ.get("AGENT_TESTER_WS") or "wss://leadsgenai.in/api/web-call/ws"

# Advanced personas — platform pitch + discovery + objections
PERSONAS: dict[str, list[str]] = {
    "ai_marketing_interested": [
        "haan ji batao",
        "khud post dalte hain staff nahi hai",
        "Google pe upar nahi dikhte",
        "trial kaise shuru karun",
    ],
    "ai_marketing_busy": [
        "haan",
        "abhi meeting me hoon busy hoon",
    ],
    "ai_marketing_skeptic": [
        "nahi interest",
        "pehle se agency hai",
        "mehenga hoga na",
        "soch ke batata hoon",
    ],
    "ai_marketing_confused": [
        "kya?",
        "samjha nahi",
        "aap kaun ho",
    ],
    "solar_objection": [
        "haan boliye",
        "bill 8000 aata hai",
        "solar bahut mehenga",
        "abhi nahi",
    ],
}

BANNED = [
    "maine pehle",
    "pehle hi poocha",
    "unclear hai",
    "maaf kij",
    "zara dobara",
    "aapne hamari service ke baare me poocha",
    "[echo",
    "(no response)",
]
GOOD_MARKERS = ["marketing", "google", "trial", "audit", "post", "lead", "business"]


async def _collect_bots(
    ws: aiohttp.ClientWebSocketResponse,
    first_timeout: float = 14.0,
    settle: float = 2.0,
) -> tuple[list[str], str]:
    """Returns (all_bot_texts, primary_reply). Primary = last message with `heard` or last bot."""
    bots: list[str] = []
    heard_reply = ""
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
        if d.get("type") != "bot":
            continue
        ct = d.get("chunk_total")
        if ct and ct > 1:
            if d.get("chunk_index", 0) == 0:
                txt = (d.get("full_text") or d.get("text") or "").strip()
                bots.append(txt)
                if d.get("heard"):
                    heard_reply = txt
        else:
            txt = (d.get("text") or "").strip()
            bots.append(txt)
            if d.get("heard"):
                heard_reply = txt
    primary = heard_reply or (bots[-1] if bots else "")
    return bots, primary


async def _collect_greeting(ws: aiohttp.ClientWebSocketResponse, niche: str) -> list[str]:
    """Collect opener (3 segments for ai_marketing)."""
    greet, _ = await _collect_bots(ws, first_timeout=12.0, settle=2.0)
    return greet


def _score_turn(niche: str, user: str, reply: str, dt: float, n_bots: int, last: str) -> list[str]:
    issues: list[str] = []
    if n_bots == 0:
        issues.append(f"NO REPLY to {user!r}")
    if n_bots > 1:
        issues.append(f"DOUBLE REPLY ({n_bots}): {reply[:60]!r}")
    if not reply.strip():
        issues.append(f"EMPTY for {user!r}")
    low = reply.lower()
    for b in BANNED:
        if b in low:
            issues.append(f"BANNED '{b}' in {reply!r}")
    if reply and reply == last:
        issues.append(f"REPEAT {reply!r}")
    if len(reply.split()) > 35:
        issues.append(f"TOO LONG ({len(reply.split())}w)")
    if dt > 10:
        issues.append(f"SLOW {dt:.1f}s")
    return issues


async def run_persona(name: str, turns: list[str], niche: str) -> dict:
    transcript: list[dict[str, str]] = []
    issues: list[str] = []
    last = ""
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(WS, timeout=45, heartbeat=20) as ws:
            await ws.send_json(
                {"type": "start", "niche": niche, "flow": "qualify", "client_name": "LeadGen AI"}
            )
            greet = await _collect_greeting(ws, niche)
            for g in greet:
                if g:
                    transcript.append({"role": "assistant", "content": g})
            for turn in turns:
                await ws.send_json({"type": "user", "text": turn, "niche": niche})
                t0 = time.time()
                bots, reply = await _collect_bots(ws)
                dt = time.time() - t0
                # Multi-chunk streaming = 1 reply; double = 2+ heard replies only
                heard_count = 1 if reply else 0
                n_for_score = heard_count if heard_count else len(bots)
                transcript.append({"role": "user", "content": turn})
                if reply:
                    transcript.append({"role": "assistant", "content": reply})
                issues.extend(_score_turn(niche, turn, reply, dt, n_for_score, last))
                last = reply
                print(f"  [{name}] U: {turn}\n           B({len(bots)}, {dt:.1f}s): {reply[:100]}")
    # Quality heuristics on full transcript
    bot_text = " ".join(t["content"] for t in transcript if t["role"] == "assistant").lower()
    if niche == "ai_marketing" and "interested" in name:
        if not any(m in bot_text for m in GOOD_MARKERS):
            issues.append("WEAK: no value/discovery markers in transcript")
    if "aapne hamari service" in bot_text:
        issues.append("WRONG OPENER: inbound script leaked")
    score = max(0.0, 1.0 - 0.15 * len(issues))
    return {
        "persona": name,
        "niche": niche,
        "issues": issues,
        "score": score,
        "transcript": transcript,
    }


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rounds", type=int, default=1)
    p.add_argument("--niche", default="")
    args = p.parse_args()
    personas = PERSONAS
    if args.niche:
        personas = {k: v for k, v in PERSONAS.items() if args.niche in k or args.niche == "all"}
        if not personas:
            personas = {"custom": PERSONAS.get("ai_marketing_interested", ["haan"])}

    all_issues: list[str] = []
    scores: list[float] = []
    print(f"WS={WS} rounds={args.rounds} personas={len(personas)}")

    for r in range(args.rounds):
        print(f"\n{'=' * 50}\nROUND {r + 1}/{args.rounds}\n{'=' * 50}")
        if r > 0:
            await asyncio.sleep(5.0)
        for name, turns in personas.items():
            niche = "ai_marketing" if name.startswith("ai_marketing") else "solar_residential"
            print(f"\n--- {name} (niche={niche}) ---")
            try:
                res = await run_persona(name, turns, niche)
                scores.append(res["score"])
                await asyncio.sleep(3.0)  # WS rate-limit breathing room
                for iss in res["issues"]:
                    all_issues.append(f"[{name}] {iss}")
            except Exception as e:
                all_issues.append(f"[{name}] CRASH: {e}")
                print(f"  CRASH: {e}")

    avg = sum(scores) / len(scores) if scores else 0.0
    print(f"\n{'=' * 50}")
    print(f"AVG SCORE: {avg:.2f} | issues: {len(all_issues)}")
    if all_issues:
        print("ISSUES:")
        for i in all_issues:
            print(" -", i)
        return 1
    print("OK — all personas clean")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
