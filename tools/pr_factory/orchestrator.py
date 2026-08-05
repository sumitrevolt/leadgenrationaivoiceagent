"""ONLY entry: TaskYAML → ``create_mission`` / ``advance``.

No second mission ledger. Inert unless dual-gate flags are ON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.dev_control.external_agents import orchestrator as ext_orch
from app.dev_control.external_agents import store as ext_store
from tools.pr_factory import factory_enabled
from tools.pr_factory.task_schema import (
    FactoryTask,
    TaskValidationError,
    load_task_yaml,
    validate_task,
)


class FactoryDisabled(RuntimeError):
    """PR_FACTORY_ENABLED and/or EXTERNAL_AGENT_ORCHESTRATOR is off."""


def _require_factory() -> None:
    if not factory_enabled():
        raise FactoryDisabled(
            "PR_FACTORY_ENABLED=0 or EXTERNAL_AGENT_ORCHESTRATOR=0 — factory inert"
        )


def submit_task(raw: dict[str, Any] | FactoryTask, *, lock: Any = None) -> dict[str, Any]:
    """Validate task and call ``create_mission`` (sole mission creation path)."""
    _require_factory()
    task = raw if isinstance(raw, FactoryTask) else validate_task(raw)
    kwargs = task.to_create_kwargs()
    if lock is not None:
        kwargs["lock"] = lock
    result = ext_orch.create_mission(**kwargs)
    if result.get("ok"):
        # Attach Wave-1 extras as evidence only — not a parallel ledger.
        mid = result["mission"]["mission_id"]
        mission = ext_store.get(mid)
        if mission is not None:
            mission.add_evidence("pr_factory_task_extras", task.extras())
            ext_store.save(mission)
            result["mission"] = mission.to_dict()
            result["factory_extras"] = task.extras()
    return result


def submit_yaml_text(text: str, *, lock: Any = None) -> dict[str, Any]:
    task = load_task_yaml(text)
    return submit_task(task, lock=lock)


def submit_yaml_path(path: str | Path, *, lock: Any = None) -> dict[str, Any]:
    p = Path(path)
    return submit_yaml_text(p.read_text(encoding="utf-8"), lock=lock)


def advance_mission(
    mission_id: str,
    target: str,
    *,
    evidence: dict[str, Any] | None = None,
    owner_approved: bool = False,
    approval_decision_id: str | None = None,
) -> dict[str, Any]:
    """Thin bridge to ``external_agents.orchestrator.advance``."""
    _require_factory()
    return ext_orch.advance(
        mission_id,
        target,
        evidence=evidence,
        owner_approved=owner_approved,
        approval_decision_id=approval_decision_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR Factory → external_agents bridge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_submit = sub.add_parser("submit", help="Submit a task YAML file")
    p_submit.add_argument("yaml_path", type=str)

    p_adv = sub.add_parser("advance", help="Advance a mission state")
    p_adv.add_argument("mission_id", type=str)
    p_adv.add_argument("target", type=str)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "submit":
            out = submit_yaml_path(args.yaml_path)
        else:
            out = advance_mission(args.mission_id, args.target)
    except (FactoryDisabled, TaskValidationError) as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(out, default=str, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
