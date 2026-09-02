"""AMBER negative dogfood — admin without Owner OS approval must not start a child."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ["EXTERNAL_AGENT_ORCHESTRATOR"] = "1"
    os.environ["EXTERNAL_AGENT_RUNNER"] = "1"
    os.environ["EXTERNAL_MISSION_CAS"] = "filelock"
    os.environ["EXTERNAL_AGENT_COORDINATION_BACKEND"] = "local-file"
    os.environ.setdefault(
        "EXTERNAL_MISSION_DIR",
        str(Path(os.environ.get("TEMP", ROOT / "data")) / "ext_missions_dogfood"),
    )
    os.environ["EXTERNAL_AGENT_WORKTREE_ROOT"] = str(
        Path(r"C:\Users\Ratanshila\Documents\_leadgen_worktrees")
    )

    from app.dev_control import locks as path_locks
    from app.dev_control.external_agents import cas, orchestrator, store
    from app.dev_control.external_agents.runner import run_mission_once
    from app.dev_control.external_agents.runner.authorize import authorize_mission
    from app.dev_control.external_agents.schema import RiskClass

    cas.reset_backend()
    terminal = {
        "COMPLETE",
        "CANCELLED",
        "FAILED_TERMINAL",
        "ROLLED_BACK",
        "REFUSED",
    }
    for stale in store.list_missions(limit=200):
        if stale.status.value in terminal:
            continue
        try:
            orchestrator.cancel(stale.mission_id, reason="amber_neg_preflight_cleanup")
        except Exception:
            pass
        try:
            path_locks.get_lock().release(stale.mission_id, stale.allowed_paths)
        except Exception:
            pass

    created = orchestrator.create_mission(
        title="prepare alembic migration for invoice numbering",
        description="AMBER negative dogfood — must park without child process",
        executor="cursor",
        reviewer="claude",
        idempotency_key="amber-neg-" + uuid.uuid4().hex,
        declared_risk="AMBER",
        allowed_paths=["tests/fixtures/external_agent_runner/"],
        branch="feat/ext-amber-neg-" + uuid.uuid4().hex[:6],
        worktree=str(
            Path(r"C:\Users\Ratanshila\Documents\_leadgen_worktrees")
            / ("lg-amber-neg-" + uuid.uuid4().hex[:6])
        ),
        base_sha="e64b8a9d10bcf6084488b34f886f77a5752f13f8",  # pragma: allowlist secret
        acceptance_criteria=["must not run"],
        rollback_plan="cancel",
    )
    if not created.get("ok"):
        print(json.dumps({"ok": False, "create": created}, indent=2))
        return 1
    mid = created["mission"]["mission_id"]
    from app.dev_control.external_agents import store

    mission = store.get(mid)
    assert mission is not None
    assert mission.risk_class is RiskClass.AMBER
    auth = authorize_mission(mission)
    out = run_mission_once(mid, repo_root=str(ROOT), timeout_s=60)
    print(
        json.dumps(
            {
                "ok": True,
                "mission_id": mid,
                "risk_class": mission.risk_class.value,
                "authorize": auth,
                "run_mission_once": {
                    "ok": out.get("ok"),
                    "reason": out.get("reason"),
                },
                "child_started": bool((out.get("evidence") or {}).get("executor_process")),
                "expected": "owner_decision_required and no child",
            },
            indent=2,
            default=str,
        )
    )
    if out.get("ok"):
        return 2
    if out.get("reason") != "owner_decision_required":
        return 3
    if (out.get("evidence") or {}).get("executor_process"):
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
