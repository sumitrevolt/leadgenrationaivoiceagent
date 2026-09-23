"""Diagnostic: judge_task with the SAME parameters as typesafe_session_policy.judge_task."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

sys.path.insert(0, ".")

from app.platform.typesafe_integration import get_typesafe_client


def main() -> int:
    print("=== judge_task parameters diagnostic ===\n")

    client = get_typesafe_client()
    print(f"client.enabled={client.enabled}, model={client.model}\n")

    # Build a fake record + contract similar to judge_task's expectations.
    class _StubRecord:
        task_id = "diag-judge-1"
        owner_bot = "pilot"
        assigned_agent = "manager"
        priority = "MEDIUM"
        input_payload = {
            "tenant_id": "platform",
            "client_id": "platform",
        }

    class _StubContract:
        lane = "GREEN"

    state = {
        "task_id": _StubRecord.task_id,
        "tenant_scope": "platform",
        "purpose": "substantial_agent_session_dispatch",
        "owner_bot": _StubRecord.owner_bot,
        "assigned_agent": _StubRecord.assigned_agent,
        "agent_lane": "GREEN",
        "priority": "MEDIUM",
        "payload_keys": ["tenant_id", "client_id"],
        "evidence_refs": ["data/orchestrator_ledger.db#task_records:diag-judge-1"],
    }

    questions = {
        "route": {
            "type": "Choice",
            "question": "Should this governed task proceed or require owner review?",
            "criteria": {
                "proceed": "Task is sufficiently scoped and safe",
                "review": "Semantic uncertainty merits owner review",
            },
        },
        "material": {
            "type": "Noul",
            "question": "Will this task materially change a customer, revenue, or operational outcome?",
        },
    }

    print("Calling client.system_one with SAME parameters as judge_task:")
    print(f"  connect_timeout_sec=2.0, read_timeout_sec=5.0, max_attempts=1\n")

    started = time.time()
    response = client.system_one(
        state,
        questions,
        connect_timeout_sec=2.0,
        read_timeout_sec=5.0,
        max_attempts=1,
    )
    elapsed = time.time() - started

    print(f"elapsed_sec={elapsed:.2f}")
    print(f"success={response.success}")
    print(f"error={response.error!r}")
    print(f"model={response.model!r}")
    print(f"latency_sec={response.latency_sec:.2f}")
    print(f"attempts={response.attempts}")
    if response.result:
        print(f"result_keys={list(response.result.keys())}")
        if "answers" in response.result:
            answers = response.result["answers"]
            for k, v in answers.items():
                print(f"  answer[{k}]={v}")
    return 0 if response.success else 1


if __name__ == "__main__":
    sys.exit(main())
