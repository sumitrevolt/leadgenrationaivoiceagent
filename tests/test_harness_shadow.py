"""Shadow-mode tests for the Nikhil real-agent slice.

Standalone tests exercise the record-only observe() path + eligibility with no
app.* deps. The final test drives the REAL staff.run_member dispatcher (skipped
where the app isn't importable).
"""

import asyncio
import json

import pytest
from pydantic import BaseModel, ConfigDict

from app.agents.harness import Harness, RiskClass, RunContext, ToolCall, ToolRegistry
from app.agents.harness.adapters import shadow


class _NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _canary_env(mp, agents="nikhil", harness="1", shadowf="1", enforce="0"):
    mp.setenv("AGENT_HARNESS", harness)
    mp.setenv("AGENT_HARNESS_SHADOW", shadowf)
    mp.setenv("AGENT_HARNESS_ENFORCE", enforce)
    mp.setenv("AGENT_HARNESS_CANARY_AGENTS", agents)


# ---- flag isolation --------------------------------------------------
def test_all_flags_off_no_record(monkeypatch):
    for k in (
        "AGENT_HARNESS",
        "AGENT_HARNESS_SHADOW",
        "AGENT_HARNESS_ENFORCE",
        "AGENT_HARNESS_CANARY_AGENTS",
    ):
        monkeypatch.delenv(k, raising=False)
    assert shadow.observe_legacy_run("nikhil", actual_result={"ok": True}) is None


def test_harness_on_shadow_off(monkeypatch):
    _canary_env(monkeypatch, shadowf="0")
    assert shadow.shadow_eligible("nikhil") is False


def test_empty_canary_none_eligible(monkeypatch):
    _canary_env(monkeypatch, agents="")
    assert shadow.shadow_eligible("nikhil") is False


def test_nikhil_eligible(monkeypatch):
    _canary_env(monkeypatch)
    assert shadow.shadow_eligible("nikhil") is True
    assert shadow.shadow_eligible("Nikhil") is True  # normalized


def test_peers_ineligible(monkeypatch):
    _canary_env(monkeypatch)
    for peer in ("manager", "boss", "swara", "kavya"):
        assert shadow.shadow_eligible(peer) is False


def test_enforce_on_makes_ineligible(monkeypatch):
    _canary_env(monkeypatch, enforce="1")
    assert shadow.shadow_eligible("nikhil") is False


# ---- execution safety ------------------------------------------------
def test_observer_never_invokes_tool(monkeypatch):
    called = {"n": 0}

    async def boom(**_):
        called["n"] += 1
        raise AssertionError("must not run")

    reg = ToolRegistry(permission_fn=lambda a, t: True)
    reg.register("staff.run_nikhil", boom, _NoArgs, RiskClass.WRITE_LOCAL)
    ctx = RunContext(agent="nikhil", tenant_id="__system__", source_loop="staff.run_member")
    req = ToolCall(
        name="staff.run_nikhil", idempotency_key="shadow:r1:0", risk_class=RiskClass.WRITE_LOCAL
    )
    rec = Harness(registry=reg).observe(ctx, req, actual_result={"ok": True})
    assert called["n"] == 0  # executor NEVER called
    assert rec["comparison_verdict"] == "MATCH"
    assert rec["would_checkpoint"] is True  # WRITE_LOCAL is mutating


def test_shadow_ref_is_not_legacy_key(monkeypatch):
    _canary_env(monkeypatch)
    rec = shadow.observe_legacy_run(
        "nikhil", actual_result={"ok": True}, real_run_id="realRUN", action_index=0
    )
    assert rec is not None
    assert rec["shadow_run_id"] == "shadow:realRUN:0"
    assert rec["run_id"] == "realRUN"


def test_observer_exception_does_not_propagate(monkeypatch):
    _canary_env(monkeypatch)

    def blow(*a, **k):
        raise RuntimeError("observe blew up")

    monkeypatch.setattr("app.agents.harness.loop.Harness.observe", blow)
    # adapter must swallow and return None, never raise into the caller
    assert shadow.observe_legacy_run("nikhil", actual_result={"ok": True}) is None


# ---- policy lanes recorded ------------------------------------------
def test_red_action_recorded_would_deny():
    reg = ToolRegistry(permission_fn=lambda a, t: False)  # deny
    reg.register("danger", _NoArgs and (lambda **_: None), _NoArgs, RiskClass.MONEY)
    ctx = RunContext(agent="nikhil")
    req = ToolCall(name="danger", idempotency_key="shadow:r:0", risk_class=RiskClass.MONEY)
    rec = Harness(registry=reg).observe(ctx, req, actual_result={"ok": True})
    assert rec["would_allow"] is False
    assert rec["predicted_lane"] == "RED"
    assert rec["comparison_verdict"] == "POLICY_MISMATCH"


