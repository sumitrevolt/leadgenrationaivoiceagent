"""Batch-harness shadow tests (record-only, fifth/final loop).

Standalone tests exercise the batch adapter + Harness.observe with no app deps.
The final test drives the REAL batch_harness.run_batch (skipped without the app).
"""

import asyncio
import json

import pytest

from app.agents.harness.adapters import batch_shadow, observe_batch_item, shadow_loop_eligible


def _env(mp, agents="nikhil", loops="batch_harness", harness="1", shadowf="1", enforce="0"):
    mp.setenv("AGENT_HARNESS", harness)
    mp.setenv("AGENT_HARNESS_SHADOW", shadowf)
    mp.setenv("AGENT_HARNESS_ENFORCE", enforce)
    mp.setenv("AGENT_HARNESS_CANARY_AGENTS", agents)
    mp.setenv("AGENT_HARNESS_CANARY_LOOPS", loops)


def _obs(**kw):
    base = {
        "batch_run_id": "b1",
        "batch_name": "proof",
        "item_id": "item_0",
        "item_index": 0,
        "attempt": 0,
        "agent_id": "nikhil",
        "tenant_id": "",
        "operation_name": "calc",
        "actual_executor": "calc",
        "actual_result": {"ok": True},
        "latency_ms": 4,
        "checkpoint_state": "completed",
        "resumed": False,
    }
    base.update(kw)
    return observe_batch_item(**base)


def setup_function(_):
    batch_shadow._SEEN.clear()


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


def test_eligible(monkeypatch):
    _env(monkeypatch)
    assert shadow_loop_eligible("nikhil", "batch_harness") is True
    assert _obs() is not None


def test_peer_ineligible(monkeypatch):
    _env(monkeypatch)
    assert _obs(agent_id="manager") is None


def test_wrong_loop(monkeypatch):
    _env(monkeypatch, loops="supervisor")
    assert _obs() is None


def test_enforce_on(monkeypatch):
    _env(monkeypatch, enforce="1")
    assert _obs() is None


# ---- result / identity ----------------------------------------------
def test_success_match(monkeypatch):
    _env(monkeypatch)
    rec = _obs()
    assert rec["comparison_verdict"] == "MATCH" and rec["enforcement"] is False
    assert rec["predicted_lane"] == "GREEN"
    assert rec["batch_run_id"] == "b1" and rec["item_id"] == "item_0" and rec["item_index"] == 0
    assert rec["operation_name"] == "calc" and rec["checkpoint_state"] == "completed"
    assert rec["shadow_run_id"] == "shadow:b1:item_0:0"


def test_legacy_error(monkeypatch):
    _env(monkeypatch)
    rec = _obs(actual_result=None, actual_error="boom", checkpoint_state="failed")
    assert rec["comparison_verdict"] == "LEGACY_ERROR" and rec["legacy_error"] == "boom"


def test_anonymous_op_missing_context(monkeypatch):
    _env(monkeypatch)
    rec = _obs(operation_name="<lambda>")
    assert rec["comparison_verdict"] == "MISSING_CONTEXT"


def test_tenant_and_bounds(monkeypatch):
    _env(monkeypatch)
    assert _obs(item_id="ta")["tenant_id"] == "__system__"
    assert _obs(item_id="tb", tenant_id="client:x")["tenant_id"] == "client:x"
    rec = _obs(item_id="tc", actual_result={"api_key": "sk_live_Q", "blob": "z" * 5000})
    blob = json.dumps(rec)
    assert (
        "sk_live_Q" not in blob and "REDACTED" in blob and len(rec["legacy_result_summary"]) <= 620
    )


# ---- resume / dedup --------------------------------------------------
def test_resume_skip_is_diagnostic_not_action(monkeypatch, tmp_path):
    _env(monkeypatch)
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "r.jsonl"))
    assert _obs(resumed=True, batch_run_id="rb") is None  # no action record
    rows = [json.loads(x) for x in open(tmp_path / "r.jsonl", encoding="utf-8")]
    diags = [r for r in rows if r.get("kind") == "shadow_resume_skip"]
    assert len(diags) == 1 and diags[0]["extra"]["comparison_verdict"] == "RESUME_SKIPPED"
    assert not [r for r in rows if r.get("kind") == "shadow"]  # no executed-action record


def test_dedup_duplicate_callback(monkeypatch, tmp_path):
    _env(monkeypatch)
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "r.jsonl"))
    r0 = _obs(batch_run_id="db", item_id="i", attempt=0)
    r1 = _obs(batch_run_id="db", item_id="i", attempt=0)  # duplicate callback
    assert r0 is not None and r1 is None
    rows = [json.loads(x) for x in open(tmp_path / "r.jsonl", encoding="utf-8")]
    assert [r for r in rows if r.get("kind") == "shadow_dedup"]


