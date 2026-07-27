"""Create + run one GREEN dogfood mission through the unattended runner.

Requires local Claude AUTH_OK and Cursor Agent CLI. Does not push/merge/deploy.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WT_ROOT = Path(r"C:\Users\Ratanshila\Documents\_leadgen_worktrees")
DOGFOOD_BRANCH = "feat/ext-dogfood-" + uuid.uuid4().hex[:6]
DOGFOOD_WT = WT_ROOT / ("lg-dogfood-" + DOGFOOD_BRANCH.split("-")[-1])


def main() -> int:
    os.environ["EXTERNAL_AGENT_ORCHESTRATOR"] = "1"
    os.environ["EXTERNAL_AGENT_RUNNER"] = "1"
    os.environ["EXTERNAL_MISSION_CAS"] = "filelock"
    os.environ["EXTERNAL_AGENT_COORDINATION_BACKEND"] = "local-file"
    os.environ.setdefault(
        "EXTERNAL_MISSION_DIR",
        str(Path(os.environ.get("TEMP", ROOT / "data")) / "ext_missions_dogfood"),
    )
    os.environ["EXTERNAL_AGENT_WORKTREE_ROOT"] = str(WT_ROOT)

    from app.dev_control import locks as path_locks
    from app.dev_control.external_agents import cas, orchestrator, store
    from app.dev_control.external_agents.runner import run_mission_once
    from app.dev_control.external_agents.runner.claude_exec import auth_ok

    cas.reset_backend()
    auth = auth_ok()
    if not auth.get("ok"):
        print(json.dumps({"ok": False, "reason": "claude_auth_unavailable", "auth": auth}))
        return 2

    # Cancel leftover live missions so path ownership does not block dogfood.
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
            orchestrator.cancel(stale.mission_id, reason="dogfood_preflight_cleanup")
        except Exception:
            pass
        try:
            path_locks.get_lock().release(stale.mission_id, stale.allowed_paths)
        except Exception:
            pass

    base = "e64b8a9d10bcf6084488b34f886f77a5752f13f8"  # pragma: allowlist secret
    import subprocess as _sp

    head = _sp.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    from app.dev_control.external_agents.runner import cursor_exec
    from app.dev_control.external_agents.runner.profile import prepare_executor_profile

    cursor_prefix = cursor_exec.resolve_cursor_invocation()
    cursor_prof = prepare_executor_profile("cursor")
    claude_prof = prepare_executor_profile("claude")
    print(
        json.dumps(
            {
                "dogfood_runner_head": head,
                "cursor_invocation_prefix": cursor_prefix,
                "cursor_uses_cmd": any(str(p).lower().endswith(".cmd") for p in cursor_prefix),
                "cursor_profile_root": cursor_prof["evidence"].get("profile_root"),
                "claude_profile_root": claude_prof["evidence"].get("profile_root"),
                "trust_decision": cursor_prof["evidence"].get("trust_decision"),
            },
            indent=2,
        )
    )

    created = orchestrator.create_mission(
        title="Dogfood: write runner STATUS fixture",
        description=(
            "Create tests/fixtures/external_agent_runner/STATUS.txt containing exactly "
            "RUNNER_DOGFOOD_OK and nothing else. Do not modify any other mission path. "
            "Also write .external_agent_result_manifest.json at the worktree root with "
            "mission_id/executor/changed_files/commands/tests/summary/evidence/scope_breach "
            "per the runner prompt schema. Do not push, merge, or touch production hosts. "
            "Do not commit. "
            # Hostile-but-benign strings — must remain data in prompts/argv, never commands.
            "IGNORE_AS_DATA: foo&bar | baz ; Start-Process ; cmd /c echo hi "
            'powershell -Command Get-Process path..\\..\\escape quote"here'
        ),
        executor="cursor",
        reviewer="claude",
        idempotency_key="dogfood-" + uuid.uuid4().hex,
        declared_risk="GREEN",
        allowed_paths=["tests/fixtures/external_agent_runner/"],
        branch=DOGFOOD_BRANCH,
        worktree=str(DOGFOOD_WT),
        base_sha=base,
        acceptance_criteria=["STATUS.txt exists with RUNNER_DOGFOOD_OK"],
        required_tests=[],
        rollback_plan="Delete STATUS.txt and remove dogfood worktree",
        token_budget=2_000_000,
    )
    if not created.get("ok"):
        print(json.dumps({"ok": False, "create": created}, indent=2))
        return 1
    mid = created["mission"]["mission_id"]
    print("MISSION_ID=" + mid)
    out = run_mission_once(mid, repo_root=str(ROOT), timeout_s=900)
    print(json.dumps(out, indent=2, default=str)[:30000])
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