def test_amber_action_recorded_would_require_approval():
    reg = ToolRegistry(permission_fn=lambda a, t: True)
    reg.register("send", lambda **_: None, _NoArgs, RiskClass.EXTERNAL_SEND)
    ctx = RunContext(agent="nikhil")
    req = ToolCall(name="send", idempotency_key="shadow:r:0", risk_class=RiskClass.EXTERNAL_SEND)
    rec = Harness(registry=reg).observe(ctx, req, actual_result={"ok": True})
    assert rec["would_require_approval"] is True
    assert rec["predicted_lane"] == "AMBER"


# ---- identity & privacy ---------------------------------------------
def test_recorded_agent_is_nikhil(monkeypatch):
    _canary_env(monkeypatch)
    rec = shadow.observe_legacy_run("nikhil", actual_result={"ok": True})
    assert rec["agent"] == "nikhil"
    assert rec["tenant_id"] == "__system__"  # explicit system scope, not a customer


def test_no_peer_record(monkeypatch):
    _canary_env(monkeypatch)
    assert shadow.observe_legacy_run("manager", actual_result={"ok": True}) is None


def test_secret_redaction(monkeypatch):
    _canary_env(monkeypatch)
    rec = shadow.observe_legacy_run(
        "nikhil",
        actual_result={"api_key": "sk_live_SECRET", "ok": True},  # pragma: allowlist secret
    )
    blob = json.dumps(rec)
    assert "sk_live_SECRET" not in blob
    assert "REDACTED" in blob


def test_missing_tool_metadata_safe_record():
    reg = ToolRegistry(permission_fn=lambda a, t: True)  # tool NOT registered
    ctx = RunContext(agent="nikhil")
    req = ToolCall(name="unregistered", risk_class=RiskClass.READ)
    rec = Harness(registry=reg).observe(ctx, req, actual_result={"ok": True})
    assert rec["would_validate"] is False
    assert rec["comparison_verdict"] == "MISSING_CONTEXT"


# ---- explainability --------------------------------------------------
def test_explainable_via_audit(monkeypatch, tmp_path):
    _canary_env(monkeypatch)
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    rec = shadow.observe_legacy_run(
        "nikhil", actual_result={"ok": True}, real_run_id="explainME", latency_ms=42
    )
    events = audit.replay("explainME")
    assert events, "no audit events for run"
    ev = events[-1]["extra"]
    assert ev["comparison_verdict"] == "MATCH"  # proposed-vs-actual present
    # Nikhil composite = AMBER (usage_alerts can send customer emails); registry
    # authoritative. Execution layer still MATCH (would_allow True), but the lane
    # is honestly AMBER and approval would be required.
    assert ev["predicted_lane"] == "AMBER"
    assert ev["would_require_approval"] is True
    assert ev["registry_comparison"] == "REGISTRY_MATCH"
    assert ev["stop_decision"] == "continue"  # stop decision visible
    assert ev["run_id"] == "explainME" and ev["shadow_run_id"] == "shadow:explainME:0"


# ---- REAL loop integration (skips where app not importable) ----------
def test_nikhil_through_real_run_member(monkeypatch, tmp_path):
    staff = pytest.importorskip("app.agents.staff")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _canary_env(monkeypatch)

    # isolate pause/budget so we deterministically reach dispatch (real seam kept)
    monkeypatch.setattr("app.platform.agent_controls.is_paused", lambda k: False, raising=False)

    calls = {"n": 0}

    async def fake_nikhil():
        calls["n"] += 1
        return {"ok": True, "results": {"revenue": {"ok": True}}}

    monkeypatch.setattr(staff, "run_nikhil", fake_nikhil)
    res = asyncio.run(staff.run_member("nikhil"))

    assert calls["n"] == 1  # legacy executed EXACTLY once
    assert res.get("ok") is True
    rows = [json.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    shadow_rows = [
        r for r in rows if r.get("kind") == "shadow" and r["extra"].get("agent") == "nikhil"
    ]
    assert shadow_rows, "no shadow record from real run_member"
    assert shadow_rows[-1]["extra"]["comparison_verdict"] in ("MATCH", "LEGACY_ERROR")
    assert shadow_rows[-1]["extra"]["enforcement"] is False
