"""Boss + Second Brain governed decision approvals — contract tests."""

from __future__ import annotations

import hashlib
import hmac
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.platform import boss_decision_governance as bdg
from app.platform.automation_flag_manifest import FlagGovernance, describe_flag
from app.platform.team import STAFF


@pytest.fixture()
def gov_root(tmp_path, monkeypatch):
    from app.platform import runtime_data

    runtime_data.use_test_root(tmp_path)
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "1")
    monkeypatch.setenv("BOSS_GOV_AUTHORITY_KEY", "test-boss-authority-key")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(
        "app.platform.approvals_bridge.create_verification_approval",
        lambda **kwargs: {
            "ok": True,
            "id": "oosv_testmirror01",
            "draft": {"meta": kwargs.get("meta") or {}},
        },
    )
    monkeypatch.setattr(
        "app.platform.approvals_bridge.decide",
        lambda *a, **k: {"ok": True},
    )
    return tmp_path


def _auth(decision_id: str, sha: str) -> dict:
    secret = (os.getenv("BOSS_GOV_AUTHORITY_KEY") or "").encode()
    sig = hmac.new(secret, f"{decision_id}|{sha}".encode(), hashlib.sha256).hexdigest()
    return {"kind": "hmac", "sig": sig}


def _advice_payload(sha: str, tenant: str, *, age_s: int = 0, notes=None) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return {
        "ok": True,
        "advice": {
            "source": "test",
            "authoritative": False,
            "bound_content_sha256": sha,
            "bound_tenant_id": tenant,
            "recorded_at": ts.isoformat(),
            "notes": notes
            or [
                {
                    "folder": "Decisions",
                    "slug": "t",
                    "score": 1,
                    "excerpt": "ok",
                    "tenant_id": tenant,
                }
            ],
        },
    }


def _patch_advice(monkeypatch, sha: str, tenant: str, **kw):
    payload = _advice_payload(sha, tenant, **kw)

    def _fetch(**kwargs):
        return payload

    monkeypatch.setattr(bdg, "_fetch_second_brain_advice", _fetch)


def _green_flow(gov_root, monkeypatch, agent_id: str = "isha"):
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
    _patch_advice(monkeypatch, sha, "tenant-a")
    assert bdg.record_second_brain_advice(did)["ok"]
    assert bdg.boss_review_decision(did, authority_evidence=_auth(did, sha))["ok"]
    return did, sha


def test_roster_is_exactly_31(gov_root):
    cov = bdg.routing_coverage()
    assert len(STAFF) == 31
    assert cov["staff_count"] == 31
    assert cov["ok"] is True
    assert cov["covered_count"] == 31
    assert cov["missing"] == []
    assert all(a.get("adapter") for a in cov["agents"])


def test_adapter_registry_coverage_not_hardcoded(gov_root):
    cov = bdg.routing_coverage()
    assert "explicit typed adapters" in cov["claim_note"]
    assert "roster enumeration alone" in cov["claim_note"]
    for row in cov["agents"]:
        assert row["adapter"]["producer_resolves"] is True
        assert row["adapter"]["consumer_resolves"] is True


def test_no_adapter_coverage_failure(gov_root):
    empty = bdg.build_adapter_registry(include_agents=[])
    cov = bdg.routing_coverage(registry=empty)
    assert cov["ok"] is False
    assert cov["covered_count"] == 0
    assert len(cov["missing"]) == 31


def test_routing_coverage_not_live_fire_claim(gov_root):
    cov = bdg.routing_coverage()
    held = [a for a in cov["agents"] if a["rollout"] == "held"]
    assert held, "expected some held agents"
    assert all(a["governed"] for a in cov["agents"])
    assert not all(a["armed"] for a in cov["agents"])


def test_flag_manifest_owner_gated(gov_root):
    meta = describe_flag("BOSS_DECISION_GOVERNANCE")
    assert meta.governance == FlagGovernance.OWNER_APPROVAL_REQUIRED
    assert meta.default_hint == "0"


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


def test_unknown_decision_type_refused(gov_root):
    out = bdg.propose_decision(
        tenant_id="t1",
        agent_id="isha",
        decision_type="totally_unknown_type_xyz",
        payload={},
    )
    assert out["ok"] is False
    assert out["error"] == "unknown_decision_type"
    assert bdg.classify_lane_strict("totally_unknown_type_xyz") == "UNKNOWN"


