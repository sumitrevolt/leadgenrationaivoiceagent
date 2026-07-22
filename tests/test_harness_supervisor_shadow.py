"""Supervisor-family shadow tests (record-only, fourth loop).

Standalone tests exercise the supervisor adapter + Harness.observe with no app
deps. The final test drives the REAL supervisor LangGraph (supervisor.py)
through run_supervisor_task (skipped where langgraph/app isn't importable).
"""

import json

import pytest

from app.agents.harness.adapters import (
    observe_supervisor_action,
    shadow_loop_eligible,
    supervisor_shadow,
)


def _env(mp, agents="rohan", loops="supervisor", harness="1", shadowf="1", enforce="0"):
    mp.setenv("AGENT_HARNESS", harness)
    mp.setenv("AGENT_HARNESS_SHADOW", shadowf)
    mp.setenv("AGENT_HARNESS_ENFORCE", enforce)
    mp.setenv("AGENT_HARNESS_CANARY_AGENTS", agents)
    mp.setenv("AGENT_HARNESS_CANARY_LOOPS", loops)


def _obs(**kw):
    base = {
        "supervisor_run_id": "sup1",
        "graph_run_id": "g1",
        "graph_step": 1,
        "tool_call_id": None,
        "supervisor_implementation": "supervisor",
        "actor_id": "manager",
        "delegated_agent_id": "rohan",
        "tenant_id": "",
        "tool_name": "leads_agent",
        "tool_arguments": {"task": "x"},
        "actual_executor": "leads_agent_node",
        "actual_result": {"route": "leads_agent"},
        "latency_ms": 9,
    }
    base.update(kw)
    return observe_supervisor_action(**base)


def setup_function(_):
    supervisor_shadow._SEEN.clear()  # reset dedup between tests


# ---- eligibility -----------------------------------------------------
def test_all_off(monkeypatch):
    for k in (
        "AGENT_HARNESS",
        "AGENT_HARNESS_SHADOW",
        "AGENT_HARNESS_ENFORCE",
        "AGENT_HARNESS_CANARY_AGENTS",
        "AGENT_HARNESS_CANARY_LOOPS",
    ):
        monkeypatch.delenv(k, raising=False)
    assert _obs() is None


def test_shadow_off(monkeypatch):
    _env(monkeypatch, shadowf="0")
    assert _obs() is None


def test_empty_agent(monkeypatch):
    _env(monkeypatch, agents="")
    assert _obs() is None


def test_empty_loop(monkeypatch):
    _env(monkeypatch, loops="")
    assert _obs() is None


def test_delegated_agent_eligible(monkeypatch):
    _env(monkeypatch)
    assert shadow_loop_eligible("rohan", "supervisor") is True
    assert _obs() is not None


def test_peer_ineligible(monkeypatch):
    _env(monkeypatch)
    assert _obs(delegated_agent_id="swara") is None


def test_wrong_loop(monkeypatch):
    _env(monkeypatch, loops="coordinator")
    assert _obs() is None


def test_enforce_on(monkeypatch):
    _env(monkeypatch, enforce="1")
    assert _obs() is None


def test_manager_actor_not_eligible_alone(monkeypatch):
    # Actor is manager, delegated agent is a peer NOT in canary -> ineligible.
    _env(monkeypatch, agents="rohan")
    assert _obs(actor_id="manager", delegated_agent_id="manager") is None


# ---- result / identity ----------------------------------------------
def test_success_match(monkeypatch):
    _env(monkeypatch)
    rec = _obs()
    assert rec["comparison_verdict"] == "MATCH"
    # rohan delegation is now canonically AMBER (agent.delegate.rohan = outreach);
    # registry authoritative. Execution layer still MATCH (would_allow True).
    assert rec["predicted_lane"] == "AMBER" and rec["enforcement"] is False
    assert rec["registry_comparison"] == "REGISTRY_MATCH"
    assert rec["registry_risk_class"] == "AMBER"
    assert rec["supervisor_implementation"] == "supervisor"
    assert rec["graph_run_id"] == "g1" and rec["graph_step"] == 1
    assert rec["shadow_run_id"] == "shadow:g1:1:0"
    assert rec["actor_id"] == "manager" and rec["delegated_agent"] == "rohan"


