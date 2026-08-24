import app.automation.flow_store as fs
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_customer_override():
    from app.api import customer_auth
    from app.main import app

    app.dependency_overrides.pop(customer_auth.require_customer, None)
    yield
    app.dependency_overrides.pop(customer_auth.require_customer, None)


def _as(cid):
    from app.api import customer_auth
    from app.main import app

    app.dependency_overrides[customer_auth.require_customer] = lambda: cid


def _client(tmp_path, monkeypatch, cid="cli_A", customer_flag=True):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setenv("FLOW_RUNNER", "1")
    if customer_flag:
        monkeypatch.setenv("FLOW_RUNNER_CUSTOMER", "1")
    else:
        monkeypatch.delenv("FLOW_RUNNER_CUSTOMER", raising=False)
    _as(cid)
    from app.main import app

    return TestClient(app)


def _safe_flow(name="C"):
    return {"name": name, "nodes": [{"id": "a", "action": "seo_blog_draft"}], "edges": []}


def test_flag_off_503(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, customer_flag=False)
    assert c.get("/api/customer/flows").status_code == 503


def test_create_scoped_to_caller(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, cid="cli_A")
    r = c.post("/api/customer/flow", json=_safe_flow())
    assert r.status_code == 200 and r.json()["runnable"] is True
    fid = r.json()["flow"]["id"]
    # stored under cli_A
    assert fs.get_flow(fid)["owner_client_id"] == "cli_A"
    assert any(f["id"] == fid for f in c.get("/api/customer/flows").json()["flows"])


def test_cross_tenant_get_is_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, cid="cli_A")
    fid = c.post("/api/customer/flow", json=_safe_flow()).json()["flow"]["id"]
    _as("cli_B")  # switch tenant
    assert c.get(f"/api/customer/flow/{fid}").status_code == 404  # CRITICAL isolation
    assert not c.get("/api/customer/flows").json()["flows"]  # B sees nothing


def test_cross_tenant_delete_is_404_and_preserves(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, cid="cli_A")
    fid = c.post("/api/customer/flow", json=_safe_flow()).json()["flow"]["id"]
    _as("cli_B")
    assert c.delete(f"/api/customer/flow/{fid}").status_code == 404
    _as("cli_A")
    assert c.get(f"/api/customer/flow/{fid}").status_code == 200  # still there


def test_unsafe_action_not_runnable(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, cid="cli_A")
    r = c.post(
        "/api/customer/flow",
        json={"name": "bad", "nodes": [{"id": "a", "action": "http_request"}], "edges": []},
    )
    assert r.status_code == 200 and r.json()["runnable"] is False
    assert r.json()["compile_errors"]


def test_cap_enforced(tmp_path, monkeypatch):
    import app.api.customer_flows as cfmod

    c = _client(tmp_path, monkeypatch, cid="cli_A")
    monkeypatch.setattr(cfmod, "_MAX_CUSTOMER_FLOWS", 2)
    assert c.post("/api/customer/flow", json=_safe_flow("1")).json()["ok"] is True
    assert c.post("/api/customer/flow", json=_safe_flow("2")).json()["ok"] is True
    over = c.post("/api/customer/flow", json=_safe_flow("3")).json()
    assert over.get("ok") is False and "limit" in (over.get("error", "").lower())


def test_run_and_status_owner_checked(tmp_path, monkeypatch):
    from app.agents import dag_engine, process_engine, process_library

    c = _client(tmp_path, monkeypatch, cid="cli_A")
    monkeypatch.setattr(process_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(process_engine, "_INDEX", str(tmp_path / "runs" / "index.jsonl"))
    monkeypatch.setattr(dag_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(dag_engine, "_INDEX", str(tmp_path / "runs" / "dag_index.jsonl"))

    async def _stub(inputs):
        return {"ok": True, "count": 1, "detail": "draft"}

    monkeypatch.setitem(process_library.EXECUTORS, "seo_blog_draft", _stub)

    fid = c.post("/api/customer/flow", json=_safe_flow()).json()["flow"]["id"]
    started = c.post(f"/api/customer/flow/{fid}/run").json()
    assert started.get("ok") and started.get("run_id")
    rid = started["run_id"]
    # owner can read status
    assert c.get(f"/api/customer/flow/run/{rid}").status_code == 200
    # cross-tenant cannot
    _as("cli_B")
    assert c.get(f"/api/customer/flow/run/{rid}").status_code == 404
