"""Post-call AI lead qualification + summary — Expedify-style "qualify leads 24/7".

Call ke transcript ko free-LLM se analyze karke STRUCTURED qualification deta:
interest score, qualified?, appointment chahiye?, budget signal, summary, next
action, + ek ready Hinglish follow-up draft.

DESIGN: real-time voice path ke BAHAR (post-call) — koi latency risk nahi.
Free-stack (app.voice_agent.free_ai). Import-safe, kabhi raise nahi karta.
"""

from __future__ import annotations

import json
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SYSTEM = (
    "Tum ek sales-QA analyst ho. Ek phone call ka transcript milega. SIRF ek JSON "
    "object lautao (aur kuch nahi):\n"
    '{"interest_score": <1-5 int>, "qualified": <true|false>, '
    '"appointment_requested": <true|false>, "budget_signal": "<low|medium|high|unknown>", '
    '"summary": "<1-2 line Hinglish>", "next_action": "<1 line Hinglish suggestion>", '
    '"followup_draft": "<short Hinglish follow-up message customer ke liye>"}.\n'
    "qualified=true tabhi jab customer ne genuine interest/need dikhaya ho. "
    "Koi explanation mat do, sirf JSON."
)


def _extract_json(text: str) -> dict[str, Any]:
    if not text:
        return {}
    t = text.strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1 and j > i:
        t = t[i : j + 1]
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _coerce(d: dict[str, Any]) -> dict[str, Any]:
    """LLM output ko safe shape me laao (missing/garbage -> defaults)."""
    try:
        score = int(d.get("interest_score", 0))
    except Exception:
        score = 0
    score = max(0, min(5, score))
    bud = str(d.get("budget_signal", "unknown")).lower()
    if bud not in ("low", "medium", "high", "unknown"):
        bud = "unknown"
    return {
        "interest_score": score,
        "qualified": bool(d.get("qualified", False)),
        "appointment_requested": bool(d.get("appointment_requested", False)),
        "budget_signal": bud,
        "summary": str(d.get("summary", "") or "")[:400],
        "next_action": str(d.get("next_action", "") or "")[:200],
        "followup_draft": str(d.get("followup_draft", "") or "")[:600],
    }


async def qualify_transcript(
    transcript: str, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Transcript -> structured qualification + follow-up draft. Kabhi raise nahi.

    Returns dict with keys: interest_score, qualified, appointment_requested,
    budget_signal, summary, next_action, followup_draft, provider, ok.
    """
    ctx = context or {}
    tx = (transcript or "").strip()
    if len(tx) < 10:
        return {
            "ok": False,
            "reason": "transcript too short",
            "interest_score": 0,
            "qualified": False,
            "appointment_requested": False,
            "budget_signal": "unknown",
            "summary": "",
            "next_action": "Call dobara try karo / transcript missing.",
            "followup_draft": "",
            "provider": "",
        }
    who = ctx.get("business_name") or ctx.get("name") or "customer"
    user_msg = f"Customer: {who}. Niche: {ctx.get('niche', 'general')}.\n\nTranscript:\n{tx[:4000]}"
    try:
        from app.voice_agent import free_ai

        raw, provider = await free_ai.chat(
            _SYSTEM, [{"role": "user", "content": user_msg}], max_tokens=320, temperature=0.2
        )
    except Exception as e:
        logger.warning(f"[call_qualifier] llm failed: {e}")
        raw, provider = "", ""
    parsed = _coerce(_extract_json(raw))
    parsed["provider"] = provider
    parsed["ok"] = bool(provider) and bool(parsed.get("summary"))
    if not parsed["followup_draft"]:
        parsed["followup_draft"] = (
            f"Namaste {who}! Call ke liye dhanyawad. Aapki zaroorat ke hisaab se hum aapse jald follow-up karenge."
        )
    return parsed


__all__ = ["qualify_transcript"]
