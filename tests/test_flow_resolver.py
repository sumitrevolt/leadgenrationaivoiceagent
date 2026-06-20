import app.automation.flow_store as fs
from app.agents import process_library


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    fs.save_flow({"id": "demo", "name": "d",
                  "nodes": [{"id": "a", "action": "scrape"}], "edges": []})


def test_flow_resolves_when_flag_on(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("FLOW_RUNNER", "1")
    proc = process_library.get_process("flow:demo")
    assert proc and proc["steps"][0]["action"] == "scrape"


def test_flow_none_when_flag_off(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("FLOW_RUNNER", raising=False)
    assert process_library.get_process("flow:demo") is None


def test_static_process_still_resolves():
    assert process_library.get_process("growth_audit") is not None
