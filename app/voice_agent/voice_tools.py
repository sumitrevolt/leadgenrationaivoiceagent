"""
In-call agentic tools — wiring layer for the live voice agent.
==============================================================

`function_calling.py` already DEFINES the tools (book_appointment,
check_availability, capture_lead_info, transfer_to_human, get_pricing_info,
end_call) + a robust `parse_tool_call`. This module is the thin, SAFE glue that
lets the LIVE call loop actually *use* them — the "agentic" capability Retell /
Vapi / Bland advertise.

Design (matches the rest of the project):
  * **Gated `VOICE_TOOLS=1` (default OFF)** — when off, NOTHING here runs and the
    voice agent behaves exactly as before (the brain's normal reply()/stream).
  * **Isolated** — the agentic path is a SEPARATE code path
    (`TelecallerBrain.reply_with_tools`) so the delicately-tuned default reply
    is untouched. No brain prompt is changed unless the flag is on.
  * **Defensive** — every helper is import-safe + never raises; a tool failure
    degrades to a spoken fallback, never a dropped call.

The brain, when this flag is on, is given a compact instruction telling it that
to take an action it may output exactly ONE line ``CALL <tool> {json}`` (the
convention `function_calling.parse_tool_call` already understands). Otherwise it
just speaks normally.
"""

from __future__ import annotations

import asyncio
import os

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


def voice_tools_enabled() -> bool:
    """True only when VOICE_TOOLS is explicitly enabled (default OFF).

    Default OFF = zero behaviour change; the agentic path never executes."""
    return (os.environ.get("VOICE_TOOLS", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# Tools the brain is allowed to *trigger by speaking a CALL line*. Kept to the
# high-value, low-risk actions; get_pricing_info is excluded here because the
# brain already quotes pricing in natural speech (no need to round-trip a tool).
_SPEAKABLE_TOOLS = (
    "book_appointment",
    "check_availability",
    "reschedule_appointment",
    "capture_lead_info",
    "transfer_to_human",
    "end_call",
)


def tools_instruction(registry: object | None = None) -> str:
    """Compact prompt block appended to the system prompt ONLY on the VOICE_TOOLS
    path. Lists the available in-call actions + the strict CALL convention.

    Derives the tool list from the live registry when possible (stays in sync),
    else falls back to the static high-value set. Kept short — phone hot path."""
    available = list(_SPEAKABLE_TOOLS)
    try:
        if registry is not None and hasattr(registry, "names"):
            names = [n for n in registry.names() if n in _SPEAKABLE_TOOLS]
            if names:
                available = names
    except Exception:
        pass
    tool_line = ", ".join(available)
    # Current IST date so the LLM resolves "kal"/"parso"/"Monday" → correct ISO date
    # (warna woh galat saal/date hallucinate karta — real booking garbage date pe ban
    # jaati). Defensive: clock error pe date-line skip.
    date_hint = ""
    try:
        from datetime import datetime, timedelta, timezone

        _ist = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))
        date_hint = (
            f"AAJ ki date: {_ist.strftime('%Y-%m-%d (%A)')} (IST). "
            "'kal'=+1 din, 'parso'=+2 din, weekday-naam isi se aage ka — when_iso me "
            "HAMESHA isi se resolve kiya sahi ISO date+time do (kabhi purana saal nahi).\n"
        )
    except Exception:
        pass
    return (
        "\n\nIN-CALL ACTIONS (agentic): tu sirf baat nahi karti — zaroorat pe action le sakti hai.\n"
        f"{date_hint}"
        f"Available actions: {tool_line}.\n"
        "Action lene ke liye SIRF ek line output kar, bilkul is format me (aur kuch nahi):\n"
        '  CALL <action_name> {"arg": "value"}\n'
        "Kab kya:\n"
        "- Lead specific date+time pe meeting/demo/visit ke liye haan kare -> "
        'CALL book_appointment {"when_iso":"YYYY-MM-DDTHH:MM","name":"...","phone":"..."}\n'
        "- Lead apni PEHLE se booked appointment ka time badalna/postpone karna chahe -> "
        'CALL reschedule_appointment {"new_when_iso":"YYYY-MM-DDTHH:MM","phone":"..."}\n'
        "- Lead budget / timeline / email / decision-maker bataye -> "
        'CALL capture_lead_info {"budget_range":"...","timeline":"...","interest_level":"high"}\n'
        "- Lead insaan se baat maange, ya high-value/complex case ho -> "
        'CALL transfer_to_human {"reason":"..."}\n'
        "- Baat natural taur pe khatam ho jaye (lead ne bye bola / clearly not interested) -> "
        'CALL end_call {"outcome":"qualified|not_interested|callback"}\n'
        "Agar koi action ki zaroorat NAHI hai to normal chhota Hinglish jawab de — koi CALL nahi.\n"
        "Ek turn me ZYADA SE ZYADA ek CALL. CALL line me sirf valid JSON args.\n"
        "ANTI-FAKE (ZAROORI): 'book ho gaya' / 'confirm ho gaya' / 'move kar di' / "
        "'cancel kar di' jaisa SUCCESS-confirmation KABHI mat bol jab tak tune upar wali "
        "CALL line na bheji ho — bina CALL ke booking/reschedule confirm karna JHOOTH hai. "
        "Time/detail missing ho to confirm karne ki jagah woh detail POOCHO."
    )


