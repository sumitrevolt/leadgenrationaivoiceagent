"""Agent consensus — Ruflo N-voter quorum decision (free-stack).

LLM Council ke existing pro/con debate se ALAG: yahan `voters` independent free-LLM
"voter" calls chalte hain, har ek ko ek persona + alag temperature diya jata hai
(taaki opinions sach me diverge karein), har voter EK option pick karta, votes tally
hote hain → winner + confidence + quorum check.

Quorum rule: winner ke paas > voters/2 votes hone chahiye, warna no_quorum (koi
clear majority nahi). Ek voter ka LLM fail ho jaye → woh voter ABSTAIN (kabhi crash
nahi).

Design (project patterns):
  - `enabled()` sirf is feature ka auto-use gate karta — `vote()` khud hamesha
    safe-callable (admin endpoint + tests ke liye).
  - free_ai lazy import + per-call asyncio.wait_for timeout 40s.
  - Kabhi raise nahi karta — har failure path graceful dict/abstain.

Flag: AGENT_CONSENSUS=1
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_VOTER_TIMEOUT_S = 40.0
_MAX_VOTERS = 9

# Per-voter persona + temperature — diversity ke liye index pe rotate hota.
_VOTER_PERSONAS: list[tuple[str, float]] = [
    ("Tum ek cautious, risk-averse analyst ho.", 0.2),
    ("Tum ek bold, growth-first operator ho.", 0.8),
    ("Tum ek pragmatic, data-driven engineer ho.", 0.45),
    ("Tum ek skeptical devil's-advocate reviewer ho.", 0.7),
    ("Tum ek customer-empathy product manager ho.", 0.55),
    ("Tum ek cost-conscious finance lead ho.", 0.3),
    ("Tum ek fast-moving startup founder ho.", 0.85),
    ("Tum ek compliance-aware legal advisor ho.", 0.25),
    ("Tum ek balanced senior decision-maker ho.", 0.5),
]


def enabled() -> bool:
    """Gates AUTOMATIC consensus use. vote() khud flag-independent safe-callable."""
    return (os.getenv("AGENT_CONSENSUS") or "").strip().lower() in ("1", "true", "yes")


def _map_to_option(raw: str, options: list[str]) -> str | None:
    """LLM ke free-text reply ko nearest option pe map karo (defensive parse)."""
    text = (raw or "").strip()
    if not text:
        return None
    low = text.lower()

    # 1) exact (case-insensitive) match
    for opt in options:
        if opt.strip().lower() == low:
            return opt
    # 2) option string reply ke andar substring (longest-first taaki "A" "AB" ko na cheene)
    for opt in sorted(options, key=lambda o: -len(o)):
        o = opt.strip().lower()
        if o and o in low:
            return opt
    # 3) index / number reply ("1", "option 2")
    digits = "".join(ch if ch.isdigit() else " " for ch in low).split()
    for d in digits:
        try:
            idx = int(d)
        except Exception:
            continue
        if 1 <= idx <= len(options):
            return options[idx - 1]
    return None


async def _one_vote(question: str, options: list[str], index: int) -> dict[str, Any]:
    """Ek voter ka call — persona + temperature index pe. Fail = abstain (no crash)."""
    persona, temp = _VOTER_PERSONAS[index % len(_VOTER_PERSONAS)]
    opts_block = "\n".join(f"- {o}" for o in options)
    system = persona + " Tumhe ek decision lena hai. SIRF di gayi options me se EXACTLY EK chuno."
    user = (
        f"Sawal: {question}\n\nOptions:\n{opts_block}\n\n"
        "Pehle 1 line me apna reason do, fir aakhri line me likho: "
        "CHOICE: <exact option text>"
    )
    try:
        from app.voice_agent import free_ai

        text, _prov = await asyncio.wait_for(
            free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=160,
                temperature=temp,
                scope="consensus",
            ),
            timeout=_VOTER_TIMEOUT_S,
        )
    except Exception as e:  # pragma: no cover - voter abstains, never crash
        logger.debug("consensus voter %d failed: %s", index, e)
        return {"index": index, "choice": None, "rationale": "", "ok": False}

    text = (text or "").strip()
    choice = None
    # "CHOICE:" line ko prefer karo, warna pure text pe map
    if "CHOICE:" in text.upper():
        tail = text[text.upper().rfind("CHOICE:") + len("CHOICE:") :]
        choice = _map_to_option(tail, options)
    if choice is None:
        choice = _map_to_option(text, options)
    return {
        "index": index,
        "choice": choice,
        "rationale": text[:300],
        "ok": choice is not None,
    }


async def vote(question: str, options: list[str], voters: int = 3) -> dict:
    """N-voter quorum decision. Never raises.

    Returns:
      {winner, tally:{option:count}, confidence, rationale_samples:[...]}  ya
      {winner:None, reason:"no_quorum", tally}  jab clear majority na ho.
      options < 2 → {ok:False, error:...}.
    """
    q = (question or "").strip()
    opts = [str(o).strip() for o in (options or []) if str(o).strip()]
    # dedupe order-preserving
    seen: set[str] = set()
    uniq: list[str] = []
    for o in opts:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    opts = uniq

    if len(opts) < 2:
        return {"ok": False, "error": "kam se kam 2 distinct options chahiye"}
    if not q:
        return {"ok": False, "error": "empty question"}

    try:
        n = max(1, min(int(voters or 3), _MAX_VOTERS))
    except Exception:
        n = 3

    try:
        results = await asyncio.gather(
            *[_one_vote(q, opts, i) for i in range(n)], return_exceptions=True
        )
    except Exception as e:  # pragma: no cover
        logger.debug("consensus gather failed: %s", e)
        results = []

    tally: dict[str, int] = dict.fromkeys(opts, 0)
    rationale_samples: list[str] = []
    valid_votes = 0
    for r in results:
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        choice = r.get("choice")
        if choice in tally:
            tally[choice] += 1
            valid_votes += 1
            rat = (r.get("rationale") or "").strip()
            if rat and len(rationale_samples) < 3:
                rationale_samples.append(rat)

    if valid_votes == 0:
        return {
            "winner": None,
            "reason": "no_votes",
            "tally": tally,
            "confidence": 0.0,
            "rationale_samples": [],
        }

    winner = max(tally.items(), key=lambda kv: kv[1])
    winner_opt, winner_votes = winner
    confidence = round(winner_votes / valid_votes, 3) if valid_votes else 0.0

    # Quorum: winner ke paas > voters/2 votes (requested voters pe, abstain-strict)
    if winner_votes <= n / 2:
        return {
            "winner": None,
            "reason": "no_quorum",
            "tally": tally,
            "confidence": confidence,
            "rationale_samples": rationale_samples,
            "valid_votes": valid_votes,
            "voters": n,
        }

    return {
        "winner": winner_opt,
        "tally": tally,
        "confidence": confidence,
        "rationale_samples": rationale_samples,
        "valid_votes": valid_votes,
        "voters": n,
    }


__all__ = ["enabled", "vote"]