def test_legacy_error(monkeypatch):
    _env(monkeypatch)
    rec = _obs(actual_result=None, actual_error="node blew up")
    assert rec["comparison_verdict"] == "LEGACY_ERROR"
    assert rec["legacy_error"] == "node blew up"


def test_tenant_preserved(monkeypatch):
    _env(monkeypatch)
    assert _obs(graph_run_id="ta")["tenant_id"] == "__system__"
    assert _obs(graph_run_id="tb", tenant_id="client:jiya")["tenant_id"] == "client:jiya"


def test_secret_redacted_bounded(monkeypatch):
    _env(monkeypatch)
    rec = _obs(actual_result={"api_key": "sk_live_Z", "blob": "y" * 5000})
    blob = json.dumps(rec)
    assert "sk_live_Z" not in blob and "REDACTED" in blob
    assert len(rec["legacy_result_summary"]) <= 620


# ---- replay / dedup --------------------------------------------------
def test_dedup_same_toolcall(monkeypatch):
    _env(monkeypatch)
    r0 = _obs(tool_call_id="call_abc", attempt=0)
    r1 = _obs(tool_call_id="call_abc", attempt=0)  # duplicate callback
    assert r0 is not None and r1 is None  # second suppressed


def test_retry_distinct_attempt(monkeypatch):
    _env(monkeypatch)
    r0 = _obs(tool_call_id="call_abc", attempt=0)
    r1 = _obs(tool_call_id="call_abc", attempt=1)  # genuine retry
    assert r0["shadow_run_id"] == "shadow:g1:1:call_abc"
    assert r1["shadow_run_id"] == "shadow:g1:1:call_abc"  # keyed by tool_call_id
    assert r0 is not None and r1 is not None  # distinct attempts both recorded


# ---- explainability --------------------------------------------------
def test_explainable(monkeypatch, tmp_path):
    _env(monkeypatch)
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _obs(supervisor_run_id="supE", graph_run_id="supE")
    ev = audit.replay("supE")[-1]["extra"]
    assert ev["source_loop"] == "supervisor"
    assert ev["supervisor_implementation"] == "supervisor" and ev["graph_step"] == 1
    assert ev["parent_action_id"] == "supE:1"
    assert ev["comparison_verdict"] == "MATCH" and ev["stop_decision"] == "continue"
    assert ev["enforcement"] is False


# ---- REAL supervisor graph integration (skips without langgraph) -----
def test_real_supervisor_graph(monkeypatch, tmp_path):
    sup = pytest.importorskip("app.agents.supervisor")
    if not getattr(sup, "AGENTS_AVAILABLE", False):
        pytest.skip("langgraph not available")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _env(monkeypatch, agents="rohan")  # leads route -> delegated worker 'rohan'

    # force keyword router (no network) + fixture the leaf LLM brain (safe)
    async def _boom(*a, **k):
        raise RuntimeError("no llm")

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _boom, raising=False)

    calls = {"n": 0}

    class FakeBrain:
        async def generate_response(self, **kw):
            calls["n"] += 1
            return "safe leads plan"

    monkeypatch.setattr(sup, "_llm_brain", lambda: FakeBrain())

    import asyncio

    out = asyncio.run(sup.run_supervisor_task("qualify leads and plan outreach campaign"))
    assert out["route"] == "leads_agent"
    assert calls["n"] == 1  # real node executed EXACTLY once

    rows = [json.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    sup_rows = [
        r
        for r in rows
        if r.get("kind") == "shadow"
        and r["extra"].get("source_loop") == "supervisor"
        and r["extra"].get("delegated_agent") == "rohan"
    ]
    assert len(sup_rows) == 1
    ex = sup_rows[0]["extra"]
    assert ex["comparison_verdict"] == "MATCH" and ex["enforcement"] is False
    assert ex["supervisor_implementation"] == "supervisor" and ex["actor_id"] == "manager"
