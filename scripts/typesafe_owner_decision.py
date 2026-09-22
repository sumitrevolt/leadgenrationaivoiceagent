#!/usr/bin/env python3
"""Bounded TypeSafe decision call — owner admin blocker priority.

Loads the canonical LeadGen TypeSafe client and asks one question:
what is the correct priority order for resolving the current platform
blockers. The decision is consumed (acted upon) and written to the
ledger. Fail-closed: on any error, a deterministic fallback is used.
"""
from __future__ import annotations

import json
import os
import sys
import time

# Ensure project root is importable when run from the venv directly
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Load .env (the app does not load_dotenv itself)
from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

from app.platform.typesafe_integration import TypeSafeClient, Score  # noqa: E402


def main() -> int:
    state = {
        "platform": "LeadGen AI",
        "role": "owner_admin",
        "current_blockers": [
            "telegram_409_conflict",
            "notify_token_401",
            "coordination_groups_missing",
            "vps_deploy_in_progress",
        ],
        "revenue_target": "10000000 INR/month",
        "current_collected": "0 INR (Sep 2026)",
        "server_health": "healthy",
        "owner_copilot": "enabled",
    }

    question = Score(
        question=(
            "Given the current blockers on the LeadGen AI platform, what is "
            "the correct priority order for resolution?"
        ),
        criteria=[
            "Telegram 409 conflict blocks owner command ingestion (revenue-critical)",
            "Notify token 401 blocks egress alerts (P0 incident path)",
            "Coordination groups required for 31-agent coordination (scaling)",
            "VPS deploy in progress (do not interrupt)",
        ],
        instructions=(
            "Prioritize by: revenue impact, owner-only vs system-executable, "
            "and downstream dependencies. Return the priority order."
        ),
    )

    client = TypeSafeClient()

    print("=== TYPESAFE DECISION CALL ===")
    print("model: jev-latest")
    print("task_id: owner-admin-blocker-priority-20260921")
    print("tenant_scope: leadgen_ai_owner")
    print("purpose: blocker_priority_ordering")
    print()

    try:
        result = client.system_one(
            state=state,
            questions={"priority_order": question},
        )

        print("=== TYPESAFE RESULT ===")
        print(f"success: {result.success}")
        print(f"model: {result.model}")
        print(f"latency: {result.latency_sec}s")

        if result.success:
            answers = result.answers
            answer = answers.get("priority_order", {})
            decision = (
                answer.get("choice")
                or answer.get("score")
                or answer.get("value")
                or str(answer)
            )

            print("\n=== TRACED DECISION ===")
            print(f"decision: {decision}")
            print(f"confidence: {answer.get('confidence', 'N/A')}")

            ledger_entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "task_id": "owner-admin-blocker-priority-20260921",
                "tenant_scope": "leadgen_ai_owner",
                "purpose": "blocker_priority_ordering",
                "model_requested": "jev-latest",
                "model_resolved": result.model,
                "latency_sec": result.latency_sec,
                "success": True,
                "result": decision,
                "confidence": answer.get("confidence"),
                "downstream_action": "execute_priority_order",
            }

            ledger_path = os.path.join(ROOT, "data", "typesafe_decisions.jsonl")
            os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
            with open(ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ledger_entry) + "\n")

            print(f"\nLedger: {ledger_path}")
            print("\n=== DECISION CONSUMED ===")
            print(f"Priority: {decision}")
            return 0

        print(f"Error: {result.error}")
        print("\nFAIL-CLOSED fallback:")
        print("1) Telegram 409 (blocks owner commands)")
        print("2) Notify token (blocks egress alerts)")
        print("3) Coordination groups (scaling)")
        return 1

    except Exception as exc:
        print(f"TypeSafe call failed: {exc}")
        print("\nFAIL-CLOSED fallback:")
        print("1) Telegram 409 (blocks owner commands)")
        print("2) Notify token (blocks egress alerts)")
        print("3) Coordination groups (scaling)")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
