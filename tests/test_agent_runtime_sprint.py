"""Agent Runtime — GTM sprint capabilities (kavya host) contract tests.

Covers: registration/idempotency, dispatch happy path, flag-off skip, kill
switch block, idempotency duplicate suppression, and no-mutation honesty.
"""

from __future__ import annotations

import pytest

from app.platform import agent_registry as ar
from app.platform import agent_runtime as rt
from app.platform import agent_runtime_sprint as sprint
from app.platform import agent_runtime_workforce as wf
from app.platform.team import STAFF


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(rt, "_USAGE_PATH", str(tmp_path / "usage.json"))
    monkeypatch.setattr(rt, "_DLQ_PATH", str(tmp_path / "dlq.jsonl"))
    monkeypatch.setattr(rt, "_BACKOFF_BASE_S", 0.0)
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: False)
    monkeypatch.setattr(rt, "_approval_approved", lambda tenant, ref: False)

    caps_snapshot = dict(rt._CAPABILITIES)
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "memory")
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "memory")
    from app.platform import agent_runtime_cancellation as crc
    from app.platform import agent_runtime_idempotency as arid

    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()
    rt._CAPABILITIES.clear()

    monkeypatch.setenv("AGENT_RUNTIME", "1")
    monkeypatch.setenv("OPS_HEALTH_AGENT", "1")
    yield
    rt._CAPABILITIES.clear()
    rt._CAPABILITIES.update(caps_snapshot)
    crc.reset_memory_for_tests()
    arid.reset_memory_for_tests()
    rt._ACTIVE.clear()
    rt._ACTIVE_TASKS.clear()


def test_sprint_caps_registered_idempotent():
    wf.ensure_workforce_registered()
    wf.ensure_workforce_registered()  # idempotent
    caps = rt.capabilities_for("kavya")
    for action in ("dialer_sprint_prep", "hot_wa_draft", "job_heal_sweep"):
        assert action in caps, f"{action} missing"
        cap = rt.get_capability("kavya", action)
        assert cap.side_effect == "none"
        assert cap.counts_contact is False
        assert cap.requires_approval is False


def test_sprint_caps_hosted_under_pilot():
    wf.ensure_workforce_registered()
    assert "kavya" in rt.PILOT_AGENTS
    contract = ar.get_contract("kavya")
    assert contract.lane == ar.Lane.GREEN.value
    assert contract.primary_flag == "OPS_HEALTH_AGENT"
    assert ar.validate_registry() == []
    assert len(STAFF) == 31  # invariant intact — no new persona


async def test_dialer_sprint_prep_dispatch(monkeypatch):
    wf.ensure_workforce_registered()

    async def _fake_prep(limit=3):
        return {"ok": True, "detail": f"{limit} briefs", "prepped": limit, "briefs": []}

    monkeypatch.setattr("app.agents.sprint_actions.dialer_sprint_prep", _fake_prep)
    res = await rt.submit("kavya", "dialer_sprint_prep", {"limit": 2}, idempotency_key="k1")
    assert res.status == "succeeded"
    assert res.output["ok"] is True
    assert res.output["prepped"] == 2


async def test_hot_wa_draft_dispatch(monkeypatch):
    wf.ensure_workforce_registered()

    async def _fake_draft(limit=5):
        return {"ok": True, "detail": "2 drafted", "drafted": 2, "skipped": 1}

    monkeypatch.setattr("app.agents.sprint_actions.hot_wa_draft", _fake_draft)
    res = await rt.submit("kavya", "hot_wa_draft", {"limit": 3}, idempotency_key="k2")
    assert res.status == "succeeded"
    assert res.output["drafted"] == 2


async def test_job_heal_sweep_dispatch(monkeypatch):
    wf.ensure_workforce_registered()

    async def _fake_heal(max_jobs=3):
        return {"ok": True, "started": {"ops": "ok"}, "skipped_excluded": []}

    monkeypatch.setattr("app.agents.sprint_actions.job_heal_sweep", _fake_heal)
    res = await rt.submit("kavya", "job_heal_sweep", {"max_jobs": 1}, idempotency_key="k3")
    assert res.status == "succeeded"
    assert res.output["ok"] is True


async def test_sprint_caps_flag_off_skipped(monkeypatch):
    monkeypatch.delenv("OPS_HEALTH_AGENT", raising=False)
    wf.ensure_workforce_registered()
    res = await rt.submit("kavya", "dialer_sprint_prep", {}, idempotency_key="k4")
    assert res.status == "skipped"
    assert "flag_disabled:OPS_HEALTH_AGENT" in res.reason


async def test_sprint_caps_master_flag_off_skipped(monkeypatch):
    monkeypatch.delenv("AGENT_RUNTIME", raising=False)
    wf.ensure_workforce_registered()
    res = await rt.submit("kavya", "hot_wa_draft", {}, idempotency_key="k5")
    assert res.status == "skipped"
    assert "runtime_flag_disabled" in res.reason


async def test_sprint_caps_kill_switch_blocked(monkeypatch):
    monkeypatch.setattr(rt, "_kill_engaged", lambda key: key == "owner_all_agents")
    wf.ensure_workforce_registered()
    res = await rt.submit("kavya", "job_heal_sweep", {}, idempotency_key="k6")
    assert res.status == "blocked"
    assert "kill_switch_engaged" in res.reason


async def test_sprint_caps_idempotent_duplicate(monkeypatch):
    wf.ensure_workforce_registered()

    async def _fake_prep(limit=3):
        return {"ok": True, "detail": "1 brief", "prepped": 1, "briefs": []}

    monkeypatch.setattr("app.agents.sprint_actions.dialer_sprint_prep", _fake_prep)
    r1 = await rt.submit("kavya", "dialer_sprint_prep", {}, idempotency_key="dup-key")
    assert r1.status == "succeeded"
    r2 = await rt.submit("kavya", "dialer_sprint_prep", {}, idempotency_key="dup-key")
    assert r2.status == "skipped"
    assert r2.reason == "duplicate_suppressed"


async def test_sprint_caps_never_mutate_outside_payload():
    """No-mutation honesty: caps only expose bounded limit params, no send/charge."""
    wf.ensure_workforce_registered()
    for action in ("dialer_sprint_prep", "hot_wa_draft", "job_heal_sweep"):
        cap = rt.get_capability("kavya", action)
        assert cap.side_effect == "none"
    import inspect

    src = inspect.getsource(sprint)
    assert "send_email" not in src
    assert "send_whatsapp" not in src
    assert "make_call" not in src
    assert "charge" not in src
