"""One-off TypeSafe PR-creation gate probe for AGNES-ASSIGN-CL-PUSH-GOVERNANCE-BRANCH."""

import hashlib
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.platform.typesafe_integration import typesafe_noul  # noqa: E402


def main() -> int:
    branch = "chore/governance-sha-refresh-20260923"
    head = "8c5fcd30"
    main_head = "06f33607"
    reviewers = ["Hermes", "WorkBuddy"]
    task_id = "AGNES-ASSIGN-CL-PUSH-GOVERNANCE-BRANCH"

    state = {
        "task_id": task_id,
        "branch": branch,
        "head": head,
        "repo_main_head": main_head,
        "pending_prs": [f"{branch} -> main"],
        "reviewers": reviewers,
        "owner_governance": (
            "SHA/HEAD refresh + ADR-201/201b + wave-2 coordination receipts; "
            "docs-only, no runtime code; no VPS deploy in this lane"
        ),
        "gate_question": (
            "Is it safe to push this branch and open a docs-only PR to main for "
            "Hermes + WorkBuddy review, without touching prod or compliance?"
        ),
    }
    resp = typesafe_noul(
        "Is this branch/PR state safe to proceed to push + open PR now, or should it be held?",
        state,
    )
    can_proceed = bool(resp.success) and resp.value is not None and float(resp.value) >= 0.65
    result = "PROCEED" if can_proceed else "HOLD"
    entry = {
        "decision_id": f"ts-pr-{uuid.uuid4().hex[:12]}",
        "task_id": task_id,
        "tenant_scope": "leadgenplatform",
        "purpose": "pr-creation gate",
        "state_hash": hashlib.sha256(
            json.dumps(state, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
        "evidence_refs": [
            f"git-log main={main_head}",
            f"branch-head {branch}@{head}",
            "ADR-201/ADR-201b in memory/decisions.md",
            "docs/coordination/typesafe_key_liveness_20260923.md",
            "docs/coordination/admin-tasks-db-audit-20260923.md",
        ],
        "requested_model": "jev-latest",
        "primitive": "noul",
        "result": {
            "success": resp.success,
            "value": resp.value,
            "confidence": getattr(resp, "confidence", None),
            "model": getattr(resp, "model", None),
            "latency_sec": getattr(resp, "latency_sec", None),
            "answers": getattr(resp, "answers", None),
        },
        "downstream_branch": result,
        "side_effect_id": f"push/{branch}" if can_proceed else "none",
        "observed_outcome": None,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S+05:30", time.localtime()),
        "kind": "pr_creation_gate",
    }
    print(json.dumps(entry, indent=2))
    log_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "logs", "typesafe_session_decisions.jsonl")
    )
    if not os.path.exists(os.path.dirname(log_path)):
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 0 if can_proceed else 2


if __name__ == "__main__":
    raise SystemExit(main())
