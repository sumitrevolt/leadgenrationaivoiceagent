"""Boss coordination is visible and covers all 31 STAFF without widening rollout."""

from __future__ import annotations

import asyncio
import json

from app.agents import coordinator
from app.platform import agent_maturity, coordination_hub, office_hq
from app.platform.team import STAFF


def test_canonical_boss_topology_covers_each_staff_exactly_once():
    topology = office_hq.coordination_topology()
    members = [member for team in topology["teams"] for member in team["members"]]

    assert topology["coverage_ok"] is True, topology
    assert topology["boss"] == "manager"
    assert topology["staff_count"] == topology["covered_count"] == len(STAFF) == 31
    assert set(members) == set(STAFF) - {"manager"}
    assert len(members) == len(set(members)) == 30
    assert topology["authority"]["owner_required"] == ["manual_upi_credit_confirmation"]


def test_all_profiles_have_boss_route_but_rollout_truth_stays_staged():
    portfolio = agent_maturity.portfolio()

    assert portfolio["coordination"]["coverage_ok"] is True
    assert all(row["coordination"]["ready"] for row in portfolio["agents"])
    assert all(
        row["coordination"]["owner_required"] == ["manual_upi_credit_confirmation"]
        for row in portfolio["agents"]
    )
    by_id = {row["agent_id"]: row for row in portfolio["agents"]}
    assert by_id["manager"]["coordination"]["role"] == "boss"
    assert by_id["swara"]["coordination"]["execution_note"] == "advisory_or_status_only"
    assert portfolio["rollout_counts"] == {
        "canary_ready": 12,
        "rollout_hold": 17,
        "intentionally_disabled": 2,
    }


def test_hierarchical_run_records_assignments_handoffs_and_boss_verdict(monkeypatch):
    async def fake_assign(_goal):
        return {
            "lead_lab": "lead quality check",
            "admin_finance": "revenue truth check",
        }

    async def fake_agent(agent, task, blackboard, execute):
        return {"mode": "draft", "output": f"{agent}:{task}"}

    async def fake_llm(*_args, **_kwargs):
        return "Boss verdict: dono teams complete", "test"

    monkeypatch.setattr(coordinator, "_assign_teams", fake_assign)
    monkeypatch.setattr(coordinator, "_run_agent", fake_agent)
    monkeypatch.setattr(coordinator, "_llm", fake_llm)
    monkeypatch.setattr(coordinator, "_persist", lambda _row: None)
    monkeypatch.setattr(coordinator, "_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(coordinator, "_heartbeat", lambda *_args, **_kwargs: None)

    out = asyncio.run(coordinator.coordinate_hierarchical("company revenue assurance"))

    assert out["ok"] is True
    assert out["boss"] == "manager"
    assert out["verdict"]["status"] == "completed"
    assert out["verdict"]["owner_gate"] == "manual_upi_credit_confirmation_only"
    assert out["coordination_coverage"]["coverage_ok"] is True
    assert {row["team"] for row in out["assignments"]} == {"lead_lab", "admin_finance"}
    assert any(row["from"] == "manager" and row["status"] == "assigned" for row in out["handoffs"])
    assert any(row["to"] == "diya" and row["status"] == "completed" for row in out["handoffs"])


def test_office_and_hub_project_coordination_evidence(monkeypatch, tmp_path):
    from app.platform import approvals_bridge

    path = tmp_path / "coordination_runs.jsonl"
    record = {
        "run_id": "run-proof-1",
        "goal": "proof mission",
        "pattern": "hierarchical",
        "boss": "manager",
        "assignments": [{"team": "lead_lab", "members": ["diya", "neha"]}],
        "handoffs": [{"from": "manager", "to": "team:lead_lab", "status": "assigned"}],
        "verdict": {"by": "manager", "status": "completed", "summary": "done"},
        "coordination_coverage": {"staff_count": 31, "covered_count": 31, "coverage_ok": True},
        "summary": "done",
        "at": "2026-08-06T00:00:00+00:00",
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    monkeypatch.setattr(approvals_bridge, "_COORD_RUNS", str(path))

    rows = office_hq.build_coordination(limit=1)
    assert rows[0]["run_id"] == "run-proof-1"
    assert rows[0]["assignments"][0]["team"] == "lead_lab"
    assert rows[0]["verdict"]["status"] == "completed"

    monkeypatch.setattr(coordination_hub, "hub_enabled", lambda: True)
    snap = coordination_hub.snapshot(include_git=False)
    assert snap["office_coordination"]["topology"]["covered_count"] == 31
    assert snap["office_coordination"]["rows"][0]["handoffs"]
