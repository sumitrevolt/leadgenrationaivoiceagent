"""Governed DSH NEXT-todos plan: Kavya MCP turn, frozen voice, no * allowlist."""

from __future__ import annotations

import json

from scripts.dsh_next_todos_plan import run_plan


def test_dsh_next_todos_plan_is_kavya_read_only_and_refuses_upi():
    row = run_plan(write=False)
    assert row["ok"] is True
    assert row["not"] == "harness.io"
    assert row["agent_id"] == "kavya"
    assert row["frozen_agents"] == ["ananya", "swara"]
    assert row["star_allowlist_collapses_to_empty"] is True
    assert row["provider_for"]["kavya"] == "direct"
    assert row["provider_for"]["swara"] == "direct"
    assert row["provider_for"]["ananya"] == "direct"
    assert row["heartbeat_status"] == 200
    assert row["gtm_ops_ready_status"] == 200
    assert row["upi_proposal_status"] == 403
    assert row["upi_proposal_detail"] == "decision_type_never_delegated_to_dsh"
    assert row["dsh_runtime_enabled_this_process"] is False
    dumped = json.dumps(row)
    assert "DATABASE_URL" not in dumped
    assert "*" not in str(row["provider_for"])
