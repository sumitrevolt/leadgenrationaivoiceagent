import asyncio

import app.automation.flow_store as fs
from app.agents import process_engine, process_library


def test_flow_runs_start_to_completion(tmp_path, monkeypatch):
    # isolate stores
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setattr(process_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(process_engine, "_INDEX", str(tmp_path / "runs" / "index.jsonl"))
    monkeypatch.setenv("FLOW_RUNNER", "1")

    async def _noop(inputs):
        return {"ok": True, "count": 5, "detail": "stub"}

    monkeypatch.setitem(process_library.EXECUTORS, "noop", _noop)

    fs.save_flow(
        {
            "id": "e2e",
            "name": "e2e",
            "nodes": [
                {"id": "s", "action": "noop"},
                {"id": "g", "kind": "breakpoint", "question": "ok?"},
                {"id": "s2", "action": "noop"},
            ],
            "edges": [{"f": "s", "t": "g"}, {"f": "g", "t": "s2"}],
        }
    )

    started = process_engine.start_run("flow:e2e", {})
    assert started["ok"]
    rid = started["run_id"]

    # advance to the breakpoint
    asyncio.run(process_engine.advance(rid))
    assert process_engine.replay(rid)["status"] == "waiting_approval"

    # approve + advance to completion
    assert process_engine.approve(rid, "tester")["ok"]
    asyncio.run(process_engine.advance(rid))
    assert process_engine.replay(rid)["status"] == "completed"