def test_boss_cannot_self_approve(gov_root, monkeypatch):
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
    _patch_advice(monkeypatch, sha, "tenant-a")
    bdg.record_second_brain_advice(did)
    bdg.boss_review_decision(did, authority_evidence=_auth(did, sha))
    denied = bdg.boss_approve(
        did, actor_id="manager", expected_sha256=sha, authority_evidence=_auth(did, sha)
    )
    assert denied["ok"] is False
    assert denied["error"] == "boss_cannot_self_approve"


def test_spoofed_manager_refused(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)
    denied = bdg.boss_approve(did, actor_id="manager", expected_sha256=sha)
    assert denied["ok"] is False
    assert denied["error"] == "boss_authority_required"


def test_advice_and_approval_required_before_execute(gov_root, monkeypatch):
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

    did, sha = _green_flow(gov_root, monkeypatch)
    ok = bdg.boss_approve(
        did, actor_id="manager", expected_sha256=sha, authority_evidence=_auth(did, sha)
    )
    assert ok["ok"], ok
    done = bdg.consume_or_execute(did, expected_sha256=sha, mode="execute")
    assert done["ok"], done
    assert done["decision"]["state"] == "executed"


def test_concurrent_consume_exactly_one_succeeds(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)
    assert bdg.boss_approve(did, authority_evidence=_auth(did, sha), expected_sha256=sha)["ok"]

    def _one(_):
        return bdg.consume_or_execute(did, expected_sha256=sha)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_one, range(2)))
    oks = [r for r in results if r.get("ok")]
    fails = [r for r in results if not r.get("ok")]
    assert len(oks) == 1, results
    assert len(fails) == 1, results
    assert fails[0]["error"] == "replay_rejected"


def test_hash_stale_cross_tenant_replay(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)
    bdg.boss_approve(did, authority_evidence=_auth(did, sha), expected_sha256=sha)

    stale = bdg.consume_or_execute(did, expected_sha256="0" * 64)
    assert stale["ok"] is False
    assert stale["error"] == "stale_hash"

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
    _patch_advice(monkeypatch, sha2, "other-tenant")
    bad = bdg.record_second_brain_advice(did2)
    assert bad["ok"] is False
    assert bad["error"] == "advice_cross_tenant"

    did3, sha3 = _green_flow(gov_root, monkeypatch)
    assert bdg.boss_approve(did3, authority_evidence=_auth(did3, sha3), expected_sha256=sha3)["ok"]
    assert bdg.consume_or_execute(did3, expected_sha256=sha3)["ok"]
    replay = bdg.consume_or_execute(did3, expected_sha256=sha3)
    assert replay["ok"] is False
    assert replay["error"] == "replay_rejected"


def test_future_advice_timestamp_refused(gov_root, monkeypatch):
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
    _patch_advice(monkeypatch, sha, "t1", age_s=-3600)
    bad = bdg.record_second_brain_advice(did)
    assert bad["ok"] is False
    assert bad["error"] == "advice_future_timestamp"


def test_cross_tenant_recalled_note_refused(gov_root, monkeypatch):
    out = bdg.propose_decision(
        tenant_id="tenant-a",
        agent_id="isha",
        decision_type="internal_plan",
        payload={"s": 1},
        proposed_by="isha",
    )
    did = out["decision"]["decision_id"]
    sha = out["decision"]["content_sha256"]
    bdg.request_advice(did)
    _patch_advice(
        monkeypatch,
        sha,
        "tenant-a",
        notes=[
            {
                "folder": "client:other",
                "namespace": "client:other",
                "slug": "x",
                "tenant_id": "other",
                "excerpt": "nope",
            }
        ],
    )
    bad = bdg.record_second_brain_advice(did)
    assert bad["ok"] is False
    assert bad["error"] == "advice_cross_tenant_note"


def test_green_amber_red_lanes(gov_root, monkeypatch):
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
    _patch_advice(monkeypatch, sha, "t1")
    bdg.record_second_brain_advice(did)
    bdg.boss_review_decision(did, authority_evidence=_auth(did, sha))
    need = bdg.boss_approve(did, authority_evidence=_auth(did, sha), expected_sha256=sha)
    assert need["ok"]
    assert need["decision"]["state"] == "needs_owner"
    still = bdg.boss_approve(did, authority_evidence=_auth(did, sha), expected_sha256=sha)
    assert still["ok"] is False
    assert still["error"] == "owner_decision_id_required"

    # Arbitrary owner id must fail (not found / not approved)
    arb = bdg.boss_approve(
        did,
        authority_evidence=_auth(did, sha),
        expected_sha256=sha,
        owner_decision_id="oos_dec_arbitrary",
    )
    assert arb["ok"] is False
    assert arb["error"] in (
        "owner_decision_not_found",
        "owner_decision_not_approved",
        "owner_binding_mismatch:content_sha256",
    )


