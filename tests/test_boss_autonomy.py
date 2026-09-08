"""Boss Autonomy service — contract tests.

Proves the canonical flag-gated autonomy loop over boss_decision_governance:
  * autonomy OFF leaves governance untouched
  * service uses ONLY public bdg API (static source check)
  * canonical Boss identity is manager (never hermes)
  * unknown / RED / owner-only types fail closed
  * delegated internal (GREEN) type executes exactly once
  * duplicate sweep never re-proposes
  * stale hash / wrong tenant / missing advice / low-confidence refuse or defer
  * held agents (incl. manager until mutating canary) are unarmed
"""

from __future__ import annotations

import inspect
import os
from datetime import datetime, timezone

import pytest

from app.platform import boss_autonomy as ba
from app.platform import boss_decision_governance as bdg
from app.platform.automation_flag_manifest import FlagGovernance, describe_flag


@pytest.fixture()
def gov_root(tmp_path, monkeypatch):
    from app.platform import runtime_data

    runtime_data.use_test_root(tmp_path)
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "1")
    monkeypatch.setenv("BOSS_FULL_AUTONOMY", "1")
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


def _patch_advice(
    monkeypatch, *, score: float = 1.0, ok: bool = True, error: str = "", tenant: str = ""
):
    """Patch the SANCTIONED test hook bdg._fetch_second_brain_advice (tests only)."""

    def _fetch(*, query="", tenant_id="", content_sha256="", use_council=False):
        if not ok:
            return {"ok": False, "error": error or "advice_unavailable"}
        bound_tenant = tenant or tenant_id
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "ok": True,
            "advice": {
                "source": "test",
                "authoritative": False,
                "bound_content_sha256": content_sha256,
                "bound_tenant_id": bound_tenant,
                "recorded_at": ts,
                "notes": [
                    {
                        "folder": "Decisions",
                        "slug": "t",
                        "score": score,
                        "excerpt": "ok",
                        "tenant_id": bound_tenant,
                    }
                ],
            },
        }

    monkeypatch.setattr(bdg, "_fetch_second_brain_advice", _fetch)


def test_autonomy_off_leaves_governance_untouched(gov_root, monkeypatch):
    monkeypatch.setenv("BOSS_FULL_AUTONOMY", "0")
    assert ba.enabled() is False
    assert ba.ready() is False
    out = ba.propose_and_decide(decision_type="internal_plan", title="t")
    assert out["ok"] is False
    assert out["outcome"] == "autonomy_off"
    assert bdg.metrics_snapshot()["decisions"] == 0


def test_governance_off_blocks_autonomy(gov_root, monkeypatch):
    monkeypatch.setenv("BOSS_DECISION_GOVERNANCE", "0")
    out = ba.propose_and_decide(decision_type="internal_plan", title="t")
    assert out["ok"] is False
    assert out["outcome"] == "governance_off"


def test_canonical_boss_identity_is_manager(gov_root):
    assert ba.BOSS_ID == "manager"
    assert ba.boss_id() == "manager"
    assert ba.boss_id() != "hermes"


def test_authority_classification():
    assert ba.authority_class("internal_plan") == "A"
    assert ba.authority_class("customer_content_publish") == "B"
    assert ba.authority_class("upi_payment") == "C"
    assert ba.authority_class("cold_outbound_call") == "C"
    assert ba.authority_class("totally_unknown_xyz") is None


def test_service_uses_public_api_only():
    src = inspect.getsource(ba)
    for forbidden in (
        "_OWNER_ONLY_TYPES",
        "_fetch_second_brain_advice",
        "_read_jsonl",
        "_ledger_path",
        "_latest_by_id",
        "_transition",
        "_atomic_claim",
    ):
        assert forbidden not in src, "service must not touch private bdg API: " + forbidden


def test_flag_registered_and_owner_gated(gov_root):
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "BOSS_FULL_AUTONOMY" in AUTOMATION_FLAGS
    meta = describe_flag("BOSS_FULL_AUTONOMY")
    assert meta.governance == FlagGovernance.OWNER_APPROVAL_REQUIRED
    assert meta.default_hint == "0"


