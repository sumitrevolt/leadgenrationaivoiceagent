"""Runner status for Admin/Dev Control UI."""

from __future__ import annotations

import os
from typing import Any

from app.dev_control.external_agents import store
from app.dev_control.external_agents.runner.flags import (
    RUNNER_FLAG,
    runner_enabled,
    runner_flag_alone,
)
from app.dev_control.external_agents.runner.worktrees import allowed_worktree_root


def runner_status() -> dict[str, Any]:
    rows = store.list_missions(limit=50)
    running = [
        m for m in rows if m.status.value in {"RUNNING", "CLAIMED", "TESTING", "REVIEW_REQUIRED"}
    ]
    return {
        "runner_flag": RUNNER_FLAG,
        "runner_env": runner_flag_alone(),
        "runner_enabled": runner_enabled(),
        "environment_badge": "local-canary" if runner_enabled() else "dormant",
        "worktree_root": str(allowed_worktree_root()),
        "cursor_bin": (os.getenv("EXTERNAL_AGENT_CURSOR_BIN") or "auto"),
        "active_missions": [
            {
                "mission_id": m.mission_id,
                "status": m.status.value,
                "executor": m.executor,
                "lease_owner": m.lease_owner,
                "last_heartbeat": m.last_heartbeat,
                "blocker": m.blocker,
                "evidence_count": len(m.evidence_refs),
            }
            for m in running
        ],
        "note": (
            "Runner invokes allowlisted Cursor Agent / Claude Code CLIs only. "
            "Never enables deploy, calling, billing or outreach."
        ),
    }
