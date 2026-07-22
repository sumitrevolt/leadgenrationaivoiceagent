"""batch_harness enforcement-path tests (canary preparation).

Everything here proves the INERT enforcement pipeline locally with the internal
GREEN tool + tripwire executors. No production flags, no external effects.
Enforcement is exercised only via test-local env overrides + injected gates.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from app.agents.harness.contracts import RiskClass, RunContext, ToolCall
from app.agents.harness.enforce import (
    DenialReason,
    EnforcementGate,
    ExecutorBindingRegistry,
    HarnessMode,
    _reset_guard,
    enforce_batch_item,
    resolve_mode,
)
from app.agents.harness.registry import (
    AuthorityClass,
    CanonicalToolRegistry,
    RiskLane,
    SideEffectClass,
    ToolDefinition,
)

SAFE = "batch.internal.safe_calculation"
SAFE_TOKEN = f"{SAFE}@1.0.0"


# --------------------------- helpers ---------------------------------
async def _tripwire(**_):
    raise AssertionError("bound executor must NEVER be invoked for this case")


class _Counter:
    def __init__(self):
        self.n = 0

    async def __call__(self, **kw):
        self.n += 1
        return {"ok": True, "summary": "counted", **kw}


class _FakeStop:
    def __init__(self, *, kill=False, admit=True, cont=True):
        self._kill, self._admit, self._cont = kill, admit, cont

    def killed(self, ctx):
        return self._kill

    def admit(self, ctx, u, t):
        return self._admit

    def check(self, ctx):
        from app.agents.harness.contracts import StopReason

        return (self._cont, None if self._cont else StopReason.KILL_SWITCH)


def _def(name, **kw):
    base = {
        "name": name,
        "version": "1.0.0",
        "description": "t",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        "risk_class": RiskLane.GREEN,
        "side_effect_class": SideEffectClass.READ_ONLY,
        "authority": AuthorityClass.INTERNAL_AUTONOMOUS,
        "allowed_agents": frozenset({"nikhil"}),
        "allowed_tenant_scopes": frozenset({"__system__"}),
    }
    base.update(kw)
    return ToolDefinition(**base)


def _gate_with(defn, executor=None, *, stop=None):
    """Fresh registry+executors+gate carrying one custom tool + tripwire executor."""
    reg = CanonicalToolRegistry()
    reg.register(defn)
    ex = ExecutorBindingRegistry()
    ex.bind(defn.name, defn.version, executor or _tripwire)
    return EnforcementGate(registry=reg, executors=ex, stop=stop or _FakeStop())


def _ctx(agent="nikhil", tenant="__system__"):
    return RunContext(
        run_id="t", task_id="t", tenant_id=tenant, agent=agent, source_loop="batch_harness"
    )


def _req(name=SAFE, ver="1.0.0", args=None, idem="enforce:t:i:0"):
    return ToolCall(
        name=name,
        tool_version=ver,
        args=(args or {"id": "x"}),
        risk_class=RiskClass.READ,
        idempotency_key=idem,
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (
        "AGENT_HARNESS",
        "AGENT_HARNESS_SHADOW",
        "AGENT_HARNESS_ENFORCE",
        "AGENT_HARNESS_ENFORCE_AGENTS",
        "AGENT_HARNESS_ENFORCE_LOOPS",
        "AGENT_HARNESS_ENFORCE_TOOLS",
        "AGENT_HARNESS_CANARY_AGENTS",
        "AGENT_HARNESS_CANARY_LOOPS",
    ):
        monkeypatch.delenv(k, raising=False)
    _reset_guard()
    yield
    _reset_guard()


def _enforce_env(monkeypatch, tools=SAFE_TOKEN):
    monkeypatch.setenv("AGENT_HARNESS", "1")
    monkeypatch.setenv("AGENT_HARNESS_SHADOW", "0")
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE", "1")
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE_AGENTS", "nikhil")
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE_LOOPS", "batch_harness")
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE_TOOLS", tools)


# ============ Mode resolution (1-8) ==================================
def test_mode_all_off(monkeypatch):
    assert resolve_mode(agent_id="nikhil", source_loop="batch_harness")[0] is HarnessMode.OFF


def test_mode_shadow_only(monkeypatch):
    monkeypatch.setenv("AGENT_HARNESS", "1")
    monkeypatch.setenv("AGENT_HARNESS_SHADOW", "1")
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE", "0")
    assert resolve_mode(agent_id="nikhil", source_loop="batch_harness")[0] is HarnessMode.SHADOW


def test_mode_enforce_valid(monkeypatch):
    _enforce_env(monkeypatch)
    assert resolve_mode(agent_id="nikhil", source_loop="batch_harness")[0] is HarnessMode.ENFORCE


def test_mode_shadow_and_enforce_conflict_fail_closed(monkeypatch):
    _enforce_env(monkeypatch)
    monkeypatch.setenv("AGENT_HARNESS_SHADOW", "1")  # both on = invalid
    m, notes = resolve_mode(agent_id="nikhil", source_loop="batch_harness")
    assert m is HarnessMode.OFF and any("INVALID_MODE" in n for n in notes)


def test_mode_missing_agent(monkeypatch):
    _enforce_env(monkeypatch)
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE_AGENTS", "")
    assert resolve_mode(agent_id="nikhil", source_loop="batch_harness")[0] is HarnessMode.OFF


def test_mode_missing_loop(monkeypatch):
    _enforce_env(monkeypatch)
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE_LOOPS", "")
    assert resolve_mode(agent_id="nikhil", source_loop="batch_harness")[0] is HarnessMode.OFF


def test_mode_missing_tool_allowlist(monkeypatch):
    _enforce_env(monkeypatch)
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE_TOOLS", "")
    # run-level (tool_token=None) still ENFORCE, but per-tool refinement is OFF
    assert (
        resolve_mode(agent_id="nikhil", source_loop="batch_harness", tool_token=SAFE_TOKEN)[0]
        is HarnessMode.OFF
    )


def test_mode_wrong_version_allowlist(monkeypatch):
    _enforce_env(monkeypatch, tools=f"{SAFE}@9.9.9")
    assert (
        resolve_mode(agent_id="nikhil", source_loop="batch_harness", tool_token=SAFE_TOKEN)[0]
        is HarnessMode.OFF
    )


def test_mode_wildcard_rejected(monkeypatch):
    _enforce_env(monkeypatch)
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE_AGENTS", "*")
    m, notes = resolve_mode(agent_id="nikhil", source_loop="batch_harness")
    assert m is HarnessMode.OFF and any("wildcard" in n for n in notes)


# ============ Decision pipeline (9-24) — evaluate() NEVER executes ====
def test_decision_valid_green_allowed(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"), _Counter())
    d = g.evaluate(_ctx(), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert d.allowed_for_enforcement and d.risk_lane is RiskLane.GREEN
    assert d.authority is AuthorityClass.INTERNAL_AUTONOMOUS and d.executor_bound


def test_decision_unknown_tool_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"))
    d = g.evaluate(_ctx(), _req("no.such.tool"), mode=HarnessMode.ENFORCE)
    assert not d.allowed and DenialReason.UNREGISTERED_TOOL.value in d.denial_reasons


def test_decision_disabled_tool_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run", enabled_by_default=False))
    d = g.evaluate(_ctx(), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert not d.allowed and DenialReason.TOOL_DISABLED.value in d.denial_reasons


def test_decision_version_mismatch_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@2.0.0")
    g = _gate_with(_def("demo.calc.run"))
    d = g.evaluate(_ctx(), _req("demo.calc.run", ver="2.0.0"), mode=HarnessMode.ENFORCE)
    assert DenialReason.VERSION_MISMATCH.value in d.denial_reasons


def test_decision_schema_mismatch_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"))
    d = g.evaluate(_ctx(), _req("demo.calc.run", args={"id": 123}), mode=HarnessMode.ENFORCE)
    assert DenialReason.SCHEMA_MISMATCH.value in d.denial_reasons


def test_decision_agent_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"))
    d = g.evaluate(_ctx(agent="manager"), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert DenialReason.AGENT_NOT_ALLOWED.value in d.denial_reasons


def test_decision_tenant_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"))
    d = g.evaluate(_ctx(tenant="client:acme"), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert DenialReason.TENANT_NOT_ALLOWED.value in d.denial_reasons


def test_decision_claimed_green_cannot_downgrade_red(monkeypatch):
    _enforce_env(monkeypatch, tools="x.y.z@1.0.0")
    g = _gate_with(_def("x.y.z", risk_class=RiskLane.RED, authority=AuthorityClass.ALWAYS_REFUSED))
    d = g.evaluate(_ctx(), _req("x.y.z"), mode=HarnessMode.ENFORCE)  # req CLAIMS GREEN
    assert not d.allowed and DenialReason.RISK_NOT_GREEN.value in d.denial_reasons
    assert d.risk_lane is RiskLane.RED  # registry wins


def test_decision_amber_pending_approval(monkeypatch):
    _enforce_env(monkeypatch, tools="c.d.write@1.0.0")
    g = _gate_with(
        _def(
            "c.d.write",
            risk_class=RiskLane.AMBER,
            authority=AuthorityClass.APPROVAL_REQUIRED,
            requires_approval=True,
        )
    )
    d = g.evaluate(_ctx(), _req("c.d.write"), mode=HarnessMode.ENFORCE)
    assert not d.allowed and DenialReason.APPROVAL_REQUIRED.value in d.denial_reasons
    assert d.approval_required


def test_decision_owner_os_required_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="o.s.route@1.0.0")
    g = _gate_with(_def("o.s.route", authority=AuthorityClass.OWNER_OS_REQUIRED))
    d = g.evaluate(_ctx(), _req("o.s.route"), mode=HarnessMode.ENFORCE)
    assert DenialReason.OWNER_OS_REQUIRED.value in d.denial_reasons
    assert d.owner_os_routing_required and not d.allowed


def test_decision_red_always_refused(monkeypatch):
    _enforce_env(monkeypatch, tools="shell.exec.run@1.0.0")
    g = _gate_with(
        _def(
            "shell.exec.run",
            risk_class=RiskLane.RED,
            side_effect_class=SideEffectClass.CODE_EXECUTION,
            authority=AuthorityClass.ALWAYS_REFUSED,
            sandbox_required=True,
        )
    )
    d = g.evaluate(_ctx(), _req("shell.exec.run"), mode=HarnessMode.ENFORCE)
    assert DenialReason.ALWAYS_REFUSED.value in d.denial_reasons and not d.allowed


def test_decision_sandbox_required_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="s.b.needed@1.0.0")
    g = _gate_with(_def("s.b.needed", sandbox_required=True))
    d = g.evaluate(_ctx(), _req("s.b.needed"), mode=HarnessMode.ENFORCE)
    assert DenialReason.SANDBOX_REQUIRED.value in d.denial_reasons


def test_decision_budget_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"), _Counter(), stop=_FakeStop(admit=False))
    d = g.evaluate(_ctx(), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert DenialReason.BUDGET_DENIED.value in d.denial_reasons and d.budget_allowed is False


def test_decision_kill_switch_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"), _Counter(), stop=_FakeStop(kill=True))
    d = g.evaluate(_ctx(), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert DenialReason.KILL_SWITCH.value in d.denial_reasons and d.kill_switch_clear is False


def test_decision_stop_requested_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"), _Counter(), stop=_FakeStop(cont=False))
    d = g.evaluate(_ctx(), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert DenialReason.STOP_REQUESTED.value in d.denial_reasons


def test_decision_missing_executor_binding_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    reg = CanonicalToolRegistry()
    reg.register(_def("demo.calc.run"))
    g = EnforcementGate(registry=reg, executors=ExecutorBindingRegistry(), stop=_FakeStop())
    d = g.evaluate(_ctx(), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert DenialReason.EXECUTOR_NOT_BOUND.value in d.denial_reasons


def test_decision_not_enforce_mode_denies(monkeypatch):
    g = _gate_with(_def("demo.calc.run"), _Counter())
    d = g.evaluate(_ctx(), _req("demo.calc.run"), mode=HarnessMode.SHADOW)
    assert not d.allowed and DenialReason.INVALID_MODE.value in d.denial_reasons


def test_decision_tool_not_allowlisted_denied(monkeypatch):
    _enforce_env(monkeypatch, tools="other.tool.x@1.0.0")  # demo not listed
    g = _gate_with(_def("demo.calc.run"), _Counter())
    d = g.evaluate(_ctx(), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert DenialReason.TOOL_NOT_ALLOWLISTED.value in d.denial_reasons


# ============ Execution (25-33) — execute_registered() ================
async def _boom(**_):
    raise RuntimeError("boom")


def _run(coro):
    return asyncio.run(coro)


def test_exec_bound_executor_called_once(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    c = _Counter()
    g = _gate_with(_def("demo.calc.run"), c)
    ctx, req = _ctx(), _req("demo.calc.run", idem="k1")
    d = g.evaluate(ctx, req, mode=HarnessMode.ENFORCE)
    assert d.allowed
    ok, out, err, dup = _run(g.execute_registered(ctx, req, d))
    assert ok and c.n == 1 and not dup and out["ok"]


def test_evaluate_does_not_execute(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    c = _Counter()
    g = _gate_with(_def("demo.calc.run"), c)
    g.evaluate(_ctx(), _req("demo.calc.run"), mode=HarnessMode.ENFORCE)
    assert c.n == 0  # pure decision — no execution


def test_denied_action_executes_zero(monkeypatch):
    _enforce_env(monkeypatch, tools="x.y.z@1.0.0")
    c = _Counter()
    g = _gate_with(
        _def("x.y.z", risk_class=RiskLane.RED, authority=AuthorityClass.ALWAYS_REFUSED), c
    )
    ctx, req = _ctx(), _req("x.y.z", idem="k")
    d = g.evaluate(ctx, req, mode=HarnessMode.ENFORCE)
    assert not d.allowed
    ok, out, err, dup = _run(g.execute_registered(ctx, req, d))
    assert not ok and c.n == 0


def test_executor_error_recorded_honestly(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"), _boom)
    ctx, req = _ctx(), _req("demo.calc.run", idem="k")
    d = g.evaluate(ctx, req, mode=HarnessMode.ENFORCE)
    assert d.allowed
    ok, out, err, dup = _run(g.execute_registered(ctx, req, d))
    assert not ok and out is None and "EXECUTOR_ERROR" in err


def test_duplicate_attempt_no_double_execute(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    c = _Counter()
    g = _gate_with(_def("demo.calc.run"), c)
    ctx, req = _ctx(), _req("demo.calc.run", idem="dupkey")
    d = g.evaluate(ctx, req, mode=HarnessMode.ENFORCE)
    r1 = _run(g.execute_registered(ctx, req, d))
    r2 = _run(g.execute_registered(ctx, req, d))
    assert c.n == 1 and r1[3] is False and r2[3] is True  # 2nd suppressed


def test_distinct_attempt_executes_separately(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    c = _Counter()
    g = _gate_with(_def("demo.calc.run"), c)
    ctx = _ctx()
    req1, req2 = _req("demo.calc.run", idem="a0"), _req("demo.calc.run", idem="a1")
    d1 = g.evaluate(ctx, req1, mode=HarnessMode.ENFORCE)
    d2 = g.evaluate(ctx, req2, mode=HarnessMode.ENFORCE)
    _run(g.execute_registered(ctx, req1, d1))
    _run(g.execute_registered(ctx, req2, d2))
    assert c.n == 2


def test_result_bounded_and_correlated(monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    c = _Counter()
    g = _gate_with(_def("demo.calc.run"), c)
    ctx, req = _ctx(), _req("demo.calc.run", args={"id": "corr"}, idem="k")
    d = g.evaluate(ctx, req, mode=HarnessMode.ENFORCE)
    ok, out, err, dup = _run(g.execute_registered(ctx, req, d))
    assert ok and out["id"] == "corr" and len(d.decision_id) == 16


# ============ Batch integration (34-44) ==============================
import app.agents.batch_harness as bh  # noqa: E402
from app.agents.batch_harness import run_batch  # noqa: E402
from app.agents.harness import audit as _audit  # noqa: E402
from app.agents.harness import enforce as _enf  # noqa: E402


@pytest.fixture
def batch_env(monkeypatch, tmp_path):
    monkeypatch.setattr(bh, "_DIR", str(tmp_path / "batch_runs"))
    monkeypatch.setattr(_audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _enf._SAFE_CALLS["n"] = 0
    _enf._reset_guard()
    yield tmp_path


async def _legacy_fn(item):
    return {"ok": True, "id": item["id"], "summary": "legacy"}


async def _tripwire_fn(item):
    raise AssertionError("legacy fn must NOT run in enforce mode")


def test_batch_off_preserves_legacy(batch_env, monkeypatch):
    calls = {"n": 0}

    async def fn(item):
        calls["n"] += 1
        return {"ok": True, "id": item["id"]}

    r = _run(
        run_batch(
            fn,
            [{"id": "a"}, {"id": "b"}],
            ckpt_id="off1",
            agent_id="nikhil",
            tool_name=SAFE,
            tool_version="1.0.0",
        )
    )
    assert calls["n"] == 2 and r["done"] == 2 and _enf._SAFE_CALLS["n"] == 0


def test_batch_shadow_preserves_legacy_zero_harness_exec(batch_env, monkeypatch):
    monkeypatch.setenv("AGENT_HARNESS", "1")
    monkeypatch.setenv("AGENT_HARNESS_SHADOW", "1")
    monkeypatch.setenv("AGENT_HARNESS_ENFORCE", "0")
    monkeypatch.setenv("AGENT_HARNESS_CANARY_AGENTS", "nikhil")
    monkeypatch.setenv("AGENT_HARNESS_CANARY_LOOPS", "batch_harness")
    calls = {"n": 0}

    async def fn(item):
        calls["n"] += 1
        return {"ok": True, "id": item["id"]}

    r = _run(
        run_batch(
            fn,
            [{"id": "a"}],
            ckpt_id="sh1",
            agent_id="nikhil",
            tool_name=SAFE,
            tool_version="1.0.0",
        )
    )
    assert calls["n"] == 1 and r["done"] == 1 and _enf._SAFE_CALLS["n"] == 0
    events = _audit.replay("sh1")
    assert any(e.get("kind") == "shadow" for e in events)  # shadow observed
    assert not any(e.get("kind") == "enforce" for e in events)


def test_batch_enforce_uses_registry_executor_only(batch_env, monkeypatch):
    _enforce_env(monkeypatch)
    r = _run(
        run_batch(
            _tripwire_fn,
            [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            concurrency=2,
            ckpt_id="enf1",
            agent_id="nikhil",
            tool_name=SAFE,
            tool_version="1.0.0",
        )
    )
    assert r["done"] == 3 and _enf._SAFE_CALLS["n"] == 3  # tripwire never ran


def test_batch_enforce_registered_three_items(batch_env, monkeypatch):
    _enforce_env(monkeypatch)
    r = _run(
        run_batch(
            _tripwire_fn,
            [{"id": str(i)} for i in range(3)],
            concurrency=3,
            ckpt_id="enf2",
            agent_id="nikhil",
            tool_name=SAFE,
            tool_version="1.0.0",
        )
    )
    assert r["done"] == 3 and r["failed"] == 0 and _enf._SAFE_CALLS["n"] == 3


def test_batch_enforce_unregistered_executes_zero(batch_env, monkeypatch):
    _enforce_env(monkeypatch)
    # No tool_name => legacy 'batch.execute.<id>' identity => UNREGISTERED => deny.
    r = _run(
        run_batch(
            _tripwire_fn,
            [{"id": "a"}, {"id": "b"}],
            concurrency=2,
            ckpt_id="enf3",
            agent_id="nikhil",
        )
    )
    assert _enf._SAFE_CALLS["n"] == 0 and r["failed"] == 2 and r["ok"] is False


def test_batch_enforce_failure_aggregation(batch_env, monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    g = _gate_with(_def("demo.calc.run"), _boom, stop=_FakeStop())
    r = _run(
        run_batch(
            _tripwire_fn,
            [{"id": "a"}, {"id": "b"}],
            concurrency=2,
            ckpt_id="enf4",
            agent_id="nikhil",
            tool_name="demo.calc.run",
            tool_version="1.0.0",
            _enforce_gate=g,
        )
    )
    assert r["failed"] == 2 and r["done"] == 0 and r["ok"] is False


def test_batch_enforce_checkpoint_writes(batch_env, monkeypatch):
    _enforce_env(monkeypatch)
    _run(
        run_batch(
            _tripwire_fn,
            [{"id": str(i)} for i in range(4)],
            concurrency=2,
            ckpt_id="enf5",
            agent_id="nikhil",
            tool_name=SAFE,
            tool_version="1.0.0",
        )
    )
    assert bh._done_indices("enf5") == {0, 1, 2, 3}


def test_batch_enforce_concurrency_honoured(batch_env, monkeypatch):
    _enforce_env(monkeypatch, tools="demo.slow.run@1.0.0")
    live = {"cur": 0, "max": 0}

    async def slow(**kw):
        live["cur"] += 1
        live["max"] = max(live["max"], live["cur"])
        await asyncio.sleep(0.02)
        live["cur"] -= 1
        return {"ok": True, "summary": "slow", **kw}

    g = _gate_with(_def("demo.slow.run"), slow, stop=_FakeStop())
    r = _run(
        run_batch(
            _tripwire_fn,
            [{"id": str(i)} for i in range(6)],
            concurrency=2,
            ckpt_id="enf6",
            agent_id="nikhil",
            tool_name="demo.slow.run",
            tool_version="1.0.0",
            _enforce_gate=g,
        )
    )
    assert r["done"] == 6 and live["max"] == 2  # never exceeded configured concurrency


def test_batch_enforce_kill_prevents_starts(batch_env, monkeypatch):
    _enforce_env(monkeypatch, tools="demo.calc.run@1.0.0")
    c = _Counter()
    g = _gate_with(_def("demo.calc.run"), c, stop=_FakeStop(kill=True))
    r = _run(
        run_batch(
            _tripwire_fn,
            [{"id": str(i)} for i in range(4)],
            concurrency=2,
            ckpt_id="enf7",
            agent_id="nikhil",
            tool_name="demo.calc.run",
            tool_version="1.0.0",
            _enforce_gate=g,
        )
    )
    assert c.n == 0 and r["failed"] == 4  # kill => no item starts


def test_flags_default_off(monkeypatch):
    assert resolve_mode(agent_id="nikhil", source_loop="batch_harness")[0] is HarnessMode.OFF
    assert _enf.enforcement_state()["AGENT_HARNESS_ENFORCE"] is False


# ============ Audit / explain (45-50) ================================
def _events(run_id):
    return [(e.get("extra") or {}) for e in _audit.replay(run_id)]


def test_audit_allowed_decision_visible(batch_env, monkeypatch):
    _enforce_env(monkeypatch)
    _run(
        run_batch(
            _tripwire_fn,
            [{"id": "a"}],
            ckpt_id="au1",
            agent_id="nikhil",
            tool_name=SAFE,
            tool_version="1.0.0",
        )
    )
    evs = [x.get("event") for x in _events("au1")]
    assert "enforcement_evaluated" in evs and "enforcement_completed" in evs


def test_audit_denied_decision_visible(batch_env, monkeypatch):
    _enforce_env(monkeypatch)
    _run(run_batch(_tripwire_fn, [{"id": "a"}], ckpt_id="au2", agent_id="nikhil"))  # unregistered
    evs = [x.get("event") for x in _events("au2")]
    assert "enforcement_denied" in evs


def test_audit_execution_result_visible(batch_env, monkeypatch):
    _enforce_env(monkeypatch)
    _run(
        run_batch(
            _tripwire_fn,
            [{"id": "a"}],
            ckpt_id="au3",
            agent_id="nikhil",
            tool_name=SAFE,
            tool_version="1.0.0",
        )
    )
    done = [x for x in _events("au3") if x.get("event") == "enforcement_completed"]
    assert done and done[0].get("result_status") == "ok" and done[0].get("executor_called") is True


def test_audit_duplicate_suppression_visible(batch_env, monkeypatch):
    _enforce_env(monkeypatch)
    g = _enf.EnforcementGate()
    ctx = RunContext(
        run_id="au4",
        task_id="au4",
        tenant_id="__system__",
        agent="nikhil",
        source_loop="batch_harness",
    )
    kw = {
        "ctx": ctx,
        "batch_run_id": "au4",
        "item_id": "a",
        "item_index": 0,
        "attempt": 0,
        "tool_name": SAFE,
        "tool_version": "1.0.0",
        "item": {"id": "a"},
        "gate": g,
    }
    _run(_enf.enforce_batch_item(**kw))
    _run(_enf.enforce_batch_item(**kw))  # same execution key
    evs = [x.get("event") for x in _events("au4")]
    assert "enforcement_duplicate_suppressed" in evs and _enf._SAFE_CALLS["n"] == 1


def test_audit_shadow_and_enforce_distinguishable(batch_env, monkeypatch):
    _enforce_env(monkeypatch)
    _run(
        run_batch(
            _tripwire_fn,
            [{"id": "a"}],
            ckpt_id="au5",
            agent_id="nikhil",
            tool_name=SAFE,
            tool_version="1.0.0",
        )
    )
    rows = _audit.replay("au5")
    assert all(
        (e.get("extra") or {}).get("mode") == "enforce" for e in rows if e.get("kind") == "enforce"
    )
    assert all(
        (e.get("extra") or {}).get("layer") == "enforcement"
        for e in rows
        if e.get("kind") == "enforce"
    )


def test_audit_no_secrets_in_payload(batch_env, monkeypatch):
    import json as _json

    _enforce_env(monkeypatch)
    _run(
        run_batch(
            _tripwire_fn,
            [{"id": "a"}],
            ckpt_id="au6",
            agent_id="nikhil",
            tool_name=SAFE,
            tool_version="1.0.0",
        )
    )
    blob = _json.dumps(_audit.replay("au6")).lower()
    # secret-VALUE markers (not field-name substrings like "task_id")
    for frag in ("sk_live", "sk-ant", "-----begin", "bearer ey", '"password"'):
        assert frag not in blob
