"""
NOOB-REPRO — drive TelecallerBrain directly (no server) through realistic +
slightly adversarial customer conversations, print opener + every reply with
word-count and noob-tell flags. Source-of-truth reproduction for the
"agent noob saman baat kar rahi" complaint.

Run:  .venv\\Scripts\\python.exe scripts\\noob_repro.py
"""

import asyncio
import os
import re
import sys

# --- load .env into os.environ (free_ai/providers read env directly) ---------
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

from app.voice_agent.telecaller_brain import TelecallerBrain  # noqa: E402

# Realistic end-customer turns (mix: skeptic, questions, objections, vague).
CONVOS = {
    "ai_marketing": [
        "haan boliye",
        "ye sab hota kya hai exactly",
        "achha social media wagairah?",
        "lekin mere paas time nahi hai ye sab dekhne ka",
        "kitne ka padega ye",
        "abhi soch ke batata hoon",
    ],
    "real_estate": [
        "haan kaun",
        "haan ghar dekh raha hoon par confuse hoon",
        "2 BHK chahiye budget 40 lakh tak",
        "aap log to bas paisa kamane ke chakkar me ho",
        "site visit me kya dikhaoge",
    ],
    "solar_residential": [
        "haan ji",
        "bijli bill 4000 aata hai har mahine",
        "solar to bahut mehenga hota hai na sunna",
        "chhat pe jagah hai par maintenance ka jhanjhat",
        "subsidy milti hai kya sach me",
    ],
    "insurance": [
        "hello",
        "health insurance ke baare me",
        "premium kitna hoga 35 saal ki age pe",
        "pehle se ek policy hai mere paas",
        "main abhi thoda busy hoon",
    ],
}

NOOB_PATTERNS = [
    (
        r"\b(bahut achh?a|great|wonderful|sahi decision|badhiya choice|excellent)\b",
        "generic-praise",
    ),
    (r"maaf kij|samajh nahi|unclear|maine pehle|dobara pooch|phir se pooch", "meta-apology"),
    (r"\[(company|name|project|city)\]", "placeholder-leak"),
    (r"(swara|agent|assistant)\s*:", "role-prefix-leak"),
    (r"\b(shayad|lagta hai|pata nahi|ho sakta hai|i think|maybe)\b", "unsure-hedge"),
    (r"\b(tum|tu|yaar|bhai)\b", "informal-slang"),
    (r"(sahayata|uplabdh|pradan|nivedan|vinati)", "literal-hindi"),
]


def flags(text: str, *, is_opener: bool = False) -> list[str]:
    low = (text or "").lower()
    out = []
    for pat, name in NOOB_PATTERNS:
        if re.search(pat, low):
            out.append(name)
    wc = len((text or "").split())
    # Per-turn replies: phone rule = 1 sentence / ~18 words. Permission OPENERS are
    # legitimately longer (greeting + reason + permission-ask, ~25-30w) and match
    # the phone openers verbatim — so only flag an opener that's genuinely bloated.
    limit = 34 if is_opener else 20
    if wc > limit:
        out.append(f"too-long({wc}w)")
    if not text.strip():
        out.append("EMPTY")
    return out


async def run_niche(niche: str, turns: list[str]) -> list[str]:
    issues: list[str] = []
    try:
        brain = TelecallerBrain(niche=niche, client_name="LeadGen AI")
    except Exception as e:
        print(f"[{niche}] BRAIN INIT FAILED: {e}")
        return [f"{niche}: init-failed {e}"]
    history: list[dict] = []
    opener = brain.opening_line()
    print(f"\n=== {niche} ===")
    print(f"  OPENER ({len(opener.split())}w): {opener}")
    of = flags(opener, is_opener=True)
    if of:
        issues.append(f"{niche} OPENER {of}: {opener!r}")
    history.append({"role": "assistant", "content": opener})
    last = ""
    for ut in turns:
        reply = await brain.reply(history, ut)
        history.append({"role": "user", "content": ut})
        history.append({"role": "assistant", "content": reply})
        fl = flags(reply)
        if reply and reply == last:
            fl.append("REPEAT")
        tag = (" ⚠ " + ",".join(fl)) if fl else ""
        print(f"  U: {ut}")
        print(f"  B ({len(reply.split())}w): {reply}{tag}")
        if fl:
            issues.append(f"{niche} <{ut[:25]}> {fl}: {reply!r}")
        last = reply
    return issues


async def main():
    all_issues: list[str] = []
    for niche, turns in CONVOS.items():
        all_issues += await run_niche(niche, turns)
    print("\n" + "=" * 60)
    if all_issues:
        print(f"❌ {len(all_issues)} NOOB-TELL(S):")
        for i in all_issues:
            print("  -", i)
    else:
        print("✅ no noob-tells across all niches")


if __name__ == "__main__":
    asyncio.run(main())
