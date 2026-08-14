"""Per-call session state for Swara enterprise conversation (opener + routing).

Primary state machine for greeting / introduction / stage / sticky route.
Persists only in-memory for the live call (not cross-tenant Redis).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallSessionState:
    """One outbound/inbound stream call's conversation control plane."""

    call_id: str = ""
    tenant_id: str = ""
    niche: str = ""
    greeting_completed: bool = False
    introduction_count: int = 0
    opener_blocked_count: int = 0
    semantic_loop_detected: bool = False
    conversation_stage: str = "opening"  # opening|discovery|pitch|objection|close|ended
    closing_started: bool = False
    final_message_played: bool = False
    session_closed: bool = False
    active_model_route: str = ""
    active_provider: str = ""
    active_model: str = ""
    route_version: str = "v1"
    fallback_count: int = 0
    tools_called: list[str] = field(default_factory=list)
    facts_learned: dict[str, str] = field(default_factory=dict)
    stt_metrics: dict[str, int] = field(default_factory=dict)
    turn_latencies_ms: list[float] = field(default_factory=list)

    def mark_greeting_spoken(self) -> None:
        self.greeting_completed = True
        self.introduction_count = max(self.introduction_count, 1)
        if self.conversation_stage == "opening":
            self.conversation_stage = "discovery"

    def block_opener_repeat(self) -> None:
        self.opener_blocked_count += 1

    def pin_route(
        self,
        *,
        route: str,
        provider: str,
        model: str,
        version: str = "v1",
    ) -> None:
        self.active_model_route = route
        self.active_provider = provider
        self.active_model = model
        self.route_version = version

    def record_fallback(self, provider: str, model: str) -> None:
        self.fallback_count += 1
        self.active_provider = provider
        self.active_model = model

    def note_tool(self, name: str) -> None:
        if name and name not in self.tools_called:
            self.tools_called.append(name)

    def as_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tenant_id": self.tenant_id,
            "niche": self.niche,
            "greeting_completed": self.greeting_completed,
            "introduction_count": self.introduction_count,
            "opener_blocked_count": self.opener_blocked_count,
            "semantic_loop_detected": self.semantic_loop_detected,
            "conversation_stage": self.conversation_stage,
            "closing_started": self.closing_started,
            "final_message_played": self.final_message_played,
            "session_closed": self.session_closed,
            "active_model_route": self.active_model_route,
            "active_provider": self.active_provider,
            "active_model": self.active_model,
            "route_version": self.route_version,
            "fallback_count": self.fallback_count,
            "tools_called": list(self.tools_called),
            "facts_learned": dict(self.facts_learned),
            "stt_metrics": dict(self.stt_metrics),
            "turn_latency_count": len(self.turn_latencies_ms),
            "turn_latency_p50_ms": _p50(self.turn_latencies_ms),
        }


def _p50(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    return float(s[len(s) // 2])
