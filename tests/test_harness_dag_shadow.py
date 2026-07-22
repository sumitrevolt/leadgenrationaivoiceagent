"""DAG-engine shadow tests (record-only, second real loop).

Standalone tests exercise the DAG adapter + Harness.observe with no app deps.
The final test drives the REAL dag_engine.advance() executor path (skipped where
the app isn't importable).
"""

import json
import os

import pytest

from app.agents.harness.adapters import observe_dag_action, shadow_eligible, shadow_loop_eligible


def _env(mp, agents="nikhil", loops="dag_engine", harness="1", shadowf="1", enforce="0"):
    mp.setenv("AGENT_HARNESS", harness)
    mp.setenv("AGENT_HARNESS_SHADOW", shadowf)
    mp.setenv("AGENT_HARNESS_ENFORCE", enforce)
    mp.setenv("AGENT_HARNESS_CANARY_AGENTS", agents)
    mp.setenv("AGENT_HARNESS_CANARY_LOOPS", loops)


def _obs(**kw):
    base = {
        "dag_run_id": "dr1",
        "node_id": "A",
        "attempt": 0,
        "agent_id": "nikhil",
        "tenant_id": "",
        "tool_name": "dag.noop",
        "arguments": {},
        "actual_result": {"ok": True},
        "latency_ms": 5,
        "dag_node_status": "completed",
    }
    base.update(kw)
    return observe_dag_action(**base)


# ---- eligibility -----------------------------------------------------
def test_all_off_no_record(monkeypatch):
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


def test_empty_agent_allowlist(monkeypatch):
    _env(monkeypatch, agents="")
    assert _obs() is None


def test_empty_loop_allowlist(monkeypatch):
    _env(monkeypatch, loops="")
    assert shadow_loop_eligible("nikhil", "dag_engine") is False
    assert _obs() is None


def test_nikhil_dag_eligible(monkeypatch):
    _env(monkeypatch)
    assert shadow_loop_eligible("nikhil", "dag_engine") is True
    assert _obs() is not None


def test_peer_agent_ineligible(monkeypatch):
    _env(monkeypatch)
    assert _obs(agent_id="manager") is None


def test_wrong_loop_ineligible(monkeypatch):
    _env(monkeypatch, loops="coordinator")
    assert shadow_loop_eligible("nikhil", "dag_engine") is False
    assert _obs() is None


def test_enforce_on_ineligible(monkeypatch):
    _env(monkeypatch, enforce="1")
    assert _obs() is None


# ---- success / error / retry ----------------------------------------
def test_success_record_match(monkeypatch):
    _env(monkeypatch)
    rec = _obs()
    assert rec["comparison_verdict"] == "MATCH"
    assert rec["dag_node_status"] == "completed"
    assert rec["predicted_lane"] == "GREEN"
    assert rec["would_require_approval"] is False


def test_failed_node_bounded_error(monkeypatch):
    _env(monkeypatch)
    rec = _obs(actual_result=None, actual_error="gate: min_count", dag_node_status="failed")
    assert rec["comparison_verdict"] == "LEGACY_ERROR"
    assert rec["legacy_error"] == "gate: min_count"


def test_retry_distinct_attempt_refs(monkeypatch):
    _env(monkeypatch)
    r0 = _obs(
        attempt=0,
        actual_result=None,
        actual_error="gate fail",
        dag_node_status="retry_pending",
        retry_scheduled=True,
    )
    r1 = _obs(
        attempt=1,
        actual_result=None,
        actual_error="gate fail",
        dag_node_status="retry_pending",
        retry_scheduled=True,
    )
    assert r0["comparison_verdict"] == "RETRY_OBSERVED"
    assert r0["shadow_run_id"] == "shadow:dr1:A:0"
    assert r1["shadow_run_id"] == "shadow:dr1:A:1"
    assert r0["shadow_run_id"] != r1["shadow_run_id"]
    assert r0["run_id"] == r1["run_id"] == "dr1"  # same DAG run