def confirmation_line(name: str, result: object) -> str:
    """Short Hinglish line the agent SPEAKS after running a tool. Prefers the
    tool's own confirmation_text / summary; else a safe per-action line. SHARED by
    the phone (vobiz) + web-call paths so both speak identically. Never raises."""
    try:
        data = getattr(result, "data", None)
        data = data if isinstance(data, dict) else {}
        if data.get("confirmation_text"):
            return str(data["confirmation_text"])
        if name == "book_appointment":
            when = data.get("when") or ""
            return (
                f"Theek hai, aapki appointment {when} ke liye book kar di hai. "
                "Confirmation aapko mil jayega."
            ).strip()
        if name == "check_availability":
            return (
                "In time pe slot available hai — aapko kaunsa theek rahega?"
                if data.get("slots")
                else "Main availability check kar rahi hoon, ek second."
            )
        if name == "reschedule_appointment":
            return "Theek hai, aapki appointment naye time pe move kar di hai. Confirmation mil jayega."
        if name == "capture_lead_info":
            return "Ji, aapki detail note kar li hai."
        if name == "transfer_to_human":
            return "Ek second, main aapko hamare expert se connect kar rahi hoon."
        if name == "get_pricing_info":
            return str(data.get("summary") or "Pricing main aapko bata deti hoon.")
        if name == "end_call":
            return "Aapka time dene ke liye dhanyavaad. Aapka din shubh rahe!"
        if getattr(result, "ok", False):
            return "Ji, ho gaya."
    except Exception:  # pragma: no cover - defensive
        pass
    return "Theek hai ji, aage badhte hain."


def build_registry_for(
    *,
    niche: str = "general",
    client_id: object = None,
    lead_phone: str = "",
    history: list | None = None,
):
    """Per-call ToolRegistry with the standard in-call context. Returns None if
    function_calling is unavailable (caller falls back to the normal reply)."""
    try:
        from app.voice_agent.function_calling import build_default_registry

        return build_default_registry(
            {
                "lead": {"phone": lead_phone or ""},
                "niche": niche,
                "client_id": client_id,
                "conversation_history": history or [],
            }
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"voice_tools: registry build failed: {e}")
        return None


async def run_tool_turn(
    brain: object,
    history: list,
    user_text: str,
    registry: object,
    *,
    timeout: float = 16.0,
) -> dict:
    """Run ONE agentic turn and return a TRANSPORT-AGNOSTIC decision dict:

        {"spoken": str, "did_tool": bool, "tool": str | None, "should_end": bool}

    The caller speaks ``spoken`` and, if ``should_end``, closes the call. Used by
    BOTH the phone (vobiz) and web-call paths so the agentic behaviour is
    identical everywhere. Never raises — any failure yields an empty ``spoken`` so
    the caller cleanly falls back to the normal reply path."""
    out = {"spoken": "", "did_tool": False, "tool": None, "should_end": False}
    try:
        if brain is None or registry is None or not hasattr(brain, "reply_with_tools"):
            return out
        spoken, call = await asyncio.wait_for(
            brain.reply_with_tools(history, user_text, registry), timeout=timeout
        )
        if call and call.get("name"):
            name = str(call.get("name"))
            try:
                result = await registry.execute(name, call.get("args") or {})
            except Exception as e:
                logger.warning(f"voice_tools: tool {name} execute failed: {e}")
                return out
            should_end = name == "end_call" or (
                isinstance(getattr(result, "data", None), dict) and result.data.get("should_end")
            )
            out.update(
                {
                    "spoken": confirmation_line(name, result),
                    "did_tool": True,
                    "tool": name,
                    "should_end": bool(should_end),
                }
            )
            return out
        out["spoken"] = (spoken or "").strip()
        return out
    except asyncio.TimeoutError:
        logger.warning("voice_tools: run_tool_turn timed out")
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"voice_tools: run_tool_turn failed: {e}")
        return out


__all__ = [
    "voice_tools_enabled",
    "tools_instruction",
    "confirmation_line",
    "build_registry_for",
    "run_tool_turn",
]
