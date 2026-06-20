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
    r = c.post("/api/growth/flow", json={"name": "Demo",
        "nodes": [{"id": "a", "action": "scrape"}], "edges": []})
    assert r.status_code == 200 and r.json()["runnable"] is True
    fid = r.json()["flow"]["id"]
    assert c.get(f"/api/growth/flow/{fid}").json()["runnable"] is True
    assert c.delete(f"/api/growth/flow/{fid}").json()["ok"] is True


def test_invalid_flow_reports_compile_errors(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/growth/flow", json={"name": "Bad",
        "nodes": [{"id": "a", "action": "nope"}], "edges": []})
    assert r.status_code == 200 and r.json()["runnable"] is False
    assert r.json()["compile_errors"]
