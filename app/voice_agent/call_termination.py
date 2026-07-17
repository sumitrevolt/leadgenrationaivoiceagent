"""Normalized call termination reasons + conversation length limits (voice).

Import-safe, never raises. Used by vobiz_stream + web_call + admin views.
"""

from __future__ import annotations

import os
from typing import Any

# Canonical termination reasons (stable strings for logs/dashboards).
RECIPIENT_HANGUP = "recipient_hangup"
RECIPIENT_REJECTED = "recipient_rejected"
RECIPIENT_OPTED_OUT = "recipient_opted_out"
AGENT_COMPLETED_GOAL = "agent_completed_goal"
MAX_DURATION_REACHED = "max_duration_reached"
MAX_TURNS_REACHED = "max_turns_reached"
SILENCE_TIMEOUT = "silence_timeout"
NO_INPUT_EXHAUSTED = "no_input_exhausted"
PROVIDER_DISCONNECT = "provider_disconnect"
WEBSOCKET_FAILURE = "websocket_failure"
STT_FAILURE = "stt_failure"
TTS_FAILURE = "tts_failure"
LLM_FAILURE = "llm_failure"
APPLICATION_EXCEPTION = "application_exception"
ADMIN_KILL_SWITCH = "admin_kill_switch"
CAMPAIGN_PAUSE = "campaign_pause"
UNKNOWN_TERMINATION = "unknown_termination"

ALL_REASONS: frozenset[str] = frozenset(
    {
        RECIPIENT_HANGUP,
        RECIPIENT_REJECTED,
        RECIPIENT_OPTED_OUT,
        AGENT_COMPLETED_GOAL,
        MAX_DURATION_REACHED,
        MAX_TURNS_REACHED,
        SILENCE_TIMEOUT,
        NO_INPUT_EXHAUSTED,
        PROVIDER_DISCONNECT,
        WEBSOCKET_FAILURE,
        STT_FAILURE,
        TTS_FAILURE,
        LLM_FAILURE,
        APPLICATION_EXCEPTION,
        ADMIN_KILL_SWITCH,
        CAMPAIGN_PAUSE,
        UNKNOWN_TERMINATION,
    }
)


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)) or default)
    except Exception:
        v = default
    return max(lo, min(v, hi))


def target_min_engaged_turns() -> int:
    """Soft floor for healthy engaged calls — never blocks early rejection/opt-out."""
    return _env_int("VOICE_TARGET_MIN_ENGAGED_TURNS", 10, 1, 30)


def soft_target_turns() -> int:
    return _env_int("VOICE_SOFT_TARGET_TURNS", 12, 1, 40)


def supported_max_turns() -> int:
    """Hard cap on completed dialogue exchanges (user+agent pairs)."""
    return _env_int("VOICE_SUPPORTED_MAX_TURNS", 20, 2, 50)


def max_call_duration_seconds() -> int:
    return _env_int("VOICE_MAX_CALL_DURATION_SECONDS", 600, 60, 3600)


def silence_timeout_seconds() -> float:
    try:
        v = float(os.environ.get("VOICE_SILENCE_TIMEOUT_SECONDS", "12") or 12)
    except Exception:
        v = 12.0
    return max(3.0, min(v, 120.0))


def silence_reprompts() -> int:
    return _env_int("VOICE_SILENCE_REPROMPTS", 2, 0, 5)


def end_after_rejection() -> bool:
    return (os.environ.get("VOICE_END_AFTER_REJECTION", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def end_after_optout() -> bool:
    return (os.environ.get("VOICE_END_AFTER_OPTOUT", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def count_user_turns(messages: list[dict[str, Any]]) -> int:
    return sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user")


def count_agent_turns(messages: list[dict[str, Any]]) -> int:
    return sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "assistant")


def count_completed_exchanges(messages: list[dict[str, Any]]) -> int:
    """One user utterance + one agent reply = one exchange (not audio chunks)."""
    return min(count_user_turns(messages), count_agent_turns(messages))


def classify_unknown(
    *,
    user_turns: int,
    duration_s: float,
    media_events: int = 0,
    had_speech_buffered: bool = False,
    provider_hangup_cause: str = "",
) -> str:
    """Best-effort reason when no explicit termination was recorded."""
    cause = (provider_hangup_cause or "").strip().lower()
    if "end_of_xml" in cause or "end of xml" in cause:
        if user_turns <= 0 and duration_s < 90:
            return PROVIDER_DISCONNECT
    if media_events == 0 and duration_s > 10:
        return PROVIDER_DISCONNECT
    if had_speech_buffered and user_turns == 0:
        return APPLICATION_EXCEPTION
    if user_turns > 0:
        return RECIPIENT_HANGUP
    return UNKNOWN_TERMINATION


def termination_record(
    *,
    reason: str,
    source: str,
    call_id: str = "",
    user_turns: int = 0,
    agent_turns: int = 0,
    completed_exchanges: int = 0,
    duration_s: float = 0.0,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured payload for transcript rows + call_logs qualification_data."""
    r = (reason or UNKNOWN_TERMINATION).strip()
    if r not in ALL_REASONS:
        r = UNKNOWN_TERMINATION
    rec: dict[str, Any] = {
        "termination_reason": r,
        "termination_source": (source or "unknown").strip()[:120],
        "user_turns": int(user_turns),
        "agent_turns": int(agent_turns),
        "completed_exchanges": int(completed_exchanges),
        "duration_s": round(float(duration_s), 1),
    }
    if call_id:
        rec["call_id"] = call_id
    if extra:
        rec.update(extra)
    return rec


__all__ = [
    "AGENT_COMPLETED_GOAL",
    "ALL_REASONS",
    "APPLICATION_EXCEPTION",
    "MAX_DURATION_REACHED",
    "MAX_TURNS_REACHED",
    "NO_INPUT_EXHAUSTED",
    "PROVIDER_DISCONNECT",
    "RECIPIENT_HANGUP",
    "RECIPIENT_OPTED_OUT",
    "RECIPIENT_REJECTED",
    "SILENCE_TIMEOUT",
    "UNKNOWN_TERMINATION",
    "WEBSOCKET_FAILURE",
    "classify_unknown",
    "count_agent_turns",
    "count_completed_exchanges",
    "count_user_turns",
    "end_after_optout",
    "end_after_rejection",
    "max_call_duration_seconds",
    "silence_reprompts",
    "silence_timeout_seconds",
    "soft_target_turns",
    "supported_max_turns",
    "target_min_engaged_turns",
    "termination_record",
]
