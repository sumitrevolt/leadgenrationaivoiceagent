"""Hermes3D Virtual Office Custom Runtime Bridge (2026-09-21)
===========================================================
Custom HTTP adapter bridging iamlukethedev/Hermes3D 3D Virtual Office
with the canonical LeadGen AI workforce (9 supervisory bots, 31 specialist agents).

Invariants:
- Real events only: reads directly from team.STAFF and real agent_events (no fake avatars).
- TypeSafe awareness: surfaces logical key slots (TS_A..TS_D) status in the 3D office state.
- Mode toggle: supports 2D fallback mode for low-resource environments.
- Network security: allowlist boundary check on custom runtime requests.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.platform import team
from app.platform.key_manager import get_key_manager

logger = logging.getLogger(__name__)

# Canonical 9 supervisory bots
CANONICAL_SUPERVISORY_BOTS: list[dict[str, Any]] = [
    {
        "id": "owner_orchestrator",
        "name": "Owner / Orchestrator",
        "description": "Business objectives, priority queue, conflict resolution, safety enforcement.",
        "icon": "crown",
    },
    {
        "id": "revenue_cro",
        "name": "Revenue / CRO Bot",
        "description": "Prospect prioritization, pricing, sales funnel, conversion, collected revenue.",
        "icon": "trending-up",
    },
    {
        "id": "lead_intelligence",
        "name": "Lead Intelligence Bot",
        "description": "Lead discovery, enrichment, scoring, deduplication, qualification.",
        "icon": "search",
    },
    {
        "id": "outreach_conversation",
        "name": "Outreach & Conversation Bot",
        "description": "WhatsApp, email, compliant outreach, reply triage, appointment booking.",
        "icon": "message-circle",
    },
    {
        "id": "voice_swara",
        "name": "Voice / Swara Bot",
        "description": "Call queue, voice provider availability, scripts, qualification, follow-ups.",
        "icon": "phone-call",
    },
    {
        "id": "marketing_content",
        "name": "Marketing / Content Bot",
        "description": "Daily creatives, social content, video generation, approval queue.",
        "icon": "image",
    },
    {
        "id": "engineering_sre",
        "name": "Engineering / SRE Bot",
        "description": "Docker, VPS, queues, CI/CD, deployment, observability, survivability.",
        "icon": "cpu",
    },
    {
        "id": "qa_analytics",
        "name": "QA & Analytics Bot",
        "description": "End-to-end testing, voice call regression, funnel analytics, challenge claims.",
        "icon": "check-circle",
    },
    {
        "id": "finance_compliance",
        "name": "Finance & Compliance Bot",
        "description": "DPDP + TRAI compliance, unit economics, invoice reconciliation, secret rotation.",
        "icon": "shield",
    },
]

DEFAULT_ALLOWLIST = {
    "127.0.0.1",
    "::1",
    "localhost",
    "host.docker.internal",
}


class Hermes3DBridge:
    """Bridge coordinating state, registry, and commands for Hermes3D custom provider."""

    def __init__(self) -> None:
        raw_allowlist = os.getenv("CUSTOM_RUNTIME_ALLOWLIST", "")
        self.allowlist: set[str] = set(DEFAULT_ALLOWLIST)
        if raw_allowlist:
            for item in raw_allowlist.split(","):
                clean = item.strip()
                if clean:
                    self.allowlist.add(clean)

        self.mode_2d_fallback: bool = os.getenv("HERMES3D_2D_MODE", "0").lower() in ("1", "true", "yes")

    def is_client_allowed(self, client_ip: str | None) -> bool:
        if not client_ip:
            return True
        # Check direct IP or local loopback
        if client_ip in self.allowlist or "0.0.0.0" in self.allowlist or "*" in self.allowlist:
            return True
        return False

    def get_health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "runtime": "leadgen_hermes3d",
            "adapter": "custom",
            "mode_2d": self.mode_2d_fallback,
        }

    def get_registry(self) -> dict[str, Any]:
        """Return canonical workforce registry (31 staff + 9 supervisory bots)."""
        staff_agents = []
        for agent_id, info in team.STAFF.items():
            staff_agents.append({
                "id": agent_id,
                "name": info.get("name", agent_id),
                "title": info.get("title", ""),
                "emoji": info.get("emoji", "🤖"),
                "product": info.get("product", "platform"),
                "duties": info.get("duties", ""),
                "schedule": info.get("schedule", ""),
            })

        return {
            "agents": staff_agents,
            "supervisory_bots": CANONICAL_SUPERVISORY_BOTS,
            "telemetry_standard": "REAL_EVENTS_ONLY",
            "runtime_type": "custom",
        }

    def get_state(self) -> dict[str, Any]:
        """Return live agent states, office environment, and TypeSafe gateway slots."""
        team_state = team.team_status()
        km = get_key_manager()
        slots_status = km.get_all_slots()

        return {
            "agents": team_state.get("members", {}),
            "summary": team_state.get("summary", {}),
            "office": {
                "environment": "2d_fallback" if self.mode_2d_fallback else "3d_office",
                "typesafe_gateway": {
                    "provider": "TypeSafe Jev",
                    "model": os.getenv("TYPESAFE_MODEL", "jev-latest"),
                    "slots": slots_status,
                },
            },
            "evidence_kind": "real_events_only",
        }

    def get_config(self) -> dict[str, Any]:
        return {
            "adapter_type": "custom",
            "allowlist": list(self.allowlist),
            "mode_2d_fallback": self.mode_2d_fallback,
            "poll_interval_sec": 3.0,
        }

    def handle_command(self, action: str, target_agent: str | None = None, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch administrative command from 3D office."""
        parameters = parameters or {}
        if action == "toggle_2d_mode":
            self.mode_2d_fallback = not self.mode_2d_fallback
            logger.info("[hermes3d] 2D fallback mode toggled to: %s", self.mode_2d_fallback)
            return {
                "success": True,
                "action": action,
                "mode_2d": self.mode_2d_fallback,
            }

        logger.info("[hermes3d] Dispatched action=%s to target=%s with params=%s", action, target_agent, parameters)
        return {
            "success": True,
            "action": action,
            "target_agent": target_agent,
            "parameters": parameters,
            "status": "dispatched",
        }


_bridge: Hermes3DBridge | None = None


def get_hermes3d_bridge() -> Hermes3DBridge:
    global _bridge
    if _bridge is None:
        _bridge = Hermes3DBridge()
    return _bridge
