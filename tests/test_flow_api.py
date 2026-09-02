import asyncio

import app.automation.flow_store as fs
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch, flag="1"):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    if flag is None:
        monkeypatch.delenv("FLOW_RUNNER", raising=False)
    else:
        monkeypatch.setenv("FLOW_RUNNER", flag)
    from app.api import auth_deps
    from app.main import app

    app.dependency_overrides[auth_deps.require_admin] = lambda: type("U", (), {"email": "t@t"})()
    return TestClient(app)


def test_flag_off_503(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, flag=None)
    assert c.get("/api/growth/flows").status_code == 503


def test_create_get_delete(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/growth/flow",
        json={"name": "Demo", "nodes": [{"id": "a", "action": "scrape"}], "edges": []},
    )
    assert r.status_code == 200 and r.json()["runnable"] is True
    fid = r.json()["flow"]["id"]
    assert c.get(f"/api/growth/flow/{fid}").json()["runnable"] is True
    assert c.delete(f"/api/growth/flow/{fid}").json()["ok"] is True


def test_invalid_flow_reports_compile_errors(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/growth/flow",
        json={"name": "Bad", "nodes": [{"id": "a", "action": "nope"}], "edges": []},
    )
    assert r.status_code == 200 and r.json()["runnable"] is False
    assert r.json()["compile_errors"]


def test_flow_trigger_persists_through_api(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/growth/flow",
        json={
            "name": "Cron",
            "nodes": [{"id": "a", "action": "scrape"}],
            "edges": [],
            "trigger": {"type": "cron", "cron": "*/30 * * * *"},
        },
    )
    assert r.status_code == 200 and r.json()["runnable"] is True
    fid = r.json()["flow"]["id"]
    got = c.get(f"/api/growth/flow/{fid}").json()
    assert got["flow"]["trigger"] == {"type": "cron", "cron": "*/30 * * * *"}


def test_dag_flow_runs_through_api(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)  # FLOW_RUNNER=1, admin bypassed
    # isolate engine journals so the test worker doesn't enqueue real Celery
    from app.agents import dag_engine, flow_dispatch, process_engine, process_library

    monkeypatch.setattr(process_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(process_engine, "_INDEX", str(tmp_path / "runs" / "index.jsonl"))
    monkeypatch.setattr(dag_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(dag_engine, "_INDEX", str(tmp_path / "runs" / "dag_index.jsonl"))

    async def _noop(inputs):
        return {"ok": True, "count": 5, "detail": "stub"}

    for nm in ("scrape", "rescore", "harvest"):
        monkeypatch.setitem(process_library.EXECUTORS, nm, _noop)

    r = c.post(
        "/api/growth/flow",
        json={
            "name": "Dag",
            "nodes": [
                {"id": "a", "action": "scrape"},
                {"id": "b", "action": "rescore"},
                {"id": "c", "action": "harvest"},
            ],
            "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
        },
    )
    assert r.status_code == 200 and r.json()["runnable"] is True
    fid = r.json()["flow"]["id"]

    started = c.post(
        "/api/growth/process/start", json={"process": "flow:" + fid, "inputs": {}}
    ).json()
    assert started.get("ok") and started.get("kind") == "dag"
    rid = started["run_id"]

    for _ in range(10):
        st = flow_dispatch.replay(rid)
        if st["status"] in ("completed", "failed"):
            break
        asyncio.run(flow_dispatch.advance(rid))

    detail = c.get("/api/growth/process/run/" + rid).json()["state"]
    assert detail["status"] == "completed"
    assert detail["nodes"]["c"]["state"] == "done"
