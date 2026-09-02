import app.automation.flow_store as fs


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))


def test_cron_trigger_roundtrips(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = fs.save_flow(
        {
            "name": "Daily",
            "nodes": [{"id": "a", "action": "scrape"}],
            "edges": [],
            "trigger": {"type": "cron", "cron": "*/30 * * * *"},
        }
    )
    assert r["ok"]
    got = fs.get_flow(r["flow"]["id"])
    assert got["trigger"] == {"type": "cron", "cron": "*/30 * * * *"}


def test_event_trigger_roundtrips(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = fs.save_flow(
        {
            "name": "OnLead",
            "nodes": [],
            "edges": [],
            "trigger": {"type": "event", "event": "lead.qualified"},
        }
    )
    assert fs.get_flow(r["flow"]["id"])["trigger"] == {"type": "event", "event": "lead.qualified"}


def test_missing_trigger_defaults_manual(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = fs.save_flow({"name": "Plain", "nodes": [], "edges": []})
    assert fs.get_flow(r["flow"]["id"])["trigger"] == {"type": "manual"}


def test_invalid_trigger_type_normalised_to_manual(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = fs.save_flow({"name": "Bad", "nodes": [], "edges": [], "trigger": {"type": "webhook"}})
    assert fs.get_flow(r["flow"]["id"])["trigger"] == {"type": "manual"}


def test_list_flows_exposes_trigger_type(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow(
        {
            "id": "x",
            "name": "X",
            "nodes": [],
            "edges": [],
            "trigger": {"type": "cron", "cron": "0 9 * * *"},
        }
    )
    row = next(r for r in fs.list_flows() if r["id"] == "x")
    assert row["trigger"] == "cron"


def test_list_flows_full_returns_raw_with_trigger(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow(
        {
            "id": "y",
            "name": "Y",
            "nodes": [{"id": "a", "action": "scrape"}],
            "edges": [],
            "trigger": {"type": "event", "event": "lead.created"},
        }
    )
    full = next(r for r in fs.list_flows_full() if r["id"] == "y")
    assert full["trigger"]["event"] == "lead.created" and full["nodes"][0]["action"] == "scrape"