def test_unknown_decision_type_refused(gov_root):
    out = ba.propose_and_decide(decision_type="totally_unknown_type_xyz", title="t")
    assert out["ok"] is False
    assert out["outcome"] == "unknown_decision_type"
    assert out["fail_closed"] is True


def test_red_lane_non_delegable(gov_root):
    out = ba.propose_and_decide(
        decision_type="cold_outbound_call", title="t", agent_id="isha", proposed_by="isha"
    )
    assert out["ok"] is True
    assert out["outcome"] == "refused"
    assert ba.authority_class("cold_outbound_call") == "C"


def test_upi_owner_only_non_delegable(gov_root):
    out = ba.propose_and_decide(
        decision_type="upi_payment", title="t", agent_id="isha", proposed_by="isha"
    )
    assert out["ok"] is False
    assert out["outcome"] == "non_delegable"
    assert out["authority_class"] == "C"
    assert out["fail_closed"] is True


def test_delegated_internal_type_executes_once(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    out = ba.propose_and_decide(
        decision_type="internal_plan",
        title="plan X",
        payload={"step": 1},
        agent_id="isha",
        proposed_by="isha",
    )
    assert out["ok"] is True, out
    assert out["outcome"] == "executed"
    did = out["decision_id"]
    cur = bdg.get_decision(did)
    assert cur["consumed"] is True
    assert cur["state"] == "executed"
    again = ba.advance_decision(did, max_steps=10)
    assert again["ok"] is True
    assert again["outcome"] in ("executed", "consumed")
    assert again["steps"] == 0


def test_same_decision_cannot_execute_twice(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    out = ba.propose_and_decide(decision_type="internal_plan", agent_id="isha", proposed_by="isha")
    assert out["outcome"] == "executed"
    did = out["decision_id"]
    replay = bdg.consume_or_execute(did, mode="execute")
    assert replay["ok"] is False
    assert replay["error"] == "replay_rejected"


def test_stale_hash_refused(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    out = ba.propose_and_decide(
        decision_type="internal_plan", agent_id="isha", proposed_by="isha", advance=False
    )
    did = out["decision_id"]
    bad = ba.advance_decision(did, max_steps=10, expected_sha256="0" * 64)
    assert bad["ok"] is False
    assert bad["outcome"] == "stale_hash"
    assert bad["fail_closed"] is True


def test_wrong_tenant_advice_refused(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0, tenant="other-tenant")
    out = ba.propose_and_decide(
        decision_type="internal_plan",
        agent_id="isha",
        proposed_by="isha",
        tenant_id="tenant-a",
    )
    assert out["ok"] is False
    assert out["outcome"] == "advice_cross_tenant"


def test_missing_advice_refused(gov_root, monkeypatch):
    _patch_advice(monkeypatch, ok=False, error="advice_unavailable")
    out = ba.propose_and_decide(decision_type="internal_plan", agent_id="isha", proposed_by="isha")
    assert out["ok"] is False
    assert out["outcome"] == "advice_unavailable"
    assert bdg.get_decision(out["decision_id"])["state"] == "refused"


def test_low_confidence_advice_defers_not_executes(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=0.2)
    out = ba.propose_and_decide(decision_type="internal_plan", agent_id="isha", proposed_by="isha")
    assert out["ok"] is False
    assert out["outcome"] == "deferred"
    cur = bdg.get_decision(out["decision_id"])
    assert cur["state"] == "boss_reviewed"
    assert cur["consumed"] is False


def test_boss_cannot_self_approve(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    out = ba.propose_and_decide(decision_type="internal_plan", title="t")
    assert out["ok"] is False
    assert out["outcome"] == "boss_cannot_self_approve"


def test_held_agent_unarmed(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    out = ba.propose_and_decide(
        decision_type="internal_plan", agent_id="rohan", proposed_by="rohan"
    )
    assert out["ok"] is False
    assert out["outcome"] == "agent_unarmed"


def test_amber_needs_owner(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    out = ba.propose_and_decide(
        decision_type="customer_content_publish",
        payload={"caption": "hi"},
        agent_id="isha",
        proposed_by="isha",
    )
    assert out["ok"] is False
    assert out["outcome"] == "needs_owner"
    assert out["authority_class"] == "B"
    assert bdg.get_decision(out["decision_id"])["state"] == "needs_owner"


def test_duplicate_sweep_never_reproposes(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    ids = []
    for i in range(3):
        out = ba.propose_and_decide(
            decision_type="internal_plan",
            title="p" + str(i),
            agent_id="isha",
            proposed_by="isha",
        )
        assert out["outcome"] == "executed"
        ids.append(out["decision_id"])
    before = set(ids)
    s1 = ba.sweep_due(limit=10)
    s2 = ba.sweep_due(limit=10)
    assert s1["swept"] == 0
    assert s2["swept"] == 0
    latest = {r.get("decision_id") for r in _all_rows()}
    assert latest == before


def test_sweep_bounded(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=0.2)
    for i in range(5):
        ba.propose_and_decide(
            decision_type="internal_plan", title="p" + str(i), agent_id="isha", proposed_by="isha"
        )
    out = ba.sweep_due(limit=3)
    assert out["ok"] is True
    assert out["swept"] <= 3


def test_advance_decision_reports_advanced_outcome(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    out = ba.propose_and_decide(
        decision_type="internal_plan", agent_id="isha", proposed_by="isha", advance=False
    )
    did = out["decision_id"]
    r = ba.advance_decision(did, max_steps=1)
    assert r["outcome"] == "advanced"
    assert r["steps"] == 1
    assert r["state"] == "advice_recorded"


def test_evaluate_decision_read_only(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    out = ba.propose_and_decide(
        decision_type="internal_plan", agent_id="isha", proposed_by="isha", advance=False
    )
    did = out["decision_id"]
    ev = ba.evaluate_decision(did)
    assert ev["ok"] is True
    assert ev["authority_class"] == "A"
    assert ev["state"] == "proposed"
    assert ev["consumed"] is False


def test_status_and_metrics(gov_root, monkeypatch):
    _patch_advice(monkeypatch, score=1.0)
    ba.propose_and_decide(decision_type="internal_plan", agent_id="isha", proposed_by="isha")
    st = ba.status()
    assert st["enabled"] is True
    assert st["governance_enabled"] is True
    assert st["ready"] is True
    assert st["boss_id"] == "manager"
    m = ba.metrics()
    assert m["autonomy_enabled"] is True
    assert m["decisions"] >= 1


def test_admin_boss_autopilot_endpoint():
    import asyncio
    import inspect

    from app.api.admin_dashboard import get_boss_autopilot

    # admin-gated: machine run-tokens (DSH) cannot reach this route
    assert "require_admin" in inspect.getsource(get_boss_autopilot)
    out = asyncio.run(get_boss_autopilot())
    assert out["ok"] is True
    assert set(out) >= {"status", "metrics", "governance"}
    assert out["status"]["boss_id"] == "manager"
    assert isinstance(out["status"]["enabled"], bool)
    assert out["status"]["boss_rollout"] in ("held", "canary", "disabled")


def test_admin_boss_autopilot_html_surface():
    from pathlib import Path

    html = Path("frontend/admin_dashboard.html").read_text(encoding="utf-8")
    assert 'id="sec-boss-autopilot"' in html
    assert 'id="bossAutopilotBody"' in html
    assert "/api/admin/boss-autopilot" in html
    assert 'href="#sec-boss-autopilot"' in html


def test_run_once_flag_off_inert(gov_root, monkeypatch):
    monkeypatch.setenv("BOSS_FULL_AUTONOMY", "0")
    out = ba.run_once(limit=10)
    assert out["ok"] is False
    assert out["outcome"] == "autonomy_off"


def test_boss_autonomy_sweep_registered_in_beat():
    from app.worker import celery_app

    entry = celery_app.conf.beat_schedule.get("boss-autonomy-sweep")
    assert entry is not None
    assert entry["task"] == "app.tasks.staff_jobs.boss_autonomy_sweep"


def _all_rows():
    rows = []
    try:
        from app.platform import runtime_data

        p = runtime_data.store_path("boss_decision_governance", "decisions.jsonl")
        if p.exists():
            import json

            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
    except Exception:
        pass
    return rows
