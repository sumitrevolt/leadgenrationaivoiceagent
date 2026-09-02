import asyncio

import app.automation.flow_store as fs
from app.agents import dag_engine, process_library


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setattr(dag_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(dag_engine, "_INDEX", str(tmp_path / "runs" / "dag_index.jsonl"))
    monkeypatch.setenv("FLOW_RUNNER", "1")


# ---- _resolve_inputs unit ----


def test_resolve_inputs_source_pull():
    nodes = {"a": {"state": "done", "result": {"ok": True, "count": 7, "detail": "seven"}}}
    node = {"id": "b", "action": "x", "inputs_map": {"leads": {"from": "a", "key": "detail"}}}
    eff = dag_engine._resolve_inputs(node, {"batch": 3}, nodes)
    assert eff["leads"] == "seven" and eff["batch"] == 3


def test_resolve_inputs_literal():
    node = {"id": "b", "inputs_map": {"client_id": {"value": "acme"}}}
    eff = dag_engine._resolve_inputs(node, {}, {})
    assert eff["client_id"] == "acme"


def test_resolve_inputs_missing_source_fail_closed():
    node = {"id": "b", "inputs_map": {"leads": {"from": "a", "key": "detail"}}}
    eff = dag_engine._resolve_inputs(node, {"x": 1}, {})
    assert "leads" not in eff and eff["x"] == 1  # omitted, not garbage


def test_resolve_inputs_not_done_fail_closed():
    nodes = {"a": {"state": "running", "result": None}}
    node = {"id": "b", "inputs_map": {"leads": {"from": "a", "key": "detail"}}}
    eff = dag_engine._resolve_inputs(node, {}, nodes)
    assert "leads" not in eff


def test_resolve_inputs_no_map_is_passthrough():
    eff = dag_engine._resolve_inputs({"id": "b"}, {"x": 1}, {})
    assert eff == {"x": 1}


# ---- e2e: downstream reads upstream output ----


def test_e2e_downstream_reads_upstream_output(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    received: dict = {}

    async def src(inputs):
        return {"ok": True, "count": 7, "detail": "seven"}

    async def sink(inputs):
        received.update(inputs)
        return {"ok": True, "count": 1, "detail": "done"}

    monkeypatch.setitem(process_library.EXECUTORS, "scrape", src)
    monkeypatch.setitem(process_library.EXECUTORS, "crm_queue", sink)
    fs.save_flow(
        {
            "id": "dp",
            "name": "dp",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {
                    "id": "b",
                    "action": "crm_queue",
                    "inputs_map": {
                        "leads": {"from": "a", "key": "detail"},
                        "tag": {"value": "vip"},
                    },
                },
            ],
            "edges": [{"f": "a", "t": "b"}],
        }
    )
    rid = dag_engine.start_run("flow:dp", {"run_level": "yes"})["run_id"]
    for _ in range(10):
        st = dag_engine.replay(rid)
        if st["status"] in ("completed", "failed"):
            break
        asyncio.run(dag_engine.advance(rid))
    assert dag_engine.replay(rid)["status"] == "completed"
    assert received.get("leads") == "seven"  # upstream output passed downstream
    assert received.get("tag") == "vip"  # literal injected
    assert received.get("run_level") == "yes"  # run-level inputs still present
