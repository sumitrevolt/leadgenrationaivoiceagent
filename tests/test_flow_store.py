import app.automation.flow_store as fs


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "flow_runner"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "flow_runner" / "flows.jsonl"))


def test_save_assigns_id_and_get_roundtrip(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = fs.save_flow({"name": "Demo", "nodes": [{"id": "a", "action": "scrape"}], "edges": []})
    assert r["ok"] and r["flow"]["id"].startswith("flow_")
    got = fs.get_flow(r["flow"]["id"])
    assert got["name"] == "Demo" and len(got["nodes"]) == 1


def test_upsert_keeps_id(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    a = fs.save_flow({"id": "fixed", "name": "v1", "nodes": [], "edges": []})
    b = fs.save_flow({"id": "fixed", "name": "v2", "nodes": [], "edges": []})
    assert a["flow"]["id"] == b["flow"]["id"] == "fixed"
    assert fs.get_flow("fixed")["name"] == "v2"
    assert len(fs.list_flows()) == 1


def test_list_and_delete(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow({"id": "x", "name": "X", "nodes": [], "edges": []})
    assert any(f["id"] == "x" for f in fs.list_flows())
    assert fs.delete_flow("x") is True
    assert fs.get_flow("x") is None


def test_bad_input_rejected(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert fs.save_flow("not-a-dict")["ok"] is False
