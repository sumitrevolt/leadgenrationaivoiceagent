import app.automation.flow_store as fs


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "flow_runner"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "flow_runner" / "flows.jsonl"))
    monkeypatch.setattr(fs, "_HISTORY_DIR", str(tmp_path / "flow_runner" / "flow_history"))


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


def test_new_flow_starts_at_version_1(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = fs.save_flow({"id": "v1flow", "name": "First", "nodes": [], "edges": []})
    assert r["flow"]["version"] == 1
    assert fs.list_versions("v1flow") == [
        {
            "version": 1,
            "name": "First",
            "updated_at": r["flow"]["updated_at"],
            "created_by": r["flow"]["created_by"],
            "current": True,
        }
    ]


def test_overwrite_bumps_version_and_archives_prior(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow({"id": "f1", "name": "v1", "nodes": [{"id": "a"}], "edges": []})
    fs.save_flow({"id": "f1", "name": "v2", "nodes": [{"id": "b"}], "edges": []})
    fs.save_flow({"id": "f1", "name": "v3", "nodes": [{"id": "c"}], "edges": []})

    assert fs.get_flow("f1")["version"] == 3
    versions = fs.list_versions("f1")
    assert [v["version"] for v in versions] == [3, 2, 1]
    assert versions[0]["current"] is True
    assert versions[1]["current"] is False

    v1_body = fs.get_version("f1", 1)
    assert v1_body["name"] == "v1" and v1_body["nodes"] == [{"id": "a"}]
    assert fs.get_version("f1", 99) is None


def test_rollback_restores_content_and_bumps_version_forward(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow(
        {"id": "f2", "name": "good", "nodes": [{"id": "a"}], "edges": []}, owner_client_id="cli1"
    )
    fs.save_flow({"id": "f2", "name": "broken", "nodes": [], "edges": []})

    out = fs.rollback_flow("f2", 1, by="admin")
    assert out["ok"] is True
    restored = fs.get_flow("f2")
    assert restored["name"] == "good"
    assert restored["nodes"] == [{"id": "a"}]
    assert restored["version"] == 3, "rollback is a forward save, not a version rewind"
    assert restored["owner_client_id"] == "cli1", "rollback must not drop the original owner"


def test_rollback_unknown_version_errors(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow({"id": "f3", "name": "only", "nodes": [], "edges": []})
    out = fs.rollback_flow("f3", 7)
    assert out["ok"] is False


def test_history_bounded_to_max_per_flow(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(fs, "_MAX_HISTORY_PER_FLOW", 3)
    for i in range(6):
        fs.save_flow({"id": "bounded", "name": f"v{i}", "nodes": [], "edges": []})
    versions = fs.list_versions("bounded")
    assert len(versions) == 4  # 3 archived + 1 current, oldest trimmed
    assert versions[-1]["version"] == 3, "oldest archived snapshots must be dropped, not the newest"
