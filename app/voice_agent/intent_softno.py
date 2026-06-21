"""
Polite-No detector + 2-strike de-escalation (D-8 / P3-1) — the India flagship.
=============================================================================

India me 95% customers seedha "NO" nahi bolte — soft refusal dete hain ("dekhte
hain", "baad me", "abhi nahi"). Ek pushy bot ise "maybe" samajh ke push karta
raha to woh rude lagta + trust-tod deta. Rule (Haptik/Gong India research):

  * 1st soft-no  → ONE value-anchored re-ask allowed (normal reply chalti rahe).
  * 2nd soft-no  → push BAND. Graceful exit + async option (WhatsApp pe detail).

Yeh module = PURE POLICY (no LLM, no network, never raises). Detection
`qa_checks.is_soft_no` se reuse hota hai (single source of truth). Stateless:
soft-no count poori `history` se derive hota (works whether the current turn is
already in history or not). Gated `SOFTNO_DEESCALATE` (default ON — clear
trust/compliance win; set 0 to disable).

Wired in: `telecaller_brain.reply()` + `reply_stream_sentences()` (all niches).
Partial precedent: `platform_pitch.py` ka interest gate (ai_marketing only).
"""

from __future__ import annotations

import os

try:
    from app.voice_agent.qa_checks import is_soft_no
except Exception:  # pragma: no cover - keep import-safe
    def is_soft_no(_text: str) -> bool:  # type: ignore[misc]
        return False


# Graceful de-escalation closers — warm, non-pushy, async-exit (WhatsApp/website).
DEESCALATION_TEMPLATES = [
    "Bilkul ji, samajh gayi — aap abhi busy hain, koi baat nahi. Ek choti si "
    "jaankari WhatsApp pe bhej deti hoon, fursat mile to dekh lijiyega. Aapka din shubh rahe!",
    "Koi baat nahi ji, main samajh sakti hoon — zabardasti bilkul nahi karungi. "
    "Jab bhi zarurat lage, leadsgenai dot in pe hum mil jaayenge. Aapka din accha rahe!",
    "Theek hai ji, aapka time kimti hai. Main poori detail WhatsApp pe chhod deti "
    "hoon, aaram se dekh lijiyega. Dhanyavaad aur shubh din!",
]

# Hard rule appended to the brain's system prompt (guides the LLM on edge cases).
SYSTEM_RULE = (
    "\n\nPOLITE-NO RULE (India-critical): Customer 'dekhte hain / baad me / abhi nahi / "
    "zarurat nahi / time nahi' jaisa SOFT refusal de to — pehli baar ek hi short, "
    "value-anchored re-ask karo; DOOSRI baar refusal aaye to push BILKUL band karo, "
    "warmly samajhte hue gracefully exit karo (WhatsApp/website pe detail chhod do). "
    "2 baar polite 'na' ke baad dobara pitch = rude + trust-tod, KABHI mat karo."
)


def enabled() -> bool:
    """Default ON (clear trust/compliance win). Set SOFTNO_DEESCALATE=0 to disable."""
    return (os.environ.get("SOFTNO_DEESCALATE", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def soft_no_count(history: list[dict] | None, current_text: str = "") -> int:
    """Count soft-no refusals so far. Robust to whether ``current_text`` is already
    the last user turn in ``history`` (vobiz appends before calling) or not."""
    users = [
        str(m.get("content", ""))
        for m in (history or [])
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    cnt = sum(1 for u in users if is_soft_no(u))
    cur = (current_text or "").strip()
    if cur and is_soft_no(cur):
        # Add the current turn only if it isn't already counted as the last user turn.
        if not users or (users[-1] or "").strip() != cur:
            cnt += 1
    return cnt


def should_deescalate(history: list[dict] | None, current_text: str) -> bool:
    """True when the CURRENT turn is a soft-no AND it is the 2nd (or later) one —
    i.e., time to stop pitching and gracefully exit. Gated + never raises."""
    try:
        if not enabled():
            return False
        if not is_soft_no(current_text or ""):
            return False
        return soft_no_count(history, current_text) >= 2
    except Exception:  # pragma: no cover - defensive
        return False


def deescalation_reply(niche: str = "", client_name: str = "") -> str:
    """A warm, non-pushy graceful close. Deterministic pick (no RNG) so it is
    test-stable and varies a little per niche."""
    idx = (len(str(niche)) + len(str(client_name))) % len(DEESCALATION_TEMPLATES)
    return DEESCALATION_TEMPLATES[idx]


__all__ = [
    "enabled",
    "is_soft_no",
    "soft_no_count",
    "should_deescalate",
    "deescalation_reply",
    "SYSTEM_RULE",
    "DEESCALATION_TEMPLATES",
]