def test_arbitrary_and_mismatched_owner_decision_refused(gov_root, monkeypatch):
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
    _patch_advice(monkeypatch, sha, "t1")
    bdg.record_second_brain_advice(did)
    bdg.boss_review_decision(did, authority_evidence=_auth(did, sha))
    bdg.boss_approve(did, authority_evidence=_auth(did, sha), expected_sha256=sha)

    drafts = {}

    def _create(**kwargs):
        oid = "oosv_bound01"
        drafts[oid] = {
            "id": oid,
            "status": "pending",
            "meta": kwargs.get("meta") or {},
        }
        return {"ok": True, "id": oid, "draft": drafts[oid]}

    monkeypatch.setattr("app.platform.approvals_bridge.create_verification_approval", _create)
    # Re-propose so meta is captured via real create path for get_verification_draft
    monkeypatch.setattr(
        "app.platform.approvals_bridge.get_verification_draft",
        lambda oid: (
            {
                "id": oid,
                "meta": {
                    "content_sha256": sha,
                    "tenant_id": "t1",
                    "agent_id": "isha",
                    "decision_type": "customer_content_publish",
                    "decision_id": did,
                    "lane": "AMBER",
                    "mission_id": did,
                    "action": "customer_content_publish",
                },
            }
            if oid == "oosv_good"
            else (
                {
                    "id": oid,
                    "meta": {
                        "content_sha256": "wrong",
                        "tenant_id": "t1",
                        "agent_id": "isha",
                        "decision_type": "customer_content_publish",
                        "decision_id": did,
                        "lane": "AMBER",
                        "mission_id": did,
                        "action": "customer_content_publish",
                    },
                }
                if oid == "oosv_badhash"
                else None
            )
        ),
    )
    monkeypatch.setattr(
        "app.platform.approvals_bridge._status_for",
        lambda source, item_id, smap=None: "approved",
    )

    bad_hash = bdg.boss_approve(
        did,
        authority_evidence=_auth(did, sha),
        expected_sha256=sha,
        owner_decision_id="oosv_badhash",
    )
    assert bad_hash["ok"] is False
    assert "owner_binding_mismatch" in bad_hash["error"]

    good = bdg.boss_approve(
        did,
        authority_evidence=_auth(did, sha),
        expected_sha256=sha,
        owner_decision_id="oosv_good",
    )
    assert good["ok"], good
    assert good["decision"]["state"] == "boss_approved"

    # Duplicate owner consume
    amber2 = bdg.propose_decision(
        tenant_id="t1",
        agent_id="isha",
        decision_type="social_publish",
        payload={"caption": "hi2"},
        proposed_by="isha",
    )
    did2 = amber2["decision"]["decision_id"]
    sha2 = amber2["decision"]["content_sha256"]
    bdg.request_advice(did2)
    _patch_advice(monkeypatch, sha2, "t1")
    bdg.record_second_brain_advice(did2)
    bdg.boss_review_decision(did2, authority_evidence=_auth(did2, sha2))
    bdg.boss_approve(did2, authority_evidence=_auth(did2, sha2), expected_sha256=sha2)
    monkeypatch.setattr(
        "app.platform.approvals_bridge.get_verification_draft",
        lambda oid: {
            "id": oid,
            "meta": {
                "content_sha256": sha2,
                "tenant_id": "t1",
                "agent_id": "isha",
                "decision_type": "social_publish",
                "decision_id": did2,
                "lane": "AMBER",
                "mission_id": did2,
                "action": "social_publish",
            },
        },
    )
    first = bdg.boss_approve(
        did2,
        authority_evidence=_auth(did2, sha2),
        expected_sha256=sha2,
        owner_decision_id="oosv_reuse",
    )
    assert first["ok"], first
    # Second decision trying same owner id
    amber3 = bdg.propose_decision(
        tenant_id="t1",
        agent_id="isha",
        decision_type="whatsapp_send",
        payload={"msg": "x"},
        proposed_by="isha",
    )
    did3 = amber3["decision"]["decision_id"]
    sha3 = amber3["decision"]["content_sha256"]
    bdg.request_advice(did3)
    _patch_advice(monkeypatch, sha3, "t1")
    bdg.record_second_brain_advice(did3)
    bdg.boss_review_decision(did3, authority_evidence=_auth(did3, sha3))
    bdg.boss_approve(did3, authority_evidence=_auth(did3, sha3), expected_sha256=sha3)
    monkeypatch.setattr(
        "app.platform.approvals_bridge.get_verification_draft",
        lambda oid: {
            "id": oid,
            "meta": {
                "content_sha256": sha3,
                "tenant_id": "t1",
                "agent_id": "isha",
                "decision_type": "whatsapp_send",
                "decision_id": did3,
                "lane": "AMBER",
                "mission_id": did3,
                "action": "whatsapp_send",
            },
        },
    )
    dup = bdg.boss_approve(
        did3,
        authority_evidence=_auth(did3, sha3),
        expected_sha256=sha3,
        owner_decision_id="oosv_reuse",
    )
    assert dup["ok"] is False
    assert dup["error"] == "owner_decision_already_consumed"


