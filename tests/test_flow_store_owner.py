import app.automation.flow_store as fs


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))


def test_owner_persisted(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = fs.save_flow({"name": "C", "nodes": [], "edges": []}, owner_client_id="cli_1")
    assert r["ok"] and fs.get_flow(r["flow"]["id"])["owner_client_id"] == "cli_1"


def test_admin_flow_owner_blank(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = fs.save_flow({"name": "A", "nodes": [], "edges": []})  # no owner
    assert fs.get_flow(r["flow"]["id"])["owner_client_id"] == ""


def test_list_flows_owner_filter(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow({"id": "a1", "name": "A1", "nodes": [], "edges": []}, owner_client_id="cli_1")
    fs.save_flow({"id": "a2", "name": "A2", "nodes": [], "edges": []}, owner_client_id="cli_2")
    fs.save_flow({"id": "adm", "name": "ADM", "nodes": [], "edges": []})  # admin
    ids1 = {f["id"] for f in fs.list_flows(owner="cli_1")}
    assert ids1 == {"a1"}  # only cli_1's
    all_ids = {f["id"] for f in fs.list_flows()}  # admin (no filter) sees all
    assert {"a1", "a2", "adm"} <= all_ids


def test_owned_by(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow({"id": "x", "name": "X", "nodes": [], "edges": []}, owner_client_id="cli_1")
    assert fs.owned_by("x", "cli_1") is True
    assert fs.owned_by("x", "cli_2") is False  # cross-tenant
    assert fs.owned_by("ghost", "cli_1") is False  # missing


def test_count_for_owner(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow({"id": "f1", "name": "1", "nodes": [], "edges": []}, owner_client_id="cli_1")
    fs.save_flow({"id": "f2", "name": "2", "nodes": [], "edges": []}, owner_client_id="cli_1")
    fs.save_flow({"id": "f3", "name": "3", "nodes": [], "edges": []}, owner_client_id="cli_2")
    assert fs.count_for_owner("cli_1") == 2 and fs.count_for_owner("cli_2") == 1
