"""Structured response contract for Swara turns (validate / repair).

Model may emit JSON; we always return a safe spoken Hinglish line.
Server decides hangup / tools — model only suggests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VoiceResponseContract:
    spoken_response: str
    detected_intent: str = "unknown"
    conversation_stage: str = "discovery"
    facts_learned: dict[str, str] = field(default_factory=dict)
    tool_request: dict[str, Any] | None = None
    should_end: bool = False
    end_reason: str = ""
    confidence: float = 0.5

    def as_dict(self) -> dict[str, Any]:
        return {
            "spoken_response": self.spoken_response,
            "detected_intent": self.detected_intent,
            "conversation_stage": self.conversation_stage,
            "facts_learned": dict(self.facts_learned),
            "tool_request": self.tool_request,
            "should_end": self.should_end,
            "end_reason": self.end_reason,
            "confidence": self.confidence,
        }


_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_MD_CHARS = re.compile(r"[#*_`>]{1,}")


def _strip_markdown(text: str) -> str:
    t = _MD_CHARS.sub("", text or "")
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def _one_question(text: str) -> str:
    """Keep at most one '?'. Extra questions → first sentence only."""
    t = (text or "").strip()
    if t.count("?") <= 1:
        return t
    # Keep through first question mark.
    i = t.find("?")
    return t[: i + 1].strip()


def parse_and_validate(raw: str, *, fallback_spoken: str = "") -> VoiceResponseContract:
    """Accept plain text or JSON. Never raises."""
    text = (raw or "").strip()
    if not text:
        return VoiceResponseContract(
            spoken_response=_strip_markdown(fallback_spoken or "Ji, boliye?"),
            confidence=0.2,
        )

    payload: dict[str, Any] | None = None
    # Try fenced JSON then bare object.
    m = _JSON_FENCE.search(text)
    candidate = (m.group(1) if m else text).strip()
    if candidate.startswith("{"):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                payload = obj
        except Exception:
            payload = None

    if payload is None:
        spoken = _one_question(_strip_markdown(text))
        return VoiceResponseContract(spoken_response=spoken, confidence=0.55)

    spoken = str(
        payload.get("spoken_response")
        or payload.get("reply")
        or payload.get("text")
        or fallback_spoken
        or ""
    ).strip()
    spoken = _one_question(_strip_markdown(spoken))
    if not spoken:
        spoken = _strip_markdown(fallback_spoken or "Ji, boliye?")

    facts = payload.get("facts_learned") or {}
    if not isinstance(facts, dict):
        facts = {}
    # Drop pricing keys from model-learned facts (server-owned).
    facts = {
        str(k)[:40]: str(v)[:120]
        for k, v in facts.items()
        if not str(k).lower().startswith("price") and str(k).lower() not in ("pricing", "plan")
    }

    tool = payload.get("tool_request")
    if tool is not None and not isinstance(tool, dict):
        tool = None

    try:
        conf = float(payload.get("confidence", 0.5))
    except Exception:
        conf = 0.5
    conf = max(0.0, min(conf, 1.0))

    return VoiceResponseContract(
        spoken_response=spoken,
        detected_intent=str(payload.get("detected_intent") or "unknown")[:40],
        conversation_stage=str(payload.get("conversation_stage") or "discovery")[:40],
        facts_learned=facts,
        tool_request=tool,
        should_end=bool(payload.get("should_end")),
        end_reason=str(payload.get("end_reason") or "")[:80],
        confidence=conf,
    )
