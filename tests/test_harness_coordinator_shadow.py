"""Coordinator shadow tests (record-only, third real loop).

Standalone tests exercise the coordinator adapter + Harness.observe with no app
deps. The final test drives the REAL coordinator.coordinate() entry through its
_run_agent normalized-action boundary (skipped where the app isn't importable).
"""

import json

import pytest

from app.agents.harness.adapters import observe_coordinator_action, shadow_loop_eligible


def _env(mp, agents="kavya", loops="coordinator", harness="1", shadowf="1", enforce="0"):
    mp.setenv("AGENT_HARNESS", harness)
    mp.setenv("AGENT_HARNESS_SHADOW", shadowf)
    mp.setenv("AGENT_HARNESS_ENFORCE", enforce)
    mp.setenv("AGENT_HARNESS_CANARY_AGENTS", agents)
    mp.setenv("AGENT_HARNESS_CANARY_LOOPS", loops)


def _obs(**kw):
    base = {
        "coordinator_run_id": "coord_abc",
        "orchestration_path": "coordinate",
        "action_index": 0,
        "agent_id": "kavya",
        "tenant_id": "",
        "normalized_action": {"tool": "kavya", "task": "health"},
        "actual_executor": "run_ops",
        "actual_result": {"ok": True},
        "latency_ms": 7,
    }
    base.update(kw)
    return observe_coordinator_action(**base)


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


def test_kavya_coordinator_eligible(monkeypatch):
    _env(monkeypatch)
    assert shadow_loop_eligible("kavya", "coordinator") is True
    assert _obs() is not None


def test_peer_ineligible(monkeypatch):
    _env(monkeypatch)
    assert _obs(agent_id="manager") is None


def test_wrong_loop(monkeypatch):
    _env(monkeypatch, loops="dag_engine")
    assert _obs() is None


def test_enforce_on(monkeypatch):
    _env(monkeypatch, enforce="1")
    assert _obs() is None


# ---- result / parse / delegation verdicts ---------------------------
def test_success_match(monkeypatch):
    _env(monkeypatch)
    rec = _obs()
    assert rec["comparison_verdict"] == "MATCH"
    assert rec["predicted_lane"] == "GREEN" and rec["enforcement"] is False
    assert rec["orchestration_path"] == "coordinate" and rec["action_index"] == 0
    assert rec["shadow_run_id"] == "shadow:coord_abc:coordinate:0"
    assert rec["parser_confidence"] == "HEURISTIC"  # honest default
    assert rec["actual_executor"] == "run_ops"


def test_legacy_error(monkeypatch):
    _env(monkeypatch)
    rec = _obs(actual_result=None, actual_error="tool blew up")
    assert rec["comparison_verdict"] == "LEGACY_ERROR"
    assert rec["legacy_error"] == "tool blew up"


def test_fallback_observed(monkeypatch):
    _env(monkeypatch)
    rec = _obs(fallback_used=True)
    assert rec["comparison_verdict"] == "FALLBACK_OBSERVED"
    assert rec["fallback_used"] is True


def test_delegation_observed(monkeypatch):
    _env(monkeypatch)
    rec = _obs(delegated_agent="nikhil", parent_run_id="coord_abc")
    assert rec["comparison_verdict"] == "DELEGATION_OBSERVED"
    assert rec["delegated_agent"] == "nikhil"
    assert rec["parent_run_id"] == "coord_abc"


def test_parser_ambiguity(monkeypatch):
    _env(monkeypatch)
    rec = _obs(execution_metadata={"parser_confidence": "FAILED"})
    assert rec["comparison_verdict"] == "PARSER_AMBIGUITY"


def test_action_index_distinct_refs(monkeypatch):
    _env(monkeypatch)
    r0 = _obs(action_index=0)
    r1 = _obs(action_index=1)
    assert r0["shadow_run_id"] == "shadow:coord_abc:coordinate:0"
    assert r1["shadow_run_id"] == "shadow:coord_abc:coordinate:1"
    assert r0["run_id"] == r1["run_id"] == "coord_abc"


# ---- privacy / raw response -----------------------------------------
def test_raw_response_hash_bounded(monkeypatch):
    _env(monkeypatch)
    # hash only, no prose (fake test fixture)
    rec = _obs(raw_response_hash="abc123deadbeef")  # pragma: allowlist secret
    assert rec["raw_response_hash"] == "abc123deadbeef"  # pragma: allowlist secret


def test_secret_redacted(monkeypatch):
    _env(monkeypatch)
    rec = _obs(actual_result={"api_key": "sk_live_X", "ok": True})
    blob = json.dumps(rec)
    assert "sk_live_X" not in blob and "REDACTED" in blob


def test_shadow_failure_swallowed(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(
        "app.agents.harness.loop.Harness.observe",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert _obs() is None


# ---- explainability --------------------------------------------------
def test_explainable(monkeypatch, tmp_path):
    _env(monkeypatch)
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _obs(coordinator_run_id="coordE")
    ev = audit.replay("coordE")[-1]["extra"]
    assert ev["source_loop"] == "coordinator"
    assert ev["orchestration_path"] == "coordinate"
    assert ev["parser_type"] == "_extract_list" and ev["parser_confidence"] == "HEURISTIC"
    assert ev["normalized_tool"] == "kavya" and ev["actual_executor"] == "run_ops"
    assert ev["comparison_verdict"] == "MATCH" and ev["stop_decision"] == "continue"
    assert ev["enforcement"] is False


# ---- REAL coordinator integration (skips without app) ---------------
def test_real_coordinate_shadow(monkeypatch, tmp_path):
    coord = pytest.importorskip("app.agents.coordinator")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "runs.jsonl"))
    _env(monkeypatch)  # canary agent kavya (the genuine delegated identity)

    async def fake_plan(goal, max_steps=5, hint=""):
        return [{"agent": "kavya", "task": "internal health synthesis"}]

    async def fake_llm(system, user, max_tokens=260, temperature=0.4):
        return ("boss summary", "fixture")

    calls = {"n": 0}

    async def fake_kavya(task, goal):
        calls["n"] += 1
        return {"tool": "run_ops", "result": {"ok": True}}

    monkeypatch.setattr(coord, "plan", fake_plan)
    monkeypatch.setattr(coord, "_llm", fake_llm)
    monkeypatch.setitem(coord._TOOLS, "kavya", fake_kavya)

    import asyncio

    out = asyncio.run(coord.coordinate("internal health check", execute=True, max_steps=1))
    assert out["ok"] is True
    assert calls["n"] == 1  # legacy action executed EXACTLY once

    rows = [json.loads(x) for x in open(tmp_path / "runs.jsonl", encoding="utf-8")]
    coord_rows = [
        r
        for r in rows
        if r.get("kind") == "shadow"
        and r["extra"].get("source_loop") == "coordinator"
        and r["extra"].get("agent") == "kavya"
    ]
    assert len(coord_rows) == 1  # one action -> one record
    ex = coord_rows[0]["extra"]
    assert ex["comparison_verdict"] == "MATCH" and ex["enforcement"] is False
    assert ex["orchestration_path"] == "coordinate" and ex["actual_executor"] == "run_ops"
