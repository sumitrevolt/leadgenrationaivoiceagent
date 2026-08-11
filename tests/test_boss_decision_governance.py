"""Boss + Second Brain governed decision approvals — contract tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.platform import boss_decision_governance as bdg
from app.platform.team import STAFF


@pytest.fixture()
def gov_root(tmp_path, monkeypatch):
    from app.platform import runtime_data

    runtime_data.use_test_root(tmp_path)
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "1")
    # Avoid writing into real approvals verification file during unit tests
    monkeypatch.setattr(
        "app.platform.approvals_bridge.create_verification_approval",
        lambda **kwargs: {"ok": True, "id": "oosv_testmirror01", "draft": {}},
    )
    monkeypatch.setattr(
        "app.platform.approvals_bridge.decide",
        lambda *a, **k: {"ok": True},
    )
    return tmp_path


def _advice(sha: str, tenant: str, *, age_s: int = 0) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return {
        "source": "test",
        "authoritative": False,
        "bound_content_sha256": sha,
        "bound_tenant_id": tenant,
        "recorded_at": ts.isoformat(),
        "notes": [{"folder": "Decisions", "slug": "t", "score": 1, "excerpt": "ok"}],
    }


def _green_flow(gov_root, agent_id: str = "isha"):
    out = bdg.propose_decision(
        tenant_id="tenant-a",
        agent_id=agent_id,
        decision_type="internal_plan",
        title="plan X",
        payload={"step": 1},
        proposed_by=agent_id,
    )
    assert out["ok"], out
    d = out["decision"]
    did = d["decision_id"]
    sha = d["content_sha256"]
    assert bdg.request_advice(did)["ok"]
    assert bdg.record_second_brain_advice(did, injected_advice=_advice(sha, "tenant-a"))["ok"]
    assert bdg.boss_review_decision(did, reviewer_id="manager")["ok"]
    return did, sha


def test_roster_is_exactly_31(gov_root):
    cov = bdg.routing_coverage()
    assert len(STAFF) == 31
    assert cov["staff_count"] == 31
    assert cov["ok"] is True
    assert cov["covered_count"] == 31
    assert cov["missing"] == []


def test_routing_coverage_not_live_fire_claim(gov_root):
    cov = bdg.routing_coverage()
    assert "not live customer decisions" in cov["claim_note"]
    held = [a for a in cov["agents"] if a["rollout"] == "held"]
    assert held, "expected some held agents"
    assert all(a["governed"] for a in cov["agents"])
    assert not all(a["armed"] for a in cov["agents"])


def test_non_decision_objects_refused(gov_root):
    for kind in ("heartbeat", "telemetry", "draft", "aggregate_verdict", "pulse"):
        out = bdg.propose_decision(
            tenant_id="t1",
            agent_id="isha",
            decision_type="internal_plan",
            kind=kind,
        )
        assert out["ok"] is False
        assert out["error"] == "not_a_decision_object"


def test_boss_cannot_self_approve(gov_root):
    out = bdg.propose_decision(
        tenant_id="tenant-a",
        agent_id="isha",
        decision_type="internal_plan",
        payload={"x": 1},
        proposed_by="manager",
    )
    did = out["decision"]["decision_id"]
    sha = out["decision"]["content_sha256"]
    bdg.request_advice(did)
    bdg.record_second_brain_advice(did, injected_advice=_advice(sha, "tenant-a"))
    bdg.boss_review_decision(did)
    denied = bdg.boss_approve(did, actor_id="manager", expected_sha256=sha)
    assert denied["ok"] is False
    assert denied["error"] == "boss_cannot_self_approve"


def test_advice_and_approval_required_before_execute(gov_root):
    out = bdg.propose_decision(
        tenant_id="tenant-a",
        agent_id="isha",
        decision_type="internal_plan",
        payload={"x": 1},
        proposed_by="isha",
    )
    did = out["decision"]["decision_id"]
    sha = out["decision"]["content_sha256"]
    early = bdg.consume_or_execute(did, expected_sha256=sha)
    assert early["ok"] is False
    assert early["error"] == "approval_required_before_execute"

    did, sha = _green_flow(gov_root)
    ok = bdg.boss_approve(did, actor_id="manager", expected_sha256=sha)
    assert ok["ok"], ok
    done = bdg.consume_or_execute(did, expected_sha256=sha, mode="execute")
    assert done["ok"], done
    assert done["decision"]["state"] == "executed"


def test_hash_stale_cross_tenant_replay(gov_root):
    did, sha = _green_flow(gov_root)
    bdg.boss_approve(did, actor_id="manager", expected_sha256=sha)

    stale = bdg.consume_or_execute(did, expected_sha256="0" * 64)
    assert stale["ok"] is False
    assert stale["error"] == "stale_hash"

    # Cross-tenant advice binding
    out = bdg.propose_decision(
        tenant_id="tenant-a",
        agent_id="isha",
        decision_type="ops_report",
        payload={"y": 2},
        proposed_by="isha",
    )
    did2 = out["decision"]["decision_id"]
    sha2 = out["decision"]["content_sha256"]
    bdg.request_advice(did2)
    bad = bdg.record_second_brain_advice(did2, injected_advice=_advice(sha2, "other-tenant"))
    assert bad["ok"] is False
    assert bad["error"] == "advice_cross_tenant"

    # Replay after success
    did3, sha3 = _green_flow(gov_root)
    assert bdg.boss_approve(did3, actor_id="manager", expected_sha256=sha3)["ok"]
    assert bdg.consume_or_execute(did3, expected_sha256=sha3)["ok"]
    replay = bdg.consume_or_execute(did3, expected_sha256=sha3)
    assert replay["ok"] is False
    assert replay["error"] == "replay_rejected"


def test_green_amber_red_lanes(gov_root):
    assert bdg.classify_lane_strict("internal_plan") == "GREEN"
    assert bdg.classify_lane_strict("customer_content_publish") == "AMBER"
    assert bdg.classify_lane_strict("cold_outbound_call") == "RED"

    red = bdg.propose_decision(
        tenant_id="t1",
        agent_id="isha",
        decision_type="cold_outbound_call",
        payload={},
    )
    assert red["ok"]
    assert red["decision"]["state"] == "refused"
    assert red["decision"]["lane"] == "RED"

    amber = bdg.propose_decision(
        tenant_id="t1",
        agent_id="isha",
        decision_type="customer_content_publish",
        payload={"caption": "hi"},
        proposed_by="isha",
    )
    did = amber["decision"]["decision_id"]
    sha = amber["decision"]["content_sha256"]
    bdg.request_advice(did)
    bdg.record_second_brain_advice(did, injected_advice=_advice(sha, "t1"))
    bdg.boss_review_decision(did)
    need = bdg.boss_approve(did, actor_id="manager", expected_sha256=sha)
    assert need["ok"]
    assert need["decision"]["state"] == "needs_owner"
    still = bdg.boss_approve(did, actor_id="manager", expected_sha256=sha)
    assert still["ok"] is False
    assert still["error"] == "owner_decision_id_required"
    ok = bdg.boss_approve(
        did, actor_id="manager", expected_sha256=sha, owner_decision_id="oos_dec_1"
    )
    assert ok["ok"]
    assert ok["decision"]["state"] == "boss_approved"


def test_held_agent_unarmed(gov_root):
    # rohan is AMBER_HOLD — governed routing yes, execute no
    out = bdg.propose_decision(
        tenant_id="t1",
        agent_id="rohan",
        decision_type="internal_plan",
        payload={"z": 1},
        proposed_by="rohan",
    )
    assert out["decision"]["rollout"] == "held"
    did = out["decision"]["decision_id"]
    sha = out["decision"]["content_sha256"]
    bdg.request_advice(did)
    bdg.record_second_brain_advice(did, injected_advice=_advice(sha, "t1"))
    bdg.boss_review_decision(did)
    denied = bdg.boss_approve(did, actor_id="manager", expected_sha256=sha)
    assert denied["ok"] is False
    assert denied["error"] == "agent_unarmed"


def test_advice_unavailable_fail_closed(gov_root, monkeypatch):
    monkeypatch.setattr(
        "app.platform.obsidian_sync.recall",
        lambda *a, **k: [],
    )
    out = bdg.propose_decision(
        tenant_id="t1",
        agent_id="isha",
        decision_type="internal_plan",
        payload={"a": 1},
        proposed_by="isha",
    )
    did = out["decision"]["decision_id"]
    bdg.request_advice(did)
    bad = bdg.record_second_brain_advice(did)  # no inject → real recall empty
    assert bad["ok"] is False
    assert bad["error"] == "advice_unavailable"
    assert bdg.get_decision(did)["state"] == "refused"


def test_upi_owner_only(gov_root):
    out = bdg.propose_decision(
        tenant_id="t1",
        agent_id="isha",
        decision_type="upi_payment",
        payload={"amount": 1999},
        proposed_by="isha",
    )
    did = out["decision"]["decision_id"]
    sha = out["decision"]["content_sha256"]
    assert out["decision"]["lane"] == "AMBER"
    bdg.request_advice(did)
    bdg.record_second_brain_advice(did, injected_advice=_advice(sha, "t1"))
    bdg.boss_review_decision(did)
    denied = bdg.boss_approve(did, actor_id="manager", expected_sha256=sha, owner_decision_id="x")
    assert denied["ok"] is False
    assert denied["error"] == "upi_owner_only"
    exec_denied = bdg.consume_or_execute(did, expected_sha256=sha)
    assert exec_denied["ok"] is False


def test_owner_os_visibility_and_buzz_ro(gov_root):
    _green_flow(gov_root)
    vis = bdg.owner_os_visibility()
    assert vis["ok"]
    assert vis["pending"] >= 1
    assert vis["items"][0]["decision_id"]

    from app.platform import owner_os

    inbox = owner_os.approvals_inbox()
    gov_items = [i for i in inbox["items"] if i.get("source") == "boss_decision_governance"]
    assert gov_items, inbox

    buzz = bdg.buzz_ro_projection()
    assert buzz["mode"] == "read_only"
    assert buzz["mutation"] is False
    assert "payload" not in (buzz["items"][0] if buzz["items"] else {})


def test_aggregate_verdict_is_not_per_decision_approval(gov_root):
    fake_hier = {
        "verdict": {"by": "manager", "status": "completed", "summary": "sab theek"},
        "coordination_coverage": {"staff_count": 31, "coverage_ok": True},
    }
    check = bdg.assert_aggregate_is_not_approval(fake_hier)
    assert check["is_per_decision_approval"] is False
    assert "advice_recorded" in check["required_for_execute"]


def test_flag_off_blocks_execute(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root)
    assert bdg.boss_approve(did, actor_id="manager", expected_sha256=sha)["ok"]
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "0")
    denied = bdg.consume_or_execute(did, expected_sha256=sha)
    assert denied["ok"] is False
    assert denied["error"] == "flag_off"


def test_stale_advice_fail_closed(gov_root):
    out = bdg.propose_decision(
        tenant_id="t1",
        agent_id="isha",
        decision_type="internal_plan",
        payload={"s": 1},
        proposed_by="isha",
    )
    did = out["decision"]["decision_id"]
    sha = out["decision"]["content_sha256"]
    bdg.request_advice(did)
    bad = bdg.record_second_brain_advice(did, injected_advice=_advice(sha, "t1", age_s=7 * 3600))
    assert bad["ok"] is False
    assert bad["error"] == "advice_stale"
