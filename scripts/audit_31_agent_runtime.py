"""
31-Agent Runtime & Orchestration Truth Audit Script (v2.0)
===========================================================
Non-destructive diagnostic tool that inspects:
1. 31/31 agent contracts in app/platform/agent_registry.py
2. Scheduler configuration and job triggers
3. Execution path mapping (Celery / Hermes / Local / Router)
4. Primary flags and kill switches
5. Status classification: ACTIVE / READY_IDLE / STAGED_SHADOW / DISABLED_RED
"""

from __future__ import annotations

import os
import sys
import json
from typing import Dict, Any

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.platform.agent_registry import (
    build_registry,
    Lane,
    HARD_OFF,
    LIVE,
    DRAFT,
    SHADOW,
    PROPOSAL,
    INBOUND_READY,
)


def run_audit() -> Dict[str, Any]:
    registry = build_registry()
    print(f"=== 31-AGENT RUNTIME & ORCHESTRATION AUDIT ===")
    print(f"Total Agents Registered: {len(registry)}\n")

    summary_counts = {
        "ACTIVE": 0,
        "READY_IDLE": 0,
        "STAGED_SHADOW": 0,
        "DISABLED_RED": 0,
    }

    agent_matrix = []

    for agent_id, contract in registry.items():
        primary_flag_val = os.getenv(contract.primary_flag, "") if contract.primary_flag else "1"
        is_primary_enabled = primary_flag_val.lower() in ("1", "true", "yes", "on")

        # Classification logic
        if contract.lane == Lane.RED or contract.default_mode == HARD_OFF:
            status = "DISABLED_RED"
            reason = f"RED lane / default_mode={contract.default_mode} (Safety Gated)"
        elif contract.default_mode in (DRAFT, SHADOW, PROPOSAL):
            status = "STAGED_SHADOW"
            reason = f"Staged mode ({contract.default_mode}) — non-committing"
        elif contract.default_mode == INBOUND_READY or (contract.default_mode == LIVE and (not contract.primary_flag or is_primary_enabled)):
            status = "ACTIVE"
            reason = f"Live mode + armed trigger ({', '.join(contract.trigger_types)})"
        elif contract.default_mode == LIVE and not is_primary_enabled:
            status = "READY_IDLE"
            reason = f"GREEN lane / LIVE mode ready; flag '{contract.primary_flag}' currently un-flipped"

        # Execution path mapping
        if agent_id in ("manager", "boss"):
            exec_path = "Boss Coordinator / Agent-OS Engine"
        elif "scheduled" in contract.trigger_types:
            exec_path = "Celery Beat -> leadgen_worker / worker-heavy"
        elif "inbound" in contract.trigger_types or "event" in contract.trigger_types:
            exec_path = "FastAPI Event / Lifespan Hook"
        elif "queue" in contract.trigger_types:
            exec_path = "Celery Queue (DLQ / Cadence)"
        else:
            exec_path = "Embedded Specialist Sub-engine"

        # Hermes bot mapping
        hermes_bot_map = {
            "manager": "board / pilot",
            "kavya": "guardian",
            "hermes": "platform",
            "nikhil": "operations / success",
            "vikram": "engineering",
            "guru": "engineering",
            "pranav": "platform / engineering",
            "vidya": "guardian",
            "arnav": "guardian",
            "kabir": "platform",
            "diya": "guardian",
            "aryan": "engineering",
            "arya": "platform",
            "dev": "operations",
            "rohan": "sales / hunter",
            "isha": "operations",
            "ravi": "operations",
            "neha": "sales",
            "kiran": "sales",
            "priya": "operations",
            "zara": "operations",
            "anika": "sales / hunter",
            "ira": "sales",
            "swara": "sales (Red Voice)",
            "ananya": "sales (Red Voice)",
            "riya": "operations (Inbound Voice)",
            "arjun": "operations",
            "meera": "engineering",
            "lekha": "board",
            "raksha": "operations",
            "tara": "platform",
        }

        hermes_bot = hermes_bot_map.get(agent_id, "unmapped")
        summary_counts[status] += 1

        agent_info = {
            "id": agent_id,
            "name": contract.name,
            "team": contract.team,
            "autonomy": contract.autonomy,
            "lane": contract.lane,
            "default_mode": contract.default_mode,
            "primary_flag": contract.primary_flag or "CORE (Ungated)",
            "max_concurrency": contract.max_concurrency,
            "exec_path": exec_path,
            "hermes_bot": hermes_bot,
            "status": status,
            "reason": reason,
        }
        agent_matrix.append(agent_info)

    print(f"{'ID':<10} | {'TEAM':<10} | {'LANE':<6} | {'MODE':<12} | {'CONC':<4} | {'STATUS':<13} | {'HERMES BOT':<18} | {'EXEC PATH':<35}")
    print("-" * 120)
    for a in agent_matrix:
        print(f"{a['id']:<10} | {a['team']:<10} | {a['lane']:<6} | {a['default_mode']:<12} | {a['max_concurrency']:<4} | {a['status']:<13} | {a['hermes_bot']:<18} | {a['exec_path']:<35}")

    print("\n=== SUMMARY BY STATUS ===")
    for k, v in summary_counts.items():
        print(f"  {k:<13}: {v}")

    return {
        "total": len(registry),
        "counts": summary_counts,
        "agents": agent_matrix,
    }


if __name__ == "__main__":
    run_audit()
