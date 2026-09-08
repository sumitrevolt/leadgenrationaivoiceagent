"""
CONVO TRACE — drive TelecallerBrain through LONG, messy, realistic conversations
and TAG every reply with the code-path that produced it (deescalate / fast-path /
llm / script-fallback / safe-fallback). Surfaces WHERE the agent gets confused
after a few turns (the "noob baat karta, 1-2 turn baad confuse" complaint).

Run:  .venv\\Scripts\\python.exe scripts\\noob_convo_trace.py
"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_envf = os.path.join(ROOT, ".env")
if os.path.isfile(_envf):
    for _ln in open(_envf, encoding="utf-8", errors="ignore"):
        _ln = _ln.strip()
        if not _ln or _ln.startswith("#") or "=" not in _ln:
            continue
        k, v = _ln.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from app.voice_agent import telecaller_brain as tb  # noqa: E402
from app.voice_agent.telecaller_brain import TelecallerBrain  # noqa: E402

# Realistic skeptical-customer conversations (messy: follow-ups, tangents,
# objections, vague answers, topic-switches — the stuff competitors handle).
CONVOS = {
    "ai_marketing": [
        "haan kaun bol raha",
        "achha ye sab hota kya hai",
        "main to khud hi facebook pe daal deta hoon roz",
        "to phir aapka kya kaam jab main khud karta hoon",
        "achha kitne ka padega mahine ka",
        "thoda mehenga nahi hai chhote dukaan ke liye",
        "isme aur kya kya milta hai",
        "google search me bhi upar aayega kya mera",
        "abhi to thoda busy hoon",
    ],
    "real_estate": [
        "haan",
        "haan 2 bhk dekh raha hoon par confuse hoon",
        "budget 45 lakh tak ka hai",
        "loan mil jayega kya itne ka",
        "location exactly kahan pe hai project",
        "metro station kitni door hai wahan se",
        "achha possession kab tak milega",
        "site visit weekend pe ho sakta hai",
    ],
}

PATHS = []  # per-turn list of code-path tags


def _install_trace(brain: TelecallerBrain):
    """Wrap brain internals to record which path produced the reply."""
    orig_fast = brain._fast_path_reply
    orig_gen = brain._generate
    orig_script = brain._script_fallback
    orig_safe = brain._safe_fallback

    def fast(history, ut):
        r = orig_fast(history, ut)
        if r:
            PATHS.append("FAST")
        return r

    async def gen(prompt):
        r = await orig_gen(prompt)
        PATHS.append(f"LLM:{r[1] or 'empty'}")
        return r

    def script(history):
        r = orig_script(history)
        if r:
            PATHS.append("SCRIPT-FB")
        return r

    def safe(history):
        r = orig_safe(history)
        PATHS.append("SAFE-FB")
        return r

    brain._fast_path_reply = fast
    brain._generate = gen
    brain._script_fallback = script
    brain._safe_fallback = safe


async def run(niche, turns):
    brain = TelecallerBrain(niche=niche, client_name="LeadGen AI")
    _install_trace(brain)
    history = [{"role": "assistant", "content": brain.opening_line()}]
    print(f"\n{'=' * 70}\n=== {niche} ===\n{'=' * 70}")
    print(f"  OPENER: {history[0]['content'][:100]}")
    seen_replies = []
    for ut in turns:
        PATHS.clear()
        reply = await brain.reply(history, ut)
        history.append({"role": "user", "content": ut})
        history.append({"role": "assistant", "content": reply})
        path = " > ".join(PATHS) or "?"
        # crude confusion heuristics
        warn = []
        if reply in seen_replies:
            warn.append("REPEAT")
        # user asked a question but reply is itself a question (didn't answer)
        if (
            (
                "?" in ut
                or any(q in ut.lower() for q in ("kya", "kaise", "kab", "kahan", "kitna", "kitne"))
            )
            and reply.strip().endswith("?")
            and "?" not in reply[:-1]
        ):
            # reply is purely a question back — may have dodged
            if not any(w in reply.lower() for w in ut.lower().split()[:3]):
                warn.append("DODGED-Q?")
        seen_replies.append(reply)
        tag = ("  ⚠ " + ",".join(warn)) if warn else ""
        print(f"\n  U: {ut}")
        print(f"  B [{path}]: {reply}{tag}")


async def main():
    for niche, turns in CONVOS.items():
        await run(niche, turns)


if __name__ == "__main__":
    asyncio.run(main())
