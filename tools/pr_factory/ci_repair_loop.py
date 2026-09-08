"""Open a local CI-repair mission from a failing check (CLI helper)."""

from __future__ import annotations

from typing import Any

from tools.pr_factory import budgets
from tools.pr_factory.orchestrator import FactoryDisabled, submit_task


def repair_task_from_check(
    *,
    pr_number: int,
    check_name: str,
    failing_summary: str,
    allowed_paths: list[str],
    required_tests: list[str],
    idempotency_key: str,
) -> dict[str, Any]:
    """Build a GREEN-scoped repair task YAML dict and submit via factory bridge."""
    slot = budgets.can_claim_slot("ci_repair", {"ci_repair": 0})
    if not slot.get("ok"):
        return {"ok": False, **slot}

    title = f"CI repair: PR #{int(pr_number)} — {check_name}"
    description = (
        f"Failing check `{check_name}` on PR #{int(pr_number)}.\n\n"
        f"Summary:\n{failing_summary}\n\n"
        "Allowed jobs only: failed CI root-cause, missing regression tests, "
        "review-comment resolution, PR body/evidence fix. "
        "DENY: deploy, secrets, telephony, billing, production flags."
    )
    task = {
        "title": title,
        "description": description,
        "executor": "cursor",
        "reviewer": "claude",
        "idempotency_key": idempotency_key,
        "allowed_paths": allowed_paths,
        "acceptance_criteria": [
            "Failing CI check root-caused",
            "Targeted regression test added or proven already present",
            "No protected paths touched",
        ],
        "required_tests": required_tests,
        "rollback_plan": "git revert the repair commit / close repair PR",
        "issue_id": f"pr-{int(pr_number)}",
    }
    try:
        return submit_task(task)
    except FactoryDisabled as exc:
        return {"ok": False, "reason": "factory_disabled", "detail": str(exc)}