def test_held_agent_unarmed(gov_root, monkeypatch):
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
    _patch_advice(monkeypatch, sha, "t1")
    bdg.record_second_brain_advice(did)
    bdg.boss_review_decision(did, authority_evidence=_auth(did, sha))
    denied = bdg.boss_approve(did, authority_evidence=_auth(did, sha), expected_sha256=sha)
    assert denied["ok"] is False
    assert denied["error"] == "agent_unarmed"


def test_advice_unavailable_fail_closed(gov_root, monkeypatch):
    monkeypatch.setattr(
        bdg,
        "_fetch_second_brain_advice",
        lambda **k: {"ok": False, "error": "advice_unavailable"},
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
    bad = bdg.record_second_brain_advice(did)
    assert bad["ok"] is False
    assert bad["error"] == "advice_unavailable"
    assert bdg.get_decision(did)["state"] == "refused"


def test_upi_owner_only(gov_root, monkeypatch):
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
    _patch_advice(monkeypatch, sha, "t1")
    bdg.record_second_brain_advice(did)
    bdg.boss_review_decision(did, authority_evidence=_auth(did, sha))
    denied = bdg.boss_approve(
        did,
        authority_evidence=_auth(did, sha),
        expected_sha256=sha,
        owner_decision_id="x",
    )
    assert denied["ok"] is False
    assert denied["error"] == "upi_owner_only"
    exec_denied = bdg.consume_or_execute(did, expected_sha256=sha)
    assert exec_denied["ok"] is False


def test_owner_os_visibility_and_buzz_ro(gov_root, monkeypatch):
    _green_flow(gov_root, monkeypatch)
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


def test_aggregate_verdict_is_not_per_decision_approval(gov_root):
    fake_hier = {
        "verdict": {"by": "manager", "status": "completed", "summary": "sab theek"},
        "coordination_coverage": {"staff_count": 31, "coverage_ok": True},
    }
    check = bdg.assert_aggregate_is_not_approval(fake_hier)
    assert check["is_per_decision_approval"] is False
    assert "advice_recorded" in check["required_for_execute"]


def test_flag_off_zero_governance_records(gov_root, monkeypatch):
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "0")
    before = len(bdg._latest_by_id())
    out = bdg.propose_decision(
        tenant_id="t1",
        agent_id="isha",
        decision_type="internal_plan",
        payload={"a": 1},
    )
    assert out.get("inert") is True
    assert len(bdg._latest_by_id()) == before
    assert bdg.propose_from_hierarchical_run({"run_id": "x", "teams": []}).get("inert")
    assert bdg.request_advice("missing").get("inert") is True
    assert bdg.boss_reject("missing").get("inert") is True
    assert bdg.mark_needs_owner("missing").get("inert") is True


def test_boss_run_requires_bound_hash(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)

    def _runs(_n):
        return [
            {
                "run_id": "run-bound",
                "boss": "manager",
                "pattern": "hierarchical",
                "content_sha256": sha,
            }
        ]

    monkeypatch.setattr("app.agents.coordinator.recent_runs", _runs)
    bad = bdg.boss_approve(
        did,
        expected_sha256=sha,
        authority_evidence={"kind": "boss_run", "run_id": "run-bound"},
    )
    assert bad["ok"] is False
    assert bad["error"] == "boss_run_hash_mismatch"
    ok = bdg.boss_approve(
        did,
        expected_sha256=sha,
        authority_evidence={
            "kind": "boss_run",
            "run_id": "run-bound",
            "content_sha256": sha,
        },
    )
    assert ok["ok"] is True, ok


