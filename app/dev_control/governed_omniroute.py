"""Claude/ChatGPT-governed, text-only OmniRoute proposal bridge.

OmniRoute receives one pre-built sanitized packet and returns untrusted text. It
never receives a repository/worktree path or any tool capability, and its output
can never apply a patch or authorize another side effect.
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from app.dev_control.context_packets import redact_packet_text
from app.platform.omniroute_client import OmniRouteResult, generate

Transport = Callable[..., Awaitable[OmniRouteResult | None]]

_REQUIRED_FLAGS = ("DEV_ORCHESTRATOR", "DEV_WORKER_ENABLED", "OMNIROUTE_ENABLED")


def _flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {"1", "true", "yes", "on"}


def _packet_admitted(packet_result: dict[str, Any]) -> bool:
    packet = packet_result.get("packet") or {}
    return bool(
        packet_result.get("ok")
        and packet_result.get("text")
        and packet.get("trust_label") == "UNTRUSTED_EXTERNAL_WORKER"
        and packet.get("side_effects_allowed") is False
        and packet.get("tool_access_allowed") is False
    )


async def request_governed_proposal(
    packet_result: dict[str, Any],
    *,
    task_type: str = "leadgen.coding_primary",
    transport: Transport = generate,
) -> dict[str, Any]:
    """Return a review-only proposal; never expose tools or mutate project state."""
    for name in _REQUIRED_FLAGS:
        if not _flag(name):
            return {
                "ok": False,
                "reason": "governance_disabled",
                "missing_flag": name,
                "applied": False,
            }

    if not _packet_admitted(packet_result):
        return {"ok": False, "reason": "packet_not_admitted", "applied": False}

    try:
        result = await transport(
            task_type,
            [{"role": "user", "content": packet_result["text"]}],
            "INTERNAL_SANITIZED",
        )
    except Exception as exc:  # provider/transport failure must never escape the boundary
        return {
            "ok": False,
            "reason": "omniroute_transport_error",
            "error_type": type(exc).__name__,
            "applied": False,
        }
    if result is None:
        return {"ok": False, "reason": "omniroute_unavailable", "applied": False}

    return {
        "ok": True,
        "text": redact_packet_text(result.text),
        "provider": result.provider,
        "model": result.model,
        "usage": {
            "prompt_tokens": result.input_tokens or 0,
            "completion_tokens": result.output_tokens or 0,
            "estimated": result.input_tokens is None or result.output_tokens is None,
            "actual_cost_usd": "0",
        },
        "fallback_reason": result.fallback_reason,
        "latency_ms": result.latency_ms,
        "applied": False,
        "review_required": True,
        "trust_label": "UNTRUSTED_PROVIDER_OUTPUT",
    }
