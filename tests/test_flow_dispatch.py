import asyncio

import app.automation.flow_store as fs
from app.agents import dag_engine, flow_dispatch, process_engine, process_library


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setattr(process_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(process_engine, "_INDEX", str(tmp_path / "runs" / "index.jsonl"))
    monkeypatch.setattr(dag_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(dag_engine, "_INDEX", str(tmp_path / "runs" / "dag_index.jsonl"))
    monkeypatch.setenv("FLOW_RUNNER", "1")

    async def _noop(inputs):
        return {"ok": True, "count": 5, "detail": "stub"}

    monkeypatch.setitem(process_library.EXECUTORS, "scrape", _noop)
    monkeypatch.setitem(process_library.EXECUTORS, "rescore", _noop)
    monkeypatch.setitem(process_library.EXECUTORS, "harvest", _noop)


def test_start_routes_linear_vs_dag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    fs.save_flow(
        {
            "id": "lin",
            "name": "lin",
            "nodes": [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
            "edges": [{"f": "a", "t": "b"}],
        }
    )
    fs.save_flow(
        {
            "id": "dag",
            "name": "dag",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
            ],
            "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
        }
    )
    rl = flow_dispatch.start("flow:lin", {})
    rd = flow_dispatch.start("flow:dag", {})
    assert rl["ok"] and rl["kind"] == "linear"
    assert rd["ok"] and rd["kind"] == "dag"
    assert flow_dispatch.engine_for(rl["run_id"]) is process_engine
    assert flow_dispatch.engine_for(rd["run_id"]) is dag_engine


def test_pre_phase2_run_defaults_linear(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    started = process_engine.start_run("growth_audit", {})
    assert flow_dispatch.engine_for(started["run_id"]) is process_engine


def test_dispatch_replay_advance_dag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    fs.save_flow(
        {
            "id": "dag2",
            "name": "dag2",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
            ],
            "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
        }
    )
    r = flow_dispatch.start("flow:dag2", {})
    rid = r["run_id"]
    for _ in range(10):
        st = flow_dispatch.replay(rid)
        if st["status"] in ("completed", "failed", "waiting_approval"):
            break
        asyncio.run(flow_dispatch.advance(rid))
    assert flow_dispatch.replay(rid)["status"] == "completed"


def test_list_runs_merges_both(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    fs.save_flow(
        {
            "id": "dag3",
            "name": "dag3",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
            ],
            "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
        }
    )
    flow_dispatch.start("flow:dag3", {})
    process_engine.start_run("growth_audit", {})
    runs = flow_dispatch.list_runs(20)
    engines = {r.get("engine") for r in runs}
    assert "dag" in engines and "linear" in engines