def test_green_needs_owner_rejects_arbitrary_owner_id(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)
    assert bdg.mark_needs_owner(did, owner_decision_id="oosv_arbitrary")["ok"]
    denied = bdg.boss_approve(
        did,
        expected_sha256=sha,
        owner_decision_id="oosv_arbitrary",
        authority_evidence=_auth(did, sha),
    )
    assert denied["ok"] is False
    assert denied["error"] in {
        "owner_decision_not_found",
        "owner_decision_not_approved",
        "owner_binding_mismatch:content_sha256",
        "owner_binding_mismatch:tenant_id",
        "owner_binding_mismatch:decision_id",
        "owner_binding_mismatch:agent_id",
        "owner_binding_mismatch:decision_type",
        "owner_binding_mismatch:lane",
        "owner_binding_mismatch:mission_id",
        "owner_binding_mismatch:action",
    }


def test_boss_reject_requires_authority(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)
    denied = bdg.boss_reject(did, reason="nope")
    assert denied["ok"] is False
    assert denied["error"] == "boss_authority_required"
    ok = bdg.boss_reject(did, reason="nope", authority_evidence=_auth(did, sha))
    assert ok["ok"] is True, ok


def test_audit_mirror_failure_fail_closed(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)
    # Attach a verification mirror id so consume attempts audit write.
    cur = bdg.get_decision(did)
    assert cur
    patched = dict(cur)
    patched["verification_item_id"] = "oosv_mirror_fail"
    bdg._append_jsonl(bdg._ledger_path(), patched)
    assert bdg.boss_approve(did, authority_evidence=_auth(did, sha), expected_sha256=sha)["ok"]
    monkeypatch.setattr(
        "app.platform.approvals_bridge.decide",
        lambda *a, **k: {"ok": False, "error": "mirror_down"},
    )
    out = bdg.consume_or_execute(did, expected_sha256=sha)
    assert out["ok"] is False
    assert out["error"] == "audit_mirror_failed"
    assert out.get("fail_closed") is True


def test_flag_off_blocks_execute(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)
    assert bdg.boss_approve(did, authority_evidence=_auth(did, sha), expected_sha256=sha)["ok"]
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "0")
    denied = bdg.consume_or_execute(did, expected_sha256=sha)
    assert denied["ok"] is False
    assert denied["error"] == "flag_off"


def test_stale_advice_fail_closed(gov_root, monkeypatch):
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
    _patch_advice(monkeypatch, sha, "t1", age_s=7 * 3600)
    bad = bdg.record_second_brain_advice(did)
    assert bad["ok"] is False
    assert bad["error"] == "advice_stale"


def test_owner_os_governed_consumer_flag_off(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)
    assert bdg.mark_needs_owner(did)["ok"]
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "0")
    from app.platform import owner_os

    denied = owner_os.decide_approval("boss_decision_governance", did, "approve", actor="admin")
    assert denied["ok"] is False
    assert denied["error"] == "flag_off"
    assert denied.get("fail_closed") is True


def test_owner_os_governed_consumer_approve_consume(gov_root, monkeypatch):
    """Real Owner OS adapter invokes create→stamp→boss_approve→consume once."""
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
    _patch_advice(monkeypatch, sha, "t1")
    bdg.record_second_brain_advice(did)
    bdg.boss_review_decision(did, authority_evidence=_auth(did, sha))
    # First approve without owner id parks at needs_owner
    parked = bdg.boss_approve(did, authority_evidence=_auth(did, sha), expected_sha256=sha)
    assert parked["decision"]["state"] == "needs_owner"

    store: dict = {}

    def _create(**kwargs):
        oid = "oosv_ownerpath01"
        store[oid] = {"id": oid, "status": "pending", "meta": dict(kwargs.get("meta") or {})}
        return {"ok": True, "id": oid, "draft": store[oid]}

    def _decide(source, item_id, decision, by="admin", reason=""):
        row = store.get(item_id)
        if row is not None:
            row["status"] = "approved" if decision == "approve" else "rejected"
            return {"ok": True, "status": row["status"]}
        # Propose-time mirror ids (fixture / unrelated) — stamp ok, no side effects.
        return {"ok": True, "status": "approved", "noop": True}

    monkeypatch.setattr("app.platform.approvals_bridge.create_verification_approval", _create)
    monkeypatch.setattr("app.platform.approvals_bridge.decide", _decide)
    monkeypatch.setattr(
        "app.platform.approvals_bridge.get_verification_draft",
        lambda oid: store.get(oid),
    )
    monkeypatch.setattr(
        "app.platform.approvals_bridge._status_for",
        lambda source, item_id, smap=None: (store.get(item_id) or {}).get("status") or "pending",
    )

    from app.platform import owner_os

    out = owner_os.decide_approval(
        "boss_decision_governance", did, "approve", actor="admin", reason="ok"
    )
    assert out["ok"] is True, out
    assert out.get("consumer") == "owner_os_decide_governed"
    assert out.get("side_effects") is False
    cur = bdg.get_decision(did)
    assert cur and cur["state"] == "consumed"
    # replay refused
    again = owner_os.decide_approval("boss_decision_governance", did, "approve")
    assert again["ok"] is False


