import asyncio

import app.automation.flow_store as fs
from app.agents import dag_engine, process_library


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setattr(dag_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(dag_engine, "_INDEX", str(tmp_path / "runs" / "dag_index.jsonl"))
    monkeypatch.setenv("FLOW_RUNNER", "1")


def _stub_executors(monkeypatch, count_for=None):
    cf = count_for or {}

    def make(name):
        async def _fn(inputs):
            c = cf.get(name, 1)
            return {"ok": True, "count": c, "detail": f"{name}={c}"}

        return _fn

    for nm in ("scrape", "rescore", "harvest", "optimizer", "cadence_run", "revenue_sweep"):
        monkeypatch.setitem(process_library.EXECUTORS, nm, make(nm))


def _run_to_end(rid, n=20):
    for _ in range(n):
        st = dag_engine.replay(rid)
        if st["status"] in ("completed", "failed", "waiting_approval"):
            return st
        asyncio.run(dag_engine.advance(rid))
    return dag_engine.replay(rid)


def test_if_true_branch_runs_false_skipped(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch, count_for={"scrape": 5})  # count>=1 -> true branch
    fs.save_flow(
        {
            "id": "iff",
            "name": "iff",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},  # taken when count>=1
                {"id": "c", "action": "harvest"},
            ],  # taken when count<1
            "edges": [
                {"f": "a", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}},
                {"f": "a", "t": "c", "when": {"field": "count", "op": "<", "value": 1}},
            ],
        }
    )
    started = dag_engine.start_run("flow:iff", {})
    assert started["ok"]
    st = _run_to_end(started["run_id"])
    assert st["status"] == "completed"
    assert st["nodes"]["b"]["state"] == "done"
    assert st["nodes"]["c"]["state"] == "skipped"


def test_parallel_branches_then_merge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch)
    fs.save_flow(
        {
            "id": "par",
            "name": "par",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
                {"id": "m", "kind": "merge", "join": "all"},
                {"id": "d", "action": "optimizer"},
            ],
            "edges": [
                {"f": "a", "t": "b"},
                {"f": "a", "t": "c"},
                {"f": "b", "t": "m"},
                {"f": "c", "t": "m"},
                {"f": "m", "t": "d"},
            ],
        }
    )
    started = dag_engine.start_run("flow:par", {})
    st = _run_to_end(started["run_id"])
    assert st["status"] == "completed"
    for nid in ("a", "b", "c", "m", "d"):
        assert st["nodes"][nid]["state"] == "done", nid


def test_merge_any_completes_on_first(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch, count_for={"scrape": 5})
    fs.save_flow(
        {
            "id": "anyf",
            "name": "anyf",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
                {"id": "m", "kind": "merge", "join": "any"},
            ],
            # only b's in-edge fires (count>=1); c's edge dead (count<1)
            "edges": [
                {"f": "a", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}},
                {"f": "a", "t": "c", "when": {"field": "count", "op": "<", "value": 1}},
                {"f": "b", "t": "m"},
                {"f": "c", "t": "m"},
            ],
        }
    )
    started = dag_engine.start_run("flow:anyf", {})
    st = _run_to_end(started["run_id"])
    assert st["status"] == "completed"
    assert st["nodes"]["m"]["state"] == "done"
    assert st["nodes"]["c"]["state"] == "skipped"


def test_breakpoint_in_branch_pauses_then_resumes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch)
    fs.save_flow(
        {
            "id": "bpf",
            "name": "bpf",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {"id": "g", "kind": "breakpoint", "question": "send?"},
                {"id": "b", "action": "cadence_run"},
            ],
            "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "g"}],
        }
    )  # fan-out -> dag; g is breakpoint
    started = dag_engine.start_run("flow:bpf", {})
    rid = started["run_id"]
    st = _run_to_end(rid)
    assert st["status"] == "waiting_approval"
    assert st["waiting"] == "g"
    assert dag_engine.approve(rid, "tester", node_id="g")["ok"]
    st2 = _run_to_end(rid)
    assert st2["status"] == "completed"
    assert st2["nodes"]["g"]["state"] == "done"


def test_gate_fail_fails_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch, count_for={"scrape": 0})
    fs.save_flow(
        {
            "id": "gf",
            "name": "gf",
            "nodes": [
                {"id": "a", "action": "scrape", "gate": {"min_count": 1}},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
            ],
            "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
        }
    )  # fan-out -> dag
    started = dag_engine.start_run("flow:gf", {})
    st = _run_to_end(started["run_id"])
    assert st["status"] == "failed"


def test_replay_is_pure_repeatable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch, count_for={"scrape": 5})
    fs.save_flow(
        {
            "id": "rep",
            "name": "rep",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
            ],
            "edges": [
                {"f": "a", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}},
                {"f": "a", "t": "c", "when": {"field": "count", "op": "<", "value": 1}},
            ],
        }
    )
    rid = dag_engine.start_run("flow:rep", {})["run_id"]
    _run_to_end(rid)
    s1 = dag_engine.replay(rid)
    s2 = dag_engine.replay(rid)
    assert s1["nodes"] == s2["nodes"] and s1["status"] == s2["status"]