def test_retry_distinct_attempt(monkeypatch):
    _env(monkeypatch)
    r0 = _obs(item_id="i", attempt=0)
    r1 = _obs(item_id="i", attempt=1)
    assert r0["shadow_run_id"] == "shadow:b1:i:0" and r1["shadow_run_id"] == "shadow:b1:i:1"


def test_distinct_items_same_args(monkeypatch):
    _env(monkeypatch)
    r0 = _obs(item_id="i0", operation_arguments={"x": 1})
    r1 = _obs(item_id="i1", operation_arguments={"x": 1})  # identical args, different item
    assert r0 is not None and r1 is not None  # both recorded


# ---- concurrency-safe audit -----------------------------------------
def test_concurrent_writes_valid(monkeypatch, tmp_path):
    _env(monkeypatch)
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "r.jsonl"))

    async def one(i):
        return _obs(batch_run_id="cc", item_id=f"i{i}", item_index=i)

    async def go():
        return await asyncio.gather(*(one(i) for i in range(25)))

    recs = asyncio.run(go())
    assert all(r is not None for r in recs)
    lines = open(tmp_path / "r.jsonl", encoding="utf-8").read().splitlines()
    parsed = [json.loads(x) for x in lines]  # no corrupt/interleaved lines
    shadows = [r for r in parsed if r.get("kind") == "shadow"]
    assert len(shadows) == 25  # no lost records


# ---- explainability --------------------------------------------------
def test_explainable(monkeypatch, tmp_path):
    _env(monkeypatch)
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "r.jsonl"))
    _obs(batch_run_id="be", item_id="i7", item_index=7)
    ev = audit.replay("be")[-1]["extra"]
    assert ev["source_loop"] == "batch_harness" and ev["item_id"] == "i7" and ev["item_index"] == 7
    assert ev["operation_name"] == "calc" and ev["checkpoint_state"] == "completed"
    assert ev["comparison_verdict"] == "MATCH" and ev["enforcement"] is False


# ---- REAL run_batch integration (skips without app) -----------------
def test_real_run_batch(monkeypatch, tmp_path):
    bh = pytest.importorskip("app.agents.batch_harness")
    from app.agents.harness import audit

    monkeypatch.setattr(audit, "_RUN_LOG", str(tmp_path / "r.jsonl"))
    monkeypatch.setattr(bh, "_DIR", str(tmp_path / "batch_runs"))
    _env(monkeypatch)

    calls = {}

    async def safe_calc(item):
        calls[item["id"]] = calls.get(item["id"], 0) + 1
        if item.get("boom"):
            raise RuntimeError("intended fail")
        return {"ok": True, "summary": f"len={len(item['id'])}"}

    items = [{"id": f"item_{i}"} for i in range(4)] + [{"id": "item_bad", "boom": True}]
    out = asyncio.run(
        bh.run_batch(safe_calc, items, concurrency=3, ckpt_id="t1", agent_id="nikhil")
    )
    assert out["done"] == 4 and out["failed"] == 1
    assert all(v == 1 for v in calls.values())  # each item executed exactly once

    rows = [json.loads(x) for x in open(tmp_path / "r.jsonl", encoding="utf-8")]
    actions = [
        r
        for r in rows
        if r.get("kind") == "shadow" and r["extra"].get("source_loop") == "batch_harness"
    ]
    assert len(actions) == 5  # 4 ok + 1 error, one per attempt
    verds = sorted(r["extra"]["comparison_verdict"] for r in actions)
    assert verds.count("MATCH") == 4 and verds.count("LEGACY_ERROR") == 1

    # resume: rerun same ckpt -> legacy skips all; no new action records, 5 resume diagnostics
    before = len(actions)
    calls.clear()
    out2 = asyncio.run(
        bh.run_batch(safe_calc, items, concurrency=3, ckpt_id="t1", agent_id="nikhil")
    )
    assert out2["skipped"] == 5 and calls == {}  # legacy re-ran nothing
    rows2 = [json.loads(x) for x in open(tmp_path / "r.jsonl", encoding="utf-8")]
    actions2 = [
        r
        for r in rows2
        if r.get("kind") == "shadow" and r["extra"].get("source_loop") == "batch_harness"
    ]
    skips = [r for r in rows2 if r.get("kind") == "shadow_resume_skip"]
    assert len(actions2) == before and len(skips) == 5  # no new actions; 5 resume diagnostics