def test_shadow_failure_swallowed(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(
        "app.agents.harness.loop.Harness.observe",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert _obs() is None  # never raises into the DAG


# ---- identity / privacy ---------------------------------------------
def test_correlation_preserved(monkeypatch):
    _env(monkeypatch)
    rec = _obs(dag_run_id="drX", node_id="N7", attempt=2)
    assert rec["dag_run_id"] == "drX" and rec["node_id"] == "N7" and rec["attempt"] == 2
    assert rec["shadow_run_id"] == "shadow:drX:N7:2"
    assert rec["source_loop"] == "dag_engine"


def test_agent_and_tenant(monkeypatch):
    _env(monkeypatch)
    assert _obs()["agent"] == "nikhil"
    assert _obs()["tenant_id"] == "__system__"  # default system scope
    assert _obs(tenant_id="client:acme")["tenant_id"] == "client:acme"  # preserved


def test_secret_redacted_and_bounded(monkeypatch):
    _env(monkeypatch)
    big = {"api_key": "sk_live_SECRET", "blob": "x" * 5000, "ok": True}  # pragma: allowlist secret
    rec = _obs(actual_result=big)
    blob = json.dumps(rec)
    assert "sk_live_SECRET" not in blob and "REDACTED" in blob
    assert len(rec["legacy_result_summary"]) <= 620  # bounded


# ---- explainability --------------------------------------------------
def test_explainable(monkeypatch, tmp_path):
    _env(monkeypatch)
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _obs(dag_run_id="drE", node_id="A", attempt=0)
    events = audit.replay("drE")
    assert events
    ev = events[-1]["extra"]
    assert ev["source_loop"] == "dag_engine" and ev["node_id"] == "A" and ev["attempt"] == 0
    assert ev["comparison_verdict"] == "MATCH"
    assert ev["predicted_lane"] == "GREEN" and ev["stop_decision"] == "continue"
    assert ev["enforcement"] is False


# ---- REAL dag_engine.advance integration (skips without app) ---------
def test_real_dag_advance_shadow(monkeypatch, tmp_path):
    dag = pytest.importorskip("app.agents.dag_engine")
    plib = pytest.importorskip("app.agents.process_library")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _env(monkeypatch)

    # isolate journal dir to a temp location
    runs_dir = tmp_path / "process_runs"
    runs_dir.mkdir()
    monkeypatch.setattr(dag, "_RUNS_DIR", str(runs_dir))
    monkeypatch.setattr(dag, "_INDEX", str(runs_dir / "dag_index.jsonl"))

    calls = {"n": 0}

    async def fake_step(node, inputs):
        calls["n"] += 1
        return {"ok": True, "count": 1, "detail": "fixture"}

    monkeypatch.setattr(plib, "execute_step", fake_step)
    monkeypatch.setattr(plib, "check_gate", lambda node, result: (bool(result.get("ok")), ""))

    # seed a real run journal: single task node "A" under nikhil identity
    run_id = "dr_test_1"
    graph = {"nodes": {"A": {"kind": "task", "action": "noop"}}, "in": {}, "out": {}}
    dag._append_event(
        run_id,
        "run_started",
        {
            "process": "flow:test",
            "engine": "dag",
            "graph": graph,
            "inputs": {"_harness_agent_id": "nikhil"},
        },
    )

    import asyncio

    out = asyncio.run(dag.advance(run_id))
    assert out["status"] == dag.ST_COMPLETED
    assert calls["n"] == 1  # real node executed EXACTLY once

    journal = dag.journal(run_id)
    completed = [e for e in journal if e["type"] == "node_completed"]
    assert len(completed) == 1  # no duplicate journal entry

    rows = [json.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    dag_shadow = [
        r
        for r in rows
        if r.get("kind") == "shadow"
        and r["extra"].get("source_loop") == "dag_engine"
        and r["extra"].get("node_id") == "A"
    ]
    assert len(dag_shadow) == 1  # exactly one shadow record
    ex = dag_shadow[0]["extra"]
    assert ex["agent"] == "nikhil" and ex["dag_run_id"] == run_id
    assert ex["comparison_verdict"] == "MATCH" and ex["enforcement"] is False
