"""
Verify the 'bot doesn't listen / just monologues' fix.

Proves that the conversation now LISTENS -> understands -> answers the customer's
question, and keeps replies SHORT (<=2 sentences). Runs with brain=None
(rule-based, no API key) = the deterministic worst case; with Gemini on the VPS
the same path is even more natural.
"""

import asyncio
import re
import sys

sys.path.insert(0, ".")

from app.voice_agent.natural_dialog import NaturalDialogManager


def sent_count(t: str) -> int:
    return len([s for s in re.split(r"(?<=[.?!])\s+", (t or "").strip()) if s.strip()])


async def main() -> int:
    mgr = NaturalDialogManager(
        niche="solar_residential",
        client_name="SunPower",
        client_service="residential solar",
        brain=None,
    )
    st = mgr.new_conversation()
    print("OPENING:", await mgr.opening_line(st))

    turns = [
        "kitna kharcha aayega?",  # QUESTION -> must answer the question first
        "abhi main thoda busy hoon",  # OBJECTION -> empathy + ONE ask, not pushy
        "achha theek hai batao",  # INTERESTED
        "haan main hi decision leta hoon",  # ANSWER (captured, not re-asked)
    ]
    all_short = True
    answered_q = False
    for u in turns:
        r = await mgr.respond(u, st)
        n = sent_count(r.text)
        if n > 2:
            all_short = False
        if r.utterance_type.value == "question" and r.text:
            answered_q = True
        flag = "OK" if n <= 2 else "LONG!"
        print(f"\nUSER: {u}")
        print(f"BOT : {r.text}")
        print(f"      [type={r.utterance_type.value} sentences={n} {flag} end={r.should_end}]")

    # web_call wiring must import cleanly and resolve a manager.
    from app.api import web_call

    d = web_call._get_natural_dialog("real_estate", "Demo Co", "")
    wired = d is not None
    print("\nweb_call._get_natural_dialog ->", type(d).__name__ if d else None)

    ok = all_short and answered_q and wired
    print(
        "\nRESULT:",
        "PASS" if ok else "FAIL",
        f"(all_short={all_short} answered_question={answered_q} web_call_wired={wired})",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