def test_owner_os_governed_reject(gov_root, monkeypatch):
    did, sha = _green_flow(gov_root, monkeypatch)
    assert bdg.mark_needs_owner(did)["ok"]
    from app.platform import owner_os

    out = owner_os.decide_approval(
        "boss_decision_governance", did, "reject", actor="admin", reason="nope"
    )
    assert out["ok"] is True, out
    assert bdg.get_decision(did)["state"] == "refused"


def test_hierarchical_adapter_wiring_inert_when_flag_off(gov_root, monkeypatch):
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "0")
    run = {
        "run_id": "abc",
        "tenant_id": "tenant-a",
        "teams": [
            {
                "team": "ops",
                "results": [
                    {"agent": "isha", "mode": "ok", "output": "done"},
                ],
            }
        ],
    }
    out = bdg.propose_from_hierarchical_run(run)
    assert out["inert"] is True
    assert out["written"] == 0


def test_hierarchical_adapter_wiring_when_flag_on(gov_root, monkeypatch):
    run = {
        "run_id": "abc",
        "tenant_id": "tenant-a",
        "teams": [
            {
                "team": "ops",
                "results": [
                    {"agent": "isha", "mode": "ok", "output": "done"},
                ],
            }
        ],
    }
    out = bdg.propose_from_hierarchical_run(run)
    assert out["ok"] is True
    assert out["written"] == 1
    assert out["decision_ids"]


class _FakeRedis:
    def __init__(self, *, nx_ok: bool = True, raises: bool = False):
        self.nx_ok = nx_ok
        self.raises = raises
        self.calls: list[tuple] = []

    def set(self, key, value, nx=False, ex=None):
        self.calls.append((key, value, nx, ex))
        if self.raises:
            raise ConnectionError("boom")
        return self.nx_ok


@pytest.mark.parametrize(
    "nx_ok,raises,expected",
    [
        (True, False, True),
        (False, False, False),
        (True, True, False),  # redis error → fail-closed
    ],
)
def test_atomic_claim_redis_path(gov_root, monkeypatch, nx_ok, raises, expected):
    fake = _FakeRedis(nx_ok=nx_ok, raises=raises)
    monkeypatch.setenv("REDIS_URL", "redis://test-local/0")
    monkeypatch.setattr(bdg, "_redis_client", lambda: fake)
    key = f"consume:test-redis-{nx_ok}-{raises}"
    assert bdg._atomic_claim(key) is expected
    assert fake.calls, "SET NX must be attempted when REDIS_URL path is active"
    assert fake.calls[0][0].startswith("bdg:claim:")
    assert fake.calls[0][2] is True  # nx=True


def test_record_advice_propagates_request_advice_failure(gov_root, monkeypatch):
    prop = bdg.propose_decision(
        tenant_id="tenant-a",
        agent_id="isha",
        decision_type="internal_plan",
        title="t",
        payload={"x": 1},
        proposed_by="isha",
    )
    assert prop["ok"], prop
    did = prop["decision"]["decision_id"]
    monkeypatch.setattr(
        bdg,
        "request_advice",
        lambda *_a, **_k: {"ok": False, "error": "forced_request_fail"},
    )
    out = bdg.record_second_brain_advice(did)
    assert out["ok"] is False
    assert out["error"] == "forced_request_fail"
    assert out.get("fail_closed") is True
